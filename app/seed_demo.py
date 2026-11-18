"""Datos de prueba para Eatsy: restaurante, sucursal, menú, admin y cliente.

Uso (con el .env ya configurado y las dependencias instaladas):
    python -m app.seed_demo

Crea, si no existen:
- Restaurante "Eatsy Demo" con una sucursal "Sede Centro".
- 7 productos de menú con fotos públicas (2 entradas, 2 platos, 2 bebidas
  y 1 adición de bebida para probar POST /pedidos).
- Usuario admin (rol admin) con membresía owner del restaurante.
- Usuario cliente (rol customer) con correo verificado.

Las contraseñas se toman de las variables DEMO_ADMIN_PASS y DEMO_CLIENT_PASS
(si no existen, se generan aleatorias y se muestran UNA sola vez al final).
Es idempotente: se puede ejecutar varias veces sin duplicar datos.
"""
import os
import secrets
import sys

from app.config import Settings
from app.database import connection, init_db, enable_customer_role
from app.security import password_hasher

SLUG = 'eatsy-demo'

MENU = [
    # (nombre, categoria, descripcion, precio, imagen_url)
    ('Empanadas de carne (3 und)', 'Entradas',
     'Tres empanadas doradas con ají casero.', 12000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Empanada_colombiana.jpg/640px-Empanada_colombiana.jpg'),
    ('Ceviche de camarón', 'Entradas',
     'Camarón fresco marinado en limón con cilantro.', 28000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Ceviche_de_camar%C3%B3n.jpg/640px-Ceviche_de_camar%C3%B3n.jpg'),
    ('Arroz con coco y pescado', 'Platos fuertes',
     'Pescado frito, arroz con coco y patacón.', 42000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Arroz_de_coco.jpg/640px-Arroz_de_coco.jpg'),
    ('Bandeja paisa', 'Platos fuertes',
     'Frijoles, arroz, carne molida, chicharrón, huevo y aguacate.', 38000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Bandeja_paisa.jpg/640px-Bandeja_paisa.jpg'),
    ('Limonada de coco', 'Bebidas',
     'Cremosa y bien fría.', 9000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Limonada_de_coco.jpg/640px-Limonada_de_coco.jpg'),
    ('Jugo de lulo', 'Bebidas',
     'Natural, en agua o en leche.', 8000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/9/9d/Jugo_de_lulo.jpg/640px-Jugo_de_lulo.jpg'),
    ('Gaseosa (Personal)', 'Adiciones',
     'Bebida gaseosa de 400 ml para acompañar tu plato.', 4000,
     'https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Gaseosa.jpg/640px-Gaseosa.jpg'),
]


def main() -> None:
    conf = Settings.from_env()
    init_db(conf)
    enable_customer_role(conf)

    admin_pass = os.environ.get('DEMO_ADMIN_PASS') or secrets.token_urlsafe(12)
    client_pass = os.environ.get('DEMO_CLIENT_PASS') or secrets.token_urlsafe(12)

    with connection(conf) as db:
        with db.cursor() as c:
            c.execute('SELECT id FROM restaurants WHERE slug=%s', (SLUG,))
            row = c.fetchone()
            if row:
                restaurant_id = row['id']
                print(f'Restaurante ya existía (id {restaurant_id}); no se duplica.')
            else:
                c.execute(
                    'INSERT INTO restaurants (name, slug, description) VALUES (%s,%s,%s)',
                    ('Eatsy Demo', SLUG, 'Restaurante de prueba para el proyecto Eatsy.'),
                )
                restaurant_id = c.lastrowid
                print(f'Restaurante creado (id {restaurant_id}).')

            c.execute('SELECT id FROM restaurant_branches WHERE restaurant_id=%s AND name=%s', (restaurant_id, 'Sede Centro'))
            row = c.fetchone()
            if row:
                branch_id = row['id']
                print(f'Sucursal ya existía (id {branch_id}).')
            else:
                c.execute(
                    'INSERT INTO restaurant_branches (restaurant_id, name, address, city) VALUES (%s,%s,%s,%s)',
                    (restaurant_id, 'Sede Centro', 'Calle 10 # 4-21', 'Cartagena'),
                )
                branch_id = c.lastrowid
                print(f'Sucursal creada (id {branch_id}).')

            nuevos = 0
            for name, category, description, price, image in MENU:
                c.execute('SELECT id FROM menu_products WHERE restaurant_id=%s AND name=%s', (restaurant_id, name))
                if c.fetchone():
                    continue
                c.execute(
                    'INSERT INTO menu_products (restaurant_id, name, description, category, price, image_url) VALUES (%s,%s,%s,%s,%s,%s)',
                    (restaurant_id, name, description, category, price, image),
                )
                nuevos += 1
            print(f'Productos de menú: {nuevos} nuevos, {len(MENU) - nuevos} ya existían.')

            admin_id = crear_usuario(c, 'admin.eatsy', 'Ana', 'Gómez', 'admin', admin_pass)
            cliente_id = crear_usuario(c, 'cliente.eatsy', 'Carlos', 'Ruiz', 'customer', client_pass)

            c.execute('SELECT 1 FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s', (restaurant_id, admin_id))
            if not c.fetchone():
                c.execute(
                    'INSERT INTO restaurant_memberships (restaurant_id, user_id, role) VALUES (%s,%s,%s)',
                    (restaurant_id, admin_id, 'owner'),
                )
                print('Membresía owner creada para el admin.')
            else:
                print('Membresía del admin ya existía.')

            c.execute('SELECT email FROM customer_emails WHERE user_id=%s', (cliente_id,))
            row = c.fetchone()
            correo = 'cliente.eatsy@demo.com'
            if row:
                print('Correo del cliente ya estaba verificado.')
            else:
                c.execute('INSERT INTO customer_emails (user_id, email, verified_at) VALUES (%s,%s,NOW())', (cliente_id, correo))
                print('Correo del cliente verificado.')

    print('\n================ CREDENCIALES DE PRUEBA ================')
    print(f'Admin    -> usuario: admin.eatsy   contraseña: {admin_pass}')
    print(f'Cliente  -> usuario: cliente.eatsy contraseña: {client_pass}  (correo: {correo})')
    print('Guarda estas contraseñas: no se vuelven a mostrar.')
    print('=========================================================\n')
    print('Siguiente paso: arranca la API con uvicorn app.main:app --reload')
    print('y en el panel web entra con la cuenta admin; en la app móvil usa la cuenta cliente para pedir.')


def crear_usuario(c, usuario: str, nombre: str, apellido: str, rol: str, contrasena: str) -> int:
    c.execute('SELECT id FROM users WHERE usuario=%s', (usuario,))
    row = c.fetchone()
    if row:
        print(f'Usuario {usuario} ya existía (id {row["id"]}).')
        return row['id']
    c.execute(
        'INSERT INTO users (usuario, nombre, apellido, password_hash, rol) VALUES (%s,%s,%s,%s,%s)',
        (usuario, nombre, apellido, password_hasher.hash(contrasena), rol),
    )
    print(f'Usuario {usuario} creado (id {c.lastrowid}, rol {rol}).')
    return c.lastrowid


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        print(f'Falta configuración: {e}', file=sys.stderr)
        print('Crea el archivo .env con DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET_KEY y DB_SSL_CA.', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f'No se pudo conectar con MySQL: {e}', file=sys.stderr)
        print('Revisa DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME y DB_SSL_CA en el archivo .env.', file=sys.stderr)
        sys.exit(1)
