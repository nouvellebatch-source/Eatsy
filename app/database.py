"""Acceso transaccional y esquema exclusivamente MySQL para Aiven."""
from contextlib import contextmanager

import pymysql

from app.config import Settings


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS restaurants (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(160) NOT NULL,
        slug VARCHAR(160) NOT NULL UNIQUE,
        description TEXT NULL,
        image_url VARCHAR(2048) NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS restaurant_branches (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        restaurant_id BIGINT UNSIGNED NOT NULL,
        name VARCHAR(160) NOT NULL,
        address VARCHAR(255) NOT NULL,
        city VARCHAR(120) NOT NULL,
        latitude DECIMAL(10,7) NULL,
        longitude DECIMAL(10,7) NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT fk_branch_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS menu_products (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        restaurant_id BIGINT UNSIGNED NOT NULL,
        name VARCHAR(160) NOT NULL,
        description TEXT NULL,
        category VARCHAR(100) NOT NULL,
        price BIGINT UNSIGNED NOT NULL,
        currency CHAR(3) NOT NULL DEFAULT 'COP',
        image_url VARCHAR(2048) NULL,
        available BOOLEAN NOT NULL DEFAULT TRUE,
        source_url VARCHAR(2048) NULL,
        INDEX idx_menu_restaurant_category (restaurant_id, category),
        CONSTRAINT fk_menu_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(80) NOT NULL UNIQUE,
        nombre VARCHAR(80) NOT NULL,
        apellido VARCHAR(80) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        rol VARCHAR(20) NOT NULL,
        activo TINYINT(1) NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT chk_users_role CHECK (rol IN ('admin', 'staff', 'customer')),
        CONSTRAINT chk_users_active CHECK (activo IN (0, 1))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        customer_id BIGINT UNSIGNED NOT NULL,
        restaurant_id BIGINT UNSIGNED NOT NULL,
        branch_id BIGINT UNSIGNED NOT NULL,
        idempotency_key CHAR(36) NOT NULL,
        request_hash CHAR(64) NOT NULL,
        fulfillment VARCHAR(16) NOT NULL,
        delivery_address VARCHAR(255) NULL,
        table_number VARCHAR(30) NULL,
        payment_method VARCHAR(20) NOT NULL,
        payment_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        status VARCHAR(24) NOT NULL DEFAULT 'pending_acceptance',
        total BIGINT UNSIGNED NOT NULL,
        currency CHAR(3) NOT NULL DEFAULT 'COP',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_order_idempotency (customer_id, idempotency_key),
        CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES users(id),
        CONSTRAINT fk_order_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
        CONSTRAINT fk_order_branch FOREIGN KEY (branch_id) REFERENCES restaurant_branches(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT UNSIGNED NOT NULL,
        product_id BIGINT UNSIGNED NOT NULL,
        product_name VARCHAR(160) NOT NULL,
        unit_price BIGINT UNSIGNED NOT NULL,
        quantity SMALLINT UNSIGNED NOT NULL,
        CONSTRAINT fk_order_item_order FOREIGN KEY (order_id) REFERENCES orders(id),
        CONSTRAINT fk_order_item_product FOREIGN KEY (product_id) REFERENCES menu_products(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS restaurant_memberships (
        restaurant_id BIGINT UNSIGNED NOT NULL,
        user_id BIGINT UNSIGNED NOT NULL,
        role VARCHAR(20) NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (restaurant_id, user_id),
        CONSTRAINT fk_membership_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
        CONSTRAINT fk_membership_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT chk_membership_role CHECK (role IN ('owner', 'kitchen', 'cashier', 'courier'))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS order_events (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        order_id BIGINT UNSIGNED NOT NULL,
        actor_id BIGINT UNSIGNED NOT NULL,
        previous_status VARCHAR(24) NOT NULL,
        new_status VARCHAR(24) NOT NULL,
        created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        INDEX idx_order_events_order (order_id, id),
        CONSTRAINT fk_order_event_order FOREIGN KEY (order_id) REFERENCES orders(id),
        CONSTRAINT fk_order_event_actor FOREIGN KEY (actor_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS pending_registrations (
        email VARCHAR(254) NOT NULL PRIMARY KEY,
        usuario VARCHAR(80) NOT NULL UNIQUE,
        nombre VARCHAR(80) NOT NULL,
        apellido VARCHAR(80) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        code_hash CHAR(64) NOT NULL,
        expires_at DATETIME NOT NULL,
        last_sent_at DATETIME NOT NULL,
        attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_emails (
        user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        email VARCHAR(254) NOT NULL UNIQUE,
        verified_at DATETIME NOT NULL,
        CONSTRAINT fk_customer_emails_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS verification_send_limits (
        client_hash CHAR(64) NOT NULL PRIMARY KEY,
        window_start DATETIME NOT NULL,
        sent_count SMALLINT UNSIGNED NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS login_verifications (
        user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        failures SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        code_hash CHAR(64) NULL,
        expires_at DATETIME NULL,
        last_sent_at DATETIME NULL,
        attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        CONSTRAINT fk_login_verifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(80) NOT NULL,
        descripcion TEXT NOT NULL,
        precio BIGINT UNSIGNED NOT NULL,
        categoria VARCHAR(80) NOT NULL,
        imagen_url VARCHAR(2048) NOT NULL,
        stock BIGINT UNSIGNED NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_products_category (categoria)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS request_logs (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        request_id CHAR(36) NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        ip VARCHAR(45) NULL,
        metodo VARCHAR(10) NOT NULL,
        ruta VARCHAR(255) NOT NULL,
        status_code SMALLINT UNSIGNED NOT NULL,
        response_time_ms DECIMAL(12, 3) NOT NULL,
        user_agent VARCHAR(1024) NULL,
        device_type VARCHAR(40) NULL,
        device_platform VARCHAR(80) NULL,
        client_country VARCHAR(100) NULL,
        client_city VARCHAR(100) NULL,
        latitude DECIMAL(10, 7) NULL,
        longitude DECIMAL(10, 7) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_request_logs_request_id (request_id),
        INDEX idx_request_logs_user_created (user_id, created_at),
        INDEX idx_request_logs_ip_created (ip, created_at),
        CONSTRAINT fk_request_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


def _ssl_options(settings: Settings) -> dict | None:
    return {"ca": str(settings.db_ssl_ca), "check_hostname": True} if settings.db_ssl else None


@contextmanager
def connection(settings: Settings):
    db = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=settings.db_connect_timeout,
        read_timeout=30,
        write_timeout=30,
        ssl=_ssl_options(settings),
    )
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(settings: Settings) -> None:
    with connection(settings) as db:
        with db.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)


def init_catalog(settings: Settings) -> None:
    """Crea solo las tres tablas nuevas de catálogo, sin modificar datos existentes."""
    with connection(settings) as db:
        with db.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS[:3]:
                cursor.execute(statement)


def enable_customer_role(settings: Settings) -> None:
    """Actualiza la restricción existente conservando los usuarios actuales."""
    with connection(settings) as db:
        with db.cursor() as cursor:
            cursor.execute("""SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='chk_users_role'""")
            row = cursor.fetchone()
            if row and 'customer' in row['CHECK_CLAUSE'].lower():
                return
            if row:
                cursor.execute('ALTER TABLE users DROP CHECK chk_users_role')
            cursor.execute("ALTER TABLE users ADD CONSTRAINT chk_users_role CHECK (rol IN ('admin', 'staff', 'customer'))")
