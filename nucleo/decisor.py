"""Nucleo do motor de decisao de alertas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Iterable, Mapping, Sequence

import pandas as pd

from configuracao import config as app_config


def _perfil_config(perfil: str) -> dict[str, int]:
    janelas = app_config.janela_por_perfil
    if perfil not in janelas:
        raise ValueError(f"Perfil desconhecido: {perfil}")
    janela = janelas[perfil]
    return {
        "janela_minutos": janela,
        "cooldown_minutos": app_config.cooldown_min,
        "histerese_minutos": app_config.histerese_min,
    }

NOVO_ALERTA_STATUS: tuple[str, str] = ("aberto", "fechado")


@dataclass
class EstadoDecisor:
    """Mantem o estado incremental do motor de alertas."""

    perfil: str
    paciente_id: str
    janela_min: int
    cooldown_min: int
    histerese_min: float
    alerta_atual: dict[str, Any] | None = None
    alerta_inicio: datetime | None = None
    baseline_postura: str | None = None
    movimento_inicio: datetime | None = None
    cooldown_ate: datetime = field(default_factory=lambda: datetime.min)
    run_postura: str | None = None
    run_inicio: datetime | None = None
    ultimo_timestamp: datetime | None = None
    # Minutos de carga acumulados POR SITIO ANATOMICO desde o ultimo alivio
    # daquele sitio, e por quanto tempo cada sitio esta descarregado.
    #
    # Antes havia so `run_inicio`: uma corrida unica que qualquer mudanca de
    # postura zerava. Isso tornava o reset exploravel por ruido —
    # `lateral_direito -> supino -> lateral_direito` em 6 minutos zerava a
    # janela sem que o trocanter tivesse sido aliviado, porque 1 minuto de
    # supino nao descarrega um trocanter que ficou 50 minutos sob pressao.
    #
    # Ver `nucleo/posturas.py` para o mapa postura -> sitios.
    carga_por_sitio: dict[str, float] = field(default_factory=dict)
    alivio_por_sitio: dict[str, float] = field(default_factory=dict)
    # Sitio que disparou o alerta aberto. E o que permite exigir que o alivio
    # descarregue o sitio CERTO, e nao qualquer um.
    sitio_do_alerta: str | None = None

    @classmethod
    def criar(cls, perfil: str, paciente_id: str) -> EstadoDecisor:
        config = _perfil_config(perfil)
        return cls(
            perfil=perfil,
            paciente_id=paciente_id,
            janela_min=int(config["janela_minutos"]),
            cooldown_min=int(config["cooldown_minutos"]),
            histerese_min=float(config["histerese_minutos"]),
        )

    def clone(self) -> EstadoDecisor:
        alerta = None if self.alerta_atual is None else dict(self.alerta_atual)
        return EstadoDecisor(
            perfil=self.perfil,
            paciente_id=self.paciente_id,
            janela_min=self.janela_min,
            cooldown_min=self.cooldown_min,
            histerese_min=self.histerese_min,
            alerta_atual=alerta,
            alerta_inicio=self.alerta_inicio,
            baseline_postura=self.baseline_postura,
            movimento_inicio=self.movimento_inicio,
            cooldown_ate=self.cooldown_ate,
            run_postura=self.run_postura,
            run_inicio=self.run_inicio,
            ultimo_timestamp=self.ultimo_timestamp,
            # `dict(...)`, e nao a referencia: `clone()` existe porque
            # `processar_alertas_incremental` e PURA e devolve estado novo.
            # Compartilhar o dict faria a mutacao vazar para o estado que o
            # chamador ainda tem em maos — e o sintoma seria carga aparecendo
            # em estado que ninguem processou.
            carga_por_sitio=dict(self.carga_por_sitio),
            alivio_por_sitio=dict(self.alivio_por_sitio),
            sitio_do_alerta=self.sitio_do_alerta,
        )

    @property
    def janela_td(self) -> timedelta:
        return timedelta(minutes=self.janela_min)

    @property
    def cooldown_td(self) -> timedelta:
        return timedelta(minutes=self.cooldown_min)


def _to_datetime(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        ts = valor
    elif isinstance(valor, pd.Timestamp):
        ts = valor.to_pydatetime()
    elif isinstance(valor, str):
        ts = datetime.fromisoformat(valor[:19])
    else:
        raise TypeError(f"Tipo de timestamp invalido: {type(valor)!r}")
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts.replace(microsecond=0)


def _abrir_alerta(
    inicio: datetime, estado: EstadoDecisor, sitio: str | None = None
) -> dict[str, Any]:
    return {
        "paciente_id": estado.paciente_id,
        "inicio": inicio.strftime("%Y-%m-%dT%H:%M:%S"),
        "tipo": "imobilidade",
        "perfil": estado.perfil,
        "janela_min": estado.janela_min,
        "status": NOVO_ALERTA_STATUS[0],
        # ONDE a carga se acumulou. Um alerta que diz "vire o paciente" e menos
        # util que um que diz "o trocanter direito esta sob carga ha 60 min" — a
        # segunda informacao decide PARA QUAL LADO virar.
        "sitio": sitio,
    }


def _fechar_alerta_inplace(alerta: dict[str, Any], fim: datetime, inicio: datetime) -> dict[str, Any]:
    alerta["fim"] = fim.strftime("%Y-%m-%dT%H:%M:%S")
    alerta["status"] = NOVO_ALERTA_STATUS[1]
    alerta["duracao_min"] = round((fim - inicio).total_seconds() / 60.0, 2)
    return alerta


def reiniciar_corrida(estado: EstadoDecisor) -> EstadoDecisor:
    """Estado novo em que a corrida de imobilidade recomeca do zero.

    Pura, como o resto deste modulo: devolve um estado novo e nao toca no que
    recebeu.

    Existe porque ha eventos que interrompem a imobilidade sem que o sensor veja
    postura diferente — o paciente sai do leito para uma cirurgia, e erguido para
    a maca numa transferencia, ou a equipe reposiciona sem que a mudanca seja
    captada. Sem isto, o intervalo era lido como UMA corrida continua, e o
    paciente recebia credito de zero movimento justamente nos momentos de maior
    alivio de pressao.

    Nao mexe em `cooldown_ate`: se um alerta acabou de ser fechado, o intervalo
    de silencio combinado continua valendo.
    """
    novo_estado = estado.clone()
    novo_estado.run_postura = None
    novo_estado.run_inicio = None
    novo_estado.movimento_inicio = None
    # A carga por sitio tambem zera: o evento que interrompeu a imobilidade
    # (cirurgia, transferencia, reposicionamento manual) aliviou TODOS os
    # sitios, nao um.
    novo_estado.carga_por_sitio.clear()
    novo_estado.alivio_por_sitio.clear()
    return novo_estado


def _acumular_carga(estado: EstadoDecisor, postura: str, minutos: float) -> None:
    """Soma `minutos` de carga nos sitios que esta postura apoia.

    Muta `estado` — que e sempre o CLONE, nunca o recebido.

    Sitio carregado acumula; sitio livre acumula ALIVIO. Quando o alivio de um
    sitio atinge a histerese, a carga dele zera: e o que faz o alivio precisar
    ser SUSTENTADO para valer.

    E aqui que o reset deixa de ser exploravel por ruido. Antes, qualquer
    mudanca de postura zerava a corrida inteira, entao
    `lateral_direito -> supino -> lateral_direito` em 6 minutos zerava a janela
    sem que o trocanter tivesse sido descarregado. Agora 1 minuto de supino soma
    1 minuto de alivio ao trocanter, e a carga dele so zera se o alivio se
    sustentar pelos `histerese_min`.
    """
    from nucleo.posturas import sitios_sob_carga

    carregados = sitios_sob_carga(postura)

    for sitio in carregados:
        estado.carga_por_sitio[sitio] = estado.carga_por_sitio.get(sitio, 0.0) + minutos
        estado.alivio_por_sitio.pop(sitio, None)

    for sitio in list(estado.carga_por_sitio):
        if sitio in carregados:
            continue
        aliviado = estado.alivio_por_sitio.get(sitio, 0.0) + minutos
        if aliviado >= estado.histerese_min:
            # Alivio sustentado: o sitio zera. `pop` em vez de `= 0` para o dict
            # nao crescer indefinidamente com sitios que o paciente ja nem usa.
            estado.carga_por_sitio.pop(sitio, None)
            estado.alivio_por_sitio.pop(sitio, None)
        else:
            estado.alivio_por_sitio[sitio] = aliviado


def _sitio_mais_carregado(estado: EstadoDecisor):
    """O sitio com mais carga acumulada, e quanto.

    O alerta e sobre o sitio em pior situacao: e ele que define quando avisar e o
    que dizer para a equipe.

    Empate resolve por PRIORIDADE CLINICA, nao por ordem alfabetica. E o caso
    comum, nao a excecao: supino carrega sacro, calcaneos, occipital, escapulas e
    cotovelos ao mesmo tempo e pelo mesmo intervalo, entao a carga empata sempre.
    Desempatar por nome nomearia "calcaneo_direito" num paciente cujo problema e
    o sacro — deterministico e clinicamente inutil, porque o nome no alerta e o
    que diz para qual lado virar.
    """
    from nucleo.posturas import prioridade

    if not estado.carga_por_sitio:
        return None, 0.0
    sitio = min(
        estado.carga_por_sitio,
        key=lambda s: (-estado.carga_por_sitio[s], prioridade(s), s),
    )
    return sitio, estado.carga_por_sitio[sitio]


def processar_alertas_incremental(
    estado: EstadoDecisor,
    amostra: Mapping[str, Any],
) -> tuple[EstadoDecisor, list[dict[str, Any]]]:
    """Atualiza o estado do motor com uma nova amostra de postura."""
    if not isinstance(estado, EstadoDecisor):
        raise TypeError("Estado deve ser uma instancia de EstadoDecisor.")
    if "timestamp" not in amostra or "postura" not in amostra:
        raise ValueError("A amostra precisa conter 'timestamp' e 'postura'.")

    novo_estado = estado.clone()
    timestamp = _to_datetime(amostra["timestamp"])
    postura = str(amostra["postura"])

    if novo_estado.ultimo_timestamp and timestamp <= novo_estado.ultimo_timestamp:
        raise ValueError("Timestamps devem estar em ordem crescente.")

    alertas_emitidos: list[dict[str, Any]] = []

    if novo_estado.run_postura is None:
        novo_estado.run_postura = postura
        novo_estado.run_inicio = timestamp
        novo_estado.ultimo_timestamp = timestamp
        # Primeira amostra: nao ha intervalo anterior, logo nada a acumular. A
        # carga comeca a contar do SEGUNDO ponto — o mesmo instante em que
        # `run_inicio` passava a valer no modelo antigo.
        return novo_estado, alertas_emitidos

    # Quanto tempo passou desde a amostra anterior, atribuido a ULTIMA POSTURA
    # CONHECIDA — nao a que acabou de ser lida.
    #
    # A amostragem e discreta: entre t-5 e t sabemos que o paciente estava na
    # postura observada em t-5, e so em t descobrimos que mudou. Nao ha como
    # saber em que ponto do intervalo a mudanca ocorreu.
    #
    # Atribuir ao estado ANTERIOR e a escolha conservadora e a unica consistente
    # entre carga e alivio: se o intervalo fosse creditado a postura nova, o
    # sitio recem-liberado ganharia alivio por um tempo em que talvez ainda
    # estivesse sob carga — e o alerta fecharia antes de o alivio ter de fato
    # acontecido. Verificado: creditar a postura nova fechava o alerta uma
    # amostra mais cedo que o modelo anterior.
    minutos = max((timestamp - novo_estado.ultimo_timestamp).total_seconds() / 60.0, 0.0)
    _acumular_carga(novo_estado, novo_estado.run_postura, minutos)

    if postura != novo_estado.run_postura:
        novo_estado.run_postura = postura
        novo_estado.run_inicio = timestamp

    if novo_estado.alerta_atual is not None and novo_estado.sitio_do_alerta is not None:
        # O alerta fecha quando O SITIO QUE O DISPAROU e aliviado, nao quando a
        # postura simplesmente muda.
        #
        # A diferenca aparece num caso comum: supino -> semi-Fowler muda a
        # postura mas as DUAS carregam o sacro. O modelo antigo fecharia o
        # alerta — a tela diria que o paciente foi atendido — enquanto o sacro
        # seguia sob pressao. Agora nao fecha, porque o sitio nao foi aliviado.
        #
        # `_acumular_carga` ja zera a carga do sitio quando o alivio atinge a
        # histerese; se ele saiu do dicionario, foi aliviado o suficiente.
        if novo_estado.sitio_do_alerta not in novo_estado.carga_por_sitio:
            if novo_estado.alerta_inicio is None:
                raise RuntimeError("Estado inconsistente: alerta sem inicio registrado.")
            alerta_fechado = _fechar_alerta_inplace(
                novo_estado.alerta_atual,
                timestamp,
                novo_estado.alerta_inicio,
            )
            alertas_emitidos.append(alerta_fechado)
            novo_estado.cooldown_ate = timestamp + novo_estado.cooldown_td
            novo_estado.alerta_atual = None
            novo_estado.alerta_inicio = None
            novo_estado.baseline_postura = None
            novo_estado.movimento_inicio = None
            novo_estado.sitio_do_alerta = None

    if novo_estado.alerta_atual is None:
        sitio, carga = _sitio_mais_carregado(novo_estado)
        if sitio is not None and carga >= novo_estado.janela_min:
            # O instante EXATO em que a carga cruzou a janela, e nao a hora da
            # amostra: a amostragem e discreta, e usar `timestamp` atrasaria o
            # `inicio` do alerta pelo intervalo entre amostras.
            #
            # Para postura constante isso da `run_inicio + janela`, identico ao
            # modelo antigo — a mudanca e generalizacao, nao comportamento novo
            # no caso comum.
            detection_time = timestamp - timedelta(minutes=carga - novo_estado.janela_min)
            inicio_alerta = max(detection_time, novo_estado.cooldown_ate)
            if inicio_alerta <= timestamp:
                novo_estado.baseline_postura = novo_estado.run_postura
                novo_estado.sitio_do_alerta = sitio
                novo_estado.alerta_inicio = inicio_alerta
                alerta_aberto = _abrir_alerta(inicio_alerta, novo_estado, sitio)
                alertas_emitidos.append(alerta_aberto)
                novo_estado.alerta_atual = alerta_aberto
                novo_estado.movimento_inicio = None

    novo_estado.ultimo_timestamp = timestamp
    return novo_estado, alertas_emitidos


def _iterar_grade(grade: Sequence[Mapping[str, Any]] | pd.DataFrame) -> Iterable[Mapping[str, Any]]:
    if isinstance(grade, pd.DataFrame):
        if not {"timestamp", "postura"}.issubset(grade.columns):
            raise ValueError("DataFrame de grade precisa conter 'timestamp' e 'postura'.")
        ordenado = grade.sort_values("timestamp").reset_index(drop=True)
        for item in ordenado.to_dict("records"):
            yield item
    else:
        for item in grade:
            if "timestamp" not in item or "postura" not in item:
                raise ValueError("Cada amostra deve conter 'timestamp' e 'postura'.")
            yield item


def processar_alertas_lote(
    grade: Sequence[Mapping[str, Any]] | pd.DataFrame,
    perfil: str,
    paciente_id: str,
) -> list[dict[str, Any]]:
    """Processa uma grade completa de posturas e retorna alertas gerados."""
    estado = EstadoDecisor.criar(perfil, paciente_id)
    alertas_por_chave: dict[tuple[str, str], dict[str, Any]] = {}
    ordem: list[tuple[str, str]] = []
    estado_atual = estado

    for amostra in _iterar_grade(grade):
        estado_atual, novos = processar_alertas_incremental(estado_atual, amostra)
        for alerta in novos:
            chave = (str(alerta.get("paciente_id", "")), str(alerta.get("inicio", "")))
            if chave not in alertas_por_chave:
                ordem.append(chave)
            alertas_por_chave[chave] = alerta

    return [alertas_por_chave[chave] for chave in ordem]
