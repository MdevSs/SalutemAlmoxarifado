from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, SecretStr, field_validator


class SectorOption(BaseModel):
    id: int
    name: str
    profile: Literal["solicitante", "almoxarifado", "administrador"]
    leader_name: str | None


class SectorRead(SectorOption):
    active: bool


class SectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile: Literal["solicitante", "almoxarifado"]
    leader_name: str | None = Field(default=None, max_length=120)
    password: SecretStr

    @field_validator("name", "leader_name")
    @classmethod
    def trim_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo não pode ficar vazio.")
        return cleaned


class SectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    leader_name: str | None = Field(default=None, max_length=120)
    active: bool | None = None
    new_password: SecretStr | None = None

    @field_validator("name", "leader_name")
    @classmethod
    def trim_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O nome não pode ficar vazio.")
        return cleaned


class LoginRequest(BaseModel):
    sector_id: int = Field(gt=0)
    password: SecretStr


class CurrentUser(BaseModel):
    sector_id: int
    sector_name: str
    profile: Literal["solicitante", "almoxarifado", "administrador"]
    leader_name: str | None


class AuthResponse(BaseModel):
    user: CurrentUser
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str


class ProductUnitRead(BaseModel):
    code: str
    description: str
    operation: Literal["M", "D"]
    coefficient: Decimal
    result: str
    is_default: bool = False


class ProductRead(BaseModel):
    code: str
    description: str
    stock: Decimal
    deposit: int
    group: str
    default_unit: str
    unit_options: list[ProductUnitRead]


class ProductPage(BaseModel):
    items: list[ProductRead]
    has_more: bool
    offset: int
    limit: int


class RequestItemCreate(BaseModel):
    material_code: str = Field(min_length=1, max_length=16)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=0)
    unit_code: str | None = Field(default=None, min_length=1, max_length=6)

    @field_validator("material_code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        code = value.strip()
        if not code:
            raise ValueError("Código de produto obrigatório.")
        return code

    @field_validator("unit_code")
    @classmethod
    def clean_unit_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not code:
            raise ValueError("Selecione uma unidade de medida.")
        return code


class RequestCreate(BaseModel):
    requested_date: date
    delivery_instructions: str = Field(default="", max_length=4000)
    items: list[RequestItemCreate] = Field(min_length=1, max_length=100)

    @field_validator("requested_date")
    @classmethod
    def prevent_future_date(cls, value: date) -> date:
        if value > datetime.now(ZoneInfo("America/Sao_Paulo")).date():
            raise ValueError("A data da requisição não pode ser futura.")
        return value

    @field_validator("delivery_instructions")
    @classmethod
    def trim_instructions(cls, value: str) -> str:
        return value.strip()


class DeliveryLine(BaseModel):
    item_index: int = Field(ge=1, le=100)
    quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=0)


class FinalizeRequest(BaseModel):
    responsible_name: str = Field(min_length=1, max_length=120)
    warehouse_notes: str = Field(default="", max_length=4000)
    confirm_partial_without_note: bool = False
    deliveries: list[DeliveryLine] = Field(min_length=1, max_length=100)

    @field_validator("responsible_name")
    @classmethod
    def validate_responsible_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe o nome do responsável pela confirmação.")
        return cleaned

    @field_validator("warehouse_notes")
    @classmethod
    def trim_warehouse_notes(cls, value: str) -> str:
        return value.strip()


class NotesUpdate(BaseModel):
    warehouse_notes: str = Field(max_length=4000)

    @field_validator("warehouse_notes")
    @classmethod
    def trim_notes(cls, value: str) -> str:
        return value.strip()


class RequestItemRead(BaseModel):
    item_index: int
    material_code: str
    description: str
    requested_quantity: Decimal
    delivered_quantity: Decimal | None
    requested_unit_quantity: Decimal | None = None
    delivered_unit_quantity: Decimal | None = None
    unit_code: str | None = None
    unit_description: str | None = None
    default_unit: str | None = None
    conversion_result: str | None = None


class RequestRead(BaseModel):
    itecontrol: int
    number: str
    sector_id: int
    sector_name: str
    leader_name: str | None
    requested_date: date
    delivery_instructions: str
    status: str
    warehouse_notes: str
    responsible_name: str | None
    items: list[RequestItemRead]
    events: list[dict[str, Any]]
    erp_status: str
    erp_error: str | None
    created_at: datetime
    finalized_at: datetime | None


class RequestPage(BaseModel):
    items: list[RequestRead]
    total: int
    offset: int
    limit: int
