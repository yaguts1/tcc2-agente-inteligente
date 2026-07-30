"""A trilha registra QUEM foi afetado por uma operacao em lote.

O `AuditoriaMiddleware` extraia o `paciente_id` do CAMINHO da requisicao. As
rotas de lote (`POST /api/frontend/alerts/batch/*`) carregam os identificadores
no CORPO, entao elas eram auditadas com `paciente_id = NULL`.

O efeito e pior do que "faltava um campo". A trilha nao parecia incompleta: as
linhas existiam, com usuario, rota, IP, horario e status. So a coluna que
importa vinha vazia — e justamente na operacao de escrita de MAIOR VOLUME do
sistema, a que o botao "selecionar tudo" dispara. A pergunta do Art. 48 da LGPD,
"quais titulares foram afetados", era inrespondivel exatamente onde mais gente e
afetada de uma vez.
"""

from datetime import datetime

import pytest

from interface.db_core import connect

BASE = datetime(2026, 6, 1, 8, 0, 0)


@pytest.fixture
def cliente_autenticado(app_isolado, cabecalho_auth):
    """TestClient com sessao real. O middleware de auditoria le o JWT, entao
    token forjado nao serve — a linha sairia sem usuario."""
    from fastapi.testclient import TestClient

    return TestClient(app_isolado.app, headers=cabecalho_auth())


@pytest.fixture
def cenario(app_isolado):
    """Tres pacientes, cada um com um alerta aberto."""
    from interface.alert_id import montar_alert_id

    inicio = BASE.strftime("%Y-%m-%dT%H:%M:%S")
    ids = []
    with connect(app_isolado.db_path) as conn:
        for i in range(3):
            pid = f"PAC-{i + 1:04d}"
            conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (pid,))
            conn.execute(
                "INSERT INTO paciente_fichas"
                " (paciente_id, nome, perfil, cama_id, created_at, updated_at, unidade_id)"
                " VALUES (?,?,'alto',?,?,?,1)",
                (pid, f"Paciente {i}", f"20{i}-A", inicio, inicio),
            )
            conn.execute(
                "INSERT INTO alertas (paciente_id, inicio, tipo, perfil, janela_min, status)"
                " VALUES (?,?,'imobilidade','alto',60,'aberto')",
                (pid, inicio),
            )
            ids.append(montar_alert_id(pid, inicio))
    return ids


def _linhas_de_auditoria(db_path: str, rota_contem: str) -> list[dict]:
    with connect(db_path) as conn:
        return [
            dict(linha)
            for linha in conn.execute(
                "SELECT paciente_id, rota, status, usuario, detalhe FROM auditoria"
                " WHERE rota LIKE ? ORDER BY id",
                (f"%{rota_contem}%",),
            )
        ]


def test_lote_audita_um_paciente_por_linha(cliente_autenticado, app_isolado, cenario):
    """O defeito central. Antes: uma linha com `paciente_id = NULL`."""
    resposta = cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge", json={"alert_ids": cenario}
    )
    assert resposta.status_code == 200, resposta.text

    linhas = _linhas_de_auditoria(app_isolado.db_path, "batch/acknowledge")
    afetados = {linha["paciente_id"] for linha in linhas}

    assert afetados == {"PAC-0001", "PAC-0002", "PAC-0003"}, (
        f"a trilha registrou {afetados} — 'quais titulares foram afetados' "
        "continua sem resposta"
    )
    assert None not in afetados


def test_a_linha_diz_que_foi_lote(cliente_autenticado, app_isolado, cenario):
    """Trinta fechamentos de um clique em "selecionar tudo" nao podem ser
    indistinguiveis de trinta decisoes individuais. Essa diferenca e o cerne de
    "acao em lote fabrica documentacao": o prontuario registra reposicionamento
    para trinta pacientes, e nada distingue o lote legitimo da limpeza de tela.
    """
    cliente_autenticado.post(
        "/api/frontend/alerts/batch/complete",
        json={"alert_ids": cenario, "motivo": "reposicionado"},
    )

    linhas = _linhas_de_auditoria(app_isolado.db_path, "batch/complete")
    assert linhas, "nada foi auditado"
    for linha in linhas:
        assert linha["detalhe"] and "lote" in linha["detalhe"], (
            f"linha sem marca de lote: {linha}"
        )
        assert "3" in linha["detalhe"], "o tamanho do lote nao foi registrado"


def test_operacao_por_paciente_continua_auditando_como_antes(
    cliente_autenticado, app_isolado, cenario
):
    """A fonte pelo CAMINHO nao pode ter sido substituida, so complementada.

    Ela cobre todas as rotas `/api/pacientes/{id}/...`, que sao a maioria.
    """
    cliente_autenticado.get("/api/pacientes/PAC-0001/timeline")

    with connect(app_isolado.db_path) as conn:
        linhas = [
            dict(x)
            for x in conn.execute(
                "SELECT paciente_id FROM auditoria WHERE rota LIKE '%PAC-0001%'"
            )
        ]
    assert linhas, "a rota por paciente deixou de ser auditada"
    assert all(x["paciente_id"] == "PAC-0001" for x in linhas)


def test_lote_que_falha_ainda_registra_sobre_quem_foi(
    cliente_autenticado, app_isolado, cenario
):
    """Tentativa que da errado e tao auditavel quanto a que da certo — o
    `status` da linha distingue as duas. Declarar os pacientes so DEPOIS do
    sucesso deixaria justamente o acesso suspeito fora da trilha.
    """
    from interface.alert_id import montar_alert_id

    inexistente = montar_alert_id("PAC-9999", BASE.strftime("%Y-%m-%dT%H:%M:%S"))
    cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge",
        json={"alert_ids": [*cenario, inexistente]},
    )

    linhas = _linhas_de_auditoria(app_isolado.db_path, "batch/acknowledge")
    afetados = {linha["paciente_id"] for linha in linhas}
    assert "PAC-9999" in afetados, (
        "a tentativa sobre um paciente inexistente nao foi registrada"
    )


def test_alert_id_malformado_nao_derruba_a_operacao(
    cliente_autenticado, app_isolado, cenario
):
    """A trilha nunca pode ser o motivo de uma operacao clinica falhar."""
    resposta = cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge",
        json={"alert_ids": [*cenario, "isto-nao-e-um-alert-id"]},
    )
    assert resposta.status_code == 200, resposta.text

    afetados = {
        linha["paciente_id"]
        for linha in _linhas_de_auditoria(app_isolado.db_path, "batch/acknowledge")
    }
    assert {"PAC-0001", "PAC-0002", "PAC-0003"} <= afetados


# ---------------------------------------------------------------------------
# Teto do lote
# ---------------------------------------------------------------------------


def test_lote_gigante_e_recusado(cliente_autenticado):
    """Sem teto, um POST com 10.000 ids produz 10.000 registros de
    reposicionamento em prontuario a partir de uma requisicao.

    O limite e 100 — o tamanho da pagina que a tela carrega, entao "selecionar
    tudo" sobre uma pagina cheia continua funcionando.
    """
    from interface.alert_id import montar_alert_id

    inicio = BASE.strftime("%Y-%m-%dT%H:%M:%S")
    demais = [montar_alert_id(f"PAC-{i:04d}", inicio) for i in range(101)]

    resposta = cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge", json={"alert_ids": demais}
    )
    assert resposta.status_code == 422, resposta.status_code


def test_pagina_cheia_continua_passando(cliente_autenticado, app_isolado, cenario):
    """O teto nao pode quebrar o fluxo real: 100 e exatamente o `limit` da
    listagem que alimenta o "selecionar tudo"."""
    from interface.alert_id import montar_alert_id

    inicio = BASE.strftime("%Y-%m-%dT%H:%M:%S")
    cem = [montar_alert_id(f"PAC-{i:04d}", inicio) for i in range(100)]

    resposta = cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge", json={"alert_ids": cem}
    )
    assert resposta.status_code == 200, resposta.text


def test_lote_vazio_e_erro_e_nao_sucesso_silencioso(cliente_autenticado):
    """Respondia 200 com zero processados, indistinguivel de sucesso — a tela
    mostraria "pronto" sem nada ter acontecido."""
    resposta = cliente_autenticado.post(
        "/api/frontend/alerts/batch/acknowledge", json={"alert_ids": []}
    )
    assert resposta.status_code == 422, resposta.status_code
