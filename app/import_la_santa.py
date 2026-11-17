"""Importa de forma aditiva la carta pública de La Santa; no actualiza datos existentes."""
import argparse
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import Settings
from app.database import connection

SOURCE = 'https://queresto.com/lasantapizzactg'
SLUG = 'la-santa-pizza-bar-grill'


def _price(text: str) -> int:
    value = text.replace('\u00a0', '').strip()
    if not re.fullmatch(r'\$\s*\d{1,3}(?:\.\d{3})*', value):
        raise ValueError('Formato de precio no reconocido en la fuente.')
    return int(re.sub(r'\D', '', value))


def parse_catalog(html: str) -> tuple[str | None, list[dict]]:
    soup = BeautifulSoup(html, 'html.parser')
    cover_tag = soup.select_one('.storefront-cover-photo-banner img[src]')
    cover = _safe_image(cover_tag.get('src') if cover_tag else None)
    products = []
    sections = soup.select('section.storefront-carta-section')
    if not sections:
        raise ValueError('La fuente no contiene secciones reconocibles.')
    for section in sections:
        heading = section.select_one('h2.storefront-carta-section-title')
        if not heading:
            raise ValueError('Se encontró una sección sin categoría.')
        category = heading.get_text(' ', strip=True)
        notes = section.select_one('.storefront-carta-section-description')
        for row in section.select('li.storefront-row'):
            name_tag = row.select_one('h3.storefront-row-name')
            link = row.select_one('a.storefront-row-hit[href]')
            if not name_tag or not link:
                raise ValueError('Se encontró un producto sin nombre o enlace.')
            source = urljoin(SOURCE, link['href'])
            if urlparse(source).hostname != 'queresto.com':
                raise ValueError('Se encontró un enlace de producto fuera de la fuente.')
            name = name_tag.get_text(' ', strip=True)
            desc_tag = row.select_one('.storefront-row-description')
            description = desc_tag.get_text(' ', strip=True) if desc_tag else ''
            if notes:
                description = ' · '.join(filter(None, [description, notes.get_text(' ', strip=True)]))
            image_tag = row.select_one('.storefront-row-media img[src]')
            image = _safe_image(image_tag.get('src') if image_tag else None)
            variants = row.select('.storefront-row-variants-item')
            if variants:
                for variant in variants:
                    label, amount = variant.select_one('.storefront-row-variants-label'), variant.select_one('.storefront-row-variants-price')
                    if not label or not amount:
                        raise ValueError('Se encontró una variante incompleta.')
                    products.append(dict(name=f'{name} ({label.get_text(" ", strip=True)})', category=category,
                                         description=description or None, price=_price(amount.get_text(' ', strip=True)), image=image, source=source))
            else:
                amount = row.select_one('.storefront-row-price-now')
                if not amount:
                    raise ValueError(f'Producto sin precio reconocible: {name}')
                products.append(dict(name=name, category=category, description=description or None,
                                     price=_price(amount.get_text(' ', strip=True)), image=image, source=source))
    if len(products) < 100:
        raise ValueError('La fuente devolvió menos productos de los esperados; se cancela la importación.')
    if len({(p['source'], p['name']) for p in products}) != len(products):
        raise ValueError('La fuente contiene productos duplicados; se cancela la importación.')
    return cover, products


def _safe_image(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == 'https' and parsed.hostname == 'cdn.bistrify.app' else None


def import_catalog(settings: Settings, cover: str | None, products: list[dict]) -> tuple[int, int]:
    inserted = skipped = 0
    with connection(settings) as db:
        db.begin()
        try:
            with db.cursor() as cur:
                cur.execute('SELECT id FROM restaurants WHERE slug=%s FOR UPDATE', (SLUG,))
                restaurant = cur.fetchone()
                if restaurant:
                    raise ValueError('La Santa ya existe. Se detuvo la carga para proteger su catálogo; revisa la base antes de continuar.')
                cur.execute('INSERT INTO restaurants (name, slug, description, image_url) VALUES (%s,%s,%s,%s)',
                            ('La Santa Pizza Bar & Grill', SLUG, 'Menú consultado en QueRestó. Precios y disponibilidad sujetos a confirmación.', cover))
                restaurant_id = cur.lastrowid
                cur.execute('INSERT INTO restaurant_branches (restaurant_id,name,address,city,latitude,longitude) VALUES (%s,%s,%s,%s,%s,%s)',
                            (restaurant_id, 'La Santa', 'Diagonal 31c', 'Cartagena de Indias', 10.50743, -75.4543))
                for product in products:
                    cur.execute('''INSERT INTO menu_products (restaurant_id,name,description,category,price,currency,image_url,source_url)
                        VALUES (%s,%s,%s,%s,%s,'COP',%s,%s)''',
                        (restaurant_id, product['name'], product['description'], product['category'], product['price'], product['image'], product['source']))
                    inserted += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Inserta el catálogo una sola vez en la base configurada.')
    args = parser.parse_args()
    response = requests.get(SOURCE, timeout=20, headers={'User-Agent': 'EatsyCatalogImporter/1.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    cover, products = parse_catalog(response.text)
    print(f'Fuente: {SOURCE}; productos y tamaños: {len(products)}; categorías: {len({p["category"] for p in products})}; imágenes: {sum(bool(p["image"]) for p in products)}; portada: {bool(cover)}')
    if args.apply:
        inserted, _ = import_catalog(Settings.from_env(), cover, products)
        print(f'Productos creados: {inserted}. No se modificaron catálogos existentes.')
    else:
        print('Vista previa; no se realizaron cambios. Usa --apply para importar.')


if __name__ == '__main__':
    main()
