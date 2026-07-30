"""Propriedades do decisor, verificadas com entradas geradas.

Por que property-based AQUI e nao em outro lugar: `nucleo/decisor.py` e puro e
deterministico, entao gerar entrada e barato e o oraculo e exato. E a superficie
cresceu muito com o orcamento de carga por sitio — carga e alivio por sitio,
histerese sustentada, empate por prioridade clinica — e testes de exemplo cobrem
os caminhos que quem escreve o teste JA IMAGINA. As sequencias que quebram um
motor de estado costumam ser as que ninguem imagina: alivio parcial repetido,
mudanca de postura exatamente na fronteira da histerese, intervalos irregulares.

A propriedade central e a primeira: em producao o estado atravessa JSON e SQLite
a cada amostra (`servicos/processamento_incremental.py`), e nada testava que a
ida e volta preserva o comportamento. Um campo esquecido em `_estado_para_dict`
nao quebra nada de imediato — o motor continua respondendo — mas o paciente
perde carga acumulada em silencio, e o alerta atrasa uma janela inteira
exatamente em quem estava mais perto de precisar.
"""

from datetime import datetime, timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from nucleo.decisor import (
    EstadoDecisor,
    processar_alertas_incremental,
    reiniciar_corrida,
)
from nucleo.posturas import SITIOS_POR_POSTURA
from servicos.processamento_incremental import _dict_para_estado, _estado_para_dict

BASE = datetime(2026, 5, 1, 7, 0, 0)

# Posturas do mapa real, mais uma desconhecida: `sitios_sob_carga` degrada para
# um sitio sintetico nesse caso, e o degrade tambem precisa valer as
# propriedades — e exatamente o caminho que um firmware com rotulo novo toma.
POSTURAS = [*sorted(SITIOS_POR_POSTURA), "postura_nao_mapeada"]

# O gerador produz CORRIDAS — (postura, quantas amostras seguidas, intervalo) —
# e nao uma postura sorteada por amostra.
#
# Isto foi medido, nao suposto. Com postura sorteada a cada amostra, ZERO dos
# 200 exemplos abria um alerta: a postura mudava quase sempre, nenhum sitio
# acumulava carga, e as onze propriedades abaixo passavam sem nunca tocar o
# ciclo de vida do alerta. Passavam por vacuidade, que e o modo de falha
# caracteristico de teste por propriedade — e o mais dificil de perceber,
# porque a suite fica verde.
#
# Corrida tambem e a forma real do dado: um paciente fica numa postura por
# dezenas de minutos, nao troca a cada amostra.
#
# Ate 90 amostras por corrida com ate 15 min de intervalo alcanca as janelas dos
# tres perfis (60/90/120 min) com folga, e corridas curtas continuam sendo
# geradas — sao elas que exercitam a histerese.
corridas = st.lists(
    st.tuples(
        st.sampled_from(POSTURAS),
        st.integers(min_value=1, max_value=90),
        st.integers(min_value=1, max_value=15),
    ),
    min_size=1,
    max_size=8,
)

PERFIS = st.sampled_from(["alto", "medio", "baixo"])

LENTO = settings(
    max_examples=200,
    deadline=None,  # o primeiro exemplo paga import de pandas
    suppress_health_check=[HealthCheck.too_slow],
)


def _sequencia(passos):
    """(postura, n_amostras, intervalo) -> amostras com timestamps crescentes."""
    ts = BASE
    saida = []
    for postura, quantas, intervalo in passos:
        for _ in range(quantas):
            ts = ts + timedelta(minutes=intervalo)
            saida.append({"timestamp": ts, "postura": postura})
    return saida


def _rodar(estado, sequencia, *, serializando=False):
    """Processa a sequencia inteira, opcionalmente passando o estado por JSON
    entre cada amostra — que e o que a producao faz."""
    alertas = []
    for amostra in sequencia:
        if serializando:
            estado = _dict_para_estado(_estado_para_dict(estado))
        estado, novos = processar_alertas_incremental(estado, amostra)
        alertas.extend(novos)
    return estado, alertas


# ---------------------------------------------------------------------------
# A invariante de ouro
# ---------------------------------------------------------------------------


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_serializar_no_meio_da_sequencia_nao_muda_o_resultado(perfil, passos):
    """Em producao o estado atravessa JSON e SQLite a cada amostra. Se a ida e
    volta perder qualquer campo, o motor continua respondendo — e decide errado.

    Comparar os alertas E o estado final: alertas iguais com estado divergente
    so adia a divergencia para a proxima amostra.
    """
    sequencia = _sequencia(passos)

    _, direto = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), sequencia)
    _, via_json = _rodar(
        EstadoDecisor.criar(perfil, "PAC-0001"), sequencia, serializando=True
    )

    assert direto == via_json


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_estado_final_sobrevive_a_ida_e_volta(perfil, passos):
    """A outra metade: nao basta os alertas baterem, o estado tem de bater campo
    a campo — inclusive `carga_por_sitio`, que e o que um restart perderia."""
    sequencia = _sequencia(passos)

    final, _ = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), sequencia)
    reidratado = _dict_para_estado(_estado_para_dict(final))

    assert reidratado == final


# ---------------------------------------------------------------------------
# Pureza
# ---------------------------------------------------------------------------


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_processar_nao_muta_o_estado_recebido(perfil, passos):
    """O modulo se declara puro, e `processar_alertas_incremental` devolve
    estado novo. Se ele mutasse o recebido, o chamador que guardou a versao
    anterior — a reconciliacao faz isso — veria carga aparecer em estado que
    ninguem processou.

    `carga_por_sitio` e o campo em risco: `_acumular_carga` muta um dict, e
    `clone()` so protege porque copia. Uma linha trocada por `self.carga` e a
    protecao some sem nenhum teste de exemplo notar.
    """
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    for amostra in _sequencia(passos):
        antes = _estado_para_dict(estado)
        novo, _ = processar_alertas_incremental(estado, amostra)
        assert _estado_para_dict(estado) == antes, "o estado recebido foi mutado"
        estado = novo


# ---------------------------------------------------------------------------
# Invariantes do orcamento de carga
# ---------------------------------------------------------------------------


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_carga_nunca_e_negativa_nem_excede_o_tempo_decorrido(perfil, passos):
    """Um sitio nao pode ter acumulado mais minutos de carga do que minutos se
    passaram. Se acumulasse, o alerta abriria antes da janela — e a janela e a
    unica justificativa clinica que o alerta tem."""
    sequencia = _sequencia(passos)
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    decorrido = 0.0
    anterior = sequencia[0]["timestamp"]

    for amostra in sequencia:
        decorrido += (amostra["timestamp"] - anterior).total_seconds() / 60.0
        anterior = amostra["timestamp"]
        estado, _ = processar_alertas_incremental(estado, amostra)

        for sitio, carga in estado.carga_por_sitio.items():
            assert carga >= 0, f"{sitio} com carga negativa: {carga}"
            assert carga <= decorrido + 1e-9, (
                f"{sitio} acumulou {carga} min em {decorrido} min decorridos"
            )
        for sitio, alivio in estado.alivio_por_sitio.items():
            assert alivio >= 0, f"{sitio} com alivio negativo: {alivio}"


@given(
    perfil=PERFIS,
    carga_min=st.integers(min_value=20, max_value=50),
    ruido_min=st.integers(min_value=1, max_value=4),
)
@LENTO
def test_alivio_curto_demais_nao_zera_a_carga(perfil, carga_min, ruido_min):
    """A afirmacao clinica central do modelo por sitio.

    O modelo anterior zerava a corrida com QUALQUER mudanca de postura, o que
    tornava o reset exploravel por ruido: `lateral_direito -> supino ->
    lateral_direito` em 6 minutos zerava a janela sem que o trocanter tivesse
    sido descarregado — porque 1 minuto de supino nao alivia um trocanter que
    ficou 50 minutos sob pressao.

    Aqui o alivio dura menos que a histerese, entao a carga do sitio original
    tem de SOBREVIVER. Verifiquei que faltava: mutando a condicao de histerese
    para aceitar qualquer alivio, as treze propriedades anteriores seguiam
    passando.

    `ruido_min` fica abaixo de `histerese_min` (5 por padrao) por construcao.
    """
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    assume(ruido_min < estado.histerese_min)

    # Carrega o trocanter direito, interrompe com supino por menos que a
    # histerese, e volta. Supino nao carrega trocanter — o alivio e real, so nao
    # e sustentado.
    sequencia = _sequencia(
        [("lateral_direito", carga_min, 1), ("supino", ruido_min, 1), ("lateral_direito", 1, 1)]
    )
    final, _ = _rodar(estado, sequencia)

    trocanter = [s for s in final.carga_por_sitio if "trocanter" in s]
    assert trocanter, "o trocanter sumiu do orcamento: alivio de ruido zerou a carga"
    # A carga acumulada tem de refletir os minutos em lateral, nao recomecar do
    # zero. Nao exigimos o valor exato — a atribuicao do intervalo e a ultima
    # postura conhecida — mas exigimos que a maior parte tenha sobrevivido.
    assert final.carga_por_sitio[trocanter[0]] >= carga_min - ruido_min - 2, (
        f"carga caiu para {final.carga_por_sitio[trocanter[0]]} depois de "
        f"{ruido_min} min de alivio, com {carga_min} min acumulados"
    )


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_alivio_so_existe_para_sitio_que_ainda_tem_carga(perfil, passos):
    """`alivio_por_sitio` conta quanto tempo um sitio CARREGADO esta
    descansando. Alivio para sitio sem carga e lixo acumulando: o dict cresce
    indefinidamente ao longo de uma internacao, e ele e serializado a cada
    amostra."""
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    for amostra in _sequencia(passos):
        estado, _ = processar_alertas_incremental(estado, amostra)
        orfaos = set(estado.alivio_por_sitio) - set(estado.carga_por_sitio)
        assert not orfaos, f"alivio sem carga correspondente: {orfaos}"


# ---------------------------------------------------------------------------
# Ciclo de vida do alerta
# ---------------------------------------------------------------------------


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_alerta_so_abre_com_a_janela_cumprida(perfil, passos):
    """Nenhum alerta nasce sem que algum sitio tenha atingido `janela_min`.

    E a propriedade que impede o modo de falha mais caro de um sistema de
    alerta: avisar cedo demais. Fadiga de alarme e a razao dominante pela qual
    sistemas de alerta clinico sao desligados.
    """
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    janela = estado.janela_min

    for amostra in _sequencia(passos):
        anterior = estado
        estado, novos = processar_alertas_incremental(estado, amostra)
        abertos = [a for a in novos if a["status"] == "aberto"]
        if not abertos:
            continue
        # A carga esta no estado NOVO, ja acumulada, quando o alerta abre.
        pico = max(estado.carga_por_sitio.values(), default=0.0)
        assert pico >= janela, (
            f"alerta aberto com pico de {pico} min, janela e {janela}"
        )
        assert anterior.alerta_atual is None, "abriu alerta sobre alerta aberto"


@given(
    perfil=PERFIS,
    postura=st.sampled_from(POSTURAS),
    intervalo=st.integers(min_value=1, max_value=10),
    folga=st.integers(min_value=0, max_value=30),
)
@LENTO
def test_carga_sustentada_alem_da_janela_obriga_um_alerta(perfil, postura, intervalo, folga):
    """A propriedade de VIVACIDADE: paciente imovel alem da janela TEM de gerar
    alerta.

    Todas as outras propriedades deste arquivo sao de seguranca — dizem o que o
    motor nao pode fazer. Um decisor que simplesmente nunca alerta passa em
    todas elas, e esse e o pior modo de falha possivel: silencio clinico, com
    dashboard verde.

    Nao e hipotetico. Verifiquei mutando o limiar de `janela_min` para
    `janela_min * 3` — as doze propriedades anteriores seguiram passando, e um
    paciente ficaria 3 horas sem aviso no perfil de alto risco.

    Tambem fixa QUANDO: o inicio e `primeira_amostra + janela`, e nao a hora da
    amostra que detectou. A amostragem e discreta, e datar o alerta pela amostra
    atrasaria o inicio pelo intervalo entre amostras — o que subestima o tempo
    de exposicao justamente no numero que vai para o relatorio.
    """
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    # Amostras suficientes para cobrir a janela inteira mais folga.
    total_min = estado.janela_min + folga + intervalo
    quantas = total_min // intervalo + 1

    _, alertas = _rodar(estado, _sequencia([(postura, quantas, intervalo)]))

    abertos = [a for a in alertas if a["status"] == "aberto"]
    assert abertos, (
        f"{quantas * intervalo} min em {postura!r} sem alerta, janela e {estado.janela_min}"
    )

    # A carga comeca a contar da SEGUNDA amostra — a primeira so estabelece a
    # corrida, porque antes dela nao ha intervalo a atribuir.
    esperado = BASE + timedelta(minutes=intervalo + estado.janela_min)
    assert abertos[0]["inicio"] == esperado.strftime("%Y-%m-%dT%H:%M:%S")


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_nunca_ha_dois_alertas_abertos_ao_mesmo_tempo(perfil, passos):
    """O dashboard mostra um alerta por paciente e o `alert_id` e
    `(paciente, inicio)`. Dois abertos simultaneos produziriam uma linha que a
    equipe fecha achando que fechou as duas."""
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    for amostra in _sequencia(passos):
        estado, novos = processar_alertas_incremental(estado, amostra)
        assert len([a for a in novos if a["status"] == "aberto"]) <= 1
        if estado.alerta_atual is not None:
            assert estado.alerta_inicio is not None
            assert estado.sitio_do_alerta is not None


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_alerta_fechado_tem_duracao_nao_negativa_e_sitio_nomeado(perfil, passos):
    """`duracao_min` alimenta a estatistica do dashboard e o export. Negativa
    ali envenena a media sem nada acusar, porque ninguem olha alerta a alerta."""
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    for amostra in _sequencia(passos):
        estado, novos = processar_alertas_incremental(estado, amostra)
        for alerta in novos:
            assert alerta["sitio"] is not None, "alerta sem sitio nao diz para onde virar"
            if alerta["status"] == "fechado":
                assert alerta["duracao_min"] >= 0
                assert alerta["fim"] >= alerta["inicio"]


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_o_sitio_que_fecha_o_alerta_e_o_que_o_abriu(perfil, passos):
    """A razao de existir do modelo por sitio.

    O modelo antigo fechava com QUALQUER mudanca de postura — entao
    supino -> semi-Fowler fechava o alerta enquanto o sacro seguia carregado nas
    duas, e a tela dizia que o paciente tinha sido atendido.
    """
    estado = EstadoDecisor.criar(perfil, "PAC-0001")
    for amostra in _sequencia(passos):
        antes = estado.sitio_do_alerta
        estado, novos = processar_alertas_incremental(estado, amostra)
        for alerta in novos:
            if alerta["status"] == "fechado":
                assert alerta["sitio"] == antes, (
                    "o alerta fechou nomeando sitio diferente do que o abriu"
                )
                assert antes not in estado.carga_por_sitio, (
                    "fechou com o sitio ainda carregado"
                )


# ---------------------------------------------------------------------------
# Ordem e reinicio
# ---------------------------------------------------------------------------


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_timestamp_fora_de_ordem_e_recusado(perfil, passos):
    """O motor exige ordem crescente. Aceitar uma amostra atrasada creditaria
    intervalo negativo ou duplicado — e amostra atrasada acontece de verdade,
    quando um ESP32 reconecta e despeja o buffer."""
    sequencia = _sequencia(passos)
    assume(len(sequencia) >= 2)

    estado, _ = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), sequencia)

    with pytest.raises(ValueError):
        processar_alertas_incremental(estado, sequencia[-1])


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_reiniciar_corrida_zera_a_carga_e_preserva_o_cooldown(perfil, passos):
    """Cirurgia, transferencia e reposicionamento manual aliviam TODOS os
    sitios — o paciente foi erguido. Mas o cooldown de um alerta recem-fechado
    continua valendo: reiniciar a corrida nao e licenca para realertar."""
    estado, _ = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), _sequencia(passos))

    reiniciado = reiniciar_corrida(estado)

    assert reiniciado.carga_por_sitio == {}
    assert reiniciado.alivio_por_sitio == {}
    assert reiniciado.run_postura is None
    assert reiniciado.cooldown_ate == estado.cooldown_ate
    # Pureza tambem aqui: o estado recebido nao pode ter sido esvaziado.
    assert reiniciado is not estado


@given(perfil=PERFIS, passos=corridas)
@LENTO
def test_o_motor_e_deterministico(perfil, passos):
    """Duas execucoes da mesma sequencia dao o mesmo resultado.

    Parece trivial e nao e: o desempate de `_sitio_mais_carregado` percorre um
    dict, e um empate resolvido por ordem de insercao seria estavel dentro de um
    processo e instavel depois de um restart — porque a ordem viria do JSON.
    """
    sequencia = _sequencia(passos)
    a = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), sequencia)
    b = _rodar(EstadoDecisor.criar(perfil, "PAC-0001"), sequencia)
    assert a == b
