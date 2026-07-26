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
from typing import Any

import structlog

from interface import auditoria_cadeia as cadeia
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
    registro = {
        "ts": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "ts_ms": ts_ms,
        "usuario": usuario,
        "papel": papel,
        "acao": f"{metodo} {rota}",
        "metodo": metodo,
        "rota": rota,
        "paciente_id": paciente_id,
        "status": int(status),
        "negado": 1 if status in (401, 403) else 0,
        "ip": ip,
        "duracao_ms": duracao_ms,
        "detalhe": json.dumps(detalhe, ensure_ascii=False) if detalhe else None,
    }
    try:
        with connect(db_path) as conn:
            # BEGIN IMMEDIATE pega o lock de escrita ANTES de ler o ultimo elo.
            # Sem isso, duas requisicoes concorrentes leriam o mesmo elo anterior
            # e gravariam entradas irmas em vez de encadeadas — a verificacao
            # acusaria adulteracao onde houve apenas concorrencia, e um alarme
            # falso numa trilha de auditoria destroi a confianca nela tao bem
            # quanto nao ter trilha.
            conn.execute("BEGIN IMMEDIATE")
            ultimo = conn.execute(
                "SELECT hash FROM auditoria WHERE hash IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            hash_anterior = ultimo["hash"] if ultimo else cadeia.GENESE
            registro_hash = cadeia.calcular(registro, hash_anterior)

            conn.execute(
                "INSERT INTO auditoria"
                " (ts, ts_ms, usuario, papel, acao, metodo, rota, paciente_id,"
                "  status, negado, ip, duracao_ms, detalhe, hash_anterior, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    registro["ts"],
                    registro["ts_ms"],
                    registro["usuario"],
                    registro["papel"],
                    registro["acao"],
                    registro["metodo"],
                    registro["rota"],
                    registro["paciente_id"],
                    registro["status"],
                    registro["negado"],
                    registro["ip"],
                    registro["duracao_ms"],
                    registro["detalhe"],
                    hash_anterior,
                    registro_hash,
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


def _filtros_sql(
    paciente_id: str | None,
    usuario: str | None,
    apenas_negados: bool,
    desde_ms: int | None,
    ate_ms: int | None,
) -> tuple[str, list[Any]]:
    """Monta o WHERE compartilhado por `consultar` e `contar`.

    Existe porque `contar` recebia `**filtros` e nao usava NENHUM: contava a
    tabela inteira enquanto a docstring prometia o total dos que casam com os
    filtros. Como nada em producao chamava `contar`, o defeito nunca apareceu
    — e apareceria agora, ao paginar a consulta filtrada, na forma de um total
    maior que o real. Uma unica fonte para os dois impede que voltem a
    divergir.
    """
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
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return onde, params


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
    onde, params = _filtros_sql(paciente_id, usuario, apenas_negados, desde_ms, ate_ms)

    sql = (
        "SELECT id, ts, usuario, papel, acao, metodo, rota, paciente_id, status,"
        " negado, ip, duracao_ms, detalhe FROM auditoria"
    )
    sql += onde
    sql += " ORDER BY ts_ms DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with connect(db_path) as conn:
        linhas = conn.execute(sql, tuple(params)).fetchall()

    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["negado"] = bool(item["negado"])
        if item.get("detalhe"):
            try:
                item["detalhe"] = json.loads(item["detalhe"])
            except Exception:
                pass
        resultado.append(item)
    return resultado


def contar(
    db_path: str,
    *,
    paciente_id: str | None = None,
    usuario: str | None = None,
    apenas_negados: bool = False,
    desde_ms: int | None = None,
    ate_ms: int | None = None,
) -> int:
    """Total de registros que casam com os filtros (para paginacao).

    Os parametros eram `**filtros` e nao chegavam ao SQL: a funcao contava a
    tabela inteira, contrariando a propria docstring. Agora sao explicitos e
    passam pelo mesmo `_filtros_sql` que `consultar` usa.
    """
    onde, params = _filtros_sql(paciente_id, usuario, apenas_negados, desde_ms, ate_ms)
    with connect(db_path) as conn:
        return int(
            conn.execute(f"SELECT COUNT(*) FROM auditoria{onde}", tuple(params)).fetchone()[0]
        )


def verificar_integridade(db_path: str, limit: int | None = None) -> dict:
    """Percorre a cadeia e diz se a trilha foi adulterada.

    Le em ordem de `id` crescente, que e a ordem em que a cadeia foi montada.
    `limit` restringe as entradas MAIS RECENTES (util para uma checagem rapida
    numa trilha grande); sem ele, verifica tudo.
    """
    sql = (
        "SELECT id, ts, ts_ms, usuario, papel, acao, metodo, rota, paciente_id,"
        " status, negado, ip, duracao_ms, detalhe, hash_anterior, hash FROM auditoria"
    )
    with connect(db_path) as conn:
        if limit:
            linhas = conn.execute(
                f"SELECT * FROM ({sql} ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (int(limit),),
            ).fetchall()
        else:
            linhas = conn.execute(sql + " ORDER BY id ASC").fetchall()

    return cadeia.verificar([dict(linha) for linha in linhas])


def expurgar_anteriores_a(db_path: str, ts_ms: int) -> int:
    """Remove entradas anteriores ao instante dado.

    A LGPD pede que o dado nao seja mantido alem do necessario (Art. 15/16), mas
    a retencao adequada depende de politica da instituicao — por isso e uma
    operacao explicita, e nao um expurgo automatico com prazo arbitrario.

    O expurgo apaga o inicio da cadeia, o que e indistinguivel de uma
    adulteracao se ninguem registrar que aconteceu. Por isso ele proprio vira
    uma entrada da trilha: a remocao fica documentada DENTRO do que ela
    modificou, e quem verificar depois ve quantas linhas sairam e ate quando.
    """
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM auditoria WHERE ts_ms < ?", (int(ts_ms),))
        removidas = int(cur.rowcount or 0)

    if removidas:
        registrar(
            db_path,
            metodo="PURGE",
            rota="/auditoria",
            status=200,
            detalhe={"removidas": removidas, "anteriores_a_ms": int(ts_ms)},
        )
    return removidas
