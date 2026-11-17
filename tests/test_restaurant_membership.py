import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from app.cli import _assign_restaurant_role


class FakeCursor:
    def __init__(self, existing=False): self.calls = []; self.existing = existing
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args): self.calls.append((sql, args))
    def fetchone(self):
        sql = self.calls[-1][0]
        if 'customer_emails' in sql: return {'id': 7, 'rol': 'customer'}
        if 'FROM restaurants' in sql: return {'id': 1}
        if 'restaurant_memberships' in sql: return {'role': 'owner'} if self.existing else None
        return None


class FakeDB:
    def __init__(self, existing=False): self.cur = FakeCursor(existing); self.committed = False; self.rolled_back = False
    def cursor(self): return self.cur
    def begin(self): pass
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True


class MembershipTests(unittest.TestCase):
    def test_verified_account_is_linked_without_changing_global_role(self):
        db = FakeDB()
        @contextmanager
        def connection(_settings): yield db
        with patch('app.cli.connection', connection):
            _assign_restaurant_role(SimpleNamespace(usuario='ana', restaurante='la-santa', rol='cashier'), object())
        self.assertTrue(db.committed)
        self.assertTrue(any('INSERT INTO restaurant_memberships' in sql for sql, _ in db.cur.calls))
        self.assertFalse(any('UPDATE users' in sql for sql, _ in db.cur.calls))

    def test_existing_membership_is_not_overwritten(self):
        db = FakeDB(existing=True)
        @contextmanager
        def connection(_settings): yield db
        with patch('app.cli.connection', connection):
            with self.assertRaises(ValueError):
                _assign_restaurant_role(SimpleNamespace(usuario='ana', restaurante='la-santa', rol='cashier'), object())
        self.assertTrue(db.rolled_back)
        self.assertFalse(db.committed)


if __name__ == '__main__': unittest.main()
