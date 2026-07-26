"""Encadeamento criptografico da trilha de auditoria.

A trilha vive no mesmo SQLite que ela audita. Sem protecao, um UPDATE apaga o
registro de um acesso indevido e nada no sistema fica diferente: a trilha era
confiavel exatamente ate o momento em que alguem tivesse motivo para adultera-la
— o unico momento em que ela precisa ser confiavel.

Cada entrada carrega o hash da anterior. Alterar um campo, apagar uma linha ou
inserir uma no meio quebra o elo seguinte, e `verificar` aponta onde.

## O que isto garante, e o que nao garante

Adulteracao vira DETECTAVEL, nao impossivel. Quem escreve no banco pode
recalcular a cadeia inteira depois de mexer — a menos que nao tenha a chave.
Por isso o elo e um HMAC-SHA256 com `UPP_AUDIT_KEY`, que mora no ambiente e nao
no banco: um atacante com acesso apenas ao arquivo .db nao consegue forjar elos
validos.

Se a chave estiver no mesmo servidor que o banco, um atacante com root pega as
duas coisas. A protecao e proporcional a distancia entre a chave e o banco, e
essa e uma decisao de instalacao — o codigo so pode deixar a opcao disponivel e
avisar quando ela nao esta em uso.

Sem `UPP_AUDIT_KEY` definida, a cadeia usa SHA-256 puro: ainda detecta
adulteracao acidental, corrupcao e edicao ingenua, mas nao alguem determinado.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Mapping, Sequence

import structlog

logger = structlog.get_logger(__name__)

# Valor do elo inicial, quando ainda nao ha entrada anterior na cadeia.
GENESE = "genese"

# Campos que entram no hash, nesta ordem. Mudar a lista ou a ordem invalida
# todas as cadeias existentes — se um dia for necessario, versione o formato em
# vez de editar aqui.
CAMPOS_ASSINADOS: Sequence[str] = (
    "ts",
    "ts_ms",
    "usuario",
    "papel",
    "acao",
    "metodo",
    "rota",
    "paciente_id",
    "status",
    "negado",
    "ip",
    "duracao_ms",
    "detalhe",
)


def chave() -> bytes | None:
    """Chave do HMAC, ou None se a instalacao nao configurou uma."""
    valor = os.getenv("UPP_AUDIT_KEY", "").strip()
    return valor.encode("utf-8") if valor else None


def com_chave() -> bool:
    return chave() is not None


def _canonico(registro: Mapping[str, Any]) -> str:
    """Serializacao estavel dos campos assinados.

    `sort_keys` e separadores fixos para que o mesmo registro produza sempre a
    mesma string — um espaco a mais mudaria o hash e quebraria a cadeia sem que
    nada tivesse sido adulterado.
    """
    dados = {campo: registro.get(campo) for campo in CAMPOS_ASSINADOS}
    return json.dumps(dados, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _payload(registro: Mapping[str, Any], hash_anterior: str) -> bytes:
    return f"{hash_anterior}\n{_canonico(registro)}".encode("utf-8")


def calcular(registro: Mapping[str, Any], hash_anterior: str) -> str:
    """Elo desta entrada, a partir do conteudo dela e do elo anterior."""
    payload = _payload(registro, hash_anterior)
    segredo = chave()
    if segredo is None:
        return hashlib.sha256(payload).hexdigest()
    return hmac.new(segredo, payload, hashlib.sha256).hexdigest()


def _confere(registro: Mapping[str, Any], hash_anterior: str, guardado: str) -> str | None:
    """Diz COMO o elo confere: "forte", "fraco" ou None se nao confere.

    A entrada em uso da chave numa instalacao que ja rodava sem ela deixa um
    trecho gravado com SHA-256 puro. Recusar esse trecho reportaria adulteracao
    onde houve apenas mudanca de configuracao — e alarme falso numa trilha de
    auditoria destroi a confianca nela tao bem quanto nao ter trilha.

    Por isso o SHA-256 e aceito como fallback, mas contado a parte: se alguem
    tentar REBAIXAR entradas para SHA-256 (o melhor que consegue sem a chave),
    o elo confere, porem como "fraco" — e a trilha deixa de ser `confiavel`.
    A tentativa fica visivel em vez de passar por autentica.
    """
    payload = _payload(registro, hash_anterior)
    segredo = chave()

    if segredo is not None:
        forte = hmac.new(segredo, payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(forte, guardado):
            return "forte"
        fraco = hashlib.sha256(payload).hexdigest()
        return "fraco" if hmac.compare_digest(fraco, guardado) else None

    esperado = hashlib.sha256(payload).hexdigest()
    # Sem chave configurada nao existe "forte": todo elo e apenas SHA-256.
    return "fraco" if hmac.compare_digest(esperado, guardado) else None


def verificar(linhas: Sequence[Mapping[str, Any]]) -> dict:
    """Percorre a cadeia e relata a primeira quebra.

    `linhas` deve vir ordenada por `id` crescente — a ordem de insercao, que e a
    ordem da cadeia.

    Distingue tres situacoes, porque exigem reacoes diferentes:

    - `conteudo_alterado`: o hash guardado nao bate com o conteudo da linha.
      Alguem editou o registro.
    - `elo_quebrado`: o hash guardado bate, mas o elo anterior nao aponta para a
      linha anterior. Alguem apagou, inseriu ou reordenou linhas.
    - `sem_protecao`: linha anterior a migracao, sem hash. Nao e adulteracao —
      e ausencia de garantia, e precisa ser dita como tal.
    """
    problemas: list[dict] = []
    sem_protecao = 0
    verificadas = 0
    fracas = 0
    anterior: Mapping[str, Any] | None = None

    for linha in linhas:
        guardado = linha.get("hash")
        if not guardado:
            sem_protecao += 1
            anterior = linha
            continue

        elo_anterior = linha.get("hash_anterior") or GENESE

        # Continuidade: o elo tem de apontar para a linha imediatamente
        # anterior. A primeira linha protegida depois de um expurgo legitimo
        # nao tem como apontar para nada, entao so cobramos continuidade
        # quando a anterior tambem estava protegida.
        if anterior is not None and anterior.get("hash"):
            if elo_anterior != anterior.get("hash"):
                problemas.append({
                    "id": linha.get("id"),
                    "tipo": "elo_quebrado",
                    "detalhe": "o elo anterior nao corresponde ao registro precedente: "
                               "linha apagada, inserida ou reordenada",
                })

        forca = _confere(linha, elo_anterior, str(guardado))
        if forca is None:
            problemas.append({
                "id": linha.get("id"),
                "tipo": "conteudo_alterado",
                "detalhe": "o hash guardado nao corresponde ao conteudo da linha",
            })
        elif forca == "fraco" and com_chave():
            fracas += 1

        verificadas += 1
        anterior = linha

    # `integra` responde "achei adulteracao?", e so isso. Numa trilha sem elo
    # nenhum ela seria True com zero linhas verificadas — nada foi checado,
    # logo nada foi detectado — e quem olhasse so esse campo leria "esta tudo
    # bem" sobre uma trilha completamente desprotegida.
    #
    # `confiavel` e o campo para decidir: exige que nao haja adulteracao E que
    # tudo esteja de fato coberto pela cadeia.
    return {
        "integra": not problemas,
        "confiavel": (
            not problemas and sem_protecao == 0 and fracas == 0 and verificadas > 0
        ),
        "verificadas": verificadas,
        "sem_protecao": sem_protecao,
        # Entradas que conferem por SHA-256 puro havendo chave configurada:
        # ou sao anteriores a adocao da chave, ou alguem tentou rebaixa-las.
        # A distincao entre os dois casos nao esta no banco — e por isso que
        # `confiavel` fica False ate a trilha ser inteiramente reescrita sob a
        # chave (na pratica, ate o trecho antigo sair por retencao).
        "protecao_fraca": fracas,
        "problemas": problemas,
        "com_chave": com_chave(),
    }


def avisar_se_sem_chave() -> None:
    """Registra no startup que a trilha esta sem chave (mesmo padrao do device token)."""
    if not com_chave():
        logger.warning(
            "auditoria_sem_chave",
            motivo=(
                "UPP_AUDIT_KEY nao definida: a cadeia da trilha usa SHA-256 puro e pode "
                "ser recalculada por quem tiver acesso de escrita ao banco. Defina a "
                "variavel — de preferencia com a chave guardada fora deste servidor."
            ),
        )
