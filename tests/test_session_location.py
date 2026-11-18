import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import create_app, get_db, get_user
from app.schemas import LoginLocationInput

class Cursor:
    rowcount=1
    def __init__(self): self.calls=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params): self.calls.append((sql,params))
    def fetchall(self): return []
class DB:
    def __init__(self): self.c=Cursor()
    def cursor(self): return self.c

class SessionLocationTests(unittest.TestCase):
    def test_history_is_limited_to_successful_logins_of_current_user(self):
        endpoint=next(r.endpoint for r in create_app().routes if r.path=='/auth/sesiones')
        db=DB(); self.assertEqual(endpoint({'id':7},db,20),[])
        self.assertEqual(db.c.calls[0][1],(7,20)); self.assertIn('user_id=%s',db.c.calls[0][0]);self.assertIn("status_code=200",db.c.calls[0][0])
    def test_location_update_checks_owner_and_recent_login(self):
        endpoint=next(r.endpoint for r in create_app().routes if r.path=='/auth/sesiones/{request_id}/ubicacion')
        db=DB(); request_id=uuid4(); data=LoginLocationInput(latitude=10.4,longitude=-75.5,city='Cartagena',country='Colombia')
        endpoint(request_id,data,{'id':7},db)
        self.assertEqual(db.c.calls[0][1],(10.4,-75.5,'Cartagena','Colombia',str(request_id),7))
        self.assertIn('user_id=%s',db.c.calls[0][0]); self.assertIn('INTERVAL 10 MINUTE',db.c.calls[0][0])
        db.c.rowcount=0
        with self.assertRaises(HTTPException) as error: endpoint(request_id,data,{'id':8},db)
        self.assertEqual(error.exception.status_code,404)
    @patch('app.main._write_request_log')
    def test_browser_can_read_request_identifier(self,_):
        app=create_app(); app.dependency_overrides[get_db]=lambda: DB();app.dependency_overrides[get_user]=lambda:{'id':7}
        client=TestClient(app)
        response=client.get('/auth/sesiones',headers={'Origin':'http://localhost:53000'})
        self.assertIn('X-Request-ID',response.headers.get('access-control-expose-headers',''))
        self.assertIn('x-request-id',response.headers)
if __name__=='__main__': unittest.main()
