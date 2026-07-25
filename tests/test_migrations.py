"""Testes para o runner de migrations (migrations/runner.py)."""
from __future__ import annotations

import sqlite3


from migrations.runner import upgrade, versao_schema


def test_versao_inicial_e_zero(tmp_path):
    db_path = tmp_path / "novo.db"
    assert versao_schema(str(db_path)) == 0


def test_upgrade_aplica_baseline_e_cria_tabelas(tmp_path):
    db_path = tmp_path / "dados.db"
    versao_final = upgrade(str(db_path))

    assert versao_final >= 1
    assert versao_schema(str(db_path)) == versao_final

    conn = sqlite3.connect(str(db_path))
    try:
        tabelas = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    esperadas = {
        "pacientes", "paciente_fichas", "paciente_rotinas", "paciente_documentos",
        "grade", "eventos", "alertas", "timeline_events", "devices",
        "device_assignments", "paciente_cama_history", "device_events", "users",
        "schema_version",
    }
    assert esperadas.issubset(tabelas)


def test_upgrade_e_idempotente(tmp_path):
    db_path = tmp_path / "dados.db"
    v1 = upgrade(str(db_path))
    v2 = upgrade(str(db_path))  # rodar de novo não deve falhar nem reaplicar

    assert v1 == v2

    conn = sqlite3.connect(str(db_path))
    try:
        aplicadas = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    # cada migration só aparece uma vez em schema_version, mesmo chamando upgrade() 2x
    assert aplicadas == v1


def test_grade_tem_coluna_confianca_e_users_tem_role(tmp_path):
    """Regressão: essas colunas eram adicionadas via ALTER TABLE ad-hoc
    fora do schema base; agora devem vir direto do baseline."""
    db_path = tmp_path / "dados.db"
    upgrade(str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        colunas_grade = {row[1] for row in conn.execute("PRAGMA table_info(grade)")}
        colunas_users = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    finally:
        conn.close()

    assert "confianca" in colunas_grade
    assert "role" in colunas_users


def test_aplica_migrations_subsequentes_em_ordem(tmp_path, monkeypatch):
    """Simula uma migration nova (0002) numa pasta isolada e confirma que o
    runner aplica em ordem, incrementalmente, sem re-tocar a 0001."""
    import migrations.runner as runner_module

    migrations_dir = tmp_path / "migrations_fake"
    migrations_dir.mkdir()
    (migrations_dir / "0001_baseline.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (migrations_dir / "0002_add_t2.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )

    monkeypatch.setattr(runner_module, "_MIGRATIONS_DIR", migrations_dir)

    db_path = tmp_path / "fake.db"
    versao = runner_module.upgrade(str(db_path))
    assert versao == 2

    conn = sqlite3.connect(str(db_path))
    try:
        tabelas = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        versoes_aplicadas = [
            row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")
        ]
    finally:
        conn.close()

    assert {"t1", "t2"}.issubset(tabelas)
    assert versoes_aplicadas == [1, 2]

    # Adicionar uma 0003 e rodar upgrade de novo só aplica a nova
    (migrations_dir / "0003_add_t3.sql").write_text(
        "CREATE TABLE t3 (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    versao2 = runner_module.upgrade(str(db_path))
    assert versao2 == 3
