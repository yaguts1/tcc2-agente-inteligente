"""Inscricao de aparelhos para notificacao que sobrevive a aba fechada."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from interface.api_shared import DB_PATH, _check_api_rate_limit
from interface.dependencies import get_current_user
from interface.repositories import push as repo
from servicos import push as servico

router = APIRouter(prefix="/api", tags=["push"])


class ChavePublicaResponse(BaseModel):
    """A chave VAPID que o navegador precisa para se inscrever.

    `configurado` e explicito em vez de deduzido de `chave is None`: a tela
    precisa distinguir "o servidor nao tem push" de "a chave nao carregou", e
    tratar as duas igual faria a interface oferecer um botao que nunca funciona.
    """

    configurado: bool
    chave_publica: str | None


class InscricaoRequest(BaseModel):
    # `min_length` nos tres: uma inscricao com campo vazio e aceita pelo banco e
    # falha silenciosamente na hora do envio, horas depois, longe da causa.
    endpoint: str = Field(min_length=1, max_length=2000)
    p256dh: str = Field(min_length=1, max_length=500)
    auth: str = Field(min_length=1, max_length=500)


class InscricaoResponse(BaseModel):
    ok: bool


@router.get("/push/chave-publica", response_model=ChavePublicaResponse)
async def obter_chave_publica(
    _user: str = Depends(get_current_user),
    __: None = Depends(_check_api_rate_limit),
) -> dict:
    """Exige sessao mesmo sendo uma chave PUBLICA.

    Nao e a chave que se protege — e o fato de que este servidor existe e roda
    este sistema. Endpoint anonimo que responde com configuracao e superficie de
    reconhecimento de graca.
    """
    return {"configurado": servico.configurado(), "chave_publica": servico.chave_publica()}


@router.post("/push/inscrever", response_model=InscricaoResponse, status_code=status.HTTP_201_CREATED)
async def inscrever(
    payload: InscricaoRequest,
    user: str = Depends(get_current_user),
    _: None = Depends(_check_api_rate_limit),
) -> dict:
    """Registra o aparelho do usuario da sessao.

    O usuario vem do JWT e NAO do corpo: aceita-lo do cliente permitiria
    inscrever o aparelho de alguem para receber os alertas de outra pessoa.
    """
    if not servico.configurado():
        # 503 e nao 400: o pedido esta correto, o servidor e que nao tem como
        # atende-lo. A diferenca importa para a tela decidir se esconde o botao
        # ou mostra erro.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "push_desconfigurado",
                "message": "Notificacoes nao configuradas neste servidor",
            },
        )
    repo.inscrever(
        DB_PATH,
        usuario=user,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
    )
    return {"ok": True}


@router.post("/push/desinscrever", response_model=InscricaoResponse)
async def desinscrever(
    payload: InscricaoRequest,
    _user: str = Depends(get_current_user),
    __: None = Depends(_check_api_rate_limit),
) -> dict:
    """Remove o aparelho.

    `POST` e nao `DELETE` porque o endpoint identificador vai no CORPO — ele e
    uma URL longa, e coloca-lo no path o faria bater no limite de tamanho e
    exigir escape de barras.
    """
    repo.desinscrever(DB_PATH, payload.endpoint)
    # Idempotente de proposito: desinscrever o que ja nao existe e sucesso. O
    # cliente chama isto ao revogar permissao, e um 404 ali produziria erro na
    # tela por uma operacao que atingiu o objetivo.
    return {"ok": True}
