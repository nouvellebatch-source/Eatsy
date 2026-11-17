import unittest

from app.main import create_app


class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.sql, self.params = sql, params
    def fetchall(self): return []


class Database:
    def __init__(self): self.c = Cursor()
    def cursor(self): return self.c


class RestaurantCatalogTests(unittest.TestCase):
    def test_categories_are_scoped_to_available_products(self):
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/restaurantes/{restaurant_id}/categorias')
        db = Database()
        db.c.fetchall = lambda: [{'category': 'Pizzas'}, {'category': 'Bebidas'}]
        self.assertEqual(endpoint(42, db), ['Pizzas', 'Bebidas'])
        self.assertEqual(db.c.params, (42,))
        self.assertIn('p.available=1', db.c.sql)
        self.assertIn('r.active=1', db.c.sql)

    def test_menu_filter_is_parameterized_and_scoped(self):
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/restaurantes/{restaurant_id}/productos')
        db = Database()
        self.assertEqual(endpoint(42, db, ' Pizza ', 10, 2), [])
        self.assertEqual(db.c.params, (42, 'Pizza', 10, 2))
        self.assertIn('p.restaurant_id=%s', db.c.sql)
        self.assertIn('r.active=1', db.c.sql)

    def test_public_restaurants_are_paginated(self):
        app = create_app()
        endpoint = next(r.endpoint for r in app.routes if r.path == '/restaurantes')
        db = Database()
        self.assertEqual(endpoint(db, 25, 5), [])
        self.assertEqual(db.c.params, (25, 5))
        self.assertIn('active=1', db.c.sql)


if __name__ == '__main__':
    unittest.main()
