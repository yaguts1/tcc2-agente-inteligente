"""Notificacao que sobrevive a aba fechada.

O beep WebAudio e a Notification API de `useCriticalAlerts` exigem a aba viva, e
o tratamento da suspensao de autoplay do Chrome DESISTE EM SILENCIO quando o
navegador recusa. Clinicamente: o aviso pode nunca soar sem que ninguem saiba.

Com a escada de escalonamento (4.2) o buraco ficou maior — um alerta que passa
para `violacao` as 04:00 agora TEM o que avisar, e nao tinha por onde.

O teste central deste arquivo nao e "a notificacao e enviada". E que ela e
enviada UMA VEZ POR SUBIDA DE NIVEL. O loop roda a cada minuto; notificar por
estado em vez de por transicao produziria um aviso por minuto enquanto o alerta
estivesse aberto, e a equipe desligaria as notificacoes do navegador. Uma vez
desligadas, elas nao voltam — e o sistema fica pior do que estava antes desta
funcionalidade existir.
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest

from interface.db_core import connect
from interface.repositories import push as repo


def _agora():
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


@pytest.fixture
def usuario(app_isolado):
    from interface.repositories.users import UserRepository

    UserRepository(app_isolado.db_path).create("enfermeira", "hash", role="staff")
    return "enfermeira"


@pytest.fixture
def paciente_com_alertas(app_isolado):
    """Um paciente e alertas com idades escolhidas, para atravessar a escada.

    Perfil alto = janela de 60 min, entao 130 min em aberto e `critico` e 200 e
    `violacao` (ver `nucleo/escalonamento.py`).
    """
    agora = _agora()
    iso = agora.strftime("%Y-%m-%dT%H:%M:%S")
    with connect(app_isolado.db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES ('PAC-0001')")
        conn.execute(
            "INSERT INTO paciente_fichas"
            " (paciente_id, nome, perfil, cama_id, created_at, updated_at, unidade_id)"
            " VALUES ('PAC-0001','Ana','alto','201-A',?,?,1)",
            (iso, iso),
        )
        # A INTERNACAO ATIVA e obrigatoria. Desde 1.1 a listagem de fichas
        # exige `EXISTS (SELECT 1 FROM internacoes ... alta_ms IS NULL)`, porque
        # alta virou estado em vez de delete. Sem ela, o alerta sai com nome
        # caindo no fallback (o proprio id) e sem leito — que foi como este
        # teste falhou da primeira vez, com "sem leito" no corpo da notificacao.
        conn.execute(
            "INSERT INTO internacoes (paciente_id, admissao_ts, admissao_ms)"
            " VALUES ('PAC-0001', ?, ?)",
            (iso, int(agora.replace(tzinfo=UTC).timestamp() * 1000)),
        )

    def abrir(minutos: int) -> str:
        inicio = (agora - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S")
        with connect(app_isolado.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO alertas"
                " (paciente_id, inicio, tipo, perfil, janela_min, status)"
                " VALUES ('PAC-0001',?,'imobilidade','alto',60,'aberto')",
                (inicio,),
            )
        return inicio

    return abrir


# ---------------------------------------------------------------------------
# Inscricao
# ---------------------------------------------------------------------------


def test_reinscrever_o_mesmo_aparelho_nao_duplica(app_isolado, usuario):
    """Reinscricao no mesmo navegador devolve o MESMO endpoint.

    Sem `ON CONFLICT`, a tabela ganharia uma linha a cada recarregamento de
    pagina — e o aviso chegaria duplicado na mesma tela, que e a maneira mais
    rapida de a pessoa desligar as notificacoes.
    """
    for _ in range(3):
        repo.inscrever(
            app_isolado.db_path,
            usuario=usuario,
            endpoint="https://push.exemplo/abc",
            p256dh="chave",
            auth="segredo",
        )

    assert len(repo.listar(app_isolado.db_path)) == 1


def test_reinscrever_zera_o_historico_de_falhas(app_isolado, usuario):
    """Inscricao que o navegador voltou a oferecer esta VIVA de novo. Carregar o
    historico de falhas faria a limpeza remove-la logo em seguida."""
    repo.inscrever(
        app_isolado.db_path,
        usuario=usuario,
        endpoint="https://push.exemplo/abc",
        p256dh="k",
        auth="s",
    )
    with connect(app_isolado.db_path) as conn:
        conn.execute("UPDATE push_subscriptions SET falhas = 9, ultima_falha = '2026-01-01'")

    repo.inscrever(
        app_isolado.db_path,
        usuario=usuario,
        endpoint="https://push.exemplo/abc",
        p256dh="k",
        auth="s",
    )

    with connect(app_isolado.db_path) as conn:
        linha = conn.execute("SELECT falhas, ultima_falha FROM push_subscriptions").fetchone()
    assert linha["falhas"] == 0
    assert linha["ultima_falha"] is None


def test_o_mesmo_usuario_pode_ter_varios_aparelhos(app_isolado, usuario):
    """Tablet da ala e celular proprio precisam receber os dois."""
    for endpoint in ("https://push.exemplo/tablet", "https://push.exemplo/celular"):
        repo.inscrever(
            app_isolado.db_path,
            usuario=usuario,
            endpoint=endpoint,
            p256dh="k",
            auth="s",
        )
    assert len(repo.listar(app_isolado.db_path, usuario)) == 2


def test_remover_mortas(app_isolado, usuario):
    """404/410 do servico de push significa aparelho que desinstalou o app ou
    revogou a permissao. Sem remover, a tabela so cresce e cada ciclo gasta uma
    requisicao de rede por tela que nao existe mais."""
    for i in range(3):
        repo.inscrever(
            app_isolado.db_path,
            usuario=usuario,
            endpoint=f"https://push.exemplo/{i}",
            p256dh="k",
            auth="s",
        )

    removidas = repo.remover_mortas(
        app_isolado.db_path, ["https://push.exemplo/0", "https://push.exemplo/2"]
    )

    assert removidas == 2
    assert [i["endpoint"] for i in repo.listar(app_isolado.db_path)] == [
        "https://push.exemplo/1"
    ]


# ---------------------------------------------------------------------------
# Envio por transicao — o teste central
# ---------------------------------------------------------------------------


@pytest.fixture
def push_falso(monkeypatch, app_isolado):
    """Substitui o envio real e conta as chamadas."""
    from servicos import push as servico

    enviados: list[dict] = []

    def _enviar(inscricoes, payload):
        resultado = servico.ResultadoEnvio()
        for _ in inscricoes:
            enviados.append(payload)
            resultado.enviados += 1
        return resultado

    monkeypatch.setattr(servico, "enviar", _enviar)
    monkeypatch.setattr(servico, "configurado", lambda: True)

    # O servico de alertas le um DB_PATH de modulo.
    from interface.services import alerts_service

    monkeypatch.setattr(alerts_service, "DB_PATH", app_isolado.db_path)
    return enviados


def _rodar_ciclo(db_path, estado):
    """Um ciclo, com o cache da API limpo antes.

    `listar_alertas_frontend` cacheia por 30s, e o cache e um singleton de
    modulo compartilhado entre testes — sem limpar, o primeiro teste a rodar
    envenena a chave `(horas=48, unidades=None)` para todos os seguintes, e a
    falha aparece longe da causa (um alerta sem leito, em outro teste).

    Em producao o acoplamento e inofensivo: o loop roda a cada 60s e o cache
    dura 30s, entao o pior caso e agir sobre dado meio minuto antigo — abaixo da
    resolucao da propria escada, que se move em janelas de uma hora.
    """
    from interface.api_shared import api_cache
    from interface.lifespan_tasks import ciclo_push

    asyncio.run(api_cache.clear())
    return asyncio.run(ciclo_push(db_path, estado))


def test_alerta_normal_nao_notifica(app_isolado, usuario, paciente_com_alertas, push_falso):
    """Alerta recem-aberto ja e um aviso por si. Notificar no `normal` gastaria
    o canal no caso mais comum."""
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    paciente_com_alertas(10)

    _rodar_ciclo(app_isolado.db_path, {})

    assert push_falso == []


def test_notifica_uma_vez_por_subida_e_nao_a_cada_ciclo(
    app_isolado, usuario, paciente_com_alertas, push_falso
):
    """O TESTE CENTRAL.

    O loop roda a cada minuto. Notificar por ESTADO produziria um aviso por
    minuto enquanto o alerta estivesse aberto — a equipe desligaria as
    notificacoes do navegador, e uma vez desligadas elas nao voltam. O sistema
    ficaria PIOR do que antes desta funcionalidade existir.
    """
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    paciente_com_alertas(130)  # critico

    estado: dict = {}
    for _ in range(5):
        _rodar_ciclo(app_isolado.db_path, estado)

    assert len(push_falso) == 1, f"{len(push_falso)} avisos para um unico alerta"
    assert push_falso[0]["nivel"] == "critico"


def test_subir_de_nivel_notifica_de_novo(
    app_isolado, usuario, paciente_com_alertas, push_falso
):
    """A escada tem tres degraus; um alerta ignorado a noite inteira avisa no
    maximo tres vezes, e so quando algo MUDA."""
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    inicio = paciente_com_alertas(130)  # critico
    estado: dict = {}
    _rodar_ciclo(app_isolado.db_path, estado)
    assert len(push_falso) == 1

    # O mesmo alerta, envelhecido para violacao.
    novo_inicio = (_agora() - timedelta(minutes=200)).strftime("%Y-%m-%dT%H:%M:%S")
    with connect(app_isolado.db_path) as conn:
        conn.execute(
            "UPDATE alertas SET inicio = ? WHERE inicio = ?", (novo_inicio, inicio)
        )

    _rodar_ciclo(app_isolado.db_path, estado)

    assert len(push_falso) == 2
    assert push_falso[1]["nivel"] == "violacao"


def test_o_estado_sobrevive_a_restart(
    app_isolado, usuario, paciente_com_alertas, push_falso
):
    """Sem persistir, um restart reenviaria notificacao de TODO alerta aberto —
    e um deploy as 3h acordaria a ala inteira."""
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    paciente_com_alertas(130)

    _rodar_ciclo(app_isolado.db_path, {})
    assert len(push_falso) == 1

    # Simula restart: estado em memoria recarregado do banco.
    estado_novo = repo.niveis_notificados(app_isolado.db_path)
    _rodar_ciclo(app_isolado.db_path, estado_novo)

    assert len(push_falso) == 1, "o restart reenviou a notificacao"


def test_sem_ninguem_inscrito_o_nivel_ainda_e_registrado(
    app_isolado, paciente_com_alertas, push_falso
):
    """Senao o primeiro aparelho a se inscrever receberia de uma vez todo o
    historico acumulado — dezenas de notificacoes de alertas antigos."""
    paciente_com_alertas(200)
    estado: dict = {}

    _rodar_ciclo(app_isolado.db_path, estado)
    assert push_falso == []
    assert repo.niveis_notificados(app_isolado.db_path), "o nivel nao foi registrado"


def test_a_mensagem_diz_qual_leito_e_qual_sitio(
    app_isolado, usuario, paciente_com_alertas, push_falso
):
    """Notificacao que obriga a abrir o aplicativo para saber do que se trata e
    uma interrupcao sem informacao. As 4h, a diferenca entre isso e
    "201 / A · ha 3h" e a diferenca entre levantar e nao levantar."""
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    paciente_com_alertas(200)

    _rodar_ciclo(app_isolado.db_path, {})

    assert push_falso, "nada enviado"
    corpo = push_falso[0]["corpo"]
    assert "201" in corpo, corpo
    assert "h" in corpo, corpo


def test_alerta_fechado_libera_o_registro_de_nivel(
    app_isolado, usuario, paciente_com_alertas, push_falso
):
    """Um alerta REABERTO no mesmo paciente e horario precisa poder notificar de
    novo. Carregar o nivel antigo o deixaria mudo — e a tabela cresceria sem
    limite ao longo de uma internacao."""
    repo.inscrever(
        app_isolado.db_path, usuario=usuario, endpoint="https://e/1", p256dh="k", auth="s"
    )
    inicio = paciente_com_alertas(200)
    _rodar_ciclo(app_isolado.db_path, {})
    assert repo.niveis_notificados(app_isolado.db_path)

    with connect(app_isolado.db_path) as conn:
        conn.execute("UPDATE alertas SET status = 'fechado' WHERE inicio = ?", (inicio,))

    _rodar_ciclo(app_isolado.db_path, {})

    assert repo.niveis_notificados(app_isolado.db_path) == {}


# ---------------------------------------------------------------------------
# Configuracao ausente
# ---------------------------------------------------------------------------


def test_sem_vapid_o_modulo_fica_inerte_e_nao_levanta(monkeypatch):
    """Derrubar a aplicacao porque o push nao foi configurado trocaria uma
    funcionalidade ausente por um SERVICO ausente."""
    from servicos import push as servico

    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)

    assert servico.configurado() is False
    resultado = servico.enviar([{"endpoint": "x", "p256dh": "y", "auth": "z"}], {"a": 1})
    assert resultado.enviados == 0


def test_a_ausencia_de_vapid_e_dita_alto_no_boot(monkeypatch):
    """Nao pode falhar CALADO — e exatamente o defeito que este modulo veio
    corrigir. Sem o aviso, a investigacao comecaria pelo navegador."""
    import structlog

    from servicos import push as servico

    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)

    with structlog.testing.capture_logs() as registros:
        servico.avisar_se_desconfigurado()

    assert any(r.get("event") == "push_desconfigurado" for r in registros), registros
