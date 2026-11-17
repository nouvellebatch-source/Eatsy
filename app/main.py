"""API Eatsy preparada para MySQL en Aiven y despliegue en Render."""
from contextlib import asynccontextmanager
import os
import time
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
from app.schemas import OutputToken, ProductInput, ProductOutput, RequestActivityOutput, UserInput, UserOutput, UserRegistration
from app.security import create_token, password_hasher, read_subject, revoke_token, unauthorized_error, verify_password


bearer = HTTPBearer(auto_error=False)
ProductID = Annotated[int, Path(ge=1, le=10_000_000_000)]


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
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=False,
                           allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                           allow_headers=["Authorization", "Content-Type", "X-Client-Country", "X-Client-City", "X-Client-Latitude", "X-Client-Longitude", "X-Device-Platform"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": [{"loc": list(error["loc"]), "msg": "Valor no válido."} for error in exc.errors()]})

    @app.middleware("http")
    async def audit_response(request: Request, call_next):
        started, request_id = time.perf_counter(), str(uuid4())
        response = await call_next(request)
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

    @app.post("/auth/registro", response_model=UserOutput, status_code=status.HTTP_201_CREATED)
    def register(data: UserRegistration, db: DB):
        password_hash = password_hasher.hash(data.contrasena.get_secret_value())
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (usuario, nombre, apellido, password_hash, rol) VALUES (%s, %s, %s, %s, %s)",
                    (data.usuario, data.nombre, data.apellido, password_hash, "staff"),
                )
                user_id = cursor.lastrowid
        except pymysql.IntegrityError as error:
            if error.args and error.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Ese nombre de usuario ya está registrado.") from None
            raise
        return {"id": user_id, "usuario": data.usuario, "nombre": data.nombre, "apellido": data.apellido, "rol": "staff"}

    @app.post("/auth/login", response_model=OutputToken)
    def login(data: UserInput, db: DB, request: Request):
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE usuario = %s", (data.usuario,))
            user = cursor.fetchone()
        if user is None or not user["activo"] or not verify_password(data.contrasena.get_secret_value(), user["password_hash"]):
            raise unauthorized_error()
        token, issued_at, jti = create_token(user["id"], request.app.state.settings)
        return OutputToken(access_token=token, expires_in=request.app.state.settings.token_minutes * 60,
                           issued_at=issued_at, jti=jti, audience=request.app.state.settings.audience,
                           issuer=request.app.state.settings.issuer, usuario=UserOutput.model_validate(user))

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
