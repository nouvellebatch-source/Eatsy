"""Configuración segura para MySQL (Aiven/Render) y JWT."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
# Permite usar el .env existente en Eatsy y permite que api_python/.env
# sobrescriba únicamente los valores propios de la API.
load_dotenv(ROOT.parent / ".env", override=False)
load_dotenv(ROOT / ".env", override=True)


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret: str = field(repr=False)
    token_minutes: int
    issuer: str
    audience: str
    db_host: str
    db_port: int
    db_user: str
    db_password: str = field(repr=False)
    db_name: str = "eatsy"
    db_ssl: bool = True
    db_ssl_ca: Path | None = None
    db_connect_timeout: int = 10
    trusted_proxy_headers: bool = True
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("JWT_SECRET_KEY") or os.environ.get("CLAVE_SECRETA", "")
        if len(secret.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET_KEY debe tener al menos 32 bytes.")
        try:
            token_minutes = int(os.environ.get("ACCESS_TOKEN_MINUTES", os.environ.get("MINUTOS_VALIDEZ", "30")))
            db_port = int(os.environ.get("DB_PORT", "3306"))
            connect_timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "10"))
        except ValueError as error:
            raise RuntimeError("ACCESS_TOKEN_MINUTES, DB_PORT y DB_CONNECT_TIMEOUT deben ser enteros.") from error
        if not 1 <= token_minutes <= 120 or not 1 <= db_port <= 65535 or not 1 <= connect_timeout <= 60:
            raise RuntimeError("Hay valores de configuración fuera de rango.")

        db_host = os.environ.get("DB_HOST", "").strip()
        db_user = os.environ.get("DB_USER", "").strip()
        db_password = os.environ.get("DB_PASSWORD", "")
        db_name = os.environ.get("DB_NAME", "eatsy").strip()
        if not all((db_host, db_user, db_password, db_name)):
            raise RuntimeError("Configura DB_HOST, DB_USER, DB_PASSWORD y DB_NAME para MySQL.")
        issuer = os.environ.get("JWT_ISSUER", "eatsy-api").strip()
        audience = os.environ.get("JWT_AUDIENCE", "eatsy-mobile").strip()
        if not issuer or not audience:
            raise RuntimeError("JWT_ISSUER y JWT_AUDIENCE son obligatorios.")

        ssl_enabled = _as_bool(os.environ.get("DB_SSL", "true"))
        certificate_raw = os.environ.get("DB_SSL_CA", "").strip()
        certificate = None
        if ssl_enabled:
            if not certificate_raw:
                raise RuntimeError("DB_SSL_CA es obligatorio cuando DB_SSL=true.")
            certificate = Path(certificate_raw)
            if not certificate.is_absolute():
                certificate = ROOT / certificate
            if not certificate.is_file():
                raise RuntimeError(f"No se encontró el certificado CA de MySQL: {certificate}")

        return cls(
            secret=secret, token_minutes=token_minutes, issuer=issuer, audience=audience,
            db_host=db_host, db_port=db_port, db_user=db_user, db_password=db_password,
            db_name=db_name, db_ssl=ssl_enabled, db_ssl_ca=certificate,
            db_connect_timeout=connect_timeout,
            trusted_proxy_headers=_as_bool(os.environ.get("TRUSTED_PROXY_HEADERS", "true")),
            cors_origins=tuple(origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()),
        )
