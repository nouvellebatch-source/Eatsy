import os
import unittest
from unittest.mock import patch

import requests
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from starlette.requests import Request
from types import SimpleNamespace
from pydantic import ValidationError

from app.email_service import EmailDeliveryError, send_verification_email
from app.main import _code_digest, create_app
from app.schemas import UserInput, UserRegistration, VerifyRegistration


class VerificationTests(unittest.TestCase):
    def test_code_digest_is_bound_to_email_and_secret(self):
        digest = _code_digest('secret', 'ana@example.com', '012345')
        self.assertEqual(digest, _code_digest('secret', 'ana@example.com', '012345'))
        self.assertNotEqual(digest, _code_digest('secret', 'otra@example.com', '012345'))
        self.assertNotEqual(digest, _code_digest('other', 'ana@example.com', '012345'))

    def test_code_validation(self):
        self.assertEqual(VerifyRegistration(correo='ana@example.com', codigo='012345').codigo, '012345')
        with self.assertRaises(ValidationError):
            VerifyRegistration(correo='ana@example.com', codigo='12345')
        with self.assertRaises(ValidationError):
            UserRegistration(nombre='Ana', apellido='Ruiz', usuario='ana', correo='no-es-correo', contrasena='una-contrasena-larga')

    @patch.dict(os.environ, {'BREVO_API_KEY': 'test-key', 'CORREO_REMITENTE': 'sender@example.com'})
    @patch('app.email_service.requests.post')
    def test_send_brevo_https(self, post):
        send_verification_email('ana@example.com', '012345')
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(kwargs['timeout'], 10)
        self.assertIn('012345', kwargs['json']['htmlContent'])

    @patch.dict(os.environ, {'BREVO_API_KEY': 'test-key', 'CORREO_REMITENTE': 'sender@example.com'})
    @patch('app.email_service.requests.post', side_effect=requests.Timeout())
    def test_timeout_is_controlled(self, post):
        with self.assertRaises(EmailDeliveryError):
            send_verification_email('ana@example.com', '012345')

    @patch.dict(os.environ, {'EMAIL_VERIFICATION_ENABLED': 'true'})
    def test_verification_expired_wrong_and_valid(self):
        class Cursor:
            lastrowid = 7
            def __init__(self, row): self.row, self.commands = row, []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params): self.commands.append((sql, params))
            def fetchone(self): return self.row
        class DB:
            def __init__(self, row): self.cur, self.commits = Cursor(row), 0
            def begin(self): pass
            def cursor(self): return self.cur
            def commit(self): self.commits += 1
            def rollback(self): pass
        secret = 'unit-test-secret'
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        settings = SimpleNamespace(secret=secret, cors_origins=())
        app = create_app(settings)
        app.state.settings = settings
        request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': [], 'app': app})
        endpoint = next(route.endpoint for route in app.routes if route.path == '/auth/verificar-correo')
        row = {'expires_at': now + timedelta(minutes=10), 'attempts': 0,
               'code_hash': _code_digest(secret, 'ana@example.com', '123456'),
               'usuario': 'ana', 'nombre': 'Ana', 'apellido': 'Ruiz', 'password_hash': 'hash'}
        wrong = DB(row)
        with self.assertRaises(HTTPException):
            endpoint(VerifyRegistration(correo='ana@example.com', codigo='999999'), wrong, request)
        self.assertEqual(wrong.commits, 1)
        self.assertTrue(any('attempts=attempts+1' in sql for sql, _ in wrong.cur.commands))
        expired = DB(row | {'expires_at': now - timedelta(seconds=1)})
        with self.assertRaises(HTTPException):
            endpoint(VerifyRegistration(correo='ana@example.com', codigo='123456'), expired, request)
        valid = DB(row)
        result = endpoint(VerifyRegistration(correo='ana@example.com', codigo='123456'), valid, request)
        self.assertEqual(result['rol'], 'customer')
        self.assertTrue(any('DELETE FROM pending_registrations' in sql for sql, _ in valid.cur.commands))

    @patch.dict(os.environ, {'EMAIL_VERIFICATION_ENABLED': 'false'})
    @patch('app.main.verify_password', return_value=True)
    @patch('app.main.create_token', return_value=('test-token', datetime.now(timezone.utc), 'test-jti'))
    def test_existing_login_does_not_require_new_tables(self, token, password):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                self.sql = sql
                self.params = params
            def fetchone(self):
                return {'id': 1, 'usuario': 'admin', 'nombre': 'Admin', 'apellido': 'Eatsy',
                        'rol': 'admin', 'activo': 1, 'password_hash': 'hash', 'verified_email': None}
        class DB:
            def __init__(self): self.cur = Cursor()
            def cursor(self): return self.cur
        settings = SimpleNamespace(secret='unit-secret', cors_origins=(), token_minutes=30,
                                   audience='aud', issuer='iss')
        app = create_app(settings)
        app.state.settings = settings
        request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': [], 'app': app})
        endpoint = next(route.endpoint for route in app.routes if route.path == '/auth/login')
        db = DB()
        result = endpoint(UserInput(usuario='admin', contrasena='password'), db, request)
        self.assertEqual(result.access_token, 'test-token')
        self.assertNotIn('customer_emails', db.cur.sql)


if __name__ == '__main__':
    unittest.main()
