from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr

Role = Literal["admin", "staff"]


class UserInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    usuario: str = Field(min_length=1, max_length=80)
    contrasena: SecretStr = Field(min_length=1, max_length=128)


class UserRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field(min_length=1, max_length=80)
    usuario: str = Field(min_length=1, max_length=80)
    contrasena: SecretStr = Field(min_length=12, max_length=128)


class UserOutput(BaseModel):
    id: int
    nombre: str
    apellido: str
    usuario: str
    rol: Role


class OutputToken(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    issued_at: datetime
    jti: str
    audience: str
    issuer: str
    usuario: UserOutput


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(min_length=1, max_length=256)
    precio: int = Field(ge=0, le=10_000_000_000, strict=True)
    stock: int = Field(ge=0, le=10_000_000_000, strict=True)
    categoria: str = Field(min_length=1, max_length=80)
    imagen_url: HttpUrl = Field(max_length=2048)


class ProductOutput(ProductInput):
    id: int


class RequestActivityOutput(BaseModel):
    id: int
    metodo: str
    ruta: str
    status_code: int
    response_time_ms: float
    user_agent: str | None
    device_type: str | None
    device_platform: str | None
    client_country: str | None
    client_city: str | None
    latitude: float | None
    longitude: float | None
    created_at: datetime
