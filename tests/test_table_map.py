import unittest
from fastapi import HTTPException
from app.main import create_app


class Cursor:
    def __init__(self, allowed): self.allowed = allowed; self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.calls.append((sql, params))
    def fetchone(self): return {'role': 'cashier'} if self.allowed else None
    def fetchall(self): return [{'id': 1, 'branch_id': 1, 'branch_name': 'La Santa', 'table_number': 1, 'capacity': 4, 'order_id': None, 'order_status': None, 'customer_name': None}]


class DB:
    def __init__(self, allowed): self.cur = Cursor(allowed)
    def cursor(self): return self.cur


class TableMapTests(unittest.TestCase):
    def setUp(self): self.endpoint = next(r.endpoint for r in create_app().routes if r.path == '/gestion/restaurantes/{restaurant_id}/mesas')
    def test_only_scoped_restaurant_data_is_requested(self):
        db = DB(True)
        result = self.endpoint(10, {'id': 99}, db)
        self.assertEqual(result[0]['capacity'], 4)
        self.assertEqual(db.cur.calls[0][1], (10, 99))
        self.assertEqual(db.cur.calls[1][1], (10,10))
        self.assertIn('o2.restaurant_id=t.restaurant_id', db.cur.calls[1][0])
        self.assertIn('o2.branch_id=t.branch_id', db.cur.calls[1][0])
    def test_denies_unassigned_user_before_querying_tables(self):
        db = DB(False)
        with self.assertRaises(HTTPException) as error: self.endpoint(10, {'id': 99}, db)
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(len(db.cur.calls), 1)


if __name__ == '__main__': unittest.main()
