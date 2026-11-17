import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from app.main import create_app
from app.schemas import OrderInput, RestaurantEventInput

class Cursor:
    lastrowid=12
    def __init__(self, valid=True, owner=True): self.calls=[]; self.valid=valid; self.owner=owner
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args): self.calls.append((sql,args))
    def fetchone(self):
        sql=self.calls[-1][0]
        if 'idempotency_key' in sql: return None
        if 'restaurant_branches' in sql: return {'id':2}
        if 'menu_products' in sql: return {'id':3,'name':'Pizza','category':'Pizzas','price':25000,'currency':'COP'}
        if 'restaurant_promotions' in sql: return {'id':5,'code':'EATSY10','percent_off':10} if self.valid else None
        if 'FROM orders WHERE id=' in sql: return {'id':12,'total':45000,'payment_status':'pending'}
        if 'restaurant_memberships' in sql: return {'role':'owner'} if self.owner else None
        if 'COUNT(*)' in sql: return {'paid_count':2,'revenue':45000}
        return None
    def fetchall(self): return []

class DB:
    def __init__(self,**kwargs): self.cur=Cursor(**kwargs);self.committed=False;self.rolled=False
    def cursor(self):return self.cur
    def begin(self):pass
    def commit(self):self.committed=True
    def rollback(self):self.rolled=True

class CommercialTests(unittest.TestCase):
    def setUp(self):
        app=create_app()
        self.order=next(r.endpoint for r in app.routes if r.path=='/pedidos' and 'POST' in r.methods)
        self.finances=next(r.endpoint for r in app.routes if r.path=='/gestion/restaurantes/{restaurant_id}/finanzas')
        self.data=OrderInput(restaurant_id=1,branch_id=2,idempotency_key=uuid4(),fulfillment='pickup',
          payment_method='cash',discount_code='eatsy10',items=[{'product_id':3,'quantity':2}])
    @patch.dict(os.environ,{'ORDERS_ENABLED':'true'})
    def test_discount_uses_server_prices_and_snapshot(self):
        db=DB();self.order(self.data,{'id':4,'rol':'customer'},db)
        order=next(args for sql,args in db.cur.calls if 'INSERT INTO orders ' in sql)
        discount=next(args for sql,args in db.cur.calls if 'INSERT INTO order_discounts' in sql)
        self.assertEqual(order[-1],45000)
        self.assertEqual(discount[-2:],(50000,5000))
        self.assertTrue(db.committed)
    @patch.dict(os.environ,{'ORDERS_ENABLED':'true'})
    def test_invalid_coupon_rolls_back(self):
        db=DB(valid=False)
        with self.assertRaises(HTTPException) as error:self.order(self.data,{'id':4,'rol':'customer'},db)
        self.assertEqual(error.exception.status_code,409)
        self.assertTrue(db.rolled)
    def test_finances_are_scoped_and_include_only_confirmed_cash(self):
        db=DB(); result=self.finances(1,{'id':4},db)
        self.assertEqual(result['revenue'],45000)
        sql=db.cur.calls[1][0]
        self.assertIn('payment_confirmations',sql)
        self.assertIn("payment_status='paid'",sql)
        self.assertEqual(db.cur.calls[1][1],(1,))
    def test_finances_reject_other_users(self):
        with self.assertRaises(HTTPException) as error:self.finances(1,{'id':4},DB(owner=False))
        self.assertEqual(error.exception.status_code,403)
    def test_event_creation_requires_restaurant_owner(self):
        endpoint=next(r.endpoint for r in create_app().routes if r.path=='/gestion/restaurantes/{restaurant_id}/eventos' and 'POST' in r.methods)
        data=RestaurantEventInput(title='Cena',description='Evento',starts_at='2035-01-01T12:00:00-05:00',ends_at='2035-01-01T13:00:00-05:00')
        with self.assertRaises(HTTPException) as error:endpoint(1,data,{'id':4},DB(owner=False))
        self.assertEqual(error.exception.status_code,403)
    def test_public_promotions_are_restricted_to_current_restaurant_and_dates(self):
        endpoint=next(r.endpoint for r in create_app().routes if r.path=='/restaurantes/{restaurant_id}/promociones')
        db=DB();self.assertEqual(endpoint(1,db),[])
        sql,args=db.cur.calls[-1]
        self.assertEqual(args,(1,));self.assertIn('p.active=1',sql);self.assertIn('UTC_TIMESTAMP()',sql)

if __name__=='__main__':unittest.main()
