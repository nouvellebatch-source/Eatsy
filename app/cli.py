"""Administración exclusivamente MySQL de Eatsy."""
import argparse
import getpass

import pymysql

from app.config import Settings
from app.database import connection, enable_customer_role, init_db
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Administración MySQL de Eatsy")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", aliases=["init-db", "cli-init"], help="Crea las tablas MySQL requeridas.")
    commands.add_parser("check-db", help="Comprueba la conexión y las tablas principales.")
    commands.add_parser("migrate-customers", help="Habilita el rol de cliente y crea tablas de verificación.")
    create = commands.add_parser("create-user", help="Crea un usuario desde terminal.")
    create.add_argument("--usuario", required=True)
    create.add_argument("--nombre", required=True)
    create.add_argument("--apellido", required=True)
    create.add_argument("--rol", choices=["admin", "staff"], default="staff")
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command in {"init", "init-db", "cli-init"}:
            init_db(settings)
            print("Esquema MySQL de Eatsy inicializado.")
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
        else:
            _create_user(args, settings)
    except (OSError, ValueError, pymysql.MySQLError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
