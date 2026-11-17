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
from app.schemas import RestaurantOutput, BranchOutput, MenuProductOutput, OrderInput, OrderOutput, OrderTransitionInput, OrderEventOutput, KitchenOrderOutput, RestaurantTableOutput, PublicTableOutput, ReservationInput, ReservationOutput, CustomerReservationInput, PromotionInput, PromotionOutput, RestaurantEventInput, RestaurantEventOutput


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
            r'/restaurantes(?:/[0-9]+/(?:sucursales(?:/[0-9]+/mesas)?|categorias|productos|promociones|eventos))?', request.url.path
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
        if payload.get('discount_code') is None:
            payload.pop('discount_code', None)
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
                if data.fulfillment == 'dine_in':
                    if not data.table_number or not re.fullmatch(r'[1-9][0-9]{0,4}', data.table_number):
                        raise HTTPException(422, 'Selecciona una mesa válida de la sucursal.')
                    cursor.execute('SELECT id FROM restaurant_tables WHERE restaurant_id=%s AND branch_id=%s AND table_number=%s',
                                   (data.restaurant_id,data.branch_id,int(data.table_number)))
                    if not cursor.fetchone():
                        raise HTTPException(409, 'La mesa no está registrada en esta sucursal.')
                products = {}
                product_ids = {item.product_id for item in data.items}
                product_ids.update(add.product_id for item in data.items for add in item.additions)
                for product_id in sorted(product_ids):
                    cursor.execute('''SELECT id, name, category, price, currency FROM menu_products
                        WHERE id=%s AND restaurant_id=%s AND available=1 FOR UPDATE''',
                        (product_id, data.restaurant_id))
                    product = cursor.fetchone()
                    if not product or product['currency'] != 'COP':
                        raise HTTPException(409, 'Uno de los productos ya no está disponible.')
                    products[product_id] = product
                items = []
                for item in data.items:
                    product = products[item.product_id]
                    if product['category'].lower().startswith('adiciones'):
                        raise HTTPException(422, 'Las adiciones deben elegirse dentro del plato.')
                    additions = []
                    for addition in item.additions:
                        extra = products[addition.product_id]
                        extra_category = extra['category'].lower()
                        is_drink = extra_category in {'bebidas', 'jugos naturales', 'cervezas artesanales', 'cervezas importadas', 'cervezas nacionales'}
                        if is_drink:
                            if product['category'].lower() in {'bebidas', 'jugos naturales', 'cervezas artesanales', 'cervezas importadas', 'cervezas nacionales'}:
                                raise HTTPException(422, 'La bebida debe acompañar un plato.')
                            additions.append((extra, addition.quantity))
                            continue
                        size = re.search(r'\((Personal|Small|Medium|Large)\)$', product['name'], re.I)
                        extra_size = re.search(r'\((Personal|Small|Medium|Large)\)$', extra['name'], re.I)
                        if (not product['category'].lower().startswith('pizzas') or
                            extra['category'].lower() != 'adiciones pizza' or not size or not extra_size or
                            size.group(1).lower() != extra_size.group(1).lower()):
                            raise HTTPException(422, 'La adición no corresponde a esta pizza o tamaño.')
                        additions.append((extra, addition.quantity))
                    items.append((product, item.quantity, additions))
                total = sum((product['price'] + sum(extra['price'] * amount for extra, amount in additions)) * quantity
                            for product, quantity, additions in items)
                discount = 0
                promotion = None
                subtotal = total
                if data.discount_code:
                    cursor.execute('''SELECT id,code,percent_off FROM restaurant_promotions
                        WHERE restaurant_id=%s AND code=%s AND active=1 AND starts_at<=UTC_TIMESTAMP() AND ends_at>UTC_TIMESTAMP() FOR UPDATE''',
                        (data.restaurant_id,data.discount_code.strip().upper()))
                    promotion = cursor.fetchone()
                    if not promotion: raise HTTPException(409, 'El código no está disponible o ha vencido.')
                    discount = subtotal * promotion['percent_off'] // 100
                    total = subtotal - discount
                cursor.execute('''INSERT INTO orders (customer_id, restaurant_id, branch_id, idempotency_key, request_hash,
                    fulfillment, delivery_address, table_number, payment_method, customer_note, status, total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s)''',
                    (user['id'], data.restaurant_id, data.branch_id, key, request_hash, data.fulfillment,
                     data.delivery_address, data.table_number, data.payment_method, data.customer_note, total))
                order_id = cursor.lastrowid
                if promotion:
                    cursor.execute('INSERT INTO order_discounts (order_id,promotion_id,code,percent_off,subtotal,discount) VALUES (%s,%s,%s,%s,%s,%s)',
                                   (order_id,promotion['id'],promotion['code'],promotion['percent_off'],subtotal,discount))
                for product, quantity, additions in items:
                    cursor.execute('INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity) VALUES (%s,%s,%s,%s,%s)',
                                   (order_id, product['id'], product['name'], product['price'], quantity))
                    item_id = cursor.lastrowid
                    for extra, amount in additions:
                        cursor.execute('INSERT INTO order_item_additions (order_item_id,product_id,product_name,unit_price,quantity) VALUES (%s,%s,%s,%s,%s)',
                                       (item_id, extra['id'], extra['name'], extra['price'], amount))
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

    @app.get('/mis-pedidos', response_model=list[OrderOutput])
    def list_my_orders(user: User, db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 50):
        _require_orders()
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM orders WHERE customer_id=%s ORDER BY id DESC LIMIT %s', (user['id'], limit))
            return cursor.fetchall()

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

    @app.get('/restaurantes/{restaurant_id}/promociones', response_model=list[PromotionOutput])
    def public_promotions(restaurant_id: int, db: DB):
        with db.cursor() as cursor:
            cursor.execute('''SELECT p.id,p.code,p.title,p.percent_off,p.starts_at,p.ends_at,p.active
                FROM restaurant_promotions p JOIN restaurants r ON r.id=p.restaurant_id AND r.active=1
                WHERE p.restaurant_id=%s AND p.active=1 AND p.starts_at<=UTC_TIMESTAMP() AND p.ends_at>UTC_TIMESTAMP() ORDER BY p.ends_at,p.id''', (restaurant_id,))
            return cursor.fetchall()

    @app.get('/gestion/restaurantes/{restaurant_id}/promociones', response_model=list[PromotionOutput])
    def manage_promotions(restaurant_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede gestionar promociones.')
            cursor.execute('SELECT id,code,title,percent_off,starts_at,ends_at,active FROM restaurant_promotions WHERE restaurant_id=%s ORDER BY id DESC LIMIT 100', (restaurant_id,))
            return cursor.fetchall()

    @app.post('/gestion/restaurantes/{restaurant_id}/promociones', response_model=PromotionOutput, status_code=201)
    def create_promotion(restaurant_id: int, data: PromotionInput, user: User, db: DB):
        starts=data.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
        ends=data.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
        if ends <= datetime.now(timezone.utc).replace(tzinfo=None): raise HTTPException(422, 'La promoción debe terminar en el futuro.')
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
                if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede crear promociones.')
                cursor.execute('INSERT INTO restaurant_promotions (restaurant_id,code,title,percent_off,starts_at,ends_at,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (restaurant_id,data.code.upper(),data.title,data.percent_off,starts,ends,user['id']))
                return {'id':cursor.lastrowid,'code':data.code.upper(),'title':data.title,'percent_off':data.percent_off,'starts_at':starts,'ends_at':ends,'active':True}
        except pymysql.IntegrityError as error:
            if error.args and error.args[0]==1062: raise HTTPException(409, 'Ya existe ese código para este restaurante.') from None
            raise

    @app.patch('/gestion/restaurantes/{restaurant_id}/promociones/{promotion_id}/desactivar', status_code=204)
    def disable_promotion(restaurant_id: int, promotion_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede gestionar promociones.')
            cursor.execute('UPDATE restaurant_promotions SET active=0 WHERE id=%s AND restaurant_id=%s AND active=1', (promotion_id,restaurant_id))
            if not cursor.rowcount: raise HTTPException(404, 'Promoción activa no encontrada.')
        return Response(status_code=204)

    @app.get('/restaurantes/{restaurant_id}/eventos', response_model=list[RestaurantEventOutput])
    def public_events(restaurant_id: int, db: DB):
        with db.cursor() as cursor:
            cursor.execute('''SELECT e.id,e.title,e.description,e.starts_at,e.ends_at,e.active FROM restaurant_events e
                JOIN restaurants r ON r.id=e.restaurant_id AND r.active=1 WHERE e.restaurant_id=%s AND e.active=1 AND e.ends_at>UTC_TIMESTAMP() ORDER BY e.starts_at LIMIT 100''', (restaurant_id,))
            return cursor.fetchall()

    @app.get('/gestion/restaurantes/{restaurant_id}/eventos', response_model=list[RestaurantEventOutput])
    def manage_events(restaurant_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede gestionar eventos.')
            cursor.execute('SELECT id,title,description,starts_at,ends_at,active FROM restaurant_events WHERE restaurant_id=%s ORDER BY starts_at DESC LIMIT 100', (restaurant_id,))
            return cursor.fetchall()

    @app.post('/gestion/restaurantes/{restaurant_id}/eventos', response_model=RestaurantEventOutput, status_code=201)
    def create_event(restaurant_id: int, data: RestaurantEventInput, user: User, db: DB):
        starts=data.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
        ends=data.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
        if ends <= datetime.now(timezone.utc).replace(tzinfo=None): raise HTTPException(422, 'El evento debe terminar en el futuro.')
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede crear eventos.')
            cursor.execute('INSERT INTO restaurant_events (restaurant_id,title,description,starts_at,ends_at,created_by) VALUES (%s,%s,%s,%s,%s,%s)',
                (restaurant_id,data.title,data.description,starts,ends,user['id']))
            return {'id':cursor.lastrowid,'title':data.title,'description':data.description,'starts_at':starts,'ends_at':ends,'active':True}

    @app.patch('/gestion/restaurantes/{restaurant_id}/eventos/{event_id}/desactivar', status_code=204)
    def disable_event(restaurant_id: int, event_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede gestionar eventos.')
            cursor.execute('UPDATE restaurant_events SET active=0 WHERE id=%s AND restaurant_id=%s AND active=1', (event_id,restaurant_id))
            if not cursor.rowcount: raise HTTPException(404, 'Evento activo no encontrado.')
        return Response(status_code=204)

    @app.get('/gestion/restaurantes/{restaurant_id}/finanzas')
    def restaurant_finances(restaurant_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role='owner'", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'Solo el gerente puede consultar finanzas.')
            cursor.execute('''SELECT COUNT(*) AS paid_count,COALESCE(SUM(o.total),0) AS revenue
                FROM payment_confirmations p JOIN orders o ON o.id=p.order_id
                WHERE o.restaurant_id=%s AND o.payment_method='cash' AND o.payment_status='paid' ''', (restaurant_id,))
            summary=cursor.fetchone()
            cursor.execute('''SELECT DATE(DATE_SUB(p.confirmed_at,INTERVAL 5 HOUR)) AS day,
                COUNT(*) AS payments,COALESCE(SUM(o.total),0) AS revenue
                FROM payment_confirmations p JOIN orders o ON o.id=p.order_id
                WHERE o.restaurant_id=%s AND o.payment_method='cash' AND o.payment_status='paid'
                GROUP BY DATE(DATE_SUB(p.confirmed_at,INTERVAL 5 HOUR)) ORDER BY day DESC LIMIT 30''', (restaurant_id,))
            return {'currency':'COP','paid_count':summary['paid_count'],'revenue':int(summary['revenue']),
                'days':[{'day':str(row['day']),'payments':row['payments'],'revenue':int(row['revenue'])} for row in cursor.fetchall()]}

    @app.get('/restaurantes/{restaurant_id}/sucursales/{branch_id}/mesas', response_model=list[PublicTableOutput])
    def public_tables(restaurant_id: int, branch_id: int, db: DB):
        with db.cursor() as cursor:
            cursor.execute('''SELECT t.id,t.table_number,t.capacity FROM restaurant_tables t
                JOIN restaurant_branches b ON b.id=t.branch_id AND b.restaurant_id=t.restaurant_id AND b.active=1
                JOIN restaurants r ON r.id=t.restaurant_id AND r.active=1
                WHERE t.restaurant_id=%s AND t.branch_id=%s ORDER BY t.table_number''', (restaurant_id, branch_id))
            return cursor.fetchall()

    @app.get('/gestion/restaurantes/{restaurant_id}/mesas', response_model=list[RestaurantTableOutput])
    def restaurant_tables(restaurant_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','kitchen','cashier')", (restaurant_id, user['id']))
            if not cursor.fetchone():
                raise HTTPException(403, 'No tienes acceso a este restaurante.')
            cursor.execute('''SELECT t.id,t.branch_id,b.name AS branch_name,t.table_number,t.capacity,
                o.id AS order_id,o.status AS order_status,
                CONCAT(u.nombre,' ',u.apellido) AS customer_name,
                COALESCE(summary.active_orders,0) AS active_orders,
                COALESCE(summary.total_orders,0) AS total_orders,
                COALESCE(summary.total_paid,0) AS total_paid,
                summary.customer_names, reservation.customer_name AS reservation_name
                FROM restaurant_tables t JOIN restaurant_branches b ON b.id=t.branch_id AND b.restaurant_id=t.restaurant_id AND b.active=1
                LEFT JOIN (SELECT o3.restaurant_id,o3.branch_id,o3.table_number,
                    COUNT(*) AS active_orders, SUM(o3.total) AS total_orders,
                    SUM(CASE WHEN o3.payment_status='paid' THEN o3.total ELSE 0 END) AS total_paid,
                    GROUP_CONCAT(DISTINCT CONCAT(u3.nombre,' ',u3.apellido) ORDER BY u3.nombre SEPARATOR ', ') AS customer_names
                    FROM orders o3 JOIN users u3 ON u3.id=o3.customer_id
                    WHERE o3.fulfillment='dine_in' AND o3.status IN ('pending_acceptance','confirmed','preparing','cooked','ready')
                    AND o3.restaurant_id=%s GROUP BY o3.restaurant_id,o3.branch_id,o3.table_number) summary
                    ON summary.restaurant_id=t.restaurant_id AND summary.branch_id=t.branch_id AND summary.table_number=CAST(t.table_number AS CHAR)
                LEFT JOIN orders o ON o.id=(SELECT MAX(o2.id) FROM orders o2
                    WHERE o2.restaurant_id=t.restaurant_id AND o2.branch_id=t.branch_id
                    AND o2.fulfillment='dine_in' AND o2.table_number=CAST(t.table_number AS CHAR)
                    AND o2.status IN ('pending_acceptance','confirmed','preparing','cooked','ready'))
                LEFT JOIN users u ON u.id=o.customer_id
                LEFT JOIN reservations reservation ON reservation.id=(SELECT MAX(r2.id) FROM reservations r2
                    WHERE r2.table_id=t.id AND r2.restaurant_id=t.restaurant_id AND r2.status='confirmed'
                    AND r2.starts_at<=UTC_TIMESTAMP() AND r2.ends_at>UTC_TIMESTAMP())
                WHERE t.restaurant_id=%s ORDER BY b.name,t.table_number''', (restaurant_id,restaurant_id))
            return cursor.fetchall()

    @app.get('/gestion/restaurantes/{restaurant_id}/reservas', response_model=list[ReservationOutput])
    def list_reservations(restaurant_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','cashier')", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'No tienes acceso a reservas.')
            cursor.execute('''SELECT r.id,r.table_id,t.table_number,r.customer_name,r.party_size,r.starts_at,r.ends_at,r.status
                FROM reservations r JOIN restaurant_tables t ON t.id=r.table_id AND t.restaurant_id=r.restaurant_id
                WHERE r.restaurant_id=%s ORDER BY r.starts_at DESC LIMIT 200''', (restaurant_id,))
            return cursor.fetchall()

    def save_reservation(restaurant_id: int, data: ReservationInput, user: dict, db, staff_only: bool):
        starts = data.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
        ends = data.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
        if starts <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(422, 'Selecciona un horario futuro.')
        db.begin()
        try:
            with db.cursor() as cursor:
                if staff_only:
                    cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','cashier')", (restaurant_id,user['id']))
                    if not cursor.fetchone(): raise HTTPException(403, 'No tienes permiso para crear reservas.')
                cursor.execute('''SELECT t.id,t.table_number,t.capacity FROM restaurant_tables t
                    JOIN restaurant_branches b ON b.id=t.branch_id AND b.restaurant_id=t.restaurant_id AND b.active=1
                    JOIN restaurants r ON r.id=t.restaurant_id AND r.active=1
                    WHERE t.id=%s AND t.restaurant_id=%s FOR UPDATE''', (data.table_id,restaurant_id))
                table = cursor.fetchone()
                if not table: raise HTTPException(404, 'Mesa no encontrada.')
                if data.party_size > table['capacity']: raise HTTPException(422, 'La mesa no tiene capacidad para ese grupo.')
                cursor.execute("SELECT id FROM reservations WHERE table_id=%s AND status='confirmed' AND starts_at < %s AND ends_at > %s LIMIT 1", (data.table_id,ends,starts))
                if cursor.fetchone(): raise HTTPException(409, 'La mesa ya tiene una reserva para ese horario.')
                cursor.execute('INSERT INTO reservations (restaurant_id,table_id,customer_name,party_size,starts_at,ends_at,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)', (restaurant_id,data.table_id,data.customer_name,data.party_size,starts,ends,user['id']))
                result = {'id':cursor.lastrowid,'table_id':data.table_id,'table_number':table['table_number'],'customer_name':data.customer_name,'party_size':data.party_size,'starts_at':starts,'ends_at':ends,'status':'confirmed'}
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

    @app.post('/gestion/restaurantes/{restaurant_id}/reservas', response_model=ReservationOutput, status_code=201)
    def create_reservation(restaurant_id: int, data: ReservationInput, user: User, db: DB):
        return save_reservation(restaurant_id,data,user,db,True)

    @app.post('/restaurantes/{restaurant_id}/reservas', response_model=ReservationOutput, status_code=201)
    def create_customer_reservation(restaurant_id: int, data: CustomerReservationInput, user: User, db: DB):
        if user['rol'] != 'customer': raise HTTPException(403, 'Necesitas una cuenta de cliente para reservar.')
        reservation = ReservationInput(**data.model_dump(), customer_name=f"{user['nombre']} {user['apellido']}")
        return save_reservation(restaurant_id,reservation,user,db,False)

    @app.get('/mis-reservas', response_model=list[ReservationOutput])
    def my_reservations(user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute('''SELECT r.id,r.table_id,t.table_number,r.customer_name,r.party_size,r.starts_at,r.ends_at,r.status
                FROM reservations r JOIN restaurant_tables t ON t.id=r.table_id AND t.restaurant_id=r.restaurant_id
                WHERE r.created_by=%s ORDER BY r.starts_at DESC LIMIT 100''', (user['id'],))
            return cursor.fetchall()

    @app.patch('/gestion/restaurantes/{restaurant_id}/reservas/{reservation_id}/cancelar', status_code=204)
    def cancel_reservation(restaurant_id: int, reservation_id: int, user: User, db: DB):
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','cashier')", (restaurant_id,user['id']))
            if not cursor.fetchone(): raise HTTPException(403, 'No tienes permiso para cancelar reservas.')
            cursor.execute("UPDATE reservations SET status='cancelled' WHERE id=%s AND restaurant_id=%s AND status='confirmed'", (reservation_id,restaurant_id))
            if not cursor.rowcount: raise HTTPException(404, 'Reserva activa no encontrada.')
        return Response(status_code=204)

    @app.patch('/gestion/restaurantes/{restaurant_id}/pedidos/{order_id}/pago', response_model=OrderOutput)
    def confirm_cash_payment(restaurant_id: int, order_id: int, user: User, db: DB):
        db.begin()
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','cashier')", (restaurant_id,user['id']))
                if not cursor.fetchone(): raise HTTPException(403, 'No tienes permiso para confirmar pagos.')
                cursor.execute('SELECT * FROM orders WHERE id=%s AND restaurant_id=%s FOR UPDATE', (order_id,restaurant_id))
                order = cursor.fetchone()
                if not order: raise HTTPException(404, 'Pedido no encontrado.')
                if order['payment_method'] != 'cash': raise HTTPException(409, 'Solo se pueden confirmar pagos en efectivo.')
                if order['payment_status'] == 'pending':
                    cursor.execute("UPDATE orders SET payment_status='paid' WHERE id=%s AND restaurant_id=%s", (order_id,restaurant_id))
                    cursor.execute('INSERT INTO payment_confirmations (order_id,actor_id) VALUES (%s,%s)', (order_id,user['id']))
                    order['payment_status'] = 'paid'
                elif order['payment_status'] != 'paid': raise HTTPException(409, 'Estado de pago no permitido.')
            db.commit()
            return order
        except Exception:
            db.rollback()
            raise

    @app.get('/gestion/restaurantes/{restaurant_id}/pedidos', response_model=list[KitchenOrderOutput])
    def restaurant_orders(restaurant_id: int, user: User, db: DB,
                          limit: Annotated[int, Query(ge=1, le=100)] = 50):
        _require_orders()
        with db.cursor() as cursor:
            cursor.execute("SELECT role FROM restaurant_memberships WHERE restaurant_id=%s AND user_id=%s AND active=1 AND role IN ('owner','kitchen','cashier')", (restaurant_id, user['id']))
            if not cursor.fetchone():
                raise HTTPException(403, 'No tienes acceso a este restaurante.')
            cursor.execute('''SELECT o.*,d.code AS discount_code,COALESCE(d.discount,0) AS discount_amount,d.subtotal
                FROM orders o LEFT JOIN order_discounts d ON d.order_id=o.id
                WHERE o.restaurant_id=%s ORDER BY o.id DESC LIMIT %s''', (restaurant_id, limit))
            orders = cursor.fetchall()
            if orders:
                placeholders = ','.join(['%s'] * len(orders))
                cursor.execute(f'SELECT id, order_id, product_name, quantity, unit_price FROM order_items WHERE order_id IN ({placeholders}) ORDER BY id',
                               tuple(order['id'] for order in orders))
                grouped = {order['id']: [] for order in orders}
                rows = cursor.fetchall()
                item_groups = {item['id']: item for item in rows}
                for item in rows:
                    item['additions'] = []
                    grouped[item['order_id']].append(item)
                if item_groups:
                    marks = ','.join(['%s'] * len(item_groups))
                    cursor.execute(f'SELECT order_item_id,product_name,quantity,unit_price FROM order_item_additions WHERE order_item_id IN ({marks}) ORDER BY id', tuple(item_groups))
                    for addition in cursor.fetchall():
                        item_groups[addition['order_item_id']]['additions'].append(addition)
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
