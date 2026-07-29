from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List
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


# Valores aceitos para o perfil de risco. O frontend fala em ingles
# (high/medium/low) e o banco guarda em portugues (alto/medio/baixo); os dois
# vocabularios sao aceitos na entrada.
RISK_LEVELS_VALIDOS = frozenset({"high", "medium", "low", "alto", "medio", "baixo"})


class FrontendCreatePatient(BaseModel):
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    # Aceito por compatibilidade com clientes antigos, mas IGNORADO: o intervalo
    # e derivado do perfil de risco (ver paciente_service.intervalo_horas), que
    # e a mesma fonte usada pelo motor de alertas. Antes o formulario deixava
    # editar este numero, mandava para o backend e o valor era descartado sem
    # aviso — a pessoa achava ter mudado o protocolo do paciente e nao mudara
    # nada.
    repositioningInterval: float | None = None
    notes: str | None = None
    # Em qual ala o paciente esta sendo admitido. Ausente = unidade padrao, para
    # o cliente antigo (e a instalacao de uma ala so) continuar funcionando sem
    # mudanca. E ignorado no PATCH: mudar de ala e transferencia, nao edicao de
    # formulario.
    unitId: int | None = None

    @field_validator("riskLevel")
    @classmethod
    def validar_risco(cls, v: str) -> str:
        """Rejeita perfil de risco desconhecido.

        O service fazia `risk_map.get(valor, "medio")`: qualquer coisa que nao
        estivesse no mapa — um typo, "critical", "alta" — virava MEDIO em
        silencio. E um parametro clinico: ele define a janela de
        reposicionamento (2h para alto risco, 3h para medio), entao o efeito
        pratico era rebaixar o paciente de categoria sem ninguem perceber.
        """
        if str(v).lower() not in RISK_LEVELS_VALIDOS:
            aceitos = ", ".join(sorted(RISK_LEVELS_VALIDOS))
            raise ValueError(f"riskLevel invalido: {v!r}. Valores aceitos: {aceitos}.")
        return v


class FrontendPatient(BaseModel):
    id: str
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    # float: com a janela do motor, o perfil medio da 1.5h — um int truncaria
    # para 1h e a tela voltaria a divergir do comportamento real.
    repositioningInterval: float | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    unitId: int | None = None


class DeviceRegisterRequest(BaseModel):
    device_id: str
    meta: dict | None = None


class BatchAlertRequest(BaseModel):
    """Request body for batch alert operations."""
    alert_ids: List[str]
    # Por que o alerta foi fechado. Ignorado em `acknowledge`, que so registra
    # que alguem VIU. Ausente vale como `reposicionado`, o caso comum — ver
    # `MotivoFechamento`.
    motivo: str | None = None


class MotivoFechamento(BaseModel):
    """Justificativa de fechamento de alerta.

    Concluir nao recebia justificativa nenhuma: o dialogo era sim/nao. Entao
    "reposicionei o paciente", "estava em cirurgia", "o paciente recusou",
    "contraindicado por retalho na regiao sacral" e "falso alarme, o sensor
    deslocou" viravam exatamente a mesma linha — e cada um e um fato clinico
    diferente, que pede acao diferente.

    O default e `reposicionado`, o caso comum: exigir escolha explicita em toda
    conclusao adicionaria atrito na acao mais frequente da ala, e atrito na
    acao frequente e o que faz a equipe procurar o atalho. Quem faz o comum nao
    escolhe nada; a excecao e que precisa ser dita.
    """

    motivo: str | None = None
    observacao: str | None = Field(None, max_length=255)


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
