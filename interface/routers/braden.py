"""Escala de Braden: avaliacao, historico e reavaliacao vencida."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from interface.api_shared import _check_api_rate_limit
from interface.dependencies import escopo_de_unidades, get_current_user
from interface.repositories import braden as repo
from nucleo import braden as escala

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["braden"],
    dependencies=[Depends(get_current_user), Depends(_check_api_rate_limit)],
)


def _db() -> str:
    """Caminho do banco por chamada, nao congelado no import.

    Ver a mesma nota em `routers/usuarios.py` e `routers/lesoes.py`: com o import
    no topo, os testes que trocam de banco por arquivo fazem o router apontar
    para o banco de outro teste.
    """
    from interface.api_shared import DB_PATH

    return DB_PATH


class BradenCreate(BaseModel):
    """Os seis subescores. Todos obrigatorios.

    Um Braden com cinco dos seis campos nao e um Braden: o total resultante
    colocaria o paciente numa faixa de risco MAIS LEVE que a real, que e o erro
    que mais importa evitar. Por isso nao ha default em nenhum campo.
    """

    percepcao_sensorial: int = Field(..., ge=1, le=4)
    umidade: int = Field(..., ge=1, le=4)
    atividade: int = Field(..., ge=1, le=4)
    mobilidade: int = Field(..., ge=1, le=4)
    nutricao: int = Field(..., ge=1, le=4)
    # 1 a 3, nao 1 a 4: e assim na escala. Aceitar 4 inflaria o total e poderia
    # rebaixar o paciente de faixa sem ninguem perceber.
    friccao_cisalhamento: int = Field(..., ge=1, le=3)
    observacoes: str | None = Field(None, max_length=1000)
    quando: str | None = None


@router.get("/braden/escala", status_code=status.HTTP_200_OK)
def descrever_escala() -> dict:
    """Subescalas, intervalos, faixas e o mapeamento faixa -> perfil.

    A tela monta o formulario a partir DAQUI, e o mapeamento vem junto para que
    a enfermeira veja qual janela de reposicionamento o escore vai produzir ANTES
    de salvar. Sem isso, a relacao entre o instrumento que ela preenche e o
    comportamento do sistema fica invisivel — que era o estado anterior, com o
    perfil num dropdown e as janelas em variavel de ambiente.
    """
    return {
        "subescalas": {
            nome: {"minimo": minimo, "maximo": maximo}
            for nome, (minimo, maximo) in escala.SUBESCALAS.items()
        },
        "total_minimo": escala.TOTAL_MINIMO,
        "total_maximo": escala.TOTAL_MAXIMO,
        "perfil_por_faixa": escala.PERFIL_POR_FAIXA,
        "reavaliacao_horas": repo.horas_para_reavaliacao(),
    }


@router.get("/braden/pendentes", status_code=status.HTTP_200_OK)
def pendentes(
    horas: int | None = None,
    unidades: set[int] | None = Depends(escopo_de_unidades),
) -> dict:
    """Quem esta com Braden vencido — ou nunca foi avaliado.

    Os dois casos vem separados: vencido e reavaliar; nunca avaliado e um
    paciente que entrou no sistema sem passar pelo instrumento, e o problema
    esta no fluxo de admissao, nao no plantao.
    """
    return repo.reavaliacoes_pendentes(_db(), unidades=unidades, horas=horas)


@router.get("/pacientes/{paciente_id}/braden", status_code=status.HTTP_200_OK)
def listar(paciente_id: str) -> list[dict]:
    return repo.listar_do_paciente(_db(), paciente_id)


@router.post("/pacientes/{paciente_id}/braden", status_code=status.HTTP_201_CREATED)
def registrar(
    paciente_id: str, payload: BradenCreate, usuario: str = Depends(get_current_user)
) -> dict:
    """Registra a avaliacao e APLICA o perfil derivado.

    Aplicar, e nao sugerir: manter as duas classificacoes lado a lado — a do
    dropdown e a de Braden — reproduziria o problema que esta entidade existe
    para resolver.
    """
    subescores = payload.model_dump(exclude={"observacoes", "quando"})
    try:
        return repo.registrar(
            _db(),
            paciente_id,
            subescores,
            usuario=usuario,
            observacoes=payload.observacoes,
            quando=payload.quando,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "paciente_nao_encontrado", "message": str(exc)},
        ) from exc
    except escala.BradenInvalido as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "braden_invalido", "message": str(exc)},
        ) from exc
