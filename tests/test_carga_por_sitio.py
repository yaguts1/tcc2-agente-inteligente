"""Orcamento de carga por sitio anatomico, no lugar de corrida por postura.

O motor tratava toda postura como intercambiavel: `postura != run_postura`
reiniciava a corrida, e nada dizia que supino carrega sacro e calcaneos — os
sitios da maioria das lesoes de estagio 3 e 4 — enquanto lateral a 90° carrega o
trocanter, que e precisamente a razao de o padrao de cuidado ser 30° e nao 90°.

Duas consequencias, e as duas estao cobertas aqui:

  * o reset era EXPLORAVEL POR RUIDO. `lateral_direito -> supino ->
    lateral_direito` em 6 minutos zerava a janela inteira sem que o trocanter
    tivesse sido aliviado — 1 minuto de supino nao descarrega um trocanter que
    ficou 50 minutos sob pressao;

  * duas posturas DIFERENTES que carregam O MESMO sitio fechavam o alerta.
    supino -> semi-Fowler muda a postura mas as duas carregam o sacro: a tela
    dizia que o paciente foi atendido enquanto o sacro seguia sob pressao.

O modelo novo e uma GENERALIZACAO ESTRITA: para postura constante ele se comporta
exatamente como o antigo, o que e por que os 733 testes existentes passaram sem
alteracao. A diferenca aparece so nos casos acima.
"""

from datetime import datetime, timedelta

import pytest

from nucleo.decisor import EstadoDecisor, processar_alertas_incremental, reiniciar_corrida
from nucleo.posturas import SITIOS_POR_POSTURA, sitios_sob_carga

T0 = datetime(2026, 3, 10, 8, 0, 0)


def _correr(estado, postura_por_minuto, inicio=T0):
    """Aplica uma amostra por minuto. Devolve (estado, alertas)."""
    alertas = []
    for i, postura in enumerate(postura_por_minuto):
        estado, novos = processar_alertas_incremental(
            estado, {"timestamp": inicio + timedelta(minutes=i), "postura": postura}
        )
        alertas.extend(novos)
    return estado, alertas


@pytest.fixture
def estado():
    # Perfil alto: janela de 60 min, histerese 5 min, cooldown 10 min.
    return EstadoDecisor.criar("alto", "PAC-0001")


# ------------------------------------------------------- o mapa de sitios


def test_lateral_a_90_carrega_o_trocanter_e_a_30_nao():
    """A distincao clinica central: a posicao a 30° existe justamente para NAO
    apoiar no trocanter — o peso vai para a massa glutea, que tolera pressao
    muito melhor. Um modelo que tratasse as duas igual nao teria como mostrar a
    principal recomendacao pratica da area."""
    assert "trocanter_direito" in sitios_sob_carga("lateral_direito")
    assert "trocanter_direito" not in sitios_sob_carga("lateral_direito_30")


def test_supino_carrega_sacro_e_calcaneos():
    carregados = sitios_sob_carga("supino")

    assert "sacro" in carregados
    assert {"calcaneo_esquerdo", "calcaneo_direito"} <= carregados


def test_postura_desconhecida_degrada_para_o_modelo_antigo():
    """Um firmware que envie rotulo que o mapa nao conhece nao pode perder
    monitoramento nem passar a alertar diferente.

    A alternativa seria escolher entre ignorar a amostra (paciente sem
    vigilancia) ou carregar todos os sitios (alarme constante) — as duas piores
    que continuar como estava.
    """
    sitios = sitios_sob_carga("posicao_exotica_v2")

    assert len(sitios) == 1
    assert next(iter(sitios)).startswith("postura:")


def test_o_vocabulario_de_sitio_e_o_mesmo_das_lesoes():
    """Dois vocabularios para a mesma anatomia tornariam impossivel cruzar "onde
    a carga se acumulou" com "onde a lesao apareceu" — que e o cruzamento que o
    projeto existe para fazer."""
    from interface.repositories.lesoes import SITIOS_VALIDOS

    do_mapa = set().union(*SITIOS_POR_POSTURA.values())

    assert do_mapa <= SITIOS_VALIDOS, f"sitios fora do vocabulario: {do_mapa - SITIOS_VALIDOS}"


# ------------------------------------------------------- generalizacao estrita


def test_postura_constante_alerta_no_mesmo_instante_de_antes(estado):
    """A prova de que o modelo novo e generalizacao, nao comportamento novo:
    janela de 60 min em supino continua alertando em T0+60."""
    _, alertas = _correr(estado, ["supino"] * 62)

    assert len(alertas) == 1
    assert alertas[0]["inicio"] == (T0 + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")


def test_alerta_diz_qual_sitio_estourou(estado):
    """"Vire o paciente" e menos util que "o trocanter direito esta sob carga ha
    60 min" — a segunda informacao decide PARA QUAL LADO virar."""
    _, alertas = _correr(estado, ["lateral_direito"] * 62)

    assert alertas[0]["sitio"] == "trocanter_direito"


# ------------------------------------------------------- o exploit por ruido


def test_um_minuto_de_alivio_nao_zera_a_janela(estado):
    """O caso que o modelo antigo deixava passar.

    `lateral_direito -> supino -> lateral_direito` zerava a corrida inteira sem
    que o trocanter tivesse sido descarregado.
    """
    # 50 min no lateral, 1 min de supino, e volta. Repetido: no modelo antigo
    # isso NUNCA alertaria, porque cada supino zerava a corrida.
    sequencia = (["lateral_direito"] * 50 + ["supino"]) * 2

    _, alertas = _correr(estado, sequencia)

    assert alertas, "o trocanter passou ~100 min sob carga e nao houve alerta"
    assert alertas[0]["sitio"] == "trocanter_direito"


def test_alivio_sustentado_zera_de_verdade(estado):
    """A contrapartida: alivio que dura a histerese TEM que zerar.

    Sem isto, a carga so cresceria e o paciente ficaria em alerta permanente —
    o que treina a equipe a ignorar.
    """
    # 50 min lateral, 6 min de supino (> histerese de 5), 50 min lateral.
    sequencia = ["lateral_direito"] * 50 + ["supino"] * 6 + ["lateral_direito"] * 50

    _, alertas = _correr(estado, sequencia)

    do_trocanter = [a for a in alertas if a.get("sitio") == "trocanter_direito"]
    assert not do_trocanter, "o alivio sustentado nao zerou a carga do trocanter"


# ------------------------------------------------------- mesmo sitio, outra postura


def test_mudar_para_postura_que_carrega_o_mesmo_sitio_nao_fecha_o_alerta(estado):
    """supino -> semi-Fowler muda a postura, mas as DUAS carregam o sacro.

    O modelo antigo fechava o alerta — a tela dizia que o paciente foi atendido
    — enquanto o sacro seguia sob pressao. E o mesmo modo de falha que o
    reposicionamento sem confirmacao tem: a tela afirma bem-estar.
    """
    estado, abertura = _correr(estado, ["supino"] * 62)
    assert abertura and abertura[0]["sitio"] == "sacro"

    # 10 min em semi-Fowler: postura diferente, sacro ainda carregado.
    estado, depois = _correr(
        estado, ["semi_fowler"] * 10, inicio=T0 + timedelta(minutes=62)
    )

    fechados = [a for a in depois if a.get("status") == "fechado"]
    assert not fechados, "o alerta fechou sem o sacro ter sido aliviado"
    assert estado.alerta_atual is not None


def test_mudar_para_postura_que_alivia_o_sitio_fecha_o_alerta(estado):
    """Ancora do teste anterior: sem ela, ele passaria mesmo se o alerta NUNCA
    fechasse."""
    estado, _ = _correr(estado, ["supino"] * 62)

    estado, depois = _correr(
        estado, ["lateral_direito_30"] * 10, inicio=T0 + timedelta(minutes=62)
    )

    fechados = [a for a in depois if a.get("status") == "fechado"]
    assert fechados, "o alerta nao fechou apesar do sacro ter sido aliviado"
    assert estado.alerta_atual is None


# ------------------------------------------------------- pureza e estado


def test_a_funcao_continua_pura(estado):
    """O dicionario de carga nao pode vazar do clone para o estado do chamador.

    `processar_alertas_incremental` devolve estado NOVO; compartilhar o dict
    faria a mutacao aparecer em estado que ninguem processou.
    """
    antes = dict(estado.carga_por_sitio)

    novo, _ = processar_alertas_incremental(
        estado, {"timestamp": T0, "postura": "supino"}
    )
    novo, _ = processar_alertas_incremental(
        novo, {"timestamp": T0 + timedelta(minutes=10), "postura": "supino"}
    )

    assert estado.carga_por_sitio == antes
    assert novo.carga_por_sitio["sacro"] == pytest.approx(10)


def test_reiniciar_corrida_zera_a_carga(estado):
    """Cirurgia, transferencia e reposicionamento manual aliviam TODOS os sitios,
    nao um."""
    estado, _ = _correr(estado, ["supino"] * 40)
    assert estado.carga_por_sitio

    zerado = reiniciar_corrida(estado)

    assert zerado.carga_por_sitio == {}
    assert zerado.alivio_por_sitio == {}


def test_carga_sobrevive_a_serializacao(estado):
    """Sem persistir, um restart devolveria todo paciente para carga zero — e o
    sacro a 55 dos 60 minutos voltaria ao inicio, adiando o alerta por uma janela
    inteira exatamente em quem estava mais perto de precisar."""
    from servicos.processamento_incremental import _dict_para_estado, _estado_para_dict

    estado, _ = _correr(estado, ["supino"] * 40)

    voltou = _dict_para_estado(_estado_para_dict(estado))

    assert voltou.carga_por_sitio == estado.carga_por_sitio
    assert voltou.sitio_do_alerta == estado.sitio_do_alerta


def test_estado_antigo_sem_carga_continua_desserializavel():
    """Estados gravados ANTES desta mudanca nao tem as chaves novas. Quebrar a
    desserializacao perderia o estado inteiro do paciente, o que e pior que
    voltar com carga zero."""
    from servicos.processamento_incremental import _dict_para_estado

    antigo = {
        "perfil": "alto", "paciente_id": "PAC-0001", "janela_min": 60,
        "cooldown_min": 10, "histerese_min": 5.0,
        "run_postura": "supino", "run_inicio": "2026-03-10T08:00:00",
        "ultimo_timestamp": "2026-03-10T08:40:00",
    }

    estado = _dict_para_estado(antigo)

    assert estado.carga_por_sitio == {}
    assert estado.run_postura == "supino"


# ------------------------------------------------------- pressao_pico


def test_pressao_pico_e_gravada(app_isolado):
    """Era DECLARADA no schema, atravessava o exportador JSONL e nunca era
    gravada: um dado que o firmware ja envia e o sistema jogava fora a cada
    amostra."""
    import pandas as pd

    from interface.db_core import connect
    from interface.repositories.grade import inserir_grade

    df = pd.DataFrame([
        {"timestamp": "2026-03-10T08:00:00", "postura": "supino",
         "confianca": 0.9, "pressao_pico": 42.5},
    ])
    inserir_grade(app_isolado.db_path, df, "PAC-0001")

    with connect(app_isolado.db_path) as conn:
        valor = conn.execute(
            "SELECT pressao_pico FROM grade WHERE paciente_id = 'PAC-0001'"
        ).fetchone()[0]

    assert valor == pytest.approx(42.5)


def test_grade_sem_pressao_pico_continua_funcionando(app_isolado):
    """O firmware pode nao enviar. Exigir o campo derrubaria a ingestao inteira
    por um dado opcional."""
    import pandas as pd

    from interface.repositories.grade import inserir_grade

    df = pd.DataFrame([
        {"timestamp": "2026-03-10T08:00:00", "postura": "supino", "confianca": 0.9},
    ])

    assert inserir_grade(app_isolado.db_path, df, "PAC-0001") == 1
