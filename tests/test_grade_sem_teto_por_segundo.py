"""A grade descartava, em silencio, tudo que passasse de uma amostra por segundo.

A chave primaria era `(paciente_id, ts)`, `ts` e texto ISO e `norm_iso` faz
`.dt.floor("s")`. Duas amostras do mesmo segundo viravam a MESMA chave, e o
`INSERT OR IGNORE` de `inserir_grade` jogava a segunda fora:

  * sem erro, porque `OR IGNORE` e o comportamento pedido;
  * sem log e sem metrica, porque ninguem olhava `total_changes` por linha;
  * com resposta de SUCESSO para o dispositivo, que dava a amostra por entregue.

Na cadencia de hoje (`amostra_ms: 60000`) nao descartava nada. O problema era o
teto ser INVISIVEL: subir a cadencia para sub-segundo — o caminho natural para
detectar micro movimentos — sumiria com metade das leituras sem nada indicar.

Ja custou caro de um jeito instrutivo: um teste escrito para provar que o filtro
de qualidade deduplicava retransmissoes do WebSocket passava COM e SEM o filtro,
porque era esta PK comendo a duplicata. Um teto que some com dado tambem esconde
bug em teste.
"""

import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest

from interface.db_core import connect, criar_esquema
from interface.repositories.grade import inserir_grade

PACIENTE = "PAC-0001"


@pytest.fixture
def db(tmp_path):
    caminho = str(tmp_path / "t.db")
    criar_esquema(caminho)
    return caminho


def _grade(db) -> list[tuple]:
    with connect(db) as conn:
        return [
            tuple(linha)
            for linha in conn.execute(
                "SELECT ts, ts_ms, postura FROM grade WHERE paciente_id = ?"
                " ORDER BY ts_ms",
                (PACIENTE,),
            )
        ]


def test_amostras_sub_segundo_sobrevivem(db):
    """Quatro leituras dentro do MESMO segundo: as quatro precisam ficar."""
    df = pd.DataFrame({
        "timestamp": [
            "2026-03-10T10:00:00.000",
            "2026-03-10T10:00:00.250",
            "2026-03-10T10:00:00.500",
            "2026-03-10T10:00:00.750",
        ],
        "postura": ["supino", "supino", "lateral_direito", "lateral_direito"],
    })

    gravadas = inserir_grade(db, df, PACIENTE)

    assert gravadas == 4, "amostras do mesmo segundo foram descartadas"
    assert len(_grade(db)) == 4


def test_ts_ms_preserva_a_precisao_que_ts_perde(db):
    """`ts` continua de segundo cheio (todo consumidor de grade le ele);
    `ts_ms` guarda o instante de verdade."""
    df = pd.DataFrame({
        "timestamp": ["2026-03-10T10:00:00.000", "2026-03-10T10:00:00.750"],
        "postura": ["supino", "prono"],
    })

    inserir_grade(db, df, PACIENTE)
    linhas = _grade(db)

    assert [ts for ts, _, _ in linhas] == ["2026-03-10T10:00:00"] * 2
    assert linhas[1][1] - linhas[0][1] == 750, "a diferenca real era de 750ms"


def test_reenvio_da_mesma_amostra_continua_idempotente(db):
    """`OR IGNORE` nao some: reenvio do dispositivo e reingestao de evento orfao
    dependem dele. O que muda e o criterio de "mesma amostra"."""
    df = pd.DataFrame({
        "timestamp": ["2026-03-10T10:00:00.250"],
        "postura": ["supino"],
    })

    assert inserir_grade(db, df, PACIENTE) == 1
    assert inserir_grade(db, df, PACIENTE) == 0, "reenvio duplicou a leitura"
    assert len(_grade(db)) == 1


def test_descarte_deixa_rastro(db):
    """Sumir com amostra nao pode voltar a ser invisivel.

    Era assim que o teto de 1/s se escondia — e e assim que qualquer teto futuro
    se esconderia.

    `structlog.testing.capture_logs` e nao `caplog`/`capsys`: o structlog do
    projeto renderiza direto na saida padrao (logging_setup.py), entao o handler
    do stdlib nunca ve estes eventos — e o stream fica preso ao stdout real no
    momento da configuracao, o que faz `capsys` funcionar em teste isolado e
    falhar com a suite inteira.
    """
    from structlog.testing import capture_logs

    df = pd.DataFrame({
        "timestamp": ["2026-03-10T10:00:00.250"],
        "postura": ["supino"],
    })
    inserir_grade(db, df, PACIENTE)

    with capture_logs() as eventos:
        inserir_grade(db, df, PACIENTE)

    registros = [e for e in eventos if e.get("event") == "grade_amostras_ignoradas"]
    assert registros, "o descarte passou sem deixar registro"
    assert registros[0]["ignoradas"] == 1, "o registro nao diz QUANTAS amostras sumiram"


def test_migracao_preserva_grade_de_banco_legado(tmp_path):
    """Bancos que ja rodam tem a grade sem `ts_ms`. O backfill e exato: as
    linhas existentes sao todas de segundo cheio."""
    caminho = str(tmp_path / "legado.db")
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE pacientes (id TEXT PRIMARY KEY);
        INSERT INTO pacientes(id) VALUES ('PAC-0001');
        CREATE TABLE grade (
            paciente_id TEXT, ts TEXT, postura TEXT, confianca REAL,
            PRIMARY KEY (paciente_id, ts));
        INSERT INTO grade VALUES ('PAC-0001','2026-01-05T08:00:00','supino',0.9);
        INSERT INTO grade VALUES ('PAC-0001','2026-01-05T09:00:00','prono',0.8);
        """
    )
    conn.commit()
    conn.close()

    criar_esquema(caminho)

    linhas = _grade(caminho)
    assert [ts for ts, _, _ in linhas] == [
        "2026-01-05T08:00:00",
        "2026-01-05T09:00:00",
    ]
    esperado = int(datetime(2026, 1, 5, 8, tzinfo=timezone.utc).timestamp() * 1000)
    assert linhas[0][1] == esperado, "o backfill de ts_ms saiu deslocado do fuso"
