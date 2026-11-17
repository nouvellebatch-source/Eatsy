"""Administración exclusivamente MySQL de Eatsy."""
import argparse
import getpass

import pymysql

from app.config import Settings
from app.database import connection, enable_customer_role, init_catalog, init_db, init_orders, init_tables, init_commercial
from app.security import password_hasher


def _create_user(args: argparse.Namespace, settings: Settings) -> None:
    values = (args.usuario.strip(), args.nombre.strip(), args.apellido.strip())
    if not all(1 <= len(value) <= 80 for value in values):
        raise ValueError("Usuario, nombre y apellido deben tener entre 1 y 80 caracteres.")
    password = getpass.getpass("Contraseña (12 a 128 caracteres): ")
    if password != getpass.getpass("Repetir contraseña: ") or not 12 <= len(password) <= 128:
        raise ValueError("Las contraseñas no coinciden o su longitud no es válida.")
    with connection(settings) as db:
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (usuario, nombre, apellido, password_hash, rol) VALUES (%s, %s, %s, %s, %s)",
                (*values, password_hasher.hash(password), args.rol),
            )
    print("Usuario creado. La contraseña original no se almacenó.")


def _assign_kitchen(args: argparse.Namespace, settings: Settings) -> None:
    with connection(settings) as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE usuario=%s AND activo=1 AND rol IN ('staff','admin')", (args.usuario,))
            user = cursor.fetchone()
            cursor.execute('SELECT id FROM restaurants WHERE slug=%s AND active=1', (args.restaurante,))
            restaurant = cursor.fetchone()
            if not user or not restaurant:
                raise ValueError('Usuario staff/admin o restaurante no encontrado.')
            cursor.execute('SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s', (restaurant['id'], user['id']))
            membership = cursor.fetchone()
            if membership and membership['role'] not in ('owner', 'kitchen'):
                raise ValueError('La cuenta ya tiene otro rol en el restaurante; no se modificó.')
            cursor.execute("INSERT INTO restaurant_memberships (restaurant_id,user_id,role,active) VALUES (%s,%s,'kitchen',1) ON DUPLICATE KEY UPDATE active=1", (restaurant['id'], user['id']))
    print('Acceso de cocina asignado o reactivado.')


def _assign_restaurant_role(args: argparse.Namespace, settings: Settings) -> None:
    """Vincula una cuenta existente y verificada, sin alterar membresías existentes."""
    with connection(settings) as db:
        db.begin()
        try:
            with db.cursor() as cursor:
                cursor.execute('SELECT u.id,u.rol FROM users u JOIN customer_emails e ON e.user_id=u.id WHERE u.usuario=%s AND u.activo=1 AND e.verified_at IS NOT NULL FOR UPDATE', (args.usuario,))
                user = cursor.fetchone()
                cursor.execute('SELECT id FROM restaurants WHERE slug=%s AND active=1', (args.restaurante,))
                restaurant = cursor.fetchone()
                if not user or not restaurant:
                    raise ValueError('Cuenta verificada o restaurante no encontrado.')
                cursor.execute('SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s', (restaurant['id'], user['id']))
                if cursor.fetchone():
                    raise ValueError('La cuenta ya tiene una membresía; no se modificó.')
                cursor.execute('INSERT INTO restaurant_memberships (restaurant_id,user_id,role,active) VALUES (%s,%s,%s,1)',
                               (restaurant['id'], user['id'], args.rol))
            db.commit()
        except Exception:
            db.rollback()
            raise
    print('Cuenta verificada vinculada al restaurante.')


def main() -> None:
    parser = argparse.ArgumentParser(description="Administración MySQL de Eatsy")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", aliases=["init-db", "cli-init"], help="Crea las tablas MySQL requeridas.")
    commands.add_parser("check-db", help="Comprueba la conexión y las tablas principales.")
    commands.add_parser("init-catalog", help="Crea las tablas de restaurantes, sucursales y menús.")
    commands.add_parser("init-orders", help="Crea las tablas de pedidos y comanda.")
    commands.add_parser('init-commercial', help='Crea tablas de promociones y descuentos.')
    tables = commands.add_parser('seed-tables', help='Crea el mapa inicial de 15 mesas sin reemplazar mesas existentes.')
    tables.add_argument('--restaurante', required=True)
    tables.add_argument('--sucursal', required=True, type=int)
    commands.add_parser("migrate-customers", help="Habilita el rol de cliente y crea tablas de verificación.")
    create = commands.add_parser("create-user", help="Crea un usuario desde terminal.")
    create.add_argument("--usuario", required=True)
    create.add_argument("--nombre", required=True)
    create.add_argument("--apellido", required=True)
    create.add_argument("--rol", choices=["admin", "staff"], default="staff")
    kitchen = commands.add_parser('assign-kitchen', help='Da acceso a la comanda a un usuario staff o admin existente.')
    kitchen.add_argument('--usuario', required=True)
    kitchen.add_argument('--restaurante', required=True, help='Slug del restaurante.')
    membership = commands.add_parser('assign-restaurant-role', help='Vincula una cuenta verificada a un restaurante.')
    membership.add_argument('--usuario', required=True)
    membership.add_argument('--restaurante', required=True)
    membership.add_argument('--rol', required=True, choices=['owner', 'kitchen', 'cashier', 'courier'])
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command in {"init", "init-db", "cli-init"}:
            init_db(settings)
            print("Esquema MySQL de Eatsy inicializado.")
        elif args.command == "init-catalog":
            init_catalog(settings)
            print("Tablas de catálogo inicializadas.")
        elif args.command == "init-orders":
            init_orders(settings)
            print("Tablas de pedidos y comanda inicializadas.")
        elif args.command == 'init-commercial':
            init_commercial(settings)
            print('Tablas de promociones inicializadas.')
        elif args.command == 'seed-tables':
            init_tables(settings)
            with connection(settings) as db:
                db.begin()
                try:
                    with db.cursor() as cursor:
                        cursor.execute('SELECT r.id FROM restaurants r JOIN restaurant_branches b ON b.restaurant_id=r.id WHERE r.slug=%s AND b.id=%s AND r.active=1 AND b.active=1', (args.restaurante,args.sucursal))
                        restaurant = cursor.fetchone()
                        if not restaurant:
                            raise ValueError('Restaurante o sucursal no disponible.')
                        added = 0
                        for number in range(1, 16):
                            added += cursor.execute('INSERT IGNORE INTO restaurant_tables (restaurant_id,branch_id,table_number,capacity,created_by) VALUES (%s,%s,%s,4,NULL)', (restaurant['id'], args.sucursal, number))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            print(f'Mapas inicializados: {added} mesas creadas; las existentes no se modificaron.')
        elif args.command == "migrate-customers":
            init_db(settings)
            enable_customer_role(settings)
            print("Esquema de clientes y verificación inicializado.")
        elif args.command == "check-db":
            with connection(settings) as db:
                with db.cursor() as cursor:
                    cursor.execute("SELECT DATABASE() AS database_name")
                    database_name = cursor.fetchone()["database_name"]
                    cursor.execute("SHOW TABLES")
                    tables = sorted(row[next(iter(row))] for row in cursor.fetchall())
            print(f"Conexión correcta a {database_name}. Tablas: {', '.join(tables) or 'ninguna'}")
        elif args.command == 'assign-kitchen':
            _assign_kitchen(args, settings)
        elif args.command == 'assign-restaurant-role':
            _assign_restaurant_role(args, settings)
        else:
            _create_user(args, settings)
    except (OSError, ValueError, pymysql.MySQLError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
