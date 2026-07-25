"""O alerta precisa FECHAR quando o paciente e reposicionado.

Ha dois motores no sistema, e eles persistem de formas diferentes:

- `processar_alertas_lote` (simulacao) devolve o alerta UMA vez, ja fechado;
- `processar_alertas_incremental` (sensor real, amostra a amostra) emite o
  alerta DUAS vezes — 'aberto' quando a janela estoura, 'fechado' quando detecta
  o reposicionamento — em duas chamadas de persistencia com a mesma chave
  (paciente_id, inicio).

`inserir_alertas` usava `INSERT OR IGNORE`, entao o fechamento vindo do sensor
era descartado em silencio. A demonstracao com dados simulados ficava correta e
o produto com sensor real, nao: o alerta ficava 'aberto' com fim=NULL para
sempre. Como um alerta aberto ja conta como vencido, a tela mostrava o paciente
em atraso permanente DEPOIS de ele ter sido virado.
"""

import sqlite3

import pytest

from interface.dao import inserir_alertas

BASE = {
    "paciente_id": "PAC-CICLO",
    "inicio": "2026-01-05T01:30:00",
    "tipo": "imobilidade",
    "perfil": "medio",
    "janela_min": 90,
}


@pytest.fixture
def db(app_isolado):
    return app_isolado.db_path


def _linha(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT status, fim, duracao_min FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (BASE["paciente_id"], BASE["inicio"]),
        ).fetchone()


def _abrir(db):
    inserir_alertas(db, [dict(BASE, status="aberto", fim=None)])


def _fechar(db):
    inserir_alertas(
        db, [dict(BASE, status="fechado", fim="2026-01-05T03:45:00", duracao_min=135.0)]
    )


def test_fechamento_do_sensor_e_persistido(db):
    """O caso que estava quebrado: abre, depois fecha — em duas chamadas."""
    _abrir(db)
    assert _linha(db)[0] == "aberto"

    _fechar(db)

    status, fim, duracao = _linha(db)
    assert status == "fechado", (
        "o alerta continuou 'aberto' depois de o motor detectar o reposicionamento: "
        "a tela mostraria o paciente em atraso para sempre"
    )
    assert fim == "2026-01-05T03:45:00"
    assert duracao == 135.0


def test_reemissao_de_aberto_nao_rebaixa_o_que_a_equipe_ja_marcou(db):
    """Um 'aberto' repetido nao pode desfazer um reconhecimento da enfermagem."""
    _abrir(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE alertas SET status = 'reconhecido' WHERE paciente_id = ?",
            (BASE["paciente_id"],),
        )

    _abrir(db)

    assert _linha(db)[0] == "reconhecido", (
        "a reemissao do motor apagou o reconhecimento feito na tela"
    )


def test_fechamento_ja_gravado_nao_e_sobrescrito(db):
    """Fechou uma vez, fechou. Nao reabrir nem mexer na duracao."""
    _abrir(db)
    _fechar(db)

    inserir_alertas(
        db, [dict(BASE, status="fechado", fim="2026-01-05T09:00:00", duracao_min=999.0)]
    )

    _, fim, duracao = _linha(db)
    assert (fim, duracao) == ("2026-01-05T03:45:00", 135.0)


def test_timeline_nao_duplica_a_abertura(db):
    """Duas persistencias do mesmo alerta = um disparo na timeline, nao dois."""
    _abrir(db)
    _fechar(db)

    with sqlite3.connect(db) as conn:
        abre = conn.execute(
            "SELECT COUNT(*) FROM timeline_events WHERE paciente_id = ? AND tipo = 'alert_open'",
            (BASE["paciente_id"],),
        ).fetchone()[0]
        fecha = conn.execute(
            "SELECT COUNT(*) FROM timeline_events WHERE paciente_id = ? AND tipo = 'alert_close'",
            (BASE["paciente_id"],),
        ).fetchone()[0]

    assert (abre, fecha) == (1, 1), (
        f"timeline com {abre} aberturas e {fecha} fechamentos para um unico alerta"
    )


def test_os_dois_motores_concordam_sobre_quais_alertas_existem():
    """Lote e incremental tem de detectar os MESMOS alertas.

    O incremental emite transicoes (abertura e fechamento separados) e o lote
    so o resultado final — mas o conjunto de alertas, identificado por
    (inicio, fim), precisa ser identico. Se divergir, a demonstracao com dados
    simulados nao representa o que o sensor real produz.
    """
    from datetime import datetime

    import pandas as pd

    from dados_simulados.gerador import PERFIS_PREDEFINIDOS, PerfilPaciente, gerar_sessao_simulada
    from nucleo.decisor import (
        EstadoDecisor,
        processar_alertas_incremental,
        processar_alertas_lote,
    )

    df, _ = gerar_sessao_simulada(
        duracao_horas=12,
        seed=7,
        passo_min=5,
        inicio=datetime(2026, 1, 5, 0, 0, 0),
        perfil=PerfilPaciente(**PERFIS_PREDEFINIDOS["medio"]),
        incluir_contexto=True,
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    lote = processar_alertas_lote(df[["timestamp", "postura"]], "medio", "PAC-X")

    estado = EstadoDecisor(
        perfil="medio", paciente_id="PAC-X", janela_min=90, cooldown_min=15, histerese_min=5
    )
    emitidos = []
    for _, row in df.iterrows():
        estado, novos = processar_alertas_incremental(
            estado, {"timestamp": row["timestamp"], "postura": row["postura"]}
        )
        emitidos.extend(novos)

    # Estado final de cada alerta no incremental: a ultima emissao de cada `inicio`.
    final = {a["inicio"]: a for a in emitidos}
    assert {(a["inicio"], a.get("fim")) for a in lote} == {
        (a["inicio"], a.get("fim")) for a in final.values()
    }
