import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from app.main import create_app
from app.schemas import ReservationInput


class Cursor:
    lastrowid = 5
    def __init__(self, overlap=False, role='cashier', paid='pending'):
        self.calls=[]; self.overlap=overlap; self.role=role; self.paid=paid
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.calls.append((sql,params))
    def fetchone(self):
        sql=self.calls[-1][0]
        if 'restaurant_memberships' in sql: return {'role':self.role} if self.role else None
        if 'FROM restaurant_tables' in sql: return {'id':1,'table_number':1,'capacity':4}
        if 'FROM reservations' in sql: return {'id':9} if self.overlap else None
        if 'FROM orders' in sql: return {'id':8,'restaurant_id':1,'payment_method':'cash','payment_status':self.paid}
        return None


class DB:
    def __init__(self, **kwargs): self.cur=Cursor(**kwargs); self.committed=False; self.rolled=False
    def cursor(self): return self.cur
    def begin(self): pass
    def commit(self): self.committed=True
    def rollback(self): self.rolled=True


class ReservationPaymentTests(unittest.TestCase):
    def setUp(self):
        routes=create_app().routes
        self.reserve=next(r.endpoint for r in routes if r.path=='/gestion/restaurantes/{restaurant_id}/reservas' and 'POST' in r.methods)
        self.pay=next(r.endpoint for r in routes if r.path=='/gestion/restaurantes/{restaurant_id}/pedidos/{order_id}/pago')
        self.data=ReservationInput(table_id=1,customer_name='Ana',party_size=4,starts_at='2026-12-01T19:00:00-05:00',ends_at='2026-12-01T20:00:00-05:00')
    def test_rejects_overlapping_reservation_and_rolls_back(self):
        db=DB(overlap=True)
        with self.assertRaises(HTTPException) as err: self.reserve(1,self.data,{'id':7},db)
        self.assertEqual(err.exception.status_code,409); self.assertTrue(db.rolled)
        self.assertTrue(any('FOR UPDATE' in sql and 'restaurant_tables' in sql for sql,_ in db.cur.calls))
    def test_rejects_group_larger_than_table(self):
        db=DB()
        with self.assertRaises(HTTPException): self.reserve(1,self.data.model_copy(update={'party_size':5}),{'id':7},db)
        self.assertTrue(db.rolled)
    def test_cash_confirmation_is_audited_and_idempotent(self):
        db=DB(); order=self.pay(1,8,{'id':7},db)
        self.assertEqual(order['payment_status'],'paid'); self.assertTrue(db.committed)
        self.assertTrue(any('INSERT INTO payment_confirmations' in sql for sql,_ in db.cur.calls))
        again=DB(paid='paid'); self.pay(1,8,{'id':7},again)
        self.assertFalse(any('INSERT INTO payment_confirmations' in sql for sql,_ in again.cur.calls))
    def test_unauthorized_payment_rejected(self):
        db=DB(role=None)
        with self.assertRaises(HTTPException) as err: self.pay(1,8,{'id':7},db)
        self.assertEqual(err.exception.status_code,403); self.assertTrue(db.rolled)
    def test_dates_require_timezone(self):
        with self.assertRaises(ValidationError): ReservationInput(table_id=1,customer_name='Ana',party_size=2,starts_at='2026-12-01T10:00:00',ends_at='2026-12-01T11:00:00')

if __name__=='__main__': unittest.main()
