import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import Depends, Request, HTTPException, WebSocket, status
from interface.auth_utils import verify_token

logger = structlog.get_logger(__name__)

TOKEN_DISPOSITIVO_HEADER = "X-Device-Token"


def token_dispositivo_configurado() -> Optional[str]:
    """Token compartilhado que os ESP32 apresentam, ou None se nao configurado."""
    return os.getenv("UPP_DEVICE_TOKEN") or None


def credencial_de_dispositivo_ok(device_id: str | None, token: str | None) -> bool:
    """Decide se esta credencial de dispositivo vale. Fonte unica das duas portas.

    HTTP e WebSocket precisam concordar sobre quem pode enviar amostra: uma
    regra em cada lugar e como as duas portas de reconciliacao divergiram sobre
    de quem era o dado.

    A ordem existe para permitir migrar a frota aparelho por aparelho:

      1. dispositivo JA PROVISIONADO responde so pela credencial dele. Nao
         aceita o global — senao um segredo global vazado continuaria falando em
         nome de um aparelho ja migrado, e migrar nao teria efeito nenhum de
         seguranca. "Provisionado" inclui REVOGADO: revogar corta o acesso, e
         nao rebaixa o aparelho de volta para a credencial da frota;
      2. dispositivo SEM token proprio cai no global, se houver. Trocar a
         credencial da frota inteira num deploy so deixaria a ala sem
         monitoramento no instante da troca;
      3. sem nenhum dos dois, a verificacao fica desligada — comportamento
         pre-existente, para nao derrubar bancada montada. O aviso sai no
         startup (interface/web.py).
    """
    from interface.api_shared import DB_PATH
    from interface.repositories.device_tokens import foi_provisionado, validar

    try:
        provisionado = bool(device_id) and foi_provisionado(DB_PATH, str(device_id))
    except Exception:
        # Falha ao consultar o banco NAO pode virar "aceita qualquer um": o
        # caminho seguro e recusar, e a amostra e reenviada pelo firmware (que
        # trata 401 como falha TRANSIENTE justamente por isso).
        logger.warning("device_token_consulta_falhou", device_id=device_id, exc_info=True)
        return False

    if provisionado:
        return validar(DB_PATH, str(device_id), str(token or ""))

    esperado = token_dispositivo_configurado()
    if not esperado:
        return True
    return bool(token) and secrets.compare_digest(str(token), esperado)


def verificar_token_dispositivo(request: Request) -> None:
    """Autentica o dispositivo nos endpoints de ingestao.

    O firmware so envia `X-Device-Id`, que ele mesmo escolhe — nao e segredo
    nenhum, e ainda permite furar o rate limit trocando o header. Este token e
    o que de fato autentica a origem dos dados.
    """
    device_id = request.headers.get("X-Device-Id")
    recebido = request.headers.get(TOKEN_DISPOSITIVO_HEADER, "")

    if not credencial_de_dispositivo_ok(device_id, recebido):
        logger.warning(
            "device_token_invalido",
            device_id=device_id,
            cliente=request.client.host if request.client else None,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "device_nao_autenticado", "message": "Token de dispositivo invalido."},
        )


def _payload_do_jwt(request: "Request | WebSocket") -> Optional[dict]:
    """Payload do JWT apresentado (header ou cookie), ou None.

    Aceita `WebSocket` alem de `Request`: as duas classes expoem `.headers` e
    `.cookies`, e a regra de quem esta autenticado nao pode depender do
    transporte — foi assim que `/api/ws/alerts` ficou aberto enquanto todas as
    rotas HTTP vizinhas exigiam sessao.

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
            # Não há linha em `users` para este `sub`. Só existe um caso
            # legítimo: o login de fallback por variável de ambiente, que não
            # cria usuário — e que já é restrito ao admin configurado e a
            # ambientes fora de produção.
            #
            # Aceitar qualquer `sub` sem linha seria pior do que parece: um
            # usuário REMOVIDO do banco continuaria autenticado até o token
            # expirar, exatamente o oposto do que remover a conta significa.
            from interface.auth_utils import em_producao

            if em_producao():
                return False
            return username == os.getenv("UPP_ADMIN_USER", "admin")
        if not conta["ativo"]:
            return False

        corte = conta["tokens_validos_apos"]
        if corte:
            emitido_em = payload.get("iat")
            if emitido_em is None:
                # Token antigo, emitido antes de existir `iat`: não dá para
                # saber se é anterior ao corte, então recusa.
                return False
            # Comparacao estrita: `tokens_validos_apos` significa "tokens
            # emitidos ANTES deste instante nao valem". Quem grava o corte ja o
            # arredonda para o proximo segundo (ver
            # repositories/sessoes.revogar_sessoes_do_usuario), porque o `iat`
            # do JWT tem resolucao de 1s e, sem isso, a sessao criada no mesmo
            # segundo da revogacao sobreviveria.
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


async def exigir_sessao_websocket(websocket: WebSocket) -> Optional[str]:
    """Username autenticado no handshake do WebSocket, ou None (ja fechado).

    Fecha com 1008 (policy violation) ANTES do `accept()`: nao ha o que negociar
    com quem nao tem sessao, e aceitar para so depois fechar entregaria uma
    conexao aberta a um anonimo, ainda que por instantes.

    O navegador nao consegue mandar cabecalho no handshake de WebSocket, entao a
    credencial que funciona para a SPA e o cookie `access_token` — que
    `_definir_cookie_sessao` ja grava no login E no cadastro, e que o navegador
    anexa sozinho por ser mesma origem. O cabecalho `Authorization` continua
    aceito porque `_payload_do_jwt` o le, o que mantem clientes nao-navegador
    (teste, script, painel de leito futuro) funcionando sem caso especial.
    """
    payload = _payload_do_jwt(websocket)
    if not payload or not sessao_valida(payload):
        logger.warning("ws_sem_sessao", caminho=websocket.url.path)
        await websocket.close(code=1008)
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


async def escopo_de_unidades(request: Request) -> Optional[set[int]]:
    """Dependency: quais unidades o chamador enxerga. `None` = todas (admin).

    Existe como dependency, e nao como consulta dentro de cada endpoint, para
    que a regra de visibilidade tenha UM dono. Enquanto ela estava implicita
    ("todo mundo ve tudo"), nao havia lugar onde alguem pudesse ler qual era a
    regra — e e assim que o escopo passa a divergir entre a listagem, a
    estatistica e o export sem ninguem perceber.

    Falha fechada: sem sessao valida, conjunto vazio. Quem chama isto ja passou
    por `get_current_user` no router, entao na pratica nao acontece; mas o
    caminho existente nao pode ser "sem sessao => ve tudo".
    """
    from interface.api_shared import DB_PATH
    from interface.repositories.unidades import unidades_do_usuario

    payload = _payload_do_jwt(request)
    if not payload or not sessao_valida(payload):
        return set()
    username = payload.get("sub") or ""
    return unidades_do_usuario(DB_PATH, username, payload.get("role"))


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
