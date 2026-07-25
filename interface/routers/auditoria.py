"""Consulta da trilha de auditoria.

Uma trilha que nao se consegue consultar nao cumpre a finalidade: a LGPD exige
poder responder "quem acessou os dados deste titular?" (Art. 18, e Art. 48 na
comunicacao de incidente). Restrito a admin — a propria trilha revela padroes
de acesso e identificadores de pacientes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from interface.dependencies import exigir_papel

router = APIRouter(tags=["auditoria"], dependencies=[Depends(exigir_papel("admin"))])


def _db() -> str:
    from interface.api_shared import DB_PATH

    return DB_PATH


@router.get("/auditoria", status_code=status.HTTP_200_OK)
def consultar_auditoria(
    paciente_id: str | None = Query(None, description="Quem acessou este paciente"),
    usuario: str | None = Query(None, description="O que este usuario fez"),
    apenas_negados: bool = Query(False, description="Somente tentativas recusadas (401/403)"),
    desde_ms: int | None = Query(None),
    ate_ms: int | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    from interface.repositories.auditoria import consultar

    return consultar(
        _db(),
        paciente_id=paciente_id,
        usuario=usuario,
        apenas_negados=apenas_negados,
        desde_ms=desde_ms,
        ate_ms=ate_ms,
        limit=limit,
        offset=offset,
    )
