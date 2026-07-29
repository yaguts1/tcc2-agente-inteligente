"""Quem respondeu, em quanto tempo, e por que fechou.

Tres lacunas que se sustentavam:

  1. O ator do reconhecimento so existia como FRASE EM PORTUGUES dentro de
     `timeline_events.descricao` ("Alerta reconhecido por fulano"). Nao dava
     para agregar por enfermeiro nem filtrar sem LIKE em prosa.

  2. TEMPO ATE RECONHECIMENTO nao era derivavel do modelo. `duracao_min` e
     `fim - inicio` (deteccao -> resolucao); o intervalo que diz se a ala e
     RESPONSIVA — deteccao -> alguem viu — nao existia em lugar consultavel.

  3. Concluir nao recebia justificativa: o dialogo era sim/nao. "Reposicionei",
     "estava em cirurgia", "o paciente recusou", "contraindicado por retalho na
     regiao sacral" e "falso alarme, o sensor deslocou" viravam a MESMA linha.
     Sem separar o falso alarme, a taxa de falso-positivo e estruturalmente
     incognoscivel — logo, inmelhoravel —, e fadiga de alarme e a razao
     dominante pela qual sistemas de alerta clinico sao abandonados.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect
from interface.repositories.alertas import (
    MOTIVO_FALSO_ALARME,
    MOTIVO_RECUSA_DO_PACIENTE,
    MOTIVO_REPOSICIONADO,
    alterar_status_alerta,
    inserir_alertas,
)
from interface.tempo import agora_utc_naive

PACIENTE = "PAC-0001"


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


@pytest.fixture
def db(app_isolado):
    caminho = app_isolado.db_path
    with connect(caminho) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (PACIENTE,))
        agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "INSERT INTO paciente_fichas(paciente_id,nome,perfil,cama_id,created_at,updated_at,unidade_id)"
            " VALUES (?,'Ana','alto','201-A',?,?,1)",
            (PACIENTE, agora, agora),
        )
        conn.execute(
            "INSERT INTO internacoes(paciente_id,admissao_ts,admissao_ms,unidade_id)"
            " VALUES (?,?,0,1)",
            (PACIENTE, agora),
        )
    return caminho


def _abrir(db, minutos_atras=90) -> str:
    inicio = (agora_utc_naive() - timedelta(minutes=minutos_atras)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    inserir_alertas(db, [{
        "paciente_id": PACIENTE, "inicio": inicio, "tipo": "imobilidade",
        "perfil": "alto", "janela_min": 60, "status": "aberto",
    }])
    return inicio


def _linha(db, inicio) -> dict:
    with connect(db) as conn:
        return dict(conn.execute(
            "SELECT status, reconhecido_por, reconhecido_em, motivo_fechamento,"
            "       fechado_por FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (PACIENTE, inicio),
        ).fetchone())


# ---------------------------------------------------------- ator do ack


def test_reconhecer_grava_quem_viu_e_quando(db):
    inicio = _abrir(db)

    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="enf.ana")

    linha = _linha(db, inicio)
    assert linha["reconhecido_por"] == "enf.ana"
    assert linha["reconhecido_em"] is not None


def test_quem_viu_primeiro_e_quem_fica_registrado(db):
    """Gravado uma vez so, como `fim`.

    Um segundo clique nao pode reescrever o tempo de resposta da ala — seria a
    metrica de responsividade sendo apagada por quem chegou depois.
    """
    inicio = _abrir(db)
    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="primeira")
    primeiro_ts = _linha(db, inicio)["reconhecido_em"]

    # Avancar para 'fechado' passa pelo mesmo UPDATE do ack? Nao — mas repetir
    # o reconhecimento e no-op idempotente, e nao pode mexer no registro.
    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="segunda")

    linha = _linha(db, inicio)
    assert linha["reconhecido_por"] == "primeira"
    assert linha["reconhecido_em"] == primeiro_ts


def test_tempo_ate_reconhecimento_fica_derivavel(db):
    """O que `duracao_min` nunca respondeu.

    `duracao_min` e deteccao -> resolucao. Este e deteccao -> alguem viu, que e
    a pergunta "a ala e responsiva?".
    """
    inicio = _abrir(db, minutos_atras=30)

    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="enf.ana")

    from datetime import datetime

    linha = _linha(db, inicio)
    minutos = (
        datetime.fromisoformat(linha["reconhecido_em"])
        - datetime.fromisoformat(inicio)
    ).total_seconds() / 60
    assert 29 <= minutos <= 31


# ---------------------------------------------------------- motivo


def test_concluir_sem_motivo_vale_como_reposicionado(db, client, cabecalho_auth):
    """O caso comum nao pede escolha: atrito na acao frequente e o que faz a
    equipe procurar o atalho."""
    inicio = _abrir(db)

    resposta = client.post(
        f"/api/frontend/alerts/{PACIENTE}__{inicio}/complete",
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert resposta.status_code == 200, resposta.text
    assert _linha(db, inicio)["motivo_fechamento"] == MOTIVO_REPOSICIONADO


def test_motivo_de_excecao_e_gravado(db, client, cabecalho_auth):
    inicio = _abrir(db)

    resposta = client.post(
        f"/api/frontend/alerts/{PACIENTE}__{inicio}/complete",
        json={"motivo": MOTIVO_FALSO_ALARME},
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert resposta.status_code == 200, resposta.text
    assert _linha(db, inicio)["motivo_fechamento"] == MOTIVO_FALSO_ALARME


def test_motivo_invalido_e_recusado(db):
    inicio = _abrir(db)

    with pytest.raises(ValueError):
        alterar_status_alerta(
            db, PACIENTE, inicio, "fechado", definir_fim=True, motivo="chute"
        )


def test_falso_alarme_e_separavel_dos_demais(db):
    """O motivo de a taxonomia existir: sem separar, a taxa de falso-positivo e
    incognoscivel."""
    for i, motivo in enumerate((MOTIVO_REPOSICIONADO, MOTIVO_FALSO_ALARME)):
        inicio = _abrir(db, minutos_atras=200 + i * 10)
        alterar_status_alerta(
            db, PACIENTE, inicio, "fechado", definir_fim=True, motivo=motivo
        )

    with connect(db) as conn:
        falsos = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE motivo_fechamento = ?",
            (MOTIVO_FALSO_ALARME,),
        ).fetchone()[0]

    assert falsos == 1


def test_motivo_sem_reposicionamento_nao_reinicia_o_motor(db, client, cabecalho_auth):
    """"Recusa do paciente" fecha a linha na tela, mas NAO houve alivio de
    pressao.

    Zerar a corrida ali daria ao paciente credito por um movimento que nao
    aconteceu, e adiaria o proximo alerta de uma janela inteira justamente em
    quem continua imovel.
    """
    from interface.services.ingestao_service import PROCESSADOR
    from nucleo.decisor import EstadoDecisor

    inicio = _abrir(db)
    estado = EstadoDecisor.criar("alto", PACIENTE)
    estado.alerta_atual = {"paciente_id": PACIENTE, "inicio": inicio}
    estado.baseline_postura = "supino"
    PROCESSADOR._estado_cache[PACIENTE] = estado

    client.post(
        f"/api/frontend/alerts/{PACIENTE}__{inicio}/complete",
        json={"motivo": MOTIVO_RECUSA_DO_PACIENTE},
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert PROCESSADOR._estado_cache[PACIENTE].alerta_atual is not None, (
        "o motor foi reiniciado sem que o paciente tivesse sido reposicionado"
    )


def test_reposicionado_reinicia_o_motor(db, client, cabecalho_auth):
    """Ancora do teste anterior: sem ela, ele passaria mesmo se o motor nunca
    reiniciasse."""
    from interface.services.ingestao_service import PROCESSADOR
    from nucleo.decisor import EstadoDecisor

    inicio = _abrir(db)
    estado = EstadoDecisor.criar("alto", PACIENTE)
    estado.alerta_atual = {"paciente_id": PACIENTE, "inicio": inicio}
    estado.baseline_postura = "supino"
    PROCESSADOR._estado_cache[PACIENTE] = estado

    client.post(
        f"/api/frontend/alerts/{PACIENTE}__{inicio}/complete",
        json={"motivo": MOTIVO_REPOSICIONADO},
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert PROCESSADOR._estado_cache[PACIENTE].alerta_atual is None


# ---------------------------------------------------------- stats e export


def test_stats_expoe_mediana_de_tempo_ate_reconhecimento(db, client, cabecalho_auth):
    inicio = _abrir(db, minutos_atras=40)
    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="enf.ana")

    stats = client.get("/api/stats", headers=cabecalho_auth(role="admin")).json()

    assert stats["acknowledgedCount"] == 1
    assert stats["medianAckMinutes"] is not None
    assert stats["medianAckMinutes"] >= 39


def test_sem_ninguem_reconhecendo_a_mediana_e_nula_e_nao_zero(db, client, cabecalho_auth):
    """Zero minutos de resposta seria um numero excelente, e "ninguem
    reconheceu nada" e o oposto disso."""
    _abrir(db)

    stats = client.get("/api/stats", headers=cabecalho_auth(role="admin")).json()

    assert stats["medianAckMinutes"] is None
    assert stats["acknowledgedCount"] == 0


def test_export_csv_traz_ator_e_motivo(db, client, cabecalho_auth):
    """O export e o que chega a coordenacao, e nao trazia quem respondeu."""
    inicio = _abrir(db)
    alterar_status_alerta(db, PACIENTE, inicio, "reconhecido", usuario="enf.ana")
    alterar_status_alerta(
        db, PACIENTE, inicio, "fechado", definir_fim=True,
        fechado_por="enf.ana", motivo=MOTIVO_FALSO_ALARME,
    )

    csv = client.get(
        "/api/alerts/export/csv", headers=cabecalho_auth(role="admin")
    ).text

    assert "reconhecido_por" in csv
    assert "enf.ana" in csv
    assert MOTIVO_FALSO_ALARME in csv


# ---------------------------------------------------------- registro profissional


def test_usuario_define_o_proprio_coren(client, cabecalho_auth, app_isolado):
    """Exigir um administrador para cada enfermeiro cadastrar o proprio COREN
    transformaria algo que a pessoa tem no bolso num chamado de suporte — e o
    campo ficaria vazio na instalacao inteira."""
    cab = cabecalho_auth(username="enf.ana", role="staff")

    resposta = client.put(
        "/api/usuarios/eu/registro",
        json={"coren": "coren-sp 123456-enf", "categoria": "enfermeiro"},
        headers=cab,
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["coren"] == "COREN-SP 123456-ENF"
    assert resposta.json()["categoria"] == "enfermeiro"


def test_categoria_invalida_e_recusada(client, cabecalho_auth):
    cab = cabecalho_auth(username="enf.ana", role="staff")

    resposta = client.put(
        "/api/usuarios/eu/registro",
        json={"coren": "COREN-SP 1", "categoria": "medico"},
        headers=cab,
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["code"] == "categoria_invalida"


def test_coren_com_formato_livre_e_aceito(client, cabecalho_auth):
    """O formato varia por estado e categoria; uma regex errada aqui recusaria
    registro legitimo — pior que aceitar um digitado torto, porque o primeiro
    impede o trabalho e o segundo e corrigivel."""
    cab = cabecalho_auth(username="enf.ana", role="staff")

    resposta = client.put(
        "/api/usuarios/eu/registro",
        json={"coren": "COREN/MG 98765 TE", "categoria": "tecnico"},
        headers=cab,
    )

    assert resposta.status_code == 200


def test_listagem_de_usuarios_traz_o_registro(client, cabecalho_auth, app_isolado):
    admin = cabecalho_auth(username="chefe", role="admin")
    client.put(
        "/api/usuarios/chefe/registro",
        json={"coren": "COREN-SP 1", "categoria": "enfermeiro"},
        headers=admin,
    )

    usuarios = client.get("/api/usuarios", headers=admin).json()
    chefe = next(u for u in usuarios if u["username"] == "chefe")

    assert chefe["coren"] == "COREN-SP 1"
    assert chefe["categoria"] == "enfermeiro"
