"""Assumir e liberar responsabilidade por um leito.

O dashboard de uma ala de 30 leitos e uma tabela de 30 linhas ordenada por
gravidade. A ordenacao esta certa; o problema e que a lista e de TODO MUNDO,
logo de NINGUEM — cada enfermeira le as trinta, decide quais sao suas, e refaz
isso a cada atualizacao da tela.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from interface.api_shared import DB_PATH, _check_api_rate_limit
from interface.dependencies import get_current_user
from interface.repositories import atribuicoes as repo
from interface.repositories.pacientes import PatientRepository

router = APIRouter(prefix="/api", tags=["atribuicoes"])


class ResponsavelResponse(BaseModel):
    usuario: str
    display_name: str | None
    coren: str | None
    categoria: str | None
    atribuido_em: str
    # Distingue auto-atribuicao ("assumi este leito") de distribuicao pela
    # coordenacao. Sem o campo os dois ficam indistinguiveis no historico.
    atribuido_por: str


class AcaoResponse(BaseModel):
    ok: bool
    # `mudou=False` quando a operacao ja estava aplicada. Nao e erro — tocar
    # duas vezes em "assumir" acontece quando a tela demora — mas a tela pode
    # usar para nao mostrar "leito assumido" de novo.
    mudou: bool


@router.get("/pacientes/{paciente_id}/responsaveis", response_model=list[ResponsavelResponse])
async def listar_responsaveis(
    paciente_id: str,
    _: str = Depends(get_current_user),
    __: None = Depends(_check_api_rate_limit),
) -> list[dict]:
    """Quem responde por este paciente agora.

    Lista, e nao um so: numa transicao de plantao e legitimo que dois vejam o
    mesmo leito por alguns minutos, e mostrar apenas um esconderia a passagem.
    """
    return repo.responsaveis_por(DB_PATH, paciente_id)


@router.post("/pacientes/{paciente_id}/assumir", response_model=AcaoResponse)
async def assumir(
    paciente_id: str,
    user: str = Depends(get_current_user),
    _: None = Depends(_check_api_rate_limit),
) -> dict:
    """Assume o leito para o usuario da SESSAO.

    Sem parametro de usuario: aceita-lo permitiria atribuir pacientes a
    terceiros sem que eles soubessem, e a lista de trabalho de alguem passaria
    a ser escrita por outra pessoa.
    """
    if PatientRepository(DB_PATH).get_by_id(paciente_id) is None:
        # 404 antes de gravar: sem isto, a FK barraria com 500 e a tela diria
        # "erro interno" para um caso perfeitamente previsivel (o paciente
        # recebeu alta enquanto a lista estava na tela).
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Paciente nao encontrado"},
        )
    return {"ok": True, "mudou": repo.assumir(DB_PATH, paciente_id, user)}


@router.post("/pacientes/{paciente_id}/liberar", response_model=AcaoResponse)
async def liberar(
    paciente_id: str,
    user: str = Depends(get_current_user),
    _: None = Depends(_check_api_rate_limit),
) -> dict:
    """Libera o leito. Idempotente: liberar o que nao era seu e sucesso."""
    return {"ok": True, "mudou": repo.liberar(DB_PATH, paciente_id, user)}


@router.post("/meus-pacientes/liberar-todos", response_model=AcaoResponse)
async def liberar_todos(
    user: str = Depends(get_current_user),
    _: None = Depends(_check_api_rate_limit),
) -> dict:
    """Fim de plantao: solta todos os leitos de uma vez.

    Sem isto, quem sai do turno teria de liberar leito a leito — e nao faria,
    porque ninguem faz. As atribuicoes ficariam vivas indefinidamente e "meus
    pacientes" acumularia o hospital inteiro ao longo de semanas, ate deixar de
    significar qualquer coisa.
    """
    return {"ok": True, "mudou": repo.liberar_todos(DB_PATH, user) > 0}


@router.get("/meus-pacientes", response_model=list[str])
async def meus_pacientes(
    user: str = Depends(get_current_user),
    _: None = Depends(_check_api_rate_limit),
) -> list[str]:
    """Os ids atribuidos a quem pediu. A tela usa para marcar as linhas."""
    return sorted(repo.pacientes_de(DB_PATH, user))
