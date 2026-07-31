"""Inscricoes de Web Push e o nivel ja notificado por alerta."""

from __future__ import annotations

from typing import Any

from interface.db_core import connect, utc_now_iso


def inscrever(db_path: str, *, usuario: str, endpoint: str, p256dh: str, auth: str) -> None:
    """Registra (ou reativa) a inscricao de um aparelho.

    `ON CONFLICT` no endpoint, e nao `INSERT` puro: reinscricao no mesmo
    navegador devolve o MESMO endpoint, entao sem isso a tabela ganharia uma
    linha por vez que o usuario recarrega a pagina — e o aviso chegaria
    duplicado na mesma tela.

    O contador de falhas ZERA aqui. Uma inscricao que voltou a ser oferecida
    pelo navegador esta viva de novo, e carregar o historico de falhas faria a
    limpeza remove-la logo em seguida.
    """
    agora = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (usuario, endpoint, p256dh, auth, criado_em)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(endpoint) DO UPDATE SET"
            "   usuario = excluded.usuario,"
            "   p256dh = excluded.p256dh,"
            "   auth = excluded.auth,"
            "   falhas = 0,"
            "   ultima_falha = NULL",
            (usuario, endpoint, p256dh, auth, agora),
        )


def desinscrever(db_path: str, endpoint: str) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        return cur.rowcount > 0


def listar(db_path: str, usuario: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT usuario, endpoint, p256dh, auth FROM push_subscriptions"
    params: tuple = ()
    if usuario is not None:
        sql += " WHERE usuario = ?"
        params = (usuario,)
    with connect(db_path) as conn:
        return [dict(linha) for linha in conn.execute(sql, params)]


def remover_mortas(db_path: str, endpoints: list[str]) -> int:
    """Apaga inscricoes que o servico de push declarou inexistentes (404/410).

    Sem isto a tabela so cresce, e cada ciclo do loop gasta uma requisicao de
    rede por aparelho que ja nao existe.
    """
    if not endpoints:
        return 0
    marcadores = ",".join("?" for _ in endpoints)
    with connect(db_path) as conn:
        cur = conn.execute(
            f"DELETE FROM push_subscriptions WHERE endpoint IN ({marcadores})",  # noqa: S608 - marcadores gerados, nao entrada
            endpoints,
        )
        return cur.rowcount


# Nivel ja notificado -------------------------------------------------------


def niveis_notificados(db_path: str) -> dict[tuple[str, str], str]:
    """Ultimo nivel avisado por alerta, indexado por (paciente_id, inicio).

    E o que transforma envio por ESTADO em envio por TRANSICAO. Sem ele, o loop
    de fundo notificaria "ha alerta critico" a cada ciclo — a maneira mais
    rapida de fazer a equipe desligar as notificacoes do navegador, e uma vez
    desligadas elas nao voltam.
    """
    with connect(db_path) as conn:
        return {
            (linha["paciente_id"], linha["inicio"]): linha["nivel"]
            for linha in conn.execute(
                "SELECT paciente_id, inicio, nivel FROM push_nivel_notificado"
            )
        }


def registrar_nivel(db_path: str, paciente_id: str, inicio: str, nivel: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO push_nivel_notificado (paciente_id, inicio, nivel, notificado_em)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(paciente_id, inicio) DO UPDATE SET"
            "   nivel = excluded.nivel, notificado_em = excluded.notificado_em",
            (paciente_id, inicio, nivel, utc_now_iso()),
        )


def limpar_alertas_fechados(db_path: str) -> int:
    """Remove o registro de nivel dos alertas que ja nao estao abertos.

    Duas razoes, e a segunda importa mais: a tabela nao pode crescer sem limite
    ao longo de uma internacao, e um alerta REABERTO no mesmo paciente e horario
    precisa poder notificar de novo — carregar o nivel antigo o deixaria mudo.
    """
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM push_nivel_notificado"
            " WHERE (paciente_id, inicio) NOT IN ("
            "   SELECT paciente_id, inicio FROM alertas WHERE status != 'fechado'"
            " )"
        )
        return cur.rowcount
