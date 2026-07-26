"""Consulta da trilha de auditoria.

Uma trilha que nao se consegue consultar nao cumpre a finalidade: a LGPD exige
poder responder "quem acessou os dados deste titular?" (Art. 18, e Art. 48 na
comunicacao de incidente). Restrito a admin — a propria trilha revela padroes
de acesso e identificadores de pacientes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from interface.api_shared import _check_api_rate_limit
from interface.dependencies import exigir_papel

router = APIRouter(
    tags=["auditoria"],
    dependencies=[Depends(exigir_papel("admin")), Depends(_check_api_rate_limit)],
)


def _db() -> str:
    from interface.api_shared import DB_PATH

    return DB_PATH


@router.get("/auditoria", status_code=status.HTTP_200_OK)
def consultar_auditoria(
    response: Response,
    paciente_id: str | None = Query(None, description="Quem acessou este paciente"),
    usuario: str | None = Query(None, description="O que este usuario fez"),
    apenas_negados: bool = Query(False, description="Somente tentativas recusadas (401/403)"),
    desde_ms: int | None = Query(None),
    ate_ms: int | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """Consulta a trilha.

    Cabecalho `X-Total-Count`: quantas entradas casam com os filtros, antes do
    corte por `limit`. Numa trilha usada para responder "quem acessou os dados
    deste titular?" (LGPD Art. 18), uma resposta cortada em silencio produz
    resposta INCOMPLETA a uma pergunta legal — e nada na resposta indicava que
    havia mais.
    """
    from interface.repositories.auditoria import consultar, contar

    filtros = {
        "paciente_id": paciente_id,
        "usuario": usuario,
        "apenas_negados": apenas_negados,
        "desde_ms": desde_ms,
        "ate_ms": ate_ms,
    }
    response.headers["X-Total-Count"] = str(contar(_db(), **filtros))
    return consultar(_db(), limit=limit, offset=offset, **filtros)


@router.post("/auditoria/expurgar", status_code=status.HTTP_200_OK)
def expurgar_auditoria(
    antes_de_ms: int = Query(
        ...,
        description="Remove entradas anteriores a este instante (epoch ms, UTC)",
    ),
    confirmar: bool = Query(
        False,
        description="Precisa ser true para executar; sem isto responde apenas a previa",
    ),
) -> dict:
    """Expurga entradas antigas da trilha, conforme a politica de retencao.

    `expurgar_anteriores_a` existia pronto e sem NENHUMA forma de ser
    executado: nao havia endpoint, comando nem agendamento. A propria docstring
    dele diz que o expurgo deve ser "uma operacao explicita, e nao um expurgo
    automatico com prazo arbitrario" — mas explicito sem interface e apenas
    inalcancavel. Este endpoint e a interface que faltava.

    `confirmar=false` (o padrao) devolve so a PREVIA: quantas entradas sairiam.
    Apagar trilha de auditoria e irreversivel e destroi registro de acesso a
    dado clinico; exigir um segundo passo deliberado evita que um parametro
    errado numa URL leve anos de trilha junto.

    Para retencao continua, ver AUDITORIA_RETENCAO_DIAS
    (interface/lifespan_tasks.py), que agenda o mesmo expurgo diariamente.
    """
    from interface.repositories.auditoria import contar, expurgar_anteriores_a

    afetadas = contar(_db(), ate_ms=int(antes_de_ms) - 1)
    if not confirmar:
        return {"ok": True, "executado": False, "seriam_removidas": afetadas}

    removidas = expurgar_anteriores_a(_db(), int(antes_de_ms))
    return {"ok": True, "executado": True, "removidas": removidas}


@router.get("/auditoria/integridade", status_code=status.HTTP_200_OK)
def verificar_integridade_endpoint(
    limit: int | None = Query(None, description="Verifica apenas as N entradas mais recentes"),
) -> dict:
    """A trilha foi adulterada?

    Uma trilha de auditoria que ninguem consegue verificar tem o mesmo valor
    probatorio de nao existir: quem a apresenta como evidencia precisa poder
    demonstrar que ela nao foi editada depois do fato.

    `integra: false` distingue conteudo alterado (alguem editou um registro) de
    elo quebrado (alguem apagou, inseriu ou reordenou linhas), e aponta o `id`
    de cada ocorrencia.
    """
    from interface.repositories.auditoria import verificar_integridade

    return verificar_integridade(_db(), limit)
