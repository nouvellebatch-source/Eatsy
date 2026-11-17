from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, SecretStr, model_validator
from uuid import UUID

Role = Literal["admin", "staff", "customer"]


class UserInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    usuario: str = Field(min_length=1, max_length=80)
    contrasena: SecretStr = Field(min_length=1, max_length=128)


class UserRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field(min_length=1, max_length=80)
    usuario: str = Field(min_length=1, max_length=80)
    correo: EmailStr
    contrasena: SecretStr = Field(min_length=12, max_length=128)


class VerifyRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: EmailStr
    codigo: str = Field(pattern=r"^[0-9]{6}$")


class ResendVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: EmailStr


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


class RestaurantOutput(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    image_url: str | None


class BranchOutput(BaseModel):
    id: int
    restaurant_id: int
    name: str
    address: str
    city: str
    latitude: float | None
    longitude: float | None


class MenuProductOutput(BaseModel):
    id: int
    restaurant_id: int
    name: str
    description: str | None
    category: str
    price: int
    currency: str
    image_url: str | None


class OrderAdditionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=20, strict=True)


class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100, strict=True)
    additions: list[OrderAdditionInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_additions(self):
        if len({x.product_id for x in self.additions}) != len(self.additions):
            raise ValueError('No repitas la misma adición.')
        return self


class OrderInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    restaurant_id: int = Field(gt=0)
    branch_id: int = Field(gt=0)
    idempotency_key: UUID
    fulfillment: Literal['delivery', 'pickup', 'dine_in']
    delivery_address: str | None = Field(default=None, max_length=255)
    table_number: str | None = Field(default=None, max_length=30)
    payment_method: Literal['cash']
    customer_note: str | None = Field(default=None, max_length=500)
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def validate_fulfillment(self):
        if self.fulfillment == 'delivery' and not self.delivery_address:
            raise ValueError('La dirección es obligatoria para domicilio.')
        if self.fulfillment == 'dine_in' and not self.table_number:
            raise ValueError('El número de mesa es obligatorio en tienda.')
        return self


class OrderOutput(BaseModel):
    id: int
    restaurant_id: int
    branch_id: int
    fulfillment: str
    payment_method: str
    payment_status: str
    status: str
    total: int
    currency: str


class RestaurantTableOutput(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    table_number: int
    capacity: int
    order_id: int | None = None
    order_status: str | None = None
    customer_name: str | None = None
    customer_names: str | None = None
    active_orders: int = 0
    total_orders: int = 0
    total_paid: int = 0
    reservation_name: str | None = None


class PublicTableOutput(BaseModel):
    id: int
    table_number: int
    capacity: int


class ReservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    table_id: int = Field(gt=0)
    customer_name: str = Field(min_length=1, max_length=160)
    party_size: int = Field(ge=1, le=100, strict=True)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def valid_times(self):
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError('Las fechas deben incluir zona horaria.')
        if self.ends_at <= self.starts_at:
            raise ValueError('La hora final debe ser posterior a la inicial.')
        return self


class ReservationOutput(BaseModel):
    id: int
    table_id: int
    table_number: int
    customer_name: str
    party_size: int
    starts_at: datetime
    ends_at: datetime
    status: str


class CustomerReservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    table_id: int = Field(gt=0)
    party_size: int = Field(ge=1, le=100, strict=True)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def valid_times(self):
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError('Las fechas deben incluir zona horaria.')
        if self.ends_at <= self.starts_at:
            raise ValueError('La hora final debe ser posterior a la inicial.')
        return self


class KitchenOrderItem(BaseModel):
    product_name: str
    quantity: int
    unit_price: int
    additions: list['KitchenAddition'] = Field(default_factory=list)


class KitchenAddition(BaseModel):
    product_name: str
    quantity: int
    unit_price: int


class KitchenOrderOutput(OrderOutput):
    table_number: str | None
    customer_note: str | None
    created_at: datetime
    items: list[KitchenOrderItem]


class OrderTransitionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['confirmed', 'preparing', 'cooked', 'ready', 'delivered']


class OrderEventOutput(BaseModel):
    previous_status: str
    new_status: str
    created_at: datetime
