"""Lesao por pressao: registro, evolucao e o indicador que fecha o ciclo.

O sistema media adesao ao reposicionamento e nunca registrava se a lesao
aconteceu. Media o processo e ignorava o resultado.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from interface.api_shared import _check_api_rate_limit
from interface.dependencies import escopo_de_unidades, get_current_user
from interface.repositories import lesoes as repo

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["lesoes"],
    dependencies=[Depends(get_current_user), Depends(_check_api_rate_limit)],
)


def _db() -> str:
    """Caminho do banco resolvido POR CHAMADA, e nao um `DB_PATH` de import.

    O padrao usado nos routers antigos (`DB_PATH` importado no topo) congela o
    caminho no momento do import. Os testes trocam de banco por arquivo, entao o
    router passava a apontar para o banco de OUTRO teste — e o sintoma nao era
    erro de configuracao, era `no such table: lesoes`, num arquivo que passava
    sozinho e quebrava na suite. Ver a mesma nota em `routers/usuarios.py`.
    """
    from interface.api_shared import DB_PATH

    return DB_PATH


class LesaoCreate(BaseModel):
    sitio: str
    # Sem default, e o motivo nao e tecnico: uma lesao que o paciente TROUXE e
    # prevalencia na admissao, nao falha do cuidado desta unidade; uma que
    # apareceu aqui e incidencia. Um default decidiria essa pergunta por quem
    # registra, e ela e a que separa o que pode ser atribuido ao cuidado do que
    # nao pode.
    origem: str = Field(..., description="presente_na_admissao | adquirida")
    estagio: str = Field(..., description="estagio_1..4 | nao_classificavel | ...")
    identificada_em: str | None = None
    observacoes: str | None = Field(None, max_length=1000)
    comprimento_cm: float | None = Field(None, ge=0, le=100)
    largura_cm: float | None = Field(None, ge=0, le=100)


class AvaliacaoCreate(BaseModel):
    estagio: str
    comprimento_cm: float | None = Field(None, ge=0, le=100)
    largura_cm: float | None = Field(None, ge=0, le=100)
    observacoes: str | None = Field(None, max_length=1000)
    quando: str | None = None


class FecharLesao(BaseModel):
    desfecho: str = Field(
        ..., description="cicatrizada | alta_com_lesao | obito | erro_de_registro"
    )


@router.get("/lesoes/vocabulario", status_code=status.HTTP_200_OK)
def vocabulario() -> dict:
    """Sitios, origens, estagios e desfechos aceitos.

    Existe para a tela montar os seletores a partir do SERVIDOR. Uma copia da
    lista no JavaScript e o comeco de duas listas divergentes — e ja aconteceu
    neste projeto com o intervalo por perfil de risco, onde o motor usava
    60/90/120 min e a tela dizia 2/3/4 h, o dobro.
    """
    return {
        "sitios": sorted(repo.SITIOS_VALIDOS),
        "origens": sorted(repo.ORIGENS_VALIDAS),
        "estagios": sorted(repo.ESTAGIOS_VALIDOS),
        "desfechos": sorted(repo.DESFECHOS_VALIDOS),
    }


@router.get("/lesoes/indicadores", status_code=status.HTTP_200_OK)
def indicadores(
    horas: int = 720,
    unidades: set[int] | None = Depends(escopo_de_unidades),
) -> dict:
    """Incidencia de LPP por 1000 paciente-dia, na janela.

    O denominador e paciente-DIA, nao numero de pacientes: uma ala com 10
    pacientes por 30 dias e uma com 300 por 1 dia tem o mesmo paciente-dia e
    riscos completamente diferentes se comparadas por cabeca.
    """
    return repo.indicadores(_db(), horas=horas, unidades=unidades)


@router.get("/pacientes/{paciente_id}/lesoes", status_code=status.HTTP_200_OK)
def listar_lesoes(paciente_id: str) -> list[dict]:
    return repo.listar_do_paciente(_db(), paciente_id)


@router.post(
    "/pacientes/{paciente_id}/lesoes", status_code=status.HTTP_201_CREATED
)
def registrar_lesao(
    paciente_id: str, payload: LesaoCreate, usuario: str = Depends(get_current_user)
) -> dict:
    try:
        return repo.registrar(
            _db(),
            paciente_id,
            sitio=payload.sitio,
            origem=payload.origem,
            estagio=payload.estagio,
            identificada_em=payload.identificada_em,
            usuario=usuario,
            observacoes=payload.observacoes,
            comprimento_cm=payload.comprimento_cm,
            largura_cm=payload.largura_cm,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "paciente_nao_encontrado", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "lesao_invalida", "message": str(exc)},
        ) from exc


@router.get("/lesoes/{lesao_id}", status_code=status.HTTP_200_OK)
def obter_lesao(lesao_id: int) -> dict:
    lesao = repo.obter(_db(), lesao_id)
    if lesao is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "lesao_nao_encontrada", "message": "Lesao nao encontrada."},
        )
    return lesao


@router.post("/lesoes/{lesao_id}/avaliacoes", status_code=status.HTTP_201_CREATED)
def avaliar_lesao(
    lesao_id: int, payload: AvaliacaoCreate, usuario: str = Depends(get_current_user)
) -> dict:
    """Acrescenta uma avaliacao de estagio.

    Nao sobrescreve a anterior: a TRAJETORIA e o dado clinico. "Estagio 2 que
    cicatrizou em 6 dias" e "estagio 2 que virou 4" nao sao o mesmo desfecho.
    """
    try:
        return repo.avaliar(
            _db(),
            lesao_id,
            estagio=payload.estagio,
            usuario=usuario,
            comprimento_cm=payload.comprimento_cm,
            largura_cm=payload.largura_cm,
            observacoes=payload.observacoes,
            quando=payload.quando,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "lesao_nao_encontrada", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "estagio_invalido", "message": str(exc)},
        ) from exc


@router.post("/lesoes/{lesao_id}/fechamento", status_code=status.HTTP_200_OK)
def fechar_lesao(
    lesao_id: int, payload: FecharLesao, usuario: str = Depends(get_current_user)
) -> dict:
    try:
        return repo.fechar(_db(), lesao_id, payload.desfecho, usuario=usuario)
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "lesao_nao_encontrada", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "desfecho_invalido", "message": str(exc)},
        ) from exc
