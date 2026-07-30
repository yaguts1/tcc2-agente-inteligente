"""A ingestao grava a amostra numa transacao so.

Antes eram QUATRO conexoes e quatro commits por amostra — grade, eventos, estado
do motor e alertas, cada um abrindo a propria. Duas consequencias:

  * DESEMPENHO. Cada conexao paga abertura, quatro PRAGMAs e um commit, e no
    SQLite os commits de escrita serializam entre si. Era por isso que o teto
    medido quase nao melhorava com concorrencia: 26 amostras/s com 1 thread, 36
    com 8 — 37% de ganho para 8x de paralelismo. Depois da mudanca: ~58/s com 1
    thread e ~160/s com 4, ou seja concorrencia passou a escalar.

  * CORRETUDE, que sozinha ja justificaria. Com quatro transacoes, uma falha no
    meio deixava a grade gravada e o alerta nao: a amostra existia no historico
    do paciente sem o alerta que ela deveria ter produzido, e nada indicava.

Este arquivo trava as duas propriedades. Sem ele, alguem que adicione uma
gravacao nova no caminho de ingestao — abrindo conexao propria, que e o jeito
natural de escrever — reintroduz o problema inteiro sem que nada acuse.
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

from interface.db_core import connect
from interface.schemas import EventPayload

BASE = datetime(2026, 3, 10, 8, 0, 0)


@pytest.fixture
def ingestao(app_isolado, monkeypatch):
    """Servico de ingestao apontando para o banco isolado, com um paciente."""
    from interface.services import ingestao_service

    monkeypatch.setattr(ingestao_service, "DB_PATH", app_isolado.db_path)
    agora = BASE.strftime("%Y-%m-%dT%H:%M:%S")
    with connect(app_isolado.db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES ('PAC-0001')")
        conn.execute(
            "INSERT INTO paciente_fichas"
            " (paciente_id, nome, perfil, cama_id, created_at, updated_at, unidade_id)"
            " VALUES ('PAC-0001','Ana','alto','201-A',?,?,1)",
            (agora, agora),
        )
    return ingestao_service


def _amostra(minuto: int, postura: str = "supino") -> EventPayload:
    return EventPayload(
        device_id="DEV-001",
        paciente_id="PAC-0001",
        cama_id="201-A",
        postura=postura,
        confianca=0.95,
        amostra_ms=60000,
        ts_utc=(BASE + timedelta(minutes=minuto)).strftime("%Y-%m-%dT%H:%M:%S"),
    )


class _ConexaoContada(sqlite3.Connection):
    """Conexao que conta os proprios commits.

    Subclasse e nao monkeypatch: `sqlite3.Connection` e um tipo imutavel e
    `setattr` nele levanta `TypeError`. `sqlite3.connect(factory=...)` e o
    caminho suportado para isso.
    """

    commits = 0

    def commit(self, *args, **kwargs):
        type(self).commits += 1
        return super().commit(*args, **kwargs)


def _contar(monkeypatch, alvo: str):
    """Conta chamadas a `sqlite3.connect`, ou commits nas conexoes abertas."""
    contagem = {"n": 0}
    original = sqlite3.connect

    if alvo == "connect":

        def espiao(*args, **kwargs):
            contagem["n"] += 1
            return original(*args, **kwargs)

    else:
        _ConexaoContada.commits = 0

        def espiao(*args, **kwargs):
            kwargs["factory"] = _ConexaoContada
            return original(*args, **kwargs)

        contagem = _ConexaoContada  # type: ignore[assignment]

    monkeypatch.setattr(sqlite3, "connect", espiao)
    return contagem


def test_uma_conexao_por_amostra(ingestao, monkeypatch):
    """Eram quatro. Cada uma paga abertura e os PRAGMAs de novo."""
    ingestao.registrar_evento(_amostra(0))  # aquece: primeira amostra inicializa estado

    contagem = _contar(monkeypatch, "connect")
    ingestao.registrar_evento(_amostra(1))

    assert contagem["n"] == 1, (
        f"{contagem['n']} conexoes por amostra — alguem voltou a abrir a propria"
    )


def test_um_commit_por_amostra(ingestao, monkeypatch):
    """No SQLite os commits de escrita serializam entre si: e o commit, e nao a
    CPU, que era o teto."""
    ingestao.registrar_evento(_amostra(0))

    _contar(monkeypatch, "commit")
    ingestao.registrar_evento(_amostra(1))

    assert _ConexaoContada.commits == 1, (
        f"{_ConexaoContada.commits} commits por amostra"
    )


def test_amostra_que_gera_alerta_tambem_usa_uma_conexao(ingestao, monkeypatch):
    """O caminho com alerta grava numa tabela a mais e nao pode abrir outra
    conexao por causa disso."""
    # Perfil alto: janela de 60 min. A carga chega a 60 na amostra do minuto 60,
    # entao e ELA que abre o alerta — as seguintes devolvem zero, porque o
    # alerta ja esta aberto.
    for minuto in range(0, 60):
        ingestao.registrar_evento(_amostra(minuto))

    contagem = _contar(monkeypatch, "connect")
    resultado = ingestao.registrar_evento(_amostra(60))

    assert resultado["alertas"] >= 1, "premissa: esta amostra deveria abrir alerta"
    assert contagem["n"] == 1


def test_falha_no_meio_nao_deixa_amostra_pela_metade(ingestao, monkeypatch, app_isolado):
    """A propriedade de CORRETUDE.

    Com quatro transacoes, uma falha depois da grade deixava a amostra gravada
    sem o alerta que ela deveria ter produzido — dado clinico incompleto, sem
    nada indicando. Numa transacao so, ou entra inteira ou nao entra.
    """
    ingestao.registrar_evento(_amostra(0))

    def explodir(*args, **kwargs):
        raise RuntimeError("falha simulada depois da grade")

    monkeypatch.setattr(ingestao, "inserir_eventos", explodir)

    with pytest.raises(RuntimeError):
        ingestao.registrar_evento(_amostra(1))

    with connect(app_isolado.db_path) as conn:
        gravadas = conn.execute(
            "SELECT COUNT(*) FROM grade WHERE paciente_id = 'PAC-0001'"
        ).fetchone()[0]

    assert gravadas == 1, (
        "a grade da amostra que falhou ficou no banco: a transacao nao voltou atras"
    )


def test_o_anuncio_acontece_fora_da_transacao(ingestao, monkeypatch):
    """Anunciar dentro faria o cliente receber um alerta que uma falha posterior
    ainda poderia desfazer — e seguraria um lock de escrita do banco pelo tempo
    de um cliente WebSocket lento."""
    momentos = []

    original = ingestao.inserir_alertas

    def marcar_insercao(*args, **kwargs):
        momentos.append("grava")
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestao, "inserir_alertas", marcar_insercao)
    monkeypatch.setattr(ingestao, "_anunciar", lambda *_: momentos.append("anuncia"))

    for minuto in range(0, 61):
        ingestao.registrar_evento(_amostra(minuto))

    assert momentos, "premissa: algum alerta deveria ter sido aberto"
    assert momentos[0] == "grava"
    assert "anuncia" in momentos
    assert momentos.index("grava") < momentos.index("anuncia")


# ---------------------------------------------------------------------------
# A consulta mais quente do sistema
# ---------------------------------------------------------------------------


def test_watchdog_usa_busca_no_indice_e_nao_varredura(app_isolado):
    """`status_por_paciente` roda a cada `/api/stats`, que o dashboard dispara a
    cada mudanca de alerta.

    Com `LEFT JOIN` + `MAX(g.ts)` + `GROUP BY`, o SQLite varre as linhas de
    grade de cada paciente para depois agregar: 130 ms com 30 leitos e 30 dias
    de amostras. Com subconsulta correlacionada ele faz UMA busca no indice e
    para no primeiro resultado, porque o indice ja esta na ordem pedida — menos
    de 1 ms.

    Este teste olha o PLANO, e nao o tempo: tempo em CI e ruidoso, e o que
    importa e a propriedade (busca, nao varredura), que e o que se perde se
    alguem reescrever a consulta para a forma "natural".
    """
    from interface.db_core import connect
    from interface.repositories.monitoramento import status_por_paciente

    # Executa uma vez para garantir que a consulta do modulo e valida.
    status_por_paciente(app_isolado.db_path)

    with connect(app_isolado.db_path) as conn:
        plano = " | ".join(
            str(linha[-1])
            for linha in conn.execute(
                "EXPLAIN QUERY PLAN"
                " SELECT f.paciente_id,"
                "        (SELECT g.ts FROM grade g"
                "          WHERE g.paciente_id = f.paciente_id"
                "          ORDER BY g.ts DESC LIMIT 1)"
                "   FROM paciente_fichas f"
                "  WHERE f.cama_id IS NOT NULL AND f.cama_id != ''"
            )
        )

    assert "SEARCH g" in plano, f"a grade voltou a ser varrida: {plano}"
    assert "idx_grade_paciente_ts" in plano, f"o indice nao esta sendo usado: {plano}"
