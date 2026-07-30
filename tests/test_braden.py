"""Escala de Braden: o instrumento que a enfermagem ja usa.

O risco era um enum de tres valores num dropdown — sem escore, sem subescores,
sem data de reavaliacao, sem quem classificou. E as janelas de reposicionamento
(60/90/120 min) eram variaveis de ambiente GLOBAIS, sem fonte citada em lugar
nenhum do repositorio.

Numa ala brasileira, Braden E o que vai para o prontuario (Protocolo de Prevencao
de Lesao por Pressao, MS/ANVISA/FIOCRUZ 2013). Uma ferramenta que nao o consome
pede que a enfermeira mantenha uma SEGUNDA classificacao de risco, paralela e sem
justificativa, ao lado da que ela ja e obrigada a registrar — e duas
classificacoes divergem.

Tres coisas que estes testes travam, e que sao onde uma implementacao de Braden
erra:

  * MENOR escore = MAIOR risco. A inversao e contraintuitiva o suficiente para
    ter causado erro em outros sistemas;
  * friccao/cisalhamento vai de 1 a 3, nao 1 a 4. Aceitar 4 inflaria o total e
    poderia rebaixar o paciente de faixa sem ninguem perceber;
  * subescore FALTANDO nao pode virar zero nem default: o total resultante
    colocaria o paciente numa faixa MAIS LEVE que a real.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from interface.repositories import braden as repo
from interface.repositories.pacientes import PatientRepository
from interface.tempo import agora_utc_naive
from nucleo import braden as escala

# Um paciente de risco muito alto: total 9.
GRAVE = {
    "percepcao_sensorial": 2, "umidade": 2, "atividade": 1,
    "mobilidade": 1, "nutricao": 2, "friccao_cisalhamento": 1,
}
# Total 21 -> sem risco.
LEVE = {
    "percepcao_sensorial": 4, "umidade": 4, "atividade": 3,
    "mobilidade": 4, "nutricao": 3, "friccao_cisalhamento": 3,
}


@pytest.fixture
def db(app_isolado):
    return app_isolado.db_path


@pytest.fixture
def pacientes(db):
    return PatientRepository(db)


@pytest.fixture
def ana(pacientes):
    return pacientes.create(nome="Ana", perfil="baixo", cama_id="201-A")["paciente_id"]


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


# ------------------------------------------------------------ escala (puro)


@pytest.mark.parametrize(
    "escore,esperada",
    [
        (6, "muito_alto"), (9, "muito_alto"),
        (10, "alto"), (12, "alto"),
        (13, "moderado"), (14, "moderado"),
        (15, "baixo"), (18, "baixo"),
        (19, "sem_risco"), (23, "sem_risco"),
    ],
)
def test_faixas_de_risco(escore, esperada):
    """Faixas da escala original (Bergstrom et al., 1987), na forma adotada pelo
    protocolo brasileiro. Ficam explicitas para poderem ser CONFERIDAS — que era
    o que nao dava para fazer com `JANELA_ALTO=60` numa variavel de ambiente."""
    assert escala.faixa(escore) == esperada


def test_menor_escore_e_maior_risco():
    """A inversao contraintuitiva, num teste que a nomeia."""
    assert escala.perfil_para(8) == "alto"
    assert escala.perfil_para(22) == "baixo"


def test_friccao_vai_ate_3_e_nao_4():
    """Aceitar 4 inflaria o total e poderia rebaixar o paciente de faixa."""
    assert escala.SUBESCALAS["friccao_cisalhamento"] == (1, 3)

    with pytest.raises(escala.BradenInvalido):
        escala.total({**GRAVE, "friccao_cisalhamento": 4})


def test_subescore_faltando_e_recusado():
    """Um Braden com cinco dos seis campos nao e um Braden: o total colocaria o
    paciente numa faixa MAIS LEVE que a real."""
    incompleto = {k: v for k, v in GRAVE.items() if k != "nutricao"}

    with pytest.raises(escala.BradenInvalido, match="faltando"):
        escala.total(incompleto)


def test_subescore_desconhecido_e_recusado():
    with pytest.raises(escala.BradenInvalido, match="desconhecidos"):
        escala.total({**GRAVE, "hidratacao": 2})


def test_total_e_faixa_coerentes():
    r = escala.avaliar(GRAVE)

    assert r["total"] == 9
    assert r["faixa"] == "muito_alto"
    assert r["perfil"] == "alto"


def test_muito_alto_e_alto_colapsam_no_mesmo_perfil():
    """O sistema tem tres janelas e Braden tem cinco faixas. Nao ha janela mais
    curta que 60 min para oferecer, e fingir granularidade que o motor nao tem
    seria pior — a enfermeira veria uma distincao sem efeito nenhum.

    A faixa ORIGINAL fica registrada, entao o colapso nao apaga informacao.
    """
    assert escala.perfil_para(8) == escala.perfil_para(11) == "alto"
    assert escala.faixa(8) != escala.faixa(11)


def test_sem_risco_ainda_e_monitorado():
    """Braden >= 19 e baixa probabilidade, nao ausencia de risco — e um paciente
    monitorado a cada 120 min custa quase nada."""
    assert escala.perfil_para(23) == "baixo"


# ------------------------------------------------------------ persistencia


def test_avaliacao_aplica_o_perfil_na_ficha(db, ana, pacientes):
    """Aplicar, e nao sugerir: manter as duas classificacoes lado a lado — a do
    dropdown e a de Braden — reproduziria o problema que a entidade resolve."""
    assert pacientes.get_by_id(ana)["perfil"] == "baixo"

    repo.registrar(db, ana, GRAVE, usuario="enf.ana")

    assert pacientes.get_by_id(ana)["perfil"] == "alto"


def test_avaliacao_nao_sobrescreve_a_anterior(db, ana):
    """A trajetoria do escore e dado clinico: um paciente que entrou com 18 e
    esta com 9 esta piorando, e isso nao aparece se cada avaliacao sobrescrever
    a anterior.

    As duas caem no MESMO segundo aqui, o que e o caso que expoe a ambiguidade
    de ordenar so por `avaliada_ms`: sem `id DESC` como desempate, `ultima()`
    poderia devolver a antiga — e e ela que define a janela do motor.
    """
    repo.registrar(db, ana, LEVE)
    repo.registrar(db, ana, GRAVE)

    historico = repo.listar_do_paciente(db, ana)

    assert [a["total"] for a in historico] == [9, 21], "mais recente primeiro"
    assert repo.ultima(db, ana)["total"] == 9


def test_total_gravado_nunca_diverge_das_partes(db, ana):
    """O CHECK do banco e o que torna seguro guardar o total apesar de ser soma
    das partes."""
    import sqlite3

    from interface.db_core import connect

    repo.registrar(db, ana, GRAVE)

    with pytest.raises(sqlite3.IntegrityError), connect(db) as conn:
        conn.execute("UPDATE braden_avaliacoes SET total = 99")


def test_paciente_inexistente_e_recusado(db):
    with pytest.raises(LookupError):
        repo.registrar(db, "PAC-NAO-EXISTE", GRAVE)


# ------------------------------------------------------------ reavaliacao


def _envelhecer(db, paciente_id, horas):
    from interface.db_core import connect

    quando = agora_utc_naive() - timedelta(hours=horas)
    with connect(db) as conn:
        conn.execute(
            "UPDATE braden_avaliacoes SET avaliada_ms = ? WHERE paciente_id = ?",
            (int(quando.timestamp() * 1000), paciente_id),
        )


def test_nunca_avaliado_e_separado_de_vencido(db, ana, pacientes):
    """As duas situacoes pedem acao diferente: vencido e reavaliar; nunca
    avaliado e um paciente que entrou no sistema sem passar pelo instrumento, e o
    problema esta no fluxo de admissao, nao no plantao.

    Mesma separacao que `nunca_recebeu_dados` tem no watchdog de sensor.
    """
    bruno = pacientes.create(nome="Bruno", perfil="medio", cama_id="202-B")["paciente_id"]
    repo.registrar(db, bruno, GRAVE)
    _envelhecer(db, bruno, horas=48)

    pendentes = repo.reavaliacoes_pendentes(db)

    assert [p["paciente_id"] for p in pendentes["nunca_avaliado"]] == [ana]
    assert [p["paciente_id"] for p in pendentes["vencidos"]] == [bruno]
    assert pendentes["pendentes"] == 2


def test_avaliacao_recente_nao_conta_como_pendente(db, ana):
    repo.registrar(db, ana, GRAVE)

    pendentes = repo.reavaliacoes_pendentes(db)

    assert pendentes["pendentes"] == 0


def test_limite_de_horas_e_configuravel(db, ana):
    """O intervalo varia por servico: UTI reavalia por turno, longa permanencia
    semanalmente. Um numero fixo obrigaria cada instalacao a conviver com um
    alerta que nao e o dela."""
    repo.registrar(db, ana, GRAVE)
    _envelhecer(db, ana, horas=10)

    assert repo.reavaliacoes_pendentes(db, horas=24)["pendentes"] == 0
    assert repo.reavaliacoes_pendentes(db, horas=8)["pendentes"] == 1


def test_paciente_com_alta_nao_conta(db, ana, pacientes):
    """Cobrar reavaliacao de quem foi embora encheria a lista de trabalho que
    nao existe."""
    pacientes.dar_alta(ana)

    assert repo.reavaliacoes_pendentes(db)["pendentes"] == 0


def test_pendentes_respeita_o_escopo_de_unidade(db, pacientes, ana):
    from interface.repositories.unidades import criar_unidade

    outra = criar_unidade(db, "Ala Sul")["id"]
    pacientes.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=outra)

    assert repo.reavaliacoes_pendentes(db, unidades={1})["pendentes"] == 1


# ------------------------------------------------------------ endpoints


def test_escala_e_descrita_pelo_servidor(client, cabecalho_auth):
    """A tela monta o formulario daqui, e o mapeamento vem junto para a
    enfermeira ver qual janela o escore vai produzir ANTES de salvar."""
    corpo = client.get("/api/braden/escala", headers=cabecalho_auth()).json()

    assert corpo["total_minimo"] == 6
    assert corpo["total_maximo"] == 23
    assert corpo["subescalas"]["friccao_cisalhamento"] == {"minimo": 1, "maximo": 3}
    assert corpo["perfil_por_faixa"]["muito_alto"] == "alto"


def test_registrar_pela_api(client, cabecalho_auth, ana, pacientes):
    resposta = client.post(
        f"/api/pacientes/{ana}/braden",
        json=GRAVE,
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["total"] == 9
    assert resposta.json()["perfil"] == "alto"
    assert pacientes.get_by_id(ana)["perfil"] == "alto"


def test_friccao_4_e_recusada_na_api(client, cabecalho_auth, ana):
    resposta = client.post(
        f"/api/pacientes/{ana}/braden",
        json={**GRAVE, "friccao_cisalhamento": 4},
        headers=cabecalho_auth(),
    )

    assert resposta.status_code == 422


def test_subescore_faltando_e_recusado_na_api(client, cabecalho_auth, ana):
    incompleto = {k: v for k, v in GRAVE.items() if k != "mobilidade"}

    resposta = client.post(
        f"/api/pacientes/{ana}/braden", json=incompleto, headers=cabecalho_auth()
    )

    assert resposta.status_code == 422


def test_braden_exige_sessao(client, ana):
    assert client.get("/api/braden/escala").status_code == 401
    assert client.get("/api/braden/pendentes").status_code == 401
    assert client.post(f"/api/pacientes/{ana}/braden", json=GRAVE).status_code == 401


def test_stats_expoe_braden_pendente(client, cabecalho_auth, ana):
    """Fica ao lado do watchdog de sensor porque sao as duas formas de o sistema
    estar cego: um nao recebe dados, o outro vigia com uma classificacao de risco
    que pode nao valer mais."""
    stats = client.get("/api/stats", headers=cabecalho_auth(role="admin")).json()

    assert stats["bradenNuncaAvaliado"] == 1
    assert stats["bradenPendentes"] == 1
    assert stats["bradenLimiteHoras"] == 24


def test_a_janela_do_motor_passa_a_vir_do_escore(db, ana, pacientes):
    """O fecho do ciclo: o escore que a enfermeira registra e o que define a
    janela que o motor usa.

    Antes eram duas coisas sem ligacao — um dropdown numa tela e tres variaveis
    de ambiente.
    """
    from interface.services.paciente_service import intervalo_horas

    repo.registrar(db, ana, GRAVE)
    perfil_grave = pacientes.get_by_id(ana)["perfil"]

    repo.registrar(db, ana, LEVE)
    perfil_leve = pacientes.get_by_id(ana)["perfil"]

    assert intervalo_horas(perfil_grave) < intervalo_horas(perfil_leve)
