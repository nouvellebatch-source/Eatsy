"""API Eatsy preparada para MySQL en Aiven y despliegue en Render."""
from contextlib import asynccontextmanager
import os
import re
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

import jwt
import pymysql
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import connection
from app.schemas import OutputToken, ProductInput, ProductOutput, RequestActivityOutput, UserInput, UserOutput, UserRegistration, VerifyRegistration, ResendVerification
from app.security import create_token, password_hasher, read_subject, revoke_token, unauthorized_error, verify_password
from app.email_service import send_verification_email, EmailDeliveryError
from app.schemas import RestaurantOutput, BranchOutput, MenuProductOutput, OrderInput, OrderOutput, OrderTransitionInput, OrderEventOutput, KitchenOrderOutput


bearer = HTTPBearer(auto_error=False)
ProductID = Annotated[int, Path(ge=1, le=10_000_000_000)]


def _email_verification_enabled() -> bool:
    return os.environ.get('EMAIL_VERIFICATION_ENABLED', 'false').strip().lower() in {'true', '1', 'yes', 'on'}


def _require_email_verification() -> None:
    if not _email_verification_enabled():
        raise HTTPException(503, 'El registro y la verificación por correo aún no están disponibles.')


def _require_orders() -> None:
    if os.environ.get('ORDERS_ENABLED', 'false').strip().lower() != 'true':
        raise HTTPException(503, 'Los pedidos aún no están habilitados.')


def _code_digest(secret: str, email: str, code: str) -> str:
    return hmac.new(secret.encode(), f'{email}:{code}'.encode(), hashlib.sha256).hexdigest()


def _check_send_limit(cursor, request: Request, now: datetime) -> None:
    client = _client_ip(request) or 'unknown'
    key = hmac.new(request.app.state.settings.secret.encode(), client.encode(), hashlib.sha256).hexdigest()
    cursor.execute('INSERT IGNORE INTO verification_send_limits (client_hash, window_start, sent_count) VALUES (%s, %s, 0)', (key, now))
    cursor.execute('SELECT window_start, sent_count FROM verification_send_limits WHERE client_hash=%s FOR UPDATE', (key,))
    row = cursor.fetchone()
    count = 0 if now - row['window_start'] >= timedelta(hours=1) else row['sent_count']
    if count >= 10:
        raise HTTPException(429, 'Demasiadas solicitudes. Inténtalo más tarde.')
    cursor.execute('UPDATE verification_send_limits SET window_start=%s, sent_count=%s WHERE client_hash=%s',
                   (now if count == 0 else row['window_start'], count + 1, key))


def _send_code(email: str, code: str) -> None:
    try:
        send_verification_email(email, code)
    except EmailDeliveryError:
        raise HTTPException(503, 'No fue posible enviar el correo. Inténtalo más tarde.') from None


def get_db(request: Request):
    with connection(request.app.state.settings) as db:
        yield db


DB = Annotated[Any, Depends(get_db)]


def get_user(request: Request, db: DB, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized_error()
    user_id = read_subject(credentials.credentials, request.app.state.settings)
    with db.cursor() as cursor:
        cursor.execute("SELECT id, usuario, nombre, apellido, rol, activo FROM users WHERE id = %s AND activo = 1", (user_id,))
        user = cursor.fetchone()
    if user is None:
        raise unauthorized_error()
    request.state.user_id = user["id"]
    return user


User = Annotated[dict, Depends(get_user)]


def require_admin(user: User) -> dict:
    if user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Necesitas permiso de administrador.")
    return user


Admin = Annotated[dict, Depends(require_admin)]


def find_product(db: Any, product_id: int) -> dict:
    with db.cursor() as cursor:
        cursor.execute("SELECT id, nombre, descripcion, precio, categoria, imagen_url, stock FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return product


def _client_ip(request: Request) -> str | None:
    if request.app.state.settings.trusted_proxy_headers and (forwarded := request.headers.get("x-forwarded-for")):
        return forwarded.split(",", 1)[0].strip()[:45]
    return request.client.host[:45] if request.client else None


def _coordinate(request: Request, header: str, low: float, high: float) -> float | None:
    try:
        value = float(request.headers[header])
        return value if low <= value <= high else None
    except (KeyError, ValueError):
        return None


def _device_type(user_agent: str) -> str:
    agent = user_agent.lower()
    if any(token in agent for token in ("mobile", "android", "iphone")):
        return "mobile"
    if "ipad" in agent or "tablet" in agent:
        return "tablet"
    return "desktop" if user_agent else "unknown"


def _write_request_log(request: Request, response: Response, elapsed_ms: float, request_id: str) -> None:
    """No geolocaliza IPs: solo almacena la ubicación que la app envía con consentimiento."""
    user_agent = request.headers.get("user-agent", "")[:1024] or None
    platform = (request.headers.get("x-device-platform") or request.headers.get("sec-ch-ua-platform") or "").strip().strip('"')[:80] or None
    with connection(request.app.state.settings) as db:
        with db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO request_logs (request_id, user_id, ip, metodo, ruta, status_code, response_time_ms,
                   user_agent, device_type, device_platform, client_country, client_city, latitude, longitude)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (request_id, getattr(request.state, "user_id", None), _client_ip(request), request.method,
                 request.url.path[:255], response.status_code, elapsed_ms, user_agent, _device_type(user_agent or ""),
                 platform, request.headers.get("x-client-country", "").strip()[:100] or None,
                 request.headers.get("x-client-city", "").strip()[:100] or None,
                 _coordinate(request, "x-client-latitude", -90, 90), _coordinate(request, "x-client-longitude", -180, 180)),
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or Settings.from_env()
        yield

    app = FastAPI(title="Eatsy API", description="API del sistema de restaurantes Eatsy", version="1.0.0", lifespan=lifespan)
    origins = settings.cors_origins if settings else tuple(origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip())
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=False,
                       allow_origin_regex=r'http://(?:localhost|127\.0\.0\.1):[0-9]{1,5}',
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Client-Country", "X-Client-City", "X-Client-Latitude", "X-Client-Longitude", "X-Device-Platform"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": [{"loc": list(error["loc"]), "msg": "Valor no válido."} for error in exc.errors()]})

    @app.middleware("http")
    async def audit_response(request: Request, call_next):
        started, request_id = time.perf_counter(), str(uuid4())
        response = await call_next(request)
        # El catálogo es público; permitir su lectura desde navegadores sin
        # ampliar CORS de autenticación, usuarios, pedidos ni otros recursos.
        if request.method == 'GET' and re.fullmatch(
            r'/restaurantes(?:/[0-9]+/(?:sucursales|categorias|productos))?', request.url.path
        ):
            response.headers['Access-Control-Allow-Origin'] = '*'
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.3f}"
        response.headers["X-Request-ID"] = request_id
        try:
            await run_in_threadpool(_write_request_log, request, response, elapsed_ms, request_id)
        except pymysql.MySQLError:
            pass
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get('/restaurantes', response_model=list[RestaurantOutput])
    def restaurants(db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                    offset: Annotated[int, Query(ge=0)] = 0):
        with db.cursor() as cursor:
            cursor.execute('SELECT id, name, slug, description, image_url FROM restaurants WHERE active=1 ORDER BY name, id LIMIT %s OFFSET %s', (limit, offset))
            return cursor.fetchall()

    @app.get('/restaurantes/{restaurant_id}/sucursales', response_model=list[BranchOutput])
    def branches(restaurant_id: int, db: DB):
        with db.cursor() as cursor:
            cursor.execute('SELECT b.id, b.restaurant_id, b.name, b.address, b.city, b.latitude, b.longitude FROM restaurant_branches b JOIN restaurants r ON r.id=b.restaurant_id WHERE b.restaurant_id=%s AND b.active=1 AND r.active=1 ORDER BY b.name, b.id', (restaurant_id,))
            return cursor.fetchall()

    @app.get('/restaurantes/{restaurant_id}/categorias', response_model=list[str])
    def restaurant_categories(restaurant_id: int, db: DB):
        with db.cursor() as cursor:
            cursor.execute('SELECT DISTINCT p.category FROM menu_products p JOIN restaurants r ON r.id=p.restaurant_id WHERE p.restaurant_id=%s AND p.available=1 AND r.active=1 ORDER BY p.category', (restaurant_id,))
            return [row['category'] for row in cursor.fetchall()]

    @app.get('/restaurantes/{restaurant_id}/productos', response_model=list[MenuProductOutput])
    def restaurant_products(restaurant_id: int, db: DB,
                            categoria: Annotated[str | None, Query(max_length=100)] = None,
                            limit: Annotated[int, Query(ge=1, le=100)] = 50,
                            offset: Annotated[int, Query(ge=0)] = 0):
        with db.cursor() as cursor:
            if categoria and categoria.strip():
                cursor.execute('SELECT p.id, p.restaurant_id, p.name, p.description, p.category, p.price, p.currency, p.image_url FROM menu_products p JOIN restaurants r ON r.id=p.restaurant_id WHERE p.restaurant_id=%s AND p.available=1 AND r.active=1 AND p.category=%s ORDER BY p.name, p.id LIMIT %s OFFSET %s', (restaurant_id, categoria.strip(), limit, offset))
            else:
                cursor.execute('SELECT p.id, p.restaurant_id, p.name, p.description, p.category, p.price, p.currency, p.image_url FROM menu_products p JOIN restaurants r ON r.id=p.restaurant_id WHERE p.restaurant_id=%s AND p.available=1 AND r.active=1 ORDER BY p.name, p.id LIMIT %s OFFSET %s', (restaurant_id, limit, offset))
            return cursor.fetchall()

    @app.post('/pedidos', response_model=OrderOutput, status_code=201)
    def create_order(data: OrderInput, user: User, db: DB):
        _require_orders()
        if data.fulfillment == 'delivery':
            raise HTTPException(503, 'El cálculo de domicilio aún no está disponible.')
        if user['rol'] != 'customer':
            raise HTTPException(403, 'Se necesita una cuenta de cliente.')
        payload = data.model_dump(mode='json', exclude={'idempotency_key'})
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        key = str(data.idempotency_key)

        def existing(cursor):
            cursor.execute('SELECT * FROM orders WHERE customer_id=%s AND idempotency_key=%s', (user['id'], key))
            row = cursor.fetchone()
            if row and row['request_hash'] != request_hash:
                raise HTTPException(409, 'La clave del pedido ya fue usada con otros datos.')
            return row

        db.begin()
        try:
            with db.cursor() as cursor:
                previous = existing(cursor)
                if previous:
                    db.commit()
                    return previous
                cursor.execute('''SELECT b.id FROM restaurant_branches b JOIN restaurants r ON r.id=b.restaurant_id
                    WHERE b.id=%s AND b.restaurant_id=%s AND b.active=1 AND r.active=1''', (data.branch_id, data.restaurant_id))
                if not cursor.fetchone():
                    raise HTTPException(404, 'Restaurante o sucursal no disponible.')
                items = []
                for item in sorted(data.items, key=lambda value: value.product_id):
                    cursor.execute('''SELECT id, name, price, currency FROM menu_products
                        WHERE id=%s AND restaurant_id=%s AND available=1 FOR UPDATE''',
                        (item.product_id, data.restaurant_id))
                    product = cursor.fetchone()
                    if not product or product['currency'] != 'COP':
                        raise HTTPException(409, 'Uno de los productos ya no está disponible.')
                    items.append((product, item.quantity))
                total = sum(product['price'] * quantity for product, quantity in items)
                cursor.execute('''INSERT INTO orders (customer_id, restaurant_id, branch_id, idempotency_key, request_hash,
                    fulfillment, delivery_address, table_number, payment_method, customer_note, total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (user['id'], data.restaurant_id, data.branch_id, key, request_hash, data.fulfillment,
                     data.delivery_address, data.table_number, data.payment_method, data.customer_note, total))
                order_id = cursor.lastrowid
                for product, quantity in items:
                    cursor.execute('INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity) VALUES (%s,%s,%s,%s,%s)',
                                   (order_id, product['id'], product['name'], product['price'], quantity))
                cursor.execute('SELECT * FROM orders WHERE id=%s', (order_id,))
                order = cursor.fetchone()
            db.commit()
            return order
        except pymysql.IntegrityError:
            db.rollback()
            with db.cursor() as cursor:
                previous = existing(cursor)
                if previous:
                    return previous
            raise HTTPException(409, 'No se pudo crear el pedido.') from None
        except Exception:
            db.rollback()
            raise

    @app.get('/pedidos/{order_id}', response_model=OrderOutput)
    def my_order(order_id: int, user: User, db: DB):
        _require_orders()
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM orders WHERE id=%s AND customer_id=%s', (order_id, user['id']))
            row = cursor.fetchone()
        if not row:
            raise HTTPException(404, 'Pedido no encontrado.')
        return row

    @app.get('/pedidos/{order_id}/eventos', response_model=list[OrderEventOutput])
    def order_events(order_id: int, user: User, db: DB):
        _require_orders()
        with db.cursor() as cursor:
            cursor.execute('SELECT id FROM orders WHERE id=%s AND customer_id=%s', (order_id, user['id']))
            if not cursor.fetchone():
                raise HTTPException(404, 'Pedido no encontrado.')
            cursor.execute('SELECT previous_status, new_status, created_at FROM order_events WHERE order_id=%s ORDER BY id', (order_id,))
            return cursor.fetchall()

    @app.get('/gestion/restaurantes/{restaurant_id}/pedidos', response_model=list[KitchenOrderOutput])
    def restaurant_orders(restaurant_id: int, user: User, db: DB,
                          limit: Annotated[int, Query(ge=1, le=100)] = 50):
        _require_orders()
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','kitchen','cashier')", (restaurant_id, user['id']))
            if not cursor.fetchone():
                raise HTTPException(403, 'No tienes acceso a este restaurante.')
            cursor.execute('SELECT * FROM orders WHERE restaurant_id=%s ORDER BY id DESC LIMIT %s', (restaurant_id, limit))
            orders = cursor.fetchall()
            if orders:
                placeholders = ','.join(['%s'] * len(orders))
                cursor.execute(f'SELECT order_id, product_name, quantity, unit_price FROM order_items WHERE order_id IN ({placeholders}) ORDER BY id',
                               tuple(order['id'] for order in orders))
                grouped = {order['id']: [] for order in orders}
                for item in cursor.fetchall():
                    grouped[item['order_id']].append(item)
                for order in orders:
                    order['items'] = grouped[order['id']]
            return orders

    @app.patch('/gestion/restaurantes/{restaurant_id}/pedidos/{order_id}/estado', response_model=OrderOutput)
    def advance_kitchen_order(restaurant_id: int, order_id: int, data: OrderTransitionInput, user: User, db: DB):
        _require_orders()
        allowed_next = {'pending_acceptance': 'confirmed', 'confirmed': 'preparing',
                        'preparing': 'cooked', 'cooked': 'ready', 'ready': 'delivered'}
        db.begin()
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','kitchen','cashier')", (restaurant_id, user['id']))
                if not cursor.fetchone():
                    raise HTTPException(403, 'No tienes permiso para gestionar cocina.')
                cursor.execute('SELECT * FROM orders WHERE id=%s AND restaurant_id=%s FOR UPDATE', (order_id, restaurant_id))
                order = cursor.fetchone()
                if not order:
                    raise HTTPException(404, 'Pedido no encontrado.')
                if order['fulfillment'] == 'delivery' and data.status == 'delivered':
                    raise HTTPException(409, 'La entrega a domicilio debe confirmarla el domiciliario asignado.')
                previous = order['status']
                if allowed_next.get(previous) != data.status:
                    raise HTTPException(409, 'Transición de estado no permitida.')
                cursor.execute('UPDATE orders SET status=%s WHERE id=%s AND restaurant_id=%s', (data.status, order_id, restaurant_id))
                cursor.execute('INSERT INTO order_events (order_id, actor_id, previous_status, new_status) VALUES (%s,%s,%s,%s)',
                               (order_id, user['id'], previous, data.status))
                order['status'] = data.status
            db.commit()
            return order
        except Exception:
            db.rollback()
            raise

    @app.post("/auth/registro", status_code=status.HTTP_202_ACCEPTED)
    def register(data: UserRegistration, db: DB, request: Request):
        _require_email_verification()
        email = str(data.correo).strip().lower()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        code = f'{secrets.randbelow(1_000_000):06d}'
        password_hash = password_hasher.hash(data.contrasena.get_secret_value())
        try:
            db.begin()
            with db.cursor() as cursor:
                _check_send_limit(cursor, request, now)
                cursor.execute('SELECT id FROM users WHERE usuario=%s', (data.usuario,))
                if cursor.fetchone():
                    raise HTTPException(409, 'Usuario no disponible.')
                cursor.execute('SELECT user_id FROM customer_emails WHERE email=%s', (email,))
                if cursor.fetchone():
                    raise HTTPException(409, 'No se pudo crear la cuenta con esos datos.')
                cursor.execute(
                    """INSERT INTO pending_registrations
                    (email, usuario, nombre, apellido, password_hash, code_hash, expires_at, last_sent_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (email, data.usuario, data.nombre, data.apellido, password_hash,
                     _code_digest(request.app.state.settings.secret, email, code), now + timedelta(minutes=10), now),
                )
                _send_code(email, code)
            db.commit()
        except pymysql.IntegrityError as error:
            db.rollback()
            if error.args and error.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Ya existe un registro con esos datos; solicita el reenvío del código.") from None
            raise
        except Exception:
            db.rollback()
            raise
        return {'detail': 'Enviamos un código de verificación al correo.'}

    @app.post('/auth/reenviar-codigo', status_code=202)
    def resend(data: ResendVerification, db: DB, request: Request):
        _require_email_verification()
        email = str(data.correo).strip().lower()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.begin()
        try:
            with db.cursor() as cursor:
                _check_send_limit(cursor, request, now)
                cursor.execute('SELECT last_sent_at FROM pending_registrations WHERE email=%s FOR UPDATE', (email,))
                row = cursor.fetchone()
                if row and now - row['last_sent_at'] < timedelta(seconds=60):
                    raise HTTPException(429, 'Espera un minuto antes de solicitar otro código.')
                if row:
                    code = f'{secrets.randbelow(1_000_000):06d}'
                    cursor.execute('UPDATE pending_registrations SET code_hash=%s, expires_at=%s, last_sent_at=%s, attempts=0 WHERE email=%s',
                        (_code_digest(request.app.state.settings.secret, email, code), now + timedelta(minutes=10), now, email))
                    _send_code(email, code)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {'detail': 'Si existe un registro pendiente, recibirás un código.'}

    @app.post('/auth/verificar-correo', response_model=UserOutput, status_code=201)
    def verify_registration(data: VerifyRegistration, db: DB, request: Request):
        _require_email_verification()
        email = str(data.correo).strip().lower()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.begin()
        try:
            with db.cursor() as cursor:
                cursor.execute('SELECT * FROM pending_registrations WHERE email=%s FOR UPDATE', (email,))
                row = cursor.fetchone()
                if not row or row['expires_at'] <= now or row['attempts'] >= 5:
                    raise HTTPException(400, 'Código inválido o vencido. Solicita uno nuevo.')
                expected = _code_digest(request.app.state.settings.secret, email, data.codigo)
                if not hmac.compare_digest(expected, row['code_hash']):
                    cursor.execute('UPDATE pending_registrations SET attempts=attempts+1 WHERE email=%s', (email,))
                    db.commit()
                    raise HTTPException(400, 'Código inválido o vencido. Solicita uno nuevo.')
                cursor.execute('INSERT INTO users (usuario,nombre,apellido,password_hash,rol) VALUES (%s,%s,%s,%s,%s)',
                               (row['usuario'], row['nombre'], row['apellido'], row['password_hash'], 'customer'))
                user_id = cursor.lastrowid
                cursor.execute('INSERT INTO customer_emails (user_id,email,verified_at) VALUES (%s,%s,%s)', (user_id,email,now))
                cursor.execute('DELETE FROM pending_registrations WHERE email=%s', (email,))
            db.commit()
            return {'id': user_id, 'usuario': row['usuario'], 'nombre': row['nombre'], 'apellido': row['apellido'], 'rol': 'customer'}
        except pymysql.IntegrityError:
            db.rollback()
            raise HTTPException(409, 'No se pudo crear la cuenta con esos datos.') from None
        except Exception:
            db.rollback()
            raise

    @app.post("/auth/login", response_model=OutputToken)
    def login(data: UserInput, db: DB, request: Request):
        with db.cursor() as cursor:
            if _email_verification_enabled():
                cursor.execute("SELECT u.*, e.email AS verified_email FROM users u LEFT JOIN customer_emails e ON e.user_id=u.id WHERE u.usuario=%s OR e.email=%s LIMIT 1", (data.usuario, data.usuario))
            else:
                cursor.execute("SELECT u.*, NULL AS verified_email FROM users u WHERE u.usuario=%s LIMIT 1", (data.usuario,))
            user = cursor.fetchone()
        valid = verify_password(data.contrasena.get_secret_value(), user['password_hash'] if user else None)
        if user and user['verified_email']:
            db.begin()
            try:
                with db.cursor() as cursor:
                    cursor.execute('INSERT IGNORE INTO login_verifications (user_id) VALUES (%s)', (user['id'],))
                    cursor.execute('SELECT failures FROM login_verifications WHERE user_id=%s FOR UPDATE', (user['id'],))
                    failures = cursor.fetchone()['failures']
                    if failures >= 5:
                        db.commit()
                        raise HTTPException(403, 'Verifica tu correo para desbloquear el acceso.')
                    if not valid or not user['activo']:
                        cursor.execute('UPDATE login_verifications SET failures=failures+1 WHERE user_id=%s', (user['id'],))
                        if failures + 1 >= 5:
                            db.commit()
                            raise HTTPException(403, 'Verifica tu correo para desbloquear el acceso.')
                    else:
                        cursor.execute('UPDATE login_verifications SET failures=0 WHERE user_id=%s', (user['id'],))
                db.commit()
            except Exception:
                db.rollback()
                raise
        if user is None or not user["activo"] or not valid:
            raise unauthorized_error()
        token, issued_at, jti = create_token(user["id"], request.app.state.settings)
        return OutputToken(access_token=token, expires_in=request.app.state.settings.token_minutes * 60,
                           issued_at=issued_at, jti=jti, audience=request.app.state.settings.audience,
                           issuer=request.app.state.settings.issuer, usuario=UserOutput.model_validate(user))

    @app.post('/auth/codigo-acceso', status_code=202)
    def request_login_code(data: ResendVerification, db: DB, request: Request):
        _require_email_verification()
        email = str(data.correo).strip().lower()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.begin()
        try:
            with db.cursor() as cursor:
                _check_send_limit(cursor, request, now)
                cursor.execute('''SELECT v.user_id, v.last_sent_at FROM login_verifications v
                    JOIN customer_emails e ON e.user_id=v.user_id WHERE e.email=%s AND v.failures>=5 FOR UPDATE''', (email,))
                row = cursor.fetchone()
                if row and row['last_sent_at'] and now-row['last_sent_at'] < timedelta(seconds=60):
                    raise HTTPException(429, 'Espera un minuto antes de solicitar otro código.')
                if row:
                    code = f'{secrets.randbelow(1_000_000):06d}'
                    cursor.execute('UPDATE login_verifications SET code_hash=%s, expires_at=%s, last_sent_at=%s, attempts=0 WHERE user_id=%s',
                        (_code_digest(request.app.state.settings.secret, email, code), now+timedelta(minutes=10), now, row['user_id']))
                    _send_code(email, code)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {'detail': 'Si la cuenta requiere verificación, recibirás un código.'}

    @app.post('/auth/verificar-acceso')
    def verify_login_code(data: VerifyRegistration, db: DB, request: Request):
        _require_email_verification()
        email = str(data.correo).strip().lower()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.begin()
        try:
            with db.cursor() as cursor:
                cursor.execute('''SELECT v.* FROM login_verifications v JOIN customer_emails e ON e.user_id=v.user_id
                    WHERE e.email=%s AND v.failures>=5 FOR UPDATE''', (email,))
                row = cursor.fetchone()
                if not row or not row['code_hash'] or row['expires_at'] <= now or row['attempts'] >= 5:
                    raise HTTPException(400, 'Código inválido o vencido.')
                if not hmac.compare_digest(row['code_hash'], _code_digest(request.app.state.settings.secret, email, data.codigo)):
                    cursor.execute('UPDATE login_verifications SET attempts=attempts+1 WHERE user_id=%s', (row['user_id'],))
                    db.commit()
                    raise HTTPException(400, 'Código inválido o vencido.')
                cursor.execute('UPDATE login_verifications SET failures=0, code_hash=NULL, expires_at=NULL, attempts=0 WHERE user_id=%s', (row['user_id'],))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {'detail': 'Correo verificado. Ya puedes iniciar sesión.'}

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise unauthorized_error()
        read_subject(credentials.credentials, request.app.state.settings)
        revoke_token(jwt.decode(credentials.credentials, options={"verify_signature": False})["jti"])
        return Response(status_code=204)

    @app.get("/auth/me", response_model=UserOutput)
    def get_me(user: User):
        return user

    @app.get("/perfil/actividad", response_model=list[RequestActivityOutput])
    def my_activity(user: User, db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 30):
        with db.cursor() as cursor:
            cursor.execute("""SELECT id, metodo, ruta, status_code, response_time_ms, user_agent, device_type,
                           device_platform, client_country, client_city, latitude, longitude, created_at
                           FROM request_logs WHERE user_id = %s ORDER BY id DESC LIMIT %s""", (user["id"], limit))
            return cursor.fetchall()

    @app.get("/productos", response_model=list[ProductOutput])
    def list_products(user: User, db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      offset: Annotated[int, Query(ge=0)] = 0,
                      categoria: Annotated[str | None, Query(max_length=80)] = None):
        with db.cursor() as cursor:
            category = categoria.strip() if categoria else ""
            if category:
                cursor.execute("SELECT id, nombre, descripcion, precio, categoria, imagen_url, stock FROM products WHERE categoria = %s ORDER BY id LIMIT %s OFFSET %s", (category, limit, offset))
            else:
                cursor.execute("SELECT id, nombre, descripcion, precio, categoria, imagen_url, stock FROM products ORDER BY id LIMIT %s OFFSET %s", (limit, offset))
            return cursor.fetchall()

    @app.get("/productos/{product_id}", response_model=ProductOutput)
    def get_product(user: User, db: DB, product_id: ProductID):
        return find_product(db, product_id)

    @app.post("/productos", response_model=ProductOutput, status_code=201)
    def create_product(admin: Admin, data: ProductInput, db: DB, response: Response):
        with db.cursor() as cursor:
            cursor.execute("""INSERT INTO products (nombre, descripcion, precio, categoria, imagen_url, stock)
                           VALUES (%(nombre)s, %(descripcion)s, %(precio)s, %(categoria)s, %(imagen_url)s, %(stock)s)""", data.model_dump(mode="json"))
            product_id = cursor.lastrowid
        response.headers["Location"] = f"/productos/{product_id}"
        return find_product(db, product_id)

    @app.put("/productos/{product_id}", response_model=ProductOutput)
    def update_product(admin: Admin, data: ProductInput, db: DB, product_id: ProductID):
        find_product(db, product_id)
        values = data.model_dump(mode="json") | {"id": product_id}
        with db.cursor() as cursor:
            cursor.execute("""UPDATE products SET nombre=%(nombre)s, descripcion=%(descripcion)s, precio=%(precio)s,
                           categoria=%(categoria)s, imagen_url=%(imagen_url)s, stock=%(stock)s WHERE id=%(id)s""", values)
        return find_product(db, product_id)

    @app.delete("/productos/{product_id}", status_code=204)
    def delete_product(admin: Admin, db: DB, product_id: ProductID):
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            if not cursor.rowcount:
                raise HTTPException(status_code=404, detail="Producto no encontrado.")
        return Response(status_code=204)

    return app


app = create_app()
