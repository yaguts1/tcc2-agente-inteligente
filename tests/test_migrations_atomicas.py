"""Uma migration que falha no meio não pode deixar metade aplicada.

O `runner.upgrade` usava `with conn: conn.executescript(sql)` — e o comentário na
linha dizia "transacao: commit no fim do bloco, rollback se falhar". Não era
verdade. `executescript` **emite um COMMIT implícito antes** de rodar e depois
executa os statements sem controle de transação próprio; o `with conn:` não
envolvia nada.

O QUE ISSO CUSTA
----------------
`0010_unidades.sql` tem 15 statements, incluindo `INSERT`/`UPDATE` de backfill. Se
o nono falhar, os oito primeiros já estão commitados e o
`INSERT INTO schema_version` nunca roda. Na subida seguinte o runner reaplica a
migration **do início** — `duplicate column name` — e falha de novo, para sempre.
Schema travado num estado parcial, sem caminho de volta automático.

E `interface/web.py` engolia a exceção (`schema_nao_garantido`) e subia assim: o
healthcheck respondia 200 e o proxy publicava a instância, servindo e gravando
dado clínico contra um schema meio migrado.

Estes testes usam migrations de mentira num diretório temporário — o runner é
apontado para lá — para poder falhar de propósito sem tocar nas 18 reais.
"""

from __future__ import annotations

import sqlite3

import pytest

from migrations import runner


@pytest.fixture()
def migrations_falsas(tmp_path, monkeypatch):
    """Aponta o runner para um diretório próprio de migrations."""
    pasta = tmp_path / "migrations"
    pasta.mkdir()
    monkeypatch.setattr(runner, "_MIGRATIONS_DIR", pasta)
    return pasta


def _colunas(db_path: str, tabela: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")]


def _tabelas(db_path: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            linha[0]
            for linha in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


class TestFalhaNoMeioNaoDeixaResto:
    def test_statement_invalido_desfaz_os_anteriores(self, migrations_falsas, tmp_path):
        """O caso do `0010_unidades.sql`: vários statements, um quebra no meio."""
        (migrations_falsas / "0001_ok.sql").write_text(
            "CREATE TABLE base (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )
        (migrations_falsas / "0002_quebra.sql").write_text(
            "ALTER TABLE base ADD COLUMN a TEXT;\n"
            "ALTER TABLE base ADD COLUMN b TEXT;\n"
            "ALTER TABLE inexistente ADD COLUMN c TEXT;\n",  # <- explode aqui
            encoding="utf-8",
        )
        db = str(tmp_path / "d.db")

        with pytest.raises(sqlite3.Error):
            runner.upgrade(db)

        colunas = _colunas(db, "base")
        assert "a" not in colunas and "b" not in colunas, (
            f"a migration deixou colunas pela metade: {colunas}. Na próxima subida o "
            "runner reaplica do início e falha com 'duplicate column name' para sempre."
        )

    def test_tabela_criada_antes_da_falha_nao_persiste(self, migrations_falsas, tmp_path):
        (migrations_falsas / "0001_quebra.sql").write_text(
            "CREATE TABLE sobrou (id INTEGER);\n" "ISTO NAO E SQL;\n", encoding="utf-8"
        )
        db = str(tmp_path / "d.db")

        with pytest.raises(sqlite3.Error):
            runner.upgrade(db)

        assert "sobrou" not in _tabelas(db)

    def test_versao_nao_avanca_quando_falha(self, migrations_falsas, tmp_path):
        """Sem isto, o schema fica adiante do que a versão declara — e a próxima
        subida pula a migration que não terminou."""
        (migrations_falsas / "0001_ok.sql").write_text(
            "CREATE TABLE t (id INTEGER);", encoding="utf-8"
        )
        (migrations_falsas / "0002_quebra.sql").write_text("SELECT nao_existe();", encoding="utf-8")
        db = str(tmp_path / "d.db")

        with pytest.raises(sqlite3.Error):
            runner.upgrade(db)

        assert runner.versao_schema(db) == 1, "a versão só pode avançar com a migration inteira"


class TestOCaminhoFeliz:
    def test_aplica_em_ordem_e_registra_versao(self, migrations_falsas, tmp_path):
        (migrations_falsas / "0001_a.sql").write_text(
            "CREATE TABLE a (id INTEGER);", encoding="utf-8"
        )
        (migrations_falsas / "0002_b.sql").write_text(
            "CREATE TABLE b (id INTEGER);", encoding="utf-8"
        )
        db = str(tmp_path / "d.db")

        assert runner.upgrade(db) == 2
        assert {"a", "b"} <= _tabelas(db)

    def test_reaplicar_e_no_op(self, migrations_falsas, tmp_path):
        (migrations_falsas / "0001_a.sql").write_text(
            "CREATE TABLE a (id INTEGER);", encoding="utf-8"
        )
        db = str(tmp_path / "d.db")

        assert runner.upgrade(db) == 1
        assert runner.upgrade(db) == 1, "rodar de novo não pode reaplicar"

    def test_migration_com_varios_statements_aplica_todos(self, migrations_falsas, tmp_path):
        """Envolver em transação não pode quebrar o caso normal de script longo —
        é o formato de todas as 18 migrations reais."""
        (migrations_falsas / "0001_varios.sql").write_text(
            "CREATE TABLE m (id INTEGER PRIMARY KEY, nome TEXT);\n"
            "INSERT INTO m (nome) VALUES ('um');\n"
            "INSERT INTO m (nome) VALUES ('dois');\n"
            "CREATE INDEX idx_m_nome ON m(nome);\n"
            "UPDATE m SET nome = upper(nome);\n",
            encoding="utf-8",
        )
        db = str(tmp_path / "d.db")

        runner.upgrade(db)

        with sqlite3.connect(db) as conn:
            nomes = [linha[0] for linha in conn.execute("SELECT nome FROM m ORDER BY id")]
        assert nomes == ["UM", "DOIS"]


class TestAsMigrationsReais:
    def test_as_18_aplicam_do_zero(self, tmp_path):
        """Guarda contra a correção quebrar o esquema de verdade: nenhuma das
        migrations reais pode depender do autocommit que existia antes."""
        db = str(tmp_path / "real.db")

        versao = runner.upgrade(db)

        assert versao >= 18
        tabelas = _tabelas(db)
        for esperada in ("pacientes", "grade", "alertas", "eventos", "schema_version"):
            assert esperada in tabelas


class TestOStartupNaoSobeComSchemaQuebrado:
    """Falhar no boot é ruidoso e recuperável; subir quebrado é silencioso.

    O lifespan engolia a exceção com `logger.warning("schema_nao_garantido")` e
    seguia. O container ficava `healthy`, o proxy publicava a instância, e ela
    servia e gravava dado clínico contra um schema meio migrado.
    """

    def test_lifespan_propaga_falha_de_schema(self, monkeypatch, tmp_path):
        import importlib

        from fastapi.testclient import TestClient

        monkeypatch.setenv("UPP_DB_PATH", str(tmp_path / "x.db"))
        web = importlib.import_module("interface.web")

        def explodir(_db_path):
            raise sqlite3.OperationalError("duplicate column name: unidade_id")

        monkeypatch.setattr(web, "criar_esquema", explodir)

        with pytest.raises(RuntimeError, match="schema"):
            with TestClient(web.app):
                pass
