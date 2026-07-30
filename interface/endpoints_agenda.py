"""
Endpoints de API para Sistema de Agenda/Schedule.

Gerencia agendas de supressão de alertas.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

from fastapi import APIRouter, Depends, HTTPException, status, Query

from interface.dependencies import get_current_user

from interface.dao_agenda import (
    ensure_agendas_table,
    criar_agenda as dao_criar_agenda,
    obter_agenda as dao_obter_agenda,
    listar_agendas as dao_listar_agendas,
    atualizar_agenda as dao_atualizar_agenda,
    deletar_agenda as dao_deletar_agenda,
    is_timestamp_in_suppressed_period,
)

import structlog
import os

logger = structlog.get_logger(__name__)
DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

# Garantir que tabela existe
ensure_agendas_table(DB_PATH)

# Agendas sao vinculadas a um paciente e definem quando alertas ficam
# suprimidos — quem altera isso muda o cuidado prestado. Exige sessao.
router = APIRouter(tags=["agenda"], dependencies=[Depends(get_current_user)])


# ============================================================================
# Models Pydantic
# ============================================================================

_TIPOS = ("refeicao", "cirurgia", "procedimento", "atendimento", "outro")
_MODOS = ("suprimir", "reduzir", "monitorar")


def _validar_hora(v: str | None) -> str | None:
    """Exige HH:MM.

    O casamento da agenda faz `strptime(hora, "%H:%M")`. Um valor fora desse
    formato virava exceção lá no fundo do motor, onde o `except` de fail-safe
    apenas registra um warning e mantém o alerta: a agenda ficava cadastrada,
    visível na tela e sem efeito nenhum. Falhar aqui, no cadastro, é a única
    forma de quem digitou ficar sabendo.
    """
    if v is None:
        return v
    try:
        datetime.strptime(v.strip(), "%H:%M")
    except (ValueError, AttributeError):
        raise ValueError(f"hora deve estar no formato HH:MM (recebido: {v!r})") from None
    return v.strip()


def _validar_dias(v: list[int] | None) -> list[int] | None:
    """0=segunda .. 6=domingo, como `date.weekday()`."""
    if v is None:
        return v
    fora = [d for d in v if not 0 <= d <= 6]
    if fora:
        raise ValueError(f"dias_semana aceita 0-6 (Seg-Dom); invalidos: {fora}")
    return v


class AgendaCreate(BaseModel):
    """Criação de agenda."""
    tipo: str = Field(..., min_length=1, max_length=50)
    descricao: str | None = Field(None, max_length=255)
    dias_semana: list[int] | None = Field(None, description="[0-6] para Seg-Dom")
    hora_inicio: str = Field("00:00")
    hora_fim: str = Field("23:59")
    data_inicio: str | None = Field(None, description="YYYY-MM-DD")
    data_fim: str | None = Field(None, description="YYYY-MM-DD")
    modo: str = Field("suprimir", description="suprimir|reduzir|monitorar")
    reducao_janela_min: int | None = Field(None, ge=5, le=60)
    
    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v):
        if v not in _TIPOS:
            raise ValueError(f"tipo deve ser um de: {_TIPOS}")
        return v

    @field_validator("modo")
    @classmethod
    def validate_modo(cls, v):
        if v not in _MODOS:
            raise ValueError(f"modo deve ser um de: {_MODOS}")
        return v

    _horas = field_validator("hora_inicio", "hora_fim")(_validar_hora)
    _dias = field_validator("dias_semana")(_validar_dias)

    @model_validator(mode="after")
    def exigir_recorrencia_ou_data(self):
        """Uma agenda precisa dizer QUANDO vale, alem da hora.

        Os dois campos sao opcionais isoladamente porque sao alternativas
        (recorrente por dia da semana OU pontual por data), mas nenhum dos dois
        preenchidos nao e "vale sempre": `_timestamp_matches_agenda` cai no ramo
        da data pontual e faz `datetime.fromisoformat(None)`. A agenda ficaria
        cadastrada, visivel na tela, e nunca suprimiria nada — o mesmo modo de
        falha que este arquivo ja documenta ter corrigido antes.

        A tela sempre manda `data_inicio` (o formulario a marca obrigatoria),
        entao isto fecha a porta da API, nao a do usuario.
        """
        if not self.dias_semana and not self.data_inicio:
            raise ValueError(
                "informe dias_semana (recorrente) ou data_inicio (pontual);"
                " sem um dos dois a agenda nunca casaria com nenhum horario"
            )
        return self


class AgendaUpdate(BaseModel):
    """Atualização de agenda (campos opcionais).

    Os mesmos validadores do cadastro: sem eles dava para criar uma agenda
    valida e depois deixa-la inerte por um PATCH — `modo="supprimir"` (com o
    erro de digitacao) e aceito, nao casa com nenhum modo conhecido e a
    supressao simplesmente para de acontecer, sem erro em lugar nenhum.
    """
    tipo: str | None = None
    descricao: str | None = None
    dias_semana: list[int] | None = None
    hora_inicio: str | None = None
    hora_fim: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    modo: str | None = None
    reducao_janela_min: int | None = None
    ativo: bool | None = None

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v):
        if v is not None and v not in _TIPOS:
            raise ValueError(f"tipo deve ser um de: {_TIPOS}")
        return v

    @field_validator("modo")
    @classmethod
    def validate_modo(cls, v):
        if v is not None and v not in _MODOS:
            raise ValueError(f"modo deve ser um de: {_MODOS}")
        return v

    _horas = field_validator("hora_inicio", "hora_fim")(_validar_hora)
    _dias = field_validator("dias_semana")(_validar_dias)


class AgendaResponse(BaseModel):
    """Resposta de agenda."""
    id: int
    paciente_id: str
    tipo: str
    descricao: str | None
    dias_semana: list[int] | None
    hora_inicio: str
    hora_fim: str
    data_inicio: str | None
    data_fim: str | None
    modo: str
    reducao_janela_min: int | None
    ativo: bool
    created_at: str
    updated_at: str


class SuppressionCheckResponse(BaseModel):
    """Resposta da verificação de supressão."""
    em_periodo_suprimido: bool
    modo_resultado: str | None
    agendas_ativas: list[dict]


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/pacientes/{paciente_id}/agenda",
    status_code=status.HTTP_201_CREATED,
    response_model=AgendaResponse
)
def criar_agenda(paciente_id: str, payload: AgendaCreate) -> AgendaResponse:
    """Cria uma nova agenda de supressão."""
    try:
        agenda = dao_criar_agenda(
            DB_PATH,
            paciente_id,
            tipo=payload.tipo,
            descricao=payload.descricao,
            dias_semana=payload.dias_semana,
            hora_inicio=payload.hora_inicio,
            hora_fim=payload.hora_fim,
            data_inicio=payload.data_inicio,
            data_fim=payload.data_fim,
            modo=payload.modo,
            reducao_janela_min=payload.reducao_janela_min,
        )
        logger.info("agenda_criada", paciente_id=paciente_id, tipo=payload.tipo)
        return AgendaResponse(**agenda)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_agenda", "message": str(e)}
        ) from e
    except LookupError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "paciente_nao_encontrado", "message": str(e)}
        ) from e
    except Exception as e:
        logger.error("agenda_criar_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


@router.get(
    "/pacientes/{paciente_id}/agenda",
    response_model=list[AgendaResponse]
)
def listar_agendas(
    paciente_id: str,
    ativo: bool = Query(True, description="Apenas agendas ativas")
) -> list[AgendaResponse]:
    """Lista agendas de um paciente."""
    try:
        agendas = dao_listar_agendas(DB_PATH, paciente_id, ativo_only=ativo)
        return [AgendaResponse(**a) for a in agendas]
    except Exception as e:
        logger.error("agenda_listar_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


# IMPORTANTE: esta rota precisa vir ANTES de /agenda/{agenda_id}. O FastAPI
# casa na ordem de declaracao; se a rota com {agenda_id:int} vier primeiro,
# "check" e interpretado como agenda_id e a requisicao morre com 422.
@router.get(
    "/pacientes/{paciente_id}/agenda/check",
    response_model=SuppressionCheckResponse
)
def verificar_supressao(
    paciente_id: str,
    timestamp: str = Query(..., description="ISO format timestamp YYYY-MM-DDTHH:MM:SS")
) -> SuppressionCheckResponse:
    """
    Verifica se um timestamp está em período suprimido.

    Query Params:
        timestamp: ISO format (ex: 2025-10-27T12:30:00)
    """
    try:
        ts = datetime.fromisoformat(timestamp[:19])

        is_suppressed, modo = is_timestamp_in_suppressed_period(DB_PATH, paciente_id, ts)

        # Buscar agendas ativas nesse timestamp para detalhe
        agendas = dao_listar_agendas(DB_PATH, paciente_id, ativo_only=True)
        agendas_ativas = []

        for agenda in agendas:
            from interface.dao_agenda import _timestamp_matches_agenda
            if _timestamp_matches_agenda(ts, agenda):
                agendas_ativas.append({
                    "id": agenda["id"],
                    "tipo": agenda["tipo"],
                    "descricao": agenda["descricao"],
                    "hora_inicio": agenda["hora_inicio"],
                    "hora_fim": agenda["hora_fim"],
                    "modo": agenda["modo"],
                })

        return SuppressionCheckResponse(
            em_periodo_suprimido=is_suppressed,
            modo_resultado=modo,
            agendas_ativas=agendas_ativas
        )
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_timestamp", "message": f"Timestamp inválido: {e!s}"}
        ) from e
    except Exception as e:
        logger.error("agenda_verificar_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


@router.get(
    "/pacientes/{paciente_id}/agenda/{agenda_id}",
    response_model=AgendaResponse
)
def obter_agenda(paciente_id: str, agenda_id: int) -> AgendaResponse:
    """Obtém uma agenda específica."""
    try:
        agenda = dao_obter_agenda(DB_PATH, paciente_id, agenda_id)
        return AgendaResponse(**agenda)
    except LookupError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "agenda_nao_encontrada", "message": f"Agenda {agenda_id} não encontrada"},
        ) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("agenda_obter_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


@router.patch(
    "/pacientes/{paciente_id}/agenda/{agenda_id}",
    response_model=AgendaResponse
)
def atualizar_agenda(
    paciente_id: str,
    agenda_id: int,
    payload: AgendaUpdate
) -> AgendaResponse:
    """Atualiza uma agenda."""
    try:
        # Converter para dict, removendo None
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        
        if not updates:
            return AgendaResponse(**dao_obter_agenda(DB_PATH, paciente_id, agenda_id))
        
        agenda = dao_atualizar_agenda(DB_PATH, paciente_id, agenda_id, **updates)
        logger.info("agenda_atualizada", paciente_id=paciente_id, agenda_id=agenda_id)
        return AgendaResponse(**agenda)
    except LookupError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "agenda_nao_encontrada", "message": f"Agenda {agenda_id} não encontrada"},
        ) from None
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_agenda", "message": str(e)}
        ) from e
    except Exception as e:
        logger.error("agenda_atualizar_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


@router.delete(
    "/pacientes/{paciente_id}/agenda/{agenda_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def deletar_agenda(paciente_id: str, agenda_id: int):
    """Deleta uma agenda."""
    try:
        deleted = dao_deletar_agenda(DB_PATH, paciente_id, agenda_id)
        if not deleted:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "agenda_nao_encontrada", "message": f"Agenda {agenda_id} não encontrada"}
            )
        logger.info("agenda_deletada", paciente_id=paciente_id, agenda_id=agenda_id)
    except HTTPException:
        # O 404 acima e lancado DENTRO do try; sem isto o except generico
        # abaixo o recapturava e devolvia 500 para uma agenda inexistente.
        raise
    except Exception as e:
        logger.error("agenda_deletar_erro", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "agenda_error", "message": "Erro interno ao processar a requisicao."}
        ) from e


