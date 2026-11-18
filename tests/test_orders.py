import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from app.main import create_app
from app.schemas import OrderInput, OrderTransitionInput, OrderAdditionInput


class Cursor:
    lastrowid = 7
    def __init__(self): self.sql = ''; self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.sql = sql; self.calls.append((sql, params))
    def fetchone(self):
        if 'idempotency_key' in self.sql and self.sql.startswith('SELECT'): return None
        if 'restaurant_branches' in self.sql: return {'id': 2}
        if 'menu_products' in self.sql: return {'id': 3, 'name': 'Pizza', 'category': 'Pizzas', 'price': 25000, 'currency': 'COP'}
        if 'SELECT * FROM orders WHERE id=' in self.sql:
            return {'id': 7, 'restaurant_id': 1, 'branch_id': 2, 'fulfillment': 'pickup',
                    'payment_method': 'cash', 'payment_status': 'pending', 'status': 'pending_acceptance',
                    'total': 50000, 'currency': 'COP'}
        return None


class DB:
    def __init__(self): self.c = Cursor(); self.committed = False
    def cursor(self): return self.c
    def begin(self): pass
    def commit(self): self.committed = True
    def rollback(self): pass


class OrderTests(unittest.TestCase):
    def setUp(self):
        app = create_app()
        self.endpoint = next(route.endpoint for route in app.routes if route.path == '/pedidos')
        self.data = OrderInput(restaurant_id=1, branch_id=2, idempotency_key=uuid4(),
                               fulfillment='pickup', payment_method='cash',
                               items=[{'product_id': 3, 'quantity': 2}])

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_cash_order_uses_database_price_and_pending_status(self):
        db = DB()
        order = self.endpoint(self.data, {'id': 4, 'rol': 'customer'}, db)
        self.assertEqual(order['total'], 50000)
        self.assertEqual(order['payment_status'], 'pending')
        self.assertTrue(db.committed)
        insert = next(params for sql, params in db.c.calls if 'INSERT INTO orders' in sql)
        self.assertEqual(insert[-1], 50000)
        self.assertTrue(any("'confirmed'" in sql for sql, _ in db.c.calls if 'INSERT INTO orders' in sql))

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_pizza_addition_price_and_link_are_saved(self):
        class ExtraCursor(Cursor):
            def fetchone(self):
                if 'menu_products' in self.sql:
                    return {3: {'id': 3, 'name': 'Pizza (Personal)', 'category': 'Pizzas Tradicionales', 'price': 25000, 'currency': 'COP'},
                            4: {'id': 4, 'name': 'Queso (Personal)', 'category': 'Adiciones Pizza', 'price': 8000, 'currency': 'COP'}}.get(self.calls[-1][1][0])
                return super().fetchone()
        db = DB(); db.c = ExtraCursor()
        data = self.data.model_copy(update={'items': [self.data.items[0].model_copy(update={
            'additions': [OrderAdditionInput(product_id=4)]})]})
        self.endpoint(data, {'id': 4, 'rol': 'customer'}, db)
        insert = next(params for sql, params in db.c.calls if 'INSERT INTO orders' in sql)
        self.assertEqual(insert[-1], 66000)
        self.assertTrue(any('INSERT INTO order_item_additions' in sql for sql, _ in db.c.calls))

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_wrong_size_addition_is_rejected(self):
        class ExtraCursor(Cursor):
            def fetchone(self):
                if 'menu_products' in self.sql:
                    name, category = ('Pizza (Personal)', 'Pizzas') if self.calls[-1][1][0] == 3 else ('Queso (Large)', 'Adiciones Pizza')
                    return {'id': self.calls[-1][1][0], 'name': name, 'category': category, 'price': 1000, 'currency': 'COP'}
                return super().fetchone()
        db = DB(); db.c = ExtraCursor()
        data = self.data.model_copy(update={'items': [self.data.items[0].model_copy(update={'additions': [OrderAdditionInput(product_id=4)]})]})
        with self.assertRaises(HTTPException) as error:
            self.endpoint(data, {'id': 4, 'rol': 'customer'}, db)
        self.assertEqual(error.exception.status_code, 422)

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_beer_is_linked_to_a_meal_and_charged_per_meal(self):
        class DrinkCursor(Cursor):
            def fetchone(self):
                if 'menu_products' in self.sql:
                    return {3: {'id': 3, 'name': 'Bandeja', 'category': 'Almuerzos', 'price': 20000, 'currency': 'COP'},
                            4: {'id': 4, 'name': 'Cerveza', 'category': 'Cervezas Artesanales', 'price': 5000, 'currency': 'COP'}}.get(self.calls[-1][1][0])
                return super().fetchone()
        db = DB(); db.c = DrinkCursor()
        data = self.data.model_copy(update={'items': [self.data.items[0].model_copy(update={'additions': [OrderAdditionInput(product_id=4)]})]})
        self.endpoint(data, {'id': 4, 'rol': 'customer'}, db)
        insert = next(params for sql, params in db.c.calls if 'INSERT INTO orders' in sql)
        self.assertEqual(insert[-1], 50000)
        self.assertTrue(any('INSERT INTO order_item_additions' in sql for sql, _ in db.c.calls))

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_kitchen_receives_order_items_only_after_membership_check(self):
        class KitchenCursor(Cursor):
            def fetchone(self):
                return {'role': 'kitchen'} if 'restaurant_memberships' in self.sql else None
            def fetchall(self):
                if 'FROM orders' in self.sql:
                    return [{'id': 7}]
                if 'FROM order_items' in self.sql:
                    return [{'id': 9, 'order_id': 7, 'product_name': 'Pizza', 'quantity': 2, 'unit_price': 25000}]
                return []
        db = DB()
        db.c = KitchenCursor()
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/gestion/restaurantes/{restaurant_id}/pedidos')
        orders = endpoint(1, {'id': 8}, db, 50)
        self.assertEqual(orders[0]['items'][0]['product_name'], 'Pizza')
        self.assertEqual(db.c.calls[0][1], (1, 8))

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'false'})
    def test_disabled_orders_fail_closed(self):
        with self.assertRaises(HTTPException) as error:
            self.endpoint(self.data, {'id': 4, 'rol': 'customer'}, DB())
        self.assertEqual(error.exception.status_code, 503)

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_restaurant_order_search_is_scoped_and_paginated(self):
        class SearchCursor(Cursor):
            def fetchone(self): return {'role':'cashier'}
            def fetchall(self): return []
        db=DB(); db.c=SearchCursor()
        endpoint=next(r.endpoint for r in create_app().routes if r.path == '/gestion/restaurantes/{restaurant_id}/pedidos')
        self.assertEqual(endpoint(17, {'id':8}, db, 100, 200, '42'),[])
        self.assertEqual(db.c.calls[-1][1],(17,'42','42',100,200))
        self.assertIn('o.restaurant_id=%s',db.c.calls[-1][0])

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_order_history_is_limited_to_the_authenticated_customer(self):
        class HistoryCursor(Cursor):
            def fetchall(self): return []
        db = DB(); db.c = HistoryCursor()
        endpoint = next(r.endpoint for r in create_app().routes if r.path == '/mis-pedidos')
        self.assertEqual(endpoint({'id': 41}, db, 25), [])
        self.assertEqual(db.c.calls[-1][1], (41, 25))
        self.assertIn('customer_id=%s', db.c.calls[-1][0])

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_kitchen_transition_is_scoped_and_records_event(self):
        class KitchenCursor(Cursor):
            def fetchone(self):
                if 'restaurant_memberships' in self.sql: return {'role': 'kitchen'}
                if 'FROM orders' in self.sql: return {'id': 7, 'restaurant_id': 1, 'status': 'confirmed', 'fulfillment': 'pickup'}
                return None
        db = DB()
        db.c = KitchenCursor()
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/gestion/restaurantes/{restaurant_id}/pedidos/{order_id}/estado')
        order = endpoint(1, 7, OrderTransitionInput(status='preparing'), {'id': 8}, db)
        self.assertEqual(order['status'], 'preparing')
        self.assertTrue(db.committed)
        self.assertTrue(any('INSERT INTO order_events' in sql for sql, _ in db.c.calls))
        self.assertTrue(any(params == (7, 1) for sql, params in db.c.calls if 'FOR UPDATE' in sql))

    @patch.dict(os.environ, {'ORDERS_ENABLED': 'true'})
    def test_kitchen_rejects_unauthorized_membership(self):
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/gestion/restaurantes/{restaurant_id}/pedidos/{order_id}/estado')
        with self.assertRaises(HTTPException) as error:
            endpoint(1, 7, OrderTransitionInput(status='preparing'), {'id': 8}, DB())
        self.assertEqual(error.exception.status_code, 403)


if __name__ == '__main__': unittest.main()
