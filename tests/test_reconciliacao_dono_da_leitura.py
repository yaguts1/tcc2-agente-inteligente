"""De quem e esta leitura?

Uma amostra que chega sem `paciente_id` fica numa fila (`device_events`) e e
reconciliada depois. A reconciliacao resolvia o dono com
`obter_ficha_por_cama(cama_id)` — o ocupante ATUAL do leito, ignorando o
instante em que a leitura foi feita.

Uma leitura orfa das 02:00 do leito 201-A, reconciliada as 06:00 depois de o
leito trocar de paciente, ia para o prontuario do NOVO ocupante. As duas
consequencias sao as piores possiveis aqui: quem entrou recebe imobilidade que
nao e dele (e alertas calculados sobre isso), e quem saiu fica com um buraco no
historico. Nada indica nenhum dos dois.

O caminho principal (`POST /api/eventos`) sempre resolveu pelo timestamp, com
`resolver_paciente_por_device_em`. As duas portas de entrada divergiam sobre de
quem e o dado.
"""

import sqlite3
from datetime import timedelta

import pytest

from interface.db_core import criar_esquema, utc_now_iso
from interface.repositories.devices import (
    inserir_device_event,
    resolver_paciente_por_cama_em,
)
from interface.tempo import agora_utc_naive

AGORA = agora_utc_naive()
T_LEITURA = AGORA - timedelta(hours=4)   # Ana no leito
T_TROCA = AGORA - timedelta(hours=1)     # Ana sai, Bruno entra
CAMA = "201-A"


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _montar(tmp_path, *, com_assignment=True, com_historico=True):
    """Leito 201-A: Ana ate T_TROCA, Bruno depois. Leitura orfa em T_LEITURA."""
    db = str(tmp_path / "t.db")
    criar_esquema(db)
    agora_iso = utc_now_iso()

    with sqlite3.connect(db) as conn:
        for pid in ("PAC-A", "PAC-B"):
            conn.execute("INSERT INTO pacientes(id) VALUES (?)", (pid,))
        # A ficha diz que quem ocupa o leito AGORA e o Bruno.
        conn.execute(
            "INSERT INTO paciente_fichas(paciente_id,nome,perfil,cama_id,created_at,updated_at)"
            " VALUES ('PAC-A','Ana','alto',NULL,?,?)",
            (agora_iso, agora_iso),
        )
        conn.execute(
            "INSERT INTO paciente_fichas(paciente_id,nome,perfil,cama_id,created_at,updated_at)"
            " VALUES ('PAC-B','Bruno','alto',?,?,?)",
            (CAMA, agora_iso, agora_iso),
        )
        if com_assignment:
            conn.execute(
                "INSERT INTO device_assignments(device_id,paciente_id,start_ts,start_ms,end_ts,end_ms)"
                " VALUES (?,?,?,?,?,?)",
                ("dev-1", "PAC-A", str(T_LEITURA), _ms(T_LEITURA - timedelta(hours=1)),
                 str(T_TROCA), _ms(T_TROCA)),
            )
        if com_historico:
            conn.execute(
                "INSERT INTO paciente_cama_history(paciente_id,cama_id,start_ts,start_ms,end_ts,end_ms)"
                " VALUES (?,?,?,?,?,?)",
                ("PAC-A", CAMA, str(T_LEITURA), _ms(T_LEITURA - timedelta(hours=2)),
                 str(T_TROCA), _ms(T_TROCA)),
            )
            conn.execute(
                "INSERT INTO paciente_cama_history(paciente_id,cama_id,start_ts,start_ms)"
                " VALUES (?,?,?,?)",
                ("PAC-B", CAMA, str(T_TROCA), _ms(T_TROCA)),
            )

    ts_iso = T_LEITURA.strftime("%Y-%m-%dT%H:%M:%S")
    inserir_device_event(db, "dev-1", ts_iso, _ms(T_LEITURA), {
        "device_id": "dev-1", "cama_id": CAMA, "postura": "supino",
        "confianca": 0.9, "amostra_ms": 300000, "ts_utc": ts_iso,
    })
    return db


def _dono_da_amostra(db):
    with sqlite3.connect(db) as conn:
        linha = conn.execute("SELECT paciente_id FROM grade").fetchone()
    return linha[0] if linha else None


@pytest.fixture
def reconciliador(monkeypatch):
    def _run(db):
        import interface.services.ingestao_service as ing

        monkeypatch.setattr(ing, "DB_PATH", db)
        return ing._do_reconcile()

    return _run


def test_leitura_vai_para_quem_ocupava_o_leito_na_hora(tmp_path, reconciliador):
    """O caso que estava errado: leitura da Ana era gravada no Bruno."""
    db = _montar(tmp_path)

    resultado = reconciliador(db)

    assert resultado["processed"] == 1
    assert _dono_da_amostra(db) == "PAC-A", (
        "a leitura foi para o prontuario do paciente errado"
    )


def test_historico_de_leito_resolve_quando_nao_ha_vinculo_de_device(tmp_path, reconciliador):
    """`paciente_cama_history` ja era mantido e nada o consultava."""
    db = _montar(tmp_path, com_assignment=False)

    reconciliador(db)

    assert _dono_da_amostra(db) == "PAC-A"


def test_sem_saber_de_quem_e_a_leitura_fica_na_fila(tmp_path, reconciliador):
    """Buraco no historico e ruim; atribuir ao paciente errado e pior.

    Dado clinico falso e indistinguivel do verdadeiro depois de gravado.
    """
    db = _montar(tmp_path, com_assignment=False, com_historico=False)

    resultado = reconciliador(db)

    assert resultado["processed"] == 0
    assert resultado["skipped"] == 1
    assert _dono_da_amostra(db) is None, "atribuiu a leitura sem saber de quem era"

    with sqlite3.connect(db) as conn:
        pendentes = conn.execute("SELECT COUNT(*) FROM device_events").fetchone()[0]
    assert pendentes == 1, "o evento saiu da fila sem ter sido reconciliado"


def test_reconciliacao_concorda_com_a_ingestao_direta(tmp_path):
    """As duas portas de entrada nao podem divergir sobre de quem e o dado."""
    from interface.repositories.devices import resolver_paciente_por_device_em

    db = _montar(tmp_path)

    assert resolver_paciente_por_device_em(db, "dev-1", _ms(T_LEITURA)) == "PAC-A"
    assert resolver_paciente_por_cama_em(db, CAMA, _ms(T_LEITURA)) == "PAC-A"


def test_resolvedor_de_leito_respeita_a_troca(tmp_path):
    """Depois da troca, o mesmo leito pertence ao outro paciente."""
    db = _montar(tmp_path)

    assert resolver_paciente_por_cama_em(db, CAMA, _ms(T_LEITURA)) == "PAC-A"
    assert resolver_paciente_por_cama_em(db, CAMA, _ms(AGORA)) == "PAC-B"
    assert resolver_paciente_por_cama_em(db, CAMA, _ms(T_LEITURA - timedelta(days=5))) is None
