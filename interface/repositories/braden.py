"""Avaliacoes de Braden e a reavaliacao vencida.

A avaliacao APLICA o perfil derivado na ficha: e o que faz a ferramenta virar
parte do protocolo existente em vez de manter uma classificacao paralela ao lado
dele. O `perfil` da ficha continua sendo o que o motor le — nada abaixo muda.
"""
from __future__ import annotations

from datetime import datetime, UTC

import structlog

from interface.db_core import connect
from interface.repositories.unidades import filtro_sql as filtro_de_unidades
from interface.tempo import agora_utc_naive
from nucleo import braden as escala

logger = structlog.get_logger(__name__)

# Quantas horas ate a reavaliacao vencer.
#
# 24h e a pratica de cuidado agudo: Braden e reavaliado diariamente e a cada
# mudanca de condicao. Fica configuravel porque o intervalo varia por servico —
# UTI reavalia por turno, unidade de longa permanencia semanalmente — e um numero
# fixo aqui obrigaria cada instalacao a conviver com um alerta que nao e o dela.
def horas_para_reavaliacao() -> int:
    import os

    try:
        return max(int(os.getenv("BRADEN_REAVALIACAO_HORAS", "24")), 1)
    except ValueError:
        logger.warning("braden_reavaliacao_horas_invalido", usando=24)
        return 24


def registrar(
    db_path: str,
    paciente_id: str,
    subescores: dict,
    *,
    usuario: str | None = None,
    observacoes: str | None = None,
    quando: str | None = None,
) -> dict:
    """Registra a avaliacao e APLICA o perfil derivado na ficha.

    Aplicar, e nao sugerir: manter as duas classificacoes lado a lado — a do
    dropdown e a de Braden — reproduziria exatamente o problema que esta
    entidade existe para resolver. Duas classificacoes divergem, e a divergencia
    aparece no pior momento.

    O `perfil` da ficha segue sendo o que o motor le, entao nada abaixo desta
    camada precisa saber que Braden existe.
    """
    resultado = escala.avaliar(subescores)

    dt = datetime.fromisoformat(str(quando)[:19]) if quando else agora_utc_naive().replace(microsecond=0)
    ts = dt.strftime("%Y-%m-%dT%H:%M:%S")
    ms = int(dt.replace(tzinfo=UTC).timestamp() * 1000)

    with connect(db_path) as conn:
        if conn.execute(
            "SELECT 1 FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,)
        ).fetchone() is None:
            raise LookupError(f"Paciente {paciente_id} nao encontrado.")

        episodio = conn.execute(
            "SELECT id FROM internacoes WHERE paciente_id = ? AND alta_ms IS NULL",
            (paciente_id,),
        ).fetchone()

        sub = resultado["subescores"]
        cur = conn.execute(
            "INSERT INTO braden_avaliacoes"
            " (paciente_id, internacao_id, percepcao_sensorial, umidade, atividade,"
            "  mobilidade, nutricao, friccao_cisalhamento, total, faixa, perfil,"
            "  avaliada_ts, avaliada_ms, avaliada_por, observacoes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                paciente_id,
                None if episodio is None else int(episodio["id"]),
                sub["percepcao_sensorial"], sub["umidade"], sub["atividade"],
                sub["mobilidade"], sub["nutricao"], sub["friccao_cisalhamento"],
                resultado["total"], resultado["faixa"], resultado["perfil"],
                ts, ms, usuario, observacoes,
            ),
        )
        avaliacao_id = int(cur.lastrowid)

        conn.execute(
            "UPDATE paciente_fichas SET perfil = ?, updated_at = ? WHERE paciente_id = ?",
            (resultado["perfil"], ts, paciente_id),
        )

    logger.info(
        "braden_registrado",
        avaliacao_id=avaliacao_id,
        paciente_id=paciente_id,
        total=resultado["total"],
        faixa=resultado["faixa"],
        perfil=resultado["perfil"],
        por=usuario,
    )
    return {"id": avaliacao_id, "paciente_id": paciente_id, "avaliada_ts": ts, **resultado}


def listar_do_paciente(db_path: str, paciente_id: str) -> list[dict]:
    with connect(db_path) as conn:
        return [
            dict(linha)
            for linha in conn.execute(
                # `id DESC` como desempate: `avaliada_ms` tem resolucao de
                # segundo, e duas avaliacoes no mesmo segundo sao plausiveis
                # (uma correcao logo apos a outra). Sem o desempate a ordem
                # ficaria a criterio do SQLite, e `ultima()` poderia devolver a
                # avaliacao ANTIGA — que e a que define a janela do motor.
                "SELECT * FROM braden_avaliacoes WHERE paciente_id = ?"
                " ORDER BY avaliada_ms DESC, id DESC",
                (paciente_id,),
            )
        ]


def ultima(db_path: str, paciente_id: str) -> dict | None:
    with connect(db_path) as conn:
        linha = conn.execute(
            "SELECT * FROM braden_avaliacoes WHERE paciente_id = ?"
            " ORDER BY avaliada_ms DESC, id DESC LIMIT 1",
            (paciente_id,),
        ).fetchone()
    return None if linha is None else dict(linha)


def reavaliacoes_pendentes(
    db_path: str, unidades: set[int] | None = None, horas: int | None = None
) -> dict:
    """Pacientes internados com Braden vencido — ou nunca avaliado.

    `nunca_avaliado` fica separado de `vencido` de proposito, pelo mesmo motivo
    que `nunca_recebeu_dados` e separado no watchdog de monitoramento: as duas
    situacoes pedem acao diferente. Vencido e reavaliar; nunca avaliado e um
    paciente que entrou no sistema sem passar pelo instrumento, e o problema esta
    no fluxo de admissao, nao no plantao.
    """
    limite_h = horas_para_reavaliacao() if horas is None else max(int(horas), 1)
    corte_ms = int(agora_utc_naive().timestamp() * 1000) - limite_h * 3_600_000

    condicao, params = filtro_de_unidades(unidades, coluna="f.unidade_id")

    with connect(db_path) as conn:
        linhas = conn.execute(
            "SELECT f.paciente_id, f.nome, f.cama_id,"
            "       (SELECT MAX(b.avaliada_ms) FROM braden_avaliacoes b"
            "         WHERE b.paciente_id = f.paciente_id) AS ultima_ms,"
            "       (SELECT b.total FROM braden_avaliacoes b"
            "         WHERE b.paciente_id = f.paciente_id"
            "         ORDER BY b.avaliada_ms DESC, b.id DESC LIMIT 1) AS ultimo_total"
            "  FROM paciente_fichas f"
            " WHERE EXISTS (SELECT 1 FROM internacoes i"
            "               WHERE i.paciente_id = f.paciente_id AND i.alta_ms IS NULL)"
            + condicao,
            params,
        ).fetchall()

    nunca: list[dict] = []
    vencidos: list[dict] = []
    for linha in linhas:
        item = {
            "paciente_id": linha["paciente_id"],
            "nome": linha["nome"],
            "cama_id": linha["cama_id"],
            "ultimo_total": linha["ultimo_total"],
        }
        if linha["ultima_ms"] is None:
            nunca.append(item)
        elif int(linha["ultima_ms"]) < corte_ms:
            item["horas_desde_ultima"] = round(
                (int(agora_utc_naive().timestamp() * 1000) - int(linha["ultima_ms"]))
                / 3_600_000,
                1,
            )
            vencidos.append(item)

    return {
        "limite_horas": limite_h,
        "internados": len(linhas),
        "nunca_avaliado": nunca,
        "vencidos": vencidos,
        "pendentes": len(nunca) + len(vencidos),
    }
