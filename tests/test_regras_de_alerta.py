"""As regras de alerta apontam para metricas que existem de verdade.

Este arquivo protege contra um modo de falha especifico e bastante cruel: uma
regra do Prometheus que cita um nome de metrica inexistente nao dá erro. Ela
avalia para vazio, nunca dispara, e o painel fica verde. O sintoma de uma regra
quebrada e IDENTICO ao sintoma de um sistema saudavel.

Isso importa mais aqui que na media dos projetos, porque o sistema e orientado a
evento: um sensor morto nao gera erro, so para de produzir alertas. A regra
`PacienteSemMonitoramento` e o unico mecanismo que transforma esse silencio em
aviso. Se ela estiver morta, nada acusa — nem a regra, nem a tela, nem o log.

Um `_total` a mais ou a menos no nome basta. E os nomes das metricas do
`prometheus_client` nao sao os mesmos que o codigo Python usa: o `Counter`
chamado `EVENTOS_RECEBIDOS` publica `eventos_recebidos_total`, e o `Histogram`
`tempo_processamento_ms_hist` publica tres series com sufixos diferentes.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml e dependencia do teste de regras")

RAIZ = Path(__file__).resolve().parent.parent
REGRAS = RAIZ / "monitoring" / "regras_alertas.yml"
PROMETHEUS = RAIZ / "monitoring" / "prometheus.yml"
COMPOSE = RAIZ / "docker-compose.yml"

# Funcoes do PromQL e labels, que aparecem na expressao e nao sao metricas.
_NAO_E_METRICA = {
    "rate", "irate", "increase", "sum", "avg", "min", "max", "count", "by",
    "clamp_min", "clamp_max", "histogram_quantile", "humanizePercentage",
    "printf", "job", "status", "severity", "up", "on", "without", "offset",
}


def _carregar(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def _metricas_publicadas() -> set[str]:
    """Os nomes que o `/metrics` realmente serve, com os sufixos do Prometheus.

    Lidos do REGISTRY, e nao do codigo-fonte: e o registry que responde a
    requisicao, entao e ele o oraculo. Uma metrica declarada e nunca registrada
    nao apareceria aqui — e tambem nao apareceria no endpoint.

    As amostras nao bastam. Contador COM LABEL e sem nenhuma observacao ainda
    (`http_requests_total` num processo recem-subido) nao emite amostra alguma,
    e `metrica.name` vem sem o sufixo — o `prometheus_client` guarda
    `http_requests` e publica `http_requests_total`. Ler so as amostras faria
    este teste reprovar uma regra CORRETA, que e a falha mais cara possivel num
    teste: ensina a desabilita-lo.
    """
    import servicos.metricas  # noqa: F401 - o import registra os coletores
    from prometheus_client import REGISTRY

    # Sufixo por tipo, como o `prometheus_client` os publica.
    SUFIXOS = {
        "counter": ("_total", "_created"),
        "histogram": ("_bucket", "_sum", "_count"),
        "summary": ("_sum", "_count"),
        "gauge": (),
    }

    nomes: set[str] = set()
    for metrica in REGISTRY.collect():
        for amostra in metrica.samples:
            nomes.add(amostra.name)
        sufixos = SUFIXOS.get(metrica.type, ())
        # `metrica.name` NAO entra quando ha sufixo obrigatorio.
        #
        # O `prometheus_client` GUARDA o contador `eventos_recebidos_total` sob
        # o nome `eventos_recebidos`, mas nunca publica esse nome nu — o
        # endpoint serve `_total` e `_created`. Aceitar a forma nua fazia este
        # teste aprovar `rate(eventos_recebidos[15m])`, que e PromQL valido
        # apontando para serie inexistente: avalia vazio, nunca dispara, painel
        # verde. Exatamente o defeito que este arquivo existe para pegar, e ele
        # escapava — verificado por mutacao, nao por leitura.
        if not sufixos:
            nomes.add(metrica.name)
        for sufixo in sufixos:
            nomes.add(metrica.name + sufixo)
    return nomes


def _expressoes() -> list[tuple[str, str]]:
    dados = _carregar(REGRAS)
    saida = []
    for grupo in dados["groups"]:
        for regra in grupo["rules"]:
            saida.append((regra["alert"], regra["expr"]))
    return saida


def test_toda_metrica_citada_existe():
    """O teste central. Nome errado = regra que nunca dispara = falso verde."""
    publicadas = _metricas_publicadas()
    assert publicadas, "premissa: o registry devolveu metrica nenhuma"

    problemas = []
    for alerta, expr in _expressoes():
        # Seletores de label saem ANTES de tokenizar. `up{job="upp-app"}` tem
        # `upp` e `app` dentro das aspas, que nao sao metricas — e reprovar uma
        # regra correta e a falha mais cara que um teste destes pode ter,
        # porque o que ela ensina e a desabilita-lo.
        sem_labels = re.sub(r"\{[^}]*\}", "", expr)
        for token in re.findall(r"\b[a-z_][a-z0-9_]*\b", sem_labels):
            if token in _NAO_E_METRICA:
                continue
            # `_bucket`, `_sum` e `_count` sao sufixos que o histograma publica.
            candidatos = {token, token.removesuffix("_bucket").removesuffix("_sum")}
            if candidatos & publicadas:
                continue
            problemas.append(f"{alerta}: metrica `{token}` nao existe em /metrics")

    assert not problemas, "\n".join(problemas)


def test_a_regra_do_watchdog_existe_e_e_critica():
    """`pacientes_sem_monitoramento` e o melhor sinal que o sistema produz, e a
    razao de 3.4 existir. Perde-la num refactor do arquivo seria voltar ao
    estado anterior sem nada acusar."""
    por_nome = dict(_expressoes())
    assert "PacienteSemMonitoramento" in por_nome
    assert "pacientes_sem_monitoramento" in por_nome["PacienteSemMonitoramento"]

    dados = _carregar(REGRAS)
    regra = next(
        r
        for g in dados["groups"]
        for r in g["rules"]
        if r["alert"] == "PacienteSemMonitoramento"
    )
    assert regra["labels"]["severity"] == "critical"
    # Sem `for`, um reinicio de container dispara o alerta. Com `for` longo
    # demais, a equipe descobre tarde. Ver a justificativa no proprio arquivo.
    assert regra["for"] == "10m"


def test_o_caminho_de_scraping_bate_com_o_prefixo_da_aplicacao():
    """`metrics_path` carrega o APP_PREFIX.

    Se divergirem, o Prometheus recebe 404 e marca o alvo como `down` — o que
    dispara `AplicacaoForaDoAr` com a aplicacao perfeitamente saudavel. O
    resultado e pior que nao monitorar: alarme falso recorrente treina a equipe
    a ignorar a categoria inteira.
    """
    prom = _carregar(PROMETHEUS)
    caminho = prom["scrape_configs"][0]["metrics_path"]

    compose = _carregar(COMPOSE)
    ambiente = compose["services"]["app"]["environment"]
    prefixo = next(
        v.split("=", 1)[1] for v in ambiente if v.startswith("APP_PREFIX=")
    )

    assert caminho == f"{prefixo}/metrics", (
        f"scraping em {caminho!r} mas a aplicacao serve em {prefixo}/metrics"
    )


def test_prometheus_raspa_pela_rede_interna_e_nao_pelo_proxy():
    """O alvo e `app:8000`, nao o dominio publico.

    Raspar pelo Caddy criaria dependencia de TLS e DNS publico para monitorar, e
    impediria o bloqueio de `/metrics` na borda — que existe porque o endpoint
    expoe contagem de pacientes e volume de alertas sem autenticacao.
    """
    prom = _carregar(PROMETHEUS)
    alvos = prom["scrape_configs"][0]["static_configs"][0]["targets"]
    assert alvos == ["app:8000"], alvos

    caddy = (RAIZ / "Caddyfile").read_text(encoding="utf-8")
    assert "/TCC/metrics" in caddy and "respond @metrics 404" in caddy, (
        "o Caddyfile parou de bloquear /metrics na borda"
    )


def test_monitoramento_sobe_junto_e_nao_atras_de_profile():
    """Um `profiles:` opcional reproduziria o problema que 3.4 veio resolver:
    endpoint servido que ninguem raspa. Monitoramento que so sobe quando alguem
    lembra de pedir e monitoramento que nao existe."""
    compose = _carregar(COMPOSE)
    for servico in ("prometheus", "alertmanager"):
        assert servico in compose["services"], f"{servico} sumiu do compose"
        assert "profiles" not in compose["services"][servico], (
            f"{servico} ficou atras de um profile e nao sobe por padrao"
        )
        # Publicar a porta exporia a UI (contagem de pacientes, volume de
        # alertas) a quem alcance o IP da VM.
        assert "ports" not in compose["services"][servico], (
            f"{servico} publicou porta no host"
        )


def test_alertmanager_agrupa_para_nao_inundar():
    """Uma queda de switch deixa 12 leitos sem monitoramento. Sem agrupamento
    seriam 12 notificacoes para uma unica causa, e a equipe silencia a regra."""
    am = _carregar(RAIZ / "monitoring" / "alertmanager.yml")
    assert "alertname" in am["route"]["group_by"]
    assert am["route"]["repeat_interval"], "sem repeticao, um alerta ignorado some"

