"""Unit tests for alert insertion and selection helpers in DAO."""
from __future__ import annotations

from datetime import datetime, timedelta

from interface.dao import criar_esquema, inserir_alertas, selecionar_alertas_janela


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def test_inserir_e_selecionar_alertas(tmp_path) -> None:
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)

    now = datetime.now().replace(microsecond=0)
    a1_start = now - timedelta(hours=2)
    a2_start = now - timedelta(hours=1)

    alertas = [
        {
            "paciente_id": "TST-1",
            "inicio": _iso(a1_start),
            "fim": None,
            "tipo": "imobilidade",
            "perfil": "medio",
            "janela_min": 60,
            "status": "aberto",
            "duracao_min": None,
        },
        {
            "paciente_id": "TST-1",
            "inicio": _iso(a2_start),
            "fim": None,
            "tipo": "imobilidade",
            "perfil": "baixo",
            "janela_min": 30,
            "status": "aberto",
            "duracao_min": None,
        },
    ]

    # insert
    inserted = inserir_alertas(db_path, alertas)
    assert inserted == len(alertas)

    # selecting with a wide window should return both
    results = selecionar_alertas_janela(db_path, horas=24)
    assert isinstance(results, list)
    # there should be at least the two we inserted
    found = {(r.get("paciente_id"), r.get("inicio")) for r in results}
    expected = {("TST-1", _iso(a1_start)), ("TST-1", _iso(a2_start))}
    assert expected.issubset(found)

    # inserting same alerts again should be idempotent
    assert inserir_alertas(db_path, alertas) == 0
