"""As foreign keys do schema eram decoracao.

No SQLite `PRAGMA foreign_keys` e POR CONEXAO e vem DESLIGADA. Nenhuma conexao
do projeto a ligava, entao todo `REFERENCES` e todo `ON DELETE CASCADE` do
migrations/0001_baseline.sql nunca foi avaliado: o banco aceitava filho sem pai,
e as remocoes so funcionavam porque `repositories/pacientes.py` apaga tabela por
tabela na mao.

A prova de que ninguem checava: `interface/dao_agenda.py` declarava
`REFERENCES fichas_paciente(paciente_id)` — tabela que nunca existiu (a real e
`paciente_fichas`). Uma FK para uma tabela inexistente conviveu com o projeto
sem nunca dar erro, porque nunca foi lida.
"""

import sqlite3

import pytest

from interface.db_core import connect, criar_esquema


@pytest.fixture
def db(tmp_path):
    caminho = str(tmp_path / "t.db")
    criar_esquema(caminho)
    return caminho


def test_pragma_esta_ligado_na_conexao_do_app(db):
    with connect(db) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_filho_sem_pai_e_recusado(db):
    with pytest.raises(sqlite3.IntegrityError):
        with connect(db) as conn:
            conn.execute(
                "INSERT INTO paciente_fichas(paciente_id,nome,perfil,created_at,updated_at)"
                " VALUES ('PAC-NAO-EXISTE','Fantasma','alto','2026-01-01','2026-01-01')"
            )


def test_agenda_aponta_para_tabela_que_existe(db):
    """A FK quebrada de `agendas_paciente` so nao explodia porque ninguem a lia."""
    with connect(db) as conn:
        destinos = {
            linha[2] for linha in conn.execute("PRAGMA foreign_key_list(agendas_paciente)")
        }
        tabelas = {
            linha[0]
            for linha in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert destinos, "agendas_paciente ficou sem FK nenhuma"
    assert destinos <= tabelas, f"FK aponta para tabela inexistente: {destinos - tabelas}"


def test_agenda_de_paciente_inexistente_e_recusada(db):
    with connect(db) as conn:
        conn.execute("INSERT INTO pacientes(id) VALUES ('PAC-0001')")

    with connect(db) as conn:
        conn.execute(
            "INSERT INTO agendas_paciente(paciente_id,tipo,hora_inicio,hora_fim)"
            " VALUES ('PAC-0001','cirurgia','08:00','12:00')"
        )

    with pytest.raises(sqlite3.IntegrityError):
        with connect(db) as conn:
            conn.execute(
                "INSERT INTO agendas_paciente(paciente_id,tipo,hora_inicio,hora_fim)"
                " VALUES ('PAC-SUMIU','cirurgia','08:00','12:00')"
            )


def test_migracao_preserva_agendas_de_banco_legado(tmp_path):
    """Bancos que ja rodam tem a tabela com a FK quebrada, criada no import.

    O rebuild precisa preservar os ids (a tela referencia agenda por id) e
    descartar a configuracao orfa, que violaria a FK nova e abortaria tudo.
    """
    caminho = str(tmp_path / "legado.db")
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE pacientes (id TEXT PRIMARY KEY);
        INSERT INTO pacientes(id) VALUES ('PAC-0001');
        CREATE TABLE agendas_paciente (
          id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id TEXT NOT NULL,
          tipo TEXT NOT NULL, descricao TEXT, dias_semana TEXT, hora_inicio TEXT,
          hora_fim TEXT, data_inicio TEXT, data_fim TEXT, modo TEXT DEFAULT 'suprimir',
          reducao_janela_min INTEGER, ativo BOOLEAN DEFAULT 1,
          created_at TEXT, updated_at TEXT,
          FOREIGN KEY (paciente_id) REFERENCES fichas_paciente(paciente_id));
        INSERT INTO agendas_paciente(id,paciente_id,tipo,hora_inicio,hora_fim)
          VALUES (7,'PAC-0001','cirurgia','08:00','12:00');
        INSERT INTO agendas_paciente(id,paciente_id,tipo,hora_inicio,hora_fim)
          VALUES (8,'PAC-SUMIU','refeicao','12:00','13:00');
        """
    )
    conn.commit()
    conn.close()

    criar_esquema(caminho)

    with connect(caminho) as conn:
        linhas = conn.execute(
            "SELECT id, paciente_id, tipo FROM agendas_paciente ORDER BY id"
        ).fetchall()

    assert [tuple(linha) for linha in linhas] == [(7, "PAC-0001", "cirurgia")], (
        "a agenda valida precisa sobreviver com o mesmo id; a orfa precisa sair"
    )
