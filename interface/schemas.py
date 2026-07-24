from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

class EventPayload(BaseModel):
    """Modelo de evento recebido pelos endpoints."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=64)
    paciente_id: str | None = Field(None)
    cama_id: str | None = Field(None)
    postura: str = Field(..., min_length=1, max_length=64)
    confianca: float = Field(..., ge=0.0, le=1.0)
    amostra_ms: int = Field(..., gt=0)
    ts_utc: datetime
    pressao_pico: float | None = Field(default=None)

    @field_validator("ts_utc")
    @classmethod
    def _normalizar_ts(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0)


class RotinaConfig(BaseModel):
    label: str
    inicio: str
    duracao_min: int
    descricao: str | None = None
    ativo: bool
    sort_order: int


class PacienteConfigResponse(BaseModel):
    paciente_id: str
    nome: str | None = None
    cama_id: str
    perfil: str
    observacoes: str | None = None
    updated_at: str | None = None
    rotinas: List[RotinaConfig]


class ApiResponse(BaseModel):
    code: str
    message: str
    ids: dict[str, Any]


class FrontendCreatePatient(BaseModel):
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    repositioningInterval: int | None = None
    notes: str | None = None


class FrontendPatient(BaseModel):
    id: str
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    repositioningInterval: int | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class DeviceRegisterRequest(BaseModel):
    device_id: str
    meta: dict | None = None


class BatchAlertRequest(BaseModel):
    """Request body for batch alert operations."""
    alert_ids: List[str]


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
