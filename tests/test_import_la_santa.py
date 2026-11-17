import unittest
from app.import_la_santa import _price, _safe_image, parse_catalog


class ImportTests(unittest.TestCase):
    def test_cop_price(self):
        self.assertEqual(_price('$\u00a08.000'), 8000)
        self.assertEqual(_price('$ 30.000'), 30000)
        with self.assertRaises(ValueError):
            _price('desde $10.000')

    def test_image_source_is_restricted(self):
        self.assertIsNone(_safe_image('http://cdn.bistrify.app/image.png'))
        self.assertIsNone(_safe_image('https://other.example/image.png'))
        self.assertIsNotNone(_safe_image('https://cdn.bistrify.app/image.png'))

    def test_incomplete_source_cannot_be_imported(self):
        with self.assertRaises(ValueError):
            parse_catalog('<html><body>La página cambió</body></html>')


if __name__ == '__main__': unittest.main()
