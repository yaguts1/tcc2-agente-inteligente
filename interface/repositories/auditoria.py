"""Persistencia da trilha de auditoria.

Dado de saude e dado pessoal sensivel (LGPD, Art. 5o II). O registro cobre
LEITURA e nao so escrita: em prontuario, "quem consultou os dados deste
paciente" e a pergunta central, e o Art. 48 (comunicacao de incidente) exige
saber quais titulares foram expostos — o que so e possivel se os acessos de
leitura estiverem gravados.
"""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any, Optional

import structlog

from interface.db_core import connect
from interface.tempo import agora_utc_naive

logger = structlog.get_logger(__name__)


def registrar(
    db_path: str,
    *,
    metodo: str,
    rota: str,
    status: int,
    usuario: str | None = None,
    papel: str | None = None,
    paciente_id: str | None = None,
    ip: str | None = None,
    duracao_ms: int | None = None,
    detalhe: dict[str, Any] | None = None,
) -> None:
    """Grava uma entrada na trilha.

    Nunca levanta excecao: falhar ao auditar nao pode derrubar a requisicao que
    ja foi atendida. Mas a falha e logada — uma trilha que para de gravar em
    silencio e pior do que nao ter trilha, porque cria confianca indevida.
    """
    agora = agora_utc_naive()
    # `agora` e naive-UTC; .timestamp() em datetime naive interpreta como hora
    # LOCAL, o que deslocaria o ts_ms pelo offset do fuso (o mesmo defeito que
    # ja corrompeu a correlacao sensor-paciente). Marcar como UTC antes.
    ts_ms = int(agora.replace(tzinfo=timezone.utc).timestamp() * 1000)
    try:
        with connect(db_path) as conn:
            conn.execute(
                "INSERT INTO auditoria"
                " (ts, ts_ms, usuario, papel, acao, metodo, rota, paciente_id,"
                "  status, negado, ip, duracao_ms, detalhe)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agora.strftime("%Y-%m-%dT%H:%M:%S"),
                    ts_ms,
                    usuario,
                    papel,
                    f"{metodo} {rota}",
                    metodo,
                    rota,
                    paciente_id,
                    int(status),
                    1 if status in (401, 403) else 0,
                    ip,
                    duracao_ms,
                    json.dumps(detalhe, ensure_ascii=False) if detalhe else None,
                ),
            )
    except Exception:
        logger.warning(
            "auditoria_nao_gravada",
            metodo=metodo,
            rota=rota,
            usuario=usuario,
            exc_info=True,
        )


def consultar(
    db_path: str,
    *,
    paciente_id: str | None = None,
    usuario: str | None = None,
    apenas_negados: bool = False,
    desde_ms: int | None = None,
    ate_ms: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Consulta a trilha. Ordena do mais recente para o mais antigo."""
    condicoes: list[str] = []
    params: list[Any] = []
    if paciente_id:
        condicoes.append("paciente_id = ?")
        params.append(paciente_id)
    if usuario:
        condicoes.append("usuario = ?")
        params.append(usuario)
    if apenas_negados:
        condicoes.append("negado = 1")
    if desde_ms is not None:
        condicoes.append("ts_ms >= ?")
        params.append(int(desde_ms))
    if ate_ms is not None:
        condicoes.append("ts_ms <= ?")
        params.append(int(ate_ms))

    sql = (
        "SELECT id, ts, usuario, papel, acao, metodo, rota, paciente_id, status,"
        " negado, ip, duracao_ms, detalhe FROM auditoria"
    )
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY ts_ms DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with connect(db_path) as conn:
        linhas = conn.execute(sql, tuple(params)).fetchall()

    resultado = []
    for l in linhas:
        item = dict(l)
        item["negado"] = bool(item["negado"])
        if item.get("detalhe"):
            try:
                item["detalhe"] = json.loads(item["detalhe"])
            except Exception:
                pass
        resultado.append(item)
    return resultado


def contar(db_path: str, **filtros: Any) -> int:
    """Total de registros que casam com os filtros (para paginacao)."""
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0])


def expurgar_anteriores_a(db_path: str, ts_ms: int) -> int:
    """Remove entradas anteriores ao instante dado.

    A LGPD pede que o dado nao seja mantido alem do necessario (Art. 15/16), mas
    a retencao adequada depende de politica da instituicao — por isso e uma
    operacao explicita, e nao um expurgo automatico com prazo arbitrario.
    """
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM auditoria WHERE ts_ms < ?", (int(ts_ms),))
        return int(cur.rowcount or 0)
