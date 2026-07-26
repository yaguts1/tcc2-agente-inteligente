"""A trilha de auditoria precisa denunciar quem mexer nela.

Ela vive no MESMO SQLite que audita. Sem encadeamento, um UPDATE apaga o
registro de um acesso indevido e nada no sistema fica diferente — a trilha era
confiavel exatamente ate o momento em que alguem tivesse motivo para
adultera-la, que e o unico momento em que ela precisa ser confiavel.

Cada teste aqui adultera o banco DIRETAMENTE, por fora da aplicacao, que e como
a adulteracao aconteceria de verdade. Verificar apenas o caminho feliz nao
provaria nada.
"""

import sqlite3

import pytest

from interface.repositories.auditoria import (
    expurgar_anteriores_a,
    registrar,
    verificar_integridade,
)


@pytest.fixture
def db(app_isolado):
    caminho = app_isolado.db_path
    for i in range(5):
        registrar(
            caminho,
            metodo="GET",
            rota=f"/api/pacientes/PAC-{i}",
            status=200,
            usuario="enfermeira",
            papel="staff",
            paciente_id=f"PAC-{i}",
        )
    return caminho


def test_trilha_intacta_verifica(db):
    resultado = verificar_integridade(db)

    assert resultado["integra"] is True
    assert resultado["confiavel"] is True
    assert resultado["verificadas"] == 5
    assert resultado["problemas"] == []


def test_trilha_sem_elo_nenhum_nao_passa_por_confiavel():
    """`integra` sozinho e enganoso: sem nada verificado, nada e detectado.

    Uma trilha inteiramente anterior ao encadeamento nao tem adulteracao
    DETECTADA — o que e bem diferente de nao ter adulteracao. Quem olhasse so
    esse campo leria "esta tudo bem" sobre uma trilha desprotegida.
    """
    from interface.auditoria_cadeia import verificar

    antigas = [{"id": i, "ts": "2026-01-01T00:00:00", "acao": "GET /x"} for i in range(5)]
    resultado = verificar(antigas)

    assert resultado["integra"] is True, "nao ha o que acusar: nada foi verificado"
    assert resultado["verificadas"] == 0
    assert resultado["sem_protecao"] == 5
    assert resultado["confiavel"] is False, (
        "uma trilha sem nenhum elo nao pode ser apresentada como confiavel"
    )


def test_denuncia_registro_editado(db):
    """O caso classico: apagar o proprio rastro trocando o usuario."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auditoria SET usuario = 'outra_pessoa' WHERE paciente_id = 'PAC-2'"
        )

    resultado = verificar_integridade(db)

    assert resultado["integra"] is False
    tipos = {p["tipo"] for p in resultado["problemas"]}
    assert "conteudo_alterado" in tipos


def test_denuncia_registro_apagado(db):
    """Apagar a linha inteira quebra o elo da seguinte."""
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM auditoria WHERE paciente_id = 'PAC-2'")

    resultado = verificar_integridade(db)

    assert resultado["integra"] is False
    assert any(p["tipo"] == "elo_quebrado" for p in resultado["problemas"])


def test_denuncia_registro_inserido_no_meio(db):
    """Forjar um acesso que nunca aconteceu tambem quebra a cadeia."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO auditoria (ts, ts_ms, usuario, acao, metodo, rota, status, negado)"
            " VALUES ('2026-01-01T00:00:00', 1, 'forjado', 'GET /x', 'GET', '/x', 200, 0)"
        )

    resultado = verificar_integridade(db)

    # A linha forjada nao tem hash — e reportada como sem protecao, nunca como
    # verificada. Um registro sem elo jamais pode passar por autentico.
    assert resultado["sem_protecao"] == 1
    assert resultado["verificadas"] == 5


def test_denuncia_detalhe_adulterado(db):
    """Campos do JSON de contexto tambem entram no hash."""
    registrar(db, metodo="POST", rota="/api/x", status=200, detalhe={"antes": "valor"})
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auditoria SET detalhe = '{\"antes\": \"outro\"}' WHERE detalhe IS NOT NULL"
        )

    resultado = verificar_integridade(db)

    assert resultado["integra"] is False


def test_denuncia_status_adulterado(db):
    """Transformar um 403 em 200 esconderia justamente a tentativa indevida."""
    registrar(db, metodo="GET", rota="/api/pacientes/PAC-9", status=403, usuario="intruso")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE auditoria SET status = 200, negado = 0 WHERE usuario = 'intruso'")

    resultado = verificar_integridade(db)

    assert resultado["integra"] is False
    assert any(p["tipo"] == "conteudo_alterado" for p in resultado["problemas"])


def test_linhas_anteriores_a_migracao_nao_passam_por_protegidas(db):
    """Preencher a cadeia retroativamente daria uma garantia falsa.

    Uma linha sem hash e reportada como `sem_protecao`, nunca como verificada:
    ela e anterior ao encadeamento e ninguem pode afirmar que nao foi alterada.
    """
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auditoria SET hash = NULL, hash_anterior = NULL WHERE paciente_id = 'PAC-0'"
        )

    resultado = verificar_integridade(db)

    assert resultado["sem_protecao"] == 1
    assert resultado["verificadas"] == 4


def test_expurgo_legitimo_fica_registrado(app_isolado, monkeypatch):
    """Expurgo por retencao apaga o inicio da cadeia — e precisa dizer isso.

    Sem registro, a remocao e indistinguivel de adulteracao.
    """
    from datetime import datetime, timedelta

    import interface.repositories.auditoria as mod

    # Relogio controlado: as entradas nascem em dias diferentes, para o corte
    # por retencao separar de verdade. Com o relogio real elas caem todas no
    # mesmo milissegundo. O timestamp entra no hash, entao ele precisa ser o
    # verdadeiro no momento da gravacao — mexer nele depois quebraria a cadeia,
    # e com razao.
    base = datetime(2026, 1, 1, 12, 0, 0)
    instantes = iter([base + timedelta(days=d) for d in range(5)])
    monkeypatch.setattr(mod, "agora_utc_naive", lambda: next(instantes))

    db = app_isolado.db_path
    for i in range(5):
        registrar(db, metodo="GET", rota=f"/api/pacientes/PAC-{i}", status=200)

    monkeypatch.setattr(mod, "agora_utc_naive", lambda: base + timedelta(days=10))
    with sqlite3.connect(db) as conn:
        corte = conn.execute("SELECT ts_ms FROM auditoria ORDER BY id LIMIT 1 OFFSET 2").fetchone()[0]

    removidas = expurgar_anteriores_a(db, corte)
    assert removidas == 2

    from interface.repositories.auditoria import consultar

    purgas = [e for e in consultar(db) if e["metodo"] == "PURGE"]
    assert len(purgas) == 1, "o expurgo nao ficou registrado na propria trilha"
    assert purgas[0]["detalhe"]["removidas"] == 2

    # A cadeia restante continua verificavel: o expurgo cortou o comeco, nao o meio.
    assert verificar_integridade(db)["integra"] is True


def test_chave_muda_o_hash(monkeypatch):
    """Com UPP_AUDIT_KEY, os elos viram HMAC — nao da para recalcular sem a chave."""
    from interface import auditoria_cadeia as cadeia

    registro = {"ts": "2026-01-01T00:00:00", "ts_ms": 1, "acao": "GET /x"}

    monkeypatch.delenv("UPP_AUDIT_KEY", raising=False)
    sem_chave = cadeia.calcular(registro, cadeia.GENESE)

    monkeypatch.setenv("UPP_AUDIT_KEY", "segredo-da-instalacao")
    com_chave = cadeia.calcular(registro, cadeia.GENESE)

    monkeypatch.setenv("UPP_AUDIT_KEY", "outro-segredo")
    outra_chave = cadeia.calcular(registro, cadeia.GENESE)

    assert sem_chave != com_chave
    assert com_chave != outra_chave, "chaves diferentes tem de produzir elos diferentes"


def test_adotar_a_chave_nao_acusa_adulteracao_do_passado(app_isolado, monkeypatch):
    """Ligar UPP_AUDIT_KEY numa instalacao que ja rodava sem ela.

    O trecho anterior foi gravado com SHA-256 puro. Recusa-lo reportaria
    adulteracao onde houve apenas mudanca de configuracao, e alarme falso numa
    trilha de auditoria destroi a confianca nela tao bem quanto nao ter trilha.
    """
    db = app_isolado.db_path

    monkeypatch.delenv("UPP_AUDIT_KEY", raising=False)
    for i in range(3):
        registrar(db, metodo="GET", rota=f"/api/antigo/{i}", status=200)

    monkeypatch.setenv("UPP_AUDIT_KEY", "chave-adotada-depois")
    for i in range(2):
        registrar(db, metodo="GET", rota=f"/api/novo/{i}", status=200)

    resultado = verificar_integridade(db)

    assert resultado["integra"] is True, "a adocao da chave nao pode parecer adulteracao"
    assert resultado["verificadas"] == 5
    assert resultado["protecao_fraca"] == 3, "as 3 antigas seguem so com SHA-256"
    assert resultado["confiavel"] is False, (
        "com parte da trilha sem a protecao forte, ela ainda nao e plenamente confiavel"
    )


def test_rebaixar_entradas_para_sha256_fica_visivel(app_isolado, monkeypatch):
    """O melhor ataque possivel sem a chave e recalcular tudo em SHA-256.

    O elo passa a conferir, mas como FRACO — a tentativa aparece na contagem em
    vez de passar por autentica.
    """
    import hashlib

    from interface import auditoria_cadeia as cadeia

    monkeypatch.setenv("UPP_AUDIT_KEY", "chave-que-o-atacante-nao-tem")
    db = app_isolado.db_path
    for i in range(3):
        registrar(db, metodo="GET", rota=f"/api/x/{i}", status=200, usuario="alvo")

    assert verificar_integridade(db)["confiavel"] is True

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE auditoria SET usuario = 'apagado' WHERE id = 1")
        anterior = cadeia.GENESE
        for linha in conn.execute("SELECT * FROM auditoria ORDER BY id").fetchall():
            payload = f"{anterior}\n{cadeia._canonico(dict(linha))}".encode("utf-8")
            forjado = hashlib.sha256(payload).hexdigest()
            conn.execute(
                "UPDATE auditoria SET hash = ?, hash_anterior = ? WHERE id = ?",
                (forjado, anterior, linha["id"]),
            )
            anterior = forjado

    resultado = verificar_integridade(db)
    assert resultado["protecao_fraca"] == 3
    assert resultado["confiavel"] is False, "a cadeia rebaixada passou por confiavel"
