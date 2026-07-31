"""Quem responde por qual paciente.

Ver `migrations/0018_atribuicao_de_paciente.sql` para o porque de ser tabela e
nao coluna. Em resumo: a atribuicao muda a cada turno, e sem historico nao da
para responder "quem era o responsavel quando este alerta ficou 4h aberto?" —
que e a pergunta que a analise de adesao por enfermeiro (5.1) precisa fazer.
"""

from __future__ import annotations

from datetime import UTC

from interface.db_core import connect
from interface.tempo import agora_utc_naive


def _agora() -> tuple[str, int]:
    agora = agora_utc_naive().replace(microsecond=0)
    return agora.strftime("%Y-%m-%dT%H:%M:%S"), int(
        agora.replace(tzinfo=UTC).timestamp() * 1000
    )


def assumir(db_path: str, paciente_id: str, usuario: str, por: str | None = None) -> bool:
    """Atribui o paciente. Devolve `False` se ja era daquele usuario.

    IDEMPOTENTE de proposito, via o indice unico parcial: tocar duas vezes em
    "assumir" — o que acontece quando a tela demora e a pessoa insiste — nao
    pode criar duas atribuicoes ativas, senao a contagem de "meus pacientes"
    passa a mentir.
    """
    iso, ms = _agora()
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO atribuicoes_paciente"
            " (paciente_id, usuario, atribuido_em, atribuido_ms, atribuido_por)"
            " VALUES (?,?,?,?,?)",
            (paciente_id, usuario, iso, ms, por or usuario),
        )
        return cur.rowcount > 0


def liberar(db_path: str, paciente_id: str, usuario: str) -> bool:
    """Encerra a atribuicao ativa. Estado, e nao delete.

    Apagar destruiria a evidencia de quem respondia por aquele leito — o mesmo
    motivo pelo qual alta virou estado em 1.1.
    """
    iso, ms = _agora()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE atribuicoes_paciente SET liberado_em = ?, liberado_ms = ?"
            " WHERE paciente_id = ? AND usuario = ? AND liberado_ms IS NULL",
            (iso, ms, paciente_id, usuario),
        )
        return cur.rowcount > 0


def pacientes_de(db_path: str, usuario: str) -> set[str]:
    """Os pacientes ativos daquele usuario.

    `set` e nao lista: o unico uso e pertencimento, e a listagem de alertas
    filtra por ele uma vez por alerta.
    """
    with connect(db_path) as conn:
        return {
            linha["paciente_id"]
            for linha in conn.execute(
                "SELECT paciente_id FROM atribuicoes_paciente"
                " WHERE usuario = ? AND liberado_ms IS NULL",
                (usuario,),
            )
        }


def responsaveis_por(db_path: str, paciente_id: str) -> list[dict]:
    """Quem responde por este paciente agora.

    Lista e nao um so: numa transicao de plantao e legitimo que dois vejam o
    mesmo leito por alguns minutos, e mostrar so um esconderia a passagem.
    """
    with connect(db_path) as conn:
        return [
            dict(linha)
            for linha in conn.execute(
                "SELECT a.usuario, a.atribuido_em, a.atribuido_por,"
                "       u.display_name, u.coren, u.categoria"
                "  FROM atribuicoes_paciente a"
                "  LEFT JOIN users u ON u.username = a.usuario"
                " WHERE a.paciente_id = ? AND a.liberado_ms IS NULL"
                " ORDER BY a.atribuido_ms",
                (paciente_id,),
            )
        ]


def liberar_todos(db_path: str, usuario: str) -> int:
    """Fim de plantao: solta todos os leitos de uma vez.

    Sem isto, quem sai do turno teria de liberar leito a leito — e nao faria,
    porque ninguem faz. As atribuicoes ficariam vivas indefinidamente e "meus
    pacientes" acumularia o hospital inteiro ao longo de semanas, ate deixar de
    significar qualquer coisa.
    """
    iso, ms = _agora()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE atribuicoes_paciente SET liberado_em = ?, liberado_ms = ?"
            " WHERE usuario = ? AND liberado_ms IS NULL",
            (iso, ms, usuario),
        )
        return cur.rowcount
