"""Credencial por dispositivo.

Substitui — gradualmente — o `UPP_DEVICE_TOKEN` unico, que e o mesmo segredo
gravado no `config.h` de toda a frota: um ESP32 arrancado da parede entrega a
credencial de todos os outros, e nao ha revogacao possivel abaixo de reflashear
o predio inteiro.

A regra de validacao esta em `validar`, e a ordem importa:

  1. dispositivo JA PROVISIONADO responde so pela credencial dele. Nao aceita o
     global — senao um segredo global vazado continuaria falando em nome de um
     aparelho ja migrado, e a migracao nao teria efeito de seguranca nenhum. E
     "provisionado" inclui REVOGADO: revogar precisa cortar o acesso, nao
     rebaixar o aparelho de volta para a credencial da frota;
  2. dispositivo SEM token proprio cai no global, se houver. E o que permite
     migrar aparelho por aparelho sem deixar a ala sem monitoramento;
  3. sem nenhum dos dois, a verificacao fica desligada (comportamento
     pre-existente, para nao derrubar bancada montada), com aviso no startup.
"""
from __future__ import annotations

import hashlib
import secrets

import structlog

from interface.db_core import connect
from interface.tempo import agora_utc_naive

logger = structlog.get_logger(__name__)

# 32 bytes -> 43 caracteres url-safe. Espaco de busca grande o bastante para
# que forca bruta nao seja o caminho de ataque, que e o que dispensa um KDF
# lento na verificacao (ver migrations/0012).
TAMANHO_TOKEN_BYTES = 32


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def emitir(db_path: str, device_id: str, criado_por: str | None = None) -> str:
    """Gera um token novo para o dispositivo e devolve o TEXTO PURO.

    O texto puro nao e guardado: sai daqui uma vez e o banco fica so com o
    hash. Perdeu, emite outro — barato, e nao exige que o servidor guarde algo
    que ele nao precisa poder ler.

    Emitir de novo SUBSTITUI o token anterior: e a operacao de rotacao, e ter
    dois tokens validos por dispositivo so criaria a duvida de qual revogar.
    """
    if not device_id:
        raise ValueError("device_id deve ser informado")

    token = secrets.token_urlsafe(TAMANHO_TOKEN_BYTES)
    agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO devices (device_id) VALUES (?)"
            " ON CONFLICT(device_id) DO NOTHING",
            (device_id,),
        )
        conn.execute(
            "INSERT INTO device_tokens (device_id, token_hash, criado_em, criado_por)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(device_id) DO UPDATE SET"
            "   token_hash = excluded.token_hash,"
            "   criado_em = excluded.criado_em,"
            "   criado_por = excluded.criado_por,"
            "   revogado_em = NULL,"
            "   revogado_por = NULL,"
            "   ultimo_uso_em = NULL",
            (device_id, _hash(token), agora, criado_por),
        )
    logger.info("device_token_emitido", device_id=device_id, por=criado_por)
    return token


def revogar(db_path: str, device_id: str, revogado_por: str | None = None) -> bool:
    """Invalida o token do dispositivo. Devolve False se nao havia token ativo.

    NAO apaga a linha: o registro de que aquele aparelho teve credencial, e de
    quem a revogou e quando, e justamente o que se quer guardar depois de um
    aparelho sumir.
    """
    agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE device_tokens SET revogado_em = ?, revogado_por = ?"
            " WHERE device_id = ? AND revogado_em IS NULL",
            (agora, revogado_por, device_id),
        )
        mudou = cur.rowcount > 0
    if mudou:
        logger.warning("device_token_revogado", device_id=device_id, por=revogado_por)
    return mudou


def foi_provisionado(db_path: str, device_id: str) -> bool:
    """O dispositivo tem — ou JA TEVE — credencial propria.

    Deliberadamente ignora `revogado_em`. Se olhasse so os tokens ativos,
    revogar um aparelho o REBAIXARIA para a credencial global da frota em vez de
    cortar o acesso: exatamente o oposto do proposito da revogacao, e um jeito
    silencioso de um aparelho perdido continuar enviando.

    Uma vez provisionado, o aparelho responde so pela credencial dele. Para
    devolve-lo ao token global e preciso apagar a linha, que e uma acao
    explicita e nao acontece por engano.
    """
    if not device_id:
        return False
    with connect(db_path) as conn:
        linha = conn.execute(
            "SELECT 1 FROM device_tokens WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return linha is not None


def validar(db_path: str, device_id: str, token: str) -> bool:
    """True se o token confere com o do dispositivo (e nao foi revogado)."""
    if not device_id or not token:
        return False
    with connect(db_path) as conn:
        linha = conn.execute(
            "SELECT token_hash FROM device_tokens"
            " WHERE device_id = ? AND revogado_em IS NULL",
            (device_id,),
        ).fetchone()
        if linha is None:
            return False
        # `compare_digest` mesmo comparando hashes: o custo e nulo e evita ter
        # que raciocinar sobre se o vazamento por tempo importa aqui.
        confere = secrets.compare_digest(str(linha["token_hash"]), _hash(token))
        if confere:
            conn.execute(
                "UPDATE device_tokens SET ultimo_uso_em = ? WHERE device_id = ?",
                (agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S"), device_id),
            )
    return confere


def listar(db_path: str) -> list[dict]:
    """Estado das credenciais, sem nunca expor hash nem texto puro."""
    with connect(db_path) as conn:
        linhas = conn.execute(
            "SELECT device_id, criado_em, criado_por, ultimo_uso_em,"
            "       revogado_em, revogado_por"
            "  FROM device_tokens ORDER BY device_id"
        ).fetchall()
    return [dict(linha) for linha in linhas]


def ingestao_esta_aberta(db_path: str) -> bool:
    """True quando NAO ha credencial nenhuma exigivel na ingestao.

    Aberta significa: sem token de frota E sem nenhum aparelho provisionado.
    Um deploy com todos os ESP32 com token proprio e sem `UPP_DEVICE_TOKEN`
    esta correto, e o startup nao pode avisar que esta aberto — alarme falso e
    o que ensina a equipe a ignorar o log.

    Mora aqui, e nao inline no lifespan, para ser testavel sem subir o app.
    """
    from interface.dependencies import token_dispositivo_configurado

    if token_dispositivo_configurado():
        return False
    try:
        return not any(t.get("revogado_em") is None for t in listar(db_path))
    except Exception:
        # Sem conseguir consultar, avisa: o custo de um aviso a mais e menor que
        # o de silenciar um endpoint de ingestao realmente aberto.
        logger.warning("consulta_de_tokens_falhou", exc_info=True)
        return True
