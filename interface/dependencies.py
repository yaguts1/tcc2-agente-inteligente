import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import Depends, Request, HTTPException, status
from interface.auth_utils import verify_token

logger = structlog.get_logger(__name__)

TOKEN_DISPOSITIVO_HEADER = "X-Device-Token"


def token_dispositivo_configurado() -> Optional[str]:
    """Token compartilhado que os ESP32 apresentam, ou None se nao configurado."""
    return os.getenv("UPP_DEVICE_TOKEN") or None


def verificar_token_dispositivo(request: Request) -> None:
    """Autentica o dispositivo nos endpoints de ingestao.

    O firmware so envia `X-Device-Id`, que ele mesmo escolhe — nao e segredo
    nenhum, e ainda permite furar o rate limit trocando o header. Este token e
    o que de fato autentica a origem dos dados.

    Se UPP_DEVICE_TOKEN nao estiver definido, a verificacao fica desligada para
    nao derrubar bancadas ja montadas; o aviso sai no startup (interface/web.py).
    """
    esperado = token_dispositivo_configurado()
    if not esperado:
        return

    recebido = request.headers.get(TOKEN_DISPOSITIVO_HEADER, "")
    if not recebido or not secrets.compare_digest(recebido, esperado):
        logger.warning(
            "device_token_invalido",
            device_id=request.headers.get("X-Device-Id"),
            cliente=request.client.host if request.client else None,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "device_nao_autenticado", "message": "Token de dispositivo invalido."},
        )


def _payload_do_jwt(request: Request) -> Optional[dict]:
    """Payload do JWT apresentado (header ou cookie), ou None.

    NÃO confia no cookie `session_user` (texto puro, não assinado, forjável):
    qualquer um poderia mandar `Cookie: session_user=admin` e ser autenticado.
    A identidade só vem de um token assinado verificado por `verify_token`.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_token(auth_header[7:])
        if payload:
            return payload

    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        payload = verify_token(token_cookie)
        if payload:
            return payload

    return None


def sessao_valida(payload: dict) -> bool:
    """Verifica se a sessão do token continua valendo do lado do servidor.

    A assinatura do JWT prova apenas que nós o emitimos e que ainda não
    expirou. Sem esta checagem o token era irrevogável: valia as 8h inteiras
    mesmo depois do logout, da troca de senha ou do desligamento da conta.

    Três motivos para recusar:
      1. o `jti` está na denylist (logout daquela sessão);
      2. a conta foi desativada;
      3. o token foi emitido antes do corte `tokens_validos_apos` (troca de
         senha ou saída forçada de todas as sessões).

    Falha fechada: se a consulta ao banco quebrar, a sessão é recusada — o
    caminho seguro é negar acesso, não liberar.
    """
    from interface.api_shared import DB_PATH
    from interface.repositories.sessoes import estado_da_conta, token_esta_revogado

    username = payload.get("sub")
    if not username:
        return False

    try:
        if token_esta_revogado(DB_PATH, payload.get("jti", "")):
            return False

        conta = estado_da_conta(DB_PATH, username)
        if conta is None:
            # Usuário não existe no banco. Pode ser o login de fallback por
            # variável de ambiente (dev/bancada), que não cria linha em users.
            return True
        if not conta["ativo"]:
            return False

        corte = conta["tokens_validos_apos"]
        if corte:
            emitido_em = payload.get("iat")
            if emitido_em is None:
                # Token antigo, emitido antes de existir `iat`: não dá para
                # saber se é anterior ao corte, então recusa.
                return False
            corte_dt = datetime.fromisoformat(str(corte)[:19]).replace(tzinfo=timezone.utc)
            if datetime.fromtimestamp(int(emitido_em), tz=timezone.utc) < corte_dt:
                return False
    except Exception:
        logger.warning("falha_ao_validar_sessao", usuario=username, exc_info=True)
        return False

    return True


def usuario_de_jwt(request: Request) -> Optional[str]:
    """Username autenticado, ou None se não houver sessão válida."""
    payload = _payload_do_jwt(request)
    if not payload or not sessao_valida(payload):
        return None
    return payload.get("sub")


async def get_current_user(request: Request) -> str:
    """Dependency FastAPI: retorna o username autenticado (via JWT) ou 401."""
    user = usuario_de_jwt(request)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "not_authenticated", "message": "Authentication required"},
        )
    return user


def papel_do_jwt(request: Request) -> Optional[str]:
    """Papel declarado no JWT, ou None se nao houver sessao valida.

    Passa pela mesma validacao de sessao que `usuario_de_jwt`: um token
    revogado (ou de conta desativada) nao pode conceder papel nenhum.
    """
    payload = _payload_do_jwt(request)
    if not payload or not sessao_valida(payload):
        return None
    return payload.get("role")


def exigir_papel(*papeis: str):
    """Dependency que exige um dos papeis informados.

    O JWT ja carregava `role` e o /auth/me o devolvia, mas NADA no projeto
    verificava: a autorizacao era binaria (autenticado ou nao). Na pratica,
    qualquer conta recem-criada podia importar alertas em massa, apagar todos
    os backups e injetar dados sinteticos no banco de producao.

    O papel vem do token assinado — nao de um campo que o cliente possa enviar.
    """
    permitidos = set(papeis)

    async def _verificar(request: Request, usuario: str = Depends(get_current_user)) -> str:
        papel = papel_do_jwt(request)
        if papel not in permitidos:
            logger.warning(
                "acesso_negado_por_papel",
                usuario=usuario,
                papel=papel,
                exigido=sorted(permitidos),
                rota=request.url.path,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "papel_insuficiente",
                    "message": "Esta operacao requer privilegios administrativos.",
                },
            )
        return usuario

    return _verificar
