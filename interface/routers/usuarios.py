"""Gestao de usuarios.

Nao havia nenhuma: dava para criar contas, mas nao para listar, promover,
desativar ou trocar senha. Numa instalacao real isso significa que um
profissional que sai da equipe mantem acesso indefinidamente, e que nao ha como
criar um segundo administrador — se a unica conta admin se perder, as operacoes
administrativas ficam inacessiveis para sempre.

Decisoes:

- Desativar em vez de apagar. Apagar o usuario levaria junto a autoria
  registrada na timeline (quem reconheceu e quem concluiu cada alerta), que e
  justamente o que se quer preservar num prontuario.
- Toda acao sensivel revoga as sessoes do alvo. Sem isso "desativar" seria
  cosmetico: o JWT ja emitido continuaria valendo por horas.
- A instalacao nunca fica sem admin ativo: rebaixar ou desativar o ultimo e
  recusado.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.hash import bcrypt
from pydantic import BaseModel, Field

from interface.api_shared import erro_interno, exigir_senha_forte
from interface.api_shared import _check_api_rate_limit
from interface.dependencies import escopo_de_unidades
from interface.dependencies import exigir_papel, get_current_user
from interface.repositories.sessoes import revogar_sessoes_do_usuario
from interface.repositories.users import UltimoAdmin, UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["usuarios"],
    dependencies=[Depends(exigir_papel("admin")), Depends(_check_api_rate_limit)],
)
# A troca da PROPRIA senha nao e operacao administrativa: qualquer usuario
# autenticado pode (e deve poder) faze-la.
router_proprio = APIRouter(tags=["usuarios"])

def _db() -> str:
    """Caminho do banco resolvido por chamada (mesmo motivo de `_repo`)."""
    from interface.api_shared import DB_PATH

    return DB_PATH


def _repo() -> UserRepository:
    """Repositorio resolvido por chamada, e nao um singleton de import.

    O padrao usado nos outros routers (`repo = UserRepository(DB_PATH)` no
    escopo do modulo) congela o caminho do banco no momento do import, o que
    obriga os testes a recarregar a cadeia de modulos inteira sempre que trocam
    de banco — e um modulo esquecido nessa cadeia falha de formas confusas
    (passa isolado, quebra na suite). Resolvendo aqui, este router nao depende
    disso.
    """
    from interface.api_shared import DB_PATH as caminho_atual

    return UserRepository(caminho_atual)


class AlterarPapel(BaseModel):
    role: str = Field(..., description="admin ou staff")


class AlterarAtivo(BaseModel):
    ativo: bool


# O tamanho minimo NAO fica no schema: ele e o mesmo de `/auth/register` e
# precisa sair de uma unica fonte (`exigir_senha_forte`), senao os tres
# caminhos que definem senha voltam a divergir — foi assim que o cadastro ficou
# sem exigencia nenhuma enquanto a troca exigia 8.
class TrocarSenha(BaseModel):
    senha_atual: str = Field(..., min_length=1)
    nova_senha: str


class DefinirSenha(BaseModel):
    nova_senha: str


@router.get("/usuarios", status_code=status.HTTP_200_OK)
def listar_usuarios() -> list[dict]:
    """Lista os usuarios (sem hash de senha)."""
    return _repo().listar()


@router.patch("/usuarios/{username}/papel", status_code=status.HTTP_200_OK)
def alterar_papel(username: str, payload: AlterarPapel, admin: str = Depends(get_current_user)) -> dict:
    # A garantia de "nunca sem admin" vive no repositorio, na mesma transacao
    # do UPDATE. Aqui ela era conferida numa consulta separada, e duas
    # requisicoes simultaneas rebaixando admins diferentes passavam as duas.
    try:
        _repo().definir_papel(username, payload.role)
    except UltimoAdmin as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ultimo_admin", "message": str(exc)},
        ) from exc
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "usuario_nao_encontrado"})
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "papel_invalido", "message": str(exc)},
        ) from exc

    # O papel viaja DENTRO do JWT: sem revogar, o usuario continuaria operando
    # com o papel antigo ate o token expirar.
    revogar_sessoes_do_usuario(_db(), username)
    logger.info("papel_alterado", alvo=username, novo_papel=payload.role, por=admin)
    return {"ok": True, "username": username, "role": payload.role}


@router.patch("/usuarios/{username}/ativo", status_code=status.HTTP_200_OK)
def alterar_ativo(username: str, payload: AlterarAtivo, admin: str = Depends(get_current_user)) -> dict:
    # Autodesativacao continua aqui: depende de QUEM esta chamando, que o
    # repositorio nao conhece. Ja o "ultimo admin" e invariante do dado e mora
    # na transacao que o aplica.
    if not payload.ativo and username == admin:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "autodesativacao",
                "message": "Voce nao pode desativar a propria conta.",
            },
        )
    try:
        _repo().definir_ativo(username, payload.ativo)
    except UltimoAdmin as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ultimo_admin", "message": str(exc)},
        ) from exc
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "usuario_nao_encontrado"})

    if not payload.ativo:
        revogar_sessoes_do_usuario(_db(), username)
    logger.info("conta_alterada", alvo=username, ativo=payload.ativo, por=admin)
    return {"ok": True, "username": username, "ativo": payload.ativo}


@router.post("/usuarios/{username}/senha", status_code=status.HTTP_200_OK)
async def definir_senha_de_usuario(
    username: str, payload: DefinirSenha, admin: str = Depends(get_current_user)
) -> dict:
    """Reset de senha por administrador (esquecimento, comprometimento)."""
    exigir_senha_forte(payload.nova_senha)
    try:
        senha_hash = await asyncio.to_thread(bcrypt.hash, payload.nova_senha)
        await asyncio.to_thread(_repo().definir_senha, username, senha_hash)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "usuario_nao_encontrado"})
    except Exception as exc:
        raise erro_interno("senha_reset_falhou", exc, alvo=username) from exc

    revogar_sessoes_do_usuario(_db(), username)
    logger.info("senha_redefinida_por_admin", alvo=username, por=admin)
    return {"ok": True, "username": username}


@router_proprio.post("/usuarios/eu/senha", status_code=status.HTTP_200_OK)
async def trocar_propria_senha(payload: TrocarSenha, usuario: str = Depends(get_current_user)) -> dict:
    """Troca da propria senha, exigindo a senha atual.

    Exigir a atual impede que alguem com uma sessao aberta esquecida assuma a
    conta trocando a credencial.
    """
    exigir_senha_forte(payload.nova_senha)

    registro = _repo().get_by_username(usuario)
    if registro is None or not registro.get("password_hash"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "usuario_nao_encontrado"})

    confere = await asyncio.to_thread(
        bcrypt.verify, payload.senha_atual, registro["password_hash"]
    )
    if not confere:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "senha_atual_invalida", "message": "Senha atual incorreta."},
        )

    try:
        senha_hash = await asyncio.to_thread(bcrypt.hash, payload.nova_senha)
        await asyncio.to_thread(_repo().definir_senha, usuario, senha_hash)
    except Exception as exc:
        raise erro_interno("troca_de_senha_falhou", exc, usuario=usuario) from exc

    # Trocar a senha derruba as sessoes: e o que se espera de quem troca a
    # senha justamente por suspeitar que alguem tem acesso.
    revogar_sessoes_do_usuario(_db(), usuario)
    logger.info("senha_trocada", usuario=usuario)
    return {"ok": True, "sessoes_encerradas": True}


# ---------------------------------------------------------------------------
# Unidades (alas/setores) e a quais delas cada usuario tem acesso
# ---------------------------------------------------------------------------
#
# Fica no router de usuarios, sob `exigir_papel("admin")`, porque "quem ve o
# que" e decisao administrativa: quem enxerga a ala nao pode ser quem decide
# enxerga-la.


class UnidadeCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    descricao: str | None = Field(None, max_length=255)


class UnidadesDoUsuario(BaseModel):
    unidades: list[int] = Field(default_factory=list)


@router_proprio.get("/unidades", status_code=status.HTTP_200_OK)
def listar_unidades_endpoint(
    incluir_inativas: bool = False,
    unidades_visiveis: set[int] | None = Depends(escopo_de_unidades),
    # `escopo_de_unidades` sozinho NAO autentica: ele falha fechado e devolve
    # conjunto vazio, entao um anonimo recebia 200 com lista vazia em vez de
    # 401. Nao vazava dado, mas 200 para quem nao tem sessao e uma resposta
    # errada — e o proximo a mexer aqui poderia ler o 200 como "esta rota e
    # publica" e afrouxar o resto.
    _: str = Depends(get_current_user),
) -> list[dict]:
    """Unidades que o chamador enxerga.

    Fica FORA do router de admin: a enfermeira precisa da lista para escolher
    onde admitir um paciente. O que muda por papel e o alcance — admin ve todas,
    os demais so as suas —, nao o direito de consultar.

    Criar e vincular seguem restritos a admin, logo abaixo: quem enxerga a ala
    nao pode ser quem decide enxerga-la.
    """
    from interface.repositories.unidades import listar_unidades

    todas = listar_unidades(_db(), incluir_inativas=incluir_inativas)
    if unidades_visiveis is None:
        return todas
    return [u for u in todas if int(u["id"]) in unidades_visiveis]


@router.post("/unidades", status_code=status.HTTP_201_CREATED)
def criar_unidade_endpoint(payload: UnidadeCreate) -> dict:
    from interface.repositories.unidades import criar_unidade

    try:
        return criar_unidade(_db(), payload.nome, payload.descricao)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "unidade_invalida", "message": str(exc)},
        ) from exc


@router.get("/usuarios/{username}/unidades", status_code=status.HTTP_200_OK)
def unidades_do_usuario_endpoint(username: str) -> dict:
    from interface.repositories.unidades import unidades_do_usuario

    unidades = unidades_do_usuario(_db(), username)
    return {"username": username, "unidades": sorted(unidades or [])}


@router.put("/usuarios/{username}/unidades", status_code=status.HTTP_200_OK)
async def definir_unidades_endpoint(username: str, payload: UnidadesDoUsuario) -> dict:
    """Define quais unidades o usuario enxerga.

    Lista vazia e valido e significa "nao ve nada" — deny by default, como em
    `unidades_do_usuario`. Nao e o mesmo que admin: admin ve tudo por causa do
    PAPEL, e esta lista nao o restringe.
    """
    from interface.repositories.unidades import (
        UnidadeInvalida,
        definir_unidades_do_usuario,
    )

    try:
        unidades = definir_unidades_do_usuario(_db(), username, payload.unidades)
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "usuario_nao_encontrado", "message": str(exc)},
        ) from exc
    except UnidadeInvalida as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "unidade_invalida", "message": str(exc)},
        ) from exc

    # As unidades entram na chave do cache da listagem de alertas: sem limpar, o
    # usuario continuaria vendo por ate 30s a lista do escopo ANTIGO — incluindo
    # a ala da qual acabou de ser removido.
    from interface.api_shared import api_cache

    await api_cache.clear()
    return {"ok": True, "username": username, "unidades": unidades}
