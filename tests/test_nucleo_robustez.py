"""Testes de robustez, consistência e performance do núcleo de decisão.

O `nucleo.decisor` é o coração clínico do sistema (decide quando um alerta de
imobilidade abre/fecha). Ao contrário do `modulo_alerta.engine`, ele é puro —
não toca em banco — então aqui exercitamos entradas malformadas, invariantes de
ordenação/imutabilidade e o comportamento sob carga, sem depender de I/O.

Objetivos:
- Robustez: entradas inválidas falham de forma explícita (Value/TypeError), não
  silenciosa nem com resultado corrompido.
- Consistência: o motor é determinístico e o caminho incremental é equivalente
  ao caminho em lote (o incremental roda na ingestão em tempo real; o lote na
  reprocessagem — divergir entre eles seria um bug clínico).
- Performance: uma grade grande é processada em tempo linear-ish e sem explosão
  de alertas (a saída é limitada, não cresce com o ruído da entrada).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
import pytest

from nucleo.decisor import (
    EstadoDecisor,
    processar_alertas_incremental,
    processar_alertas_lote,
)


def _grade(posturas: list[str], inicio: datetime | None = None, passo_min: int = 5) -> pd.DataFrame:
    inicio = inicio or datetime(2024, 1, 1, 0, 0)
    return pd.DataFrame(
        {
            "timestamp": [inicio + timedelta(minutes=passo_min * i) for i in range(len(posturas))],
            "postura": posturas,
        }
    )


# --------------------------------------------------------------------------- #
# Robustez: entradas malformadas devem falhar explicitamente ou não quebrar    #
# --------------------------------------------------------------------------- #

def test_grade_vazia_nao_gera_alerta() -> None:
    assert processar_alertas_lote(_grade([]), "medio", "P1") == []
    assert processar_alertas_lote([], "medio", "P1") == []


def test_amostra_unica_nao_abre_alerta() -> None:
    # Uma leitura isolada nunca é imobilidade — precisa de janela.
    assert processar_alertas_lote(_grade(["supino"]), "medio", "P1") == []


def test_perfil_desconhecido_falha_explicito() -> None:
    with pytest.raises(ValueError):
        processar_alertas_lote(_grade(["supino"] * 5), "inexistente", "P1")


def test_amostra_sem_colunas_obrigatorias_falha() -> None:
    estado = EstadoDecisor.criar("medio", "P1")
    with pytest.raises(ValueError):
        processar_alertas_incremental(estado, {"timestamp": datetime(2024, 1, 1)})
    with pytest.raises(ValueError):
        processar_alertas_incremental(estado, {"postura": "supino"})


def test_lote_lista_sem_colunas_falha() -> None:
    with pytest.raises(ValueError):
        processar_alertas_lote([{"postura": "supino"}], "medio", "P1")


def test_dataframe_sem_colunas_falha() -> None:
    df = pd.DataFrame({"ts": [datetime(2024, 1, 1)], "pose": ["supino"]})
    with pytest.raises(ValueError):
        processar_alertas_lote(df, "medio", "P1")


def test_timestamp_tipo_invalido_falha() -> None:
    estado = EstadoDecisor.criar("medio", "P1")
    with pytest.raises(TypeError):
        processar_alertas_incremental(estado, {"timestamp": 12345, "postura": "supino"})


def test_timestamps_nao_crescentes_falham() -> None:
    estado = EstadoDecisor.criar("medio", "P1")
    estado, _ = processar_alertas_incremental(
        estado, {"timestamp": datetime(2024, 1, 1, 0, 0), "postura": "supino"}
    )
    # Igual ao anterior (não estritamente crescente) também é rejeitado.
    with pytest.raises(ValueError):
        processar_alertas_incremental(
            estado, {"timestamp": datetime(2024, 1, 1, 0, 0), "postura": "supino"}
        )


def test_timestamp_string_iso_e_aceito() -> None:
    # A ingestão real pode entregar timestamps como string ISO.
    grade = [
        {"timestamp": f"2024-01-01T00:{m:02d}:00", "postura": "supino"}
        for m in range(0, 60, 5)
    ] + [
        {"timestamp": "2024-01-01T01:00:00", "postura": "supino"},
        {"timestamp": "2024-01-01T01:35:00", "postura": "supino"},
    ]
    alertas = processar_alertas_lote(grade, "medio", "P1")
    assert len(alertas) == 1
    assert alertas[0]["status"] == "aberto"


def test_timestamp_tz_aware_e_normalizado_para_naive() -> None:
    # Timestamps tz-aware não podem "vazar" tzinfo para dentro do estado
    # (comparações naive vs aware lançam TypeError). O núcleo normaliza.
    inicio = pd.Timestamp("2024-01-01T00:00:00", tz="UTC")
    grade = pd.DataFrame(
        {
            "timestamp": [inicio + timedelta(minutes=5 * i) for i in range(22)],
            "postura": ["supino"] * 22,
        }
    )
    alertas = processar_alertas_lote(grade, "medio", "P1")
    assert len(alertas) == 1
    # O inicio serializado é naive (sem offset).
    assert alertas[0]["inicio"] == "2024-01-01T01:30:00"


# --------------------------------------------------------------------------- #
# Consistência: determinismo, equivalência lote/incremental, imutabilidade     #
# --------------------------------------------------------------------------- #

def test_lote_e_deterministico() -> None:
    grade = _grade(["supino"] * 21 + ["lateral_direito"] * 6 + ["supino"] * 25)
    r1 = processar_alertas_lote(grade, "medio", "P1")
    r2 = processar_alertas_lote(grade, "medio", "P1")
    assert r1 == r2


def test_lote_ordena_entrada_desordenada() -> None:
    grade = _grade(["supino"] * 30)
    embaralhada = grade.sample(frac=1.0, random_state=42).reset_index(drop=True)
    assert processar_alertas_lote(embaralhada, "medio", "P1") == processar_alertas_lote(
        grade, "medio", "P1"
    )


def test_incremental_equivale_ao_lote_em_serie_longa_e_variada() -> None:
    # Série com aberturas, fechamentos, movimentos curtos (histerese) e cooldown.
    posturas = (
        ["supino"] * 25          # abre e mantém
        + ["lateral_direito"] * 6  # fecha (histerese)
        + ["lateral_direito"] * 25  # abre de novo após cooldown
        + ["supino"] * 2          # movimento curto (< histerese): não fecha
        + ["lateral_direito"] * 20
        + ["supino"] * 8          # fecha
    )
    grade = _grade(posturas)

    estado = EstadoDecisor.criar("medio", "P1")
    acumulado: dict[tuple[str, str], dict] = {}
    ordem: list[tuple[str, str]] = []
    for linha in grade.to_dict("records"):
        estado, novos = processar_alertas_incremental(estado, linha)
        for alerta in novos:
            chave = (alerta["paciente_id"], alerta["inicio"])
            if chave not in acumulado:
                ordem.append(chave)
            acumulado[chave] = alerta
    incremental = [acumulado[c] for c in ordem]

    assert incremental == processar_alertas_lote(grade, "medio", "P1")


def test_incremental_nao_muta_o_estado_de_entrada() -> None:
    # O contrato do motor é funcional: recebe estado, devolve estado NOVO
    # (via clone). Se mutasse a entrada, um caller que guardou o estado
    # anterior (ex: para replay/rollback) veria corrupção.
    estado = EstadoDecisor.criar("medio", "P1")
    estado, _ = processar_alertas_incremental(
        estado, {"timestamp": datetime(2024, 1, 1, 0, 0), "postura": "supino"}
    )
    antes = estado.clone()
    novo, _ = processar_alertas_incremental(
        estado, {"timestamp": datetime(2024, 1, 1, 0, 5), "postura": "supino"}
    )
    assert novo is not estado
    assert estado == antes  # o estado passado ficou intacto


def test_alertas_tem_campos_clinicos_obrigatorios() -> None:
    grade = _grade(["supino"] * 21 + ["lateral_direito"] * 6)
    (alerta,) = processar_alertas_lote(grade, "alto", "P1")
    for campo in ("paciente_id", "inicio", "fim", "tipo", "perfil", "janela_min", "status", "duracao_min"):
        assert campo in alerta, f"campo clínico ausente: {campo}"
    assert alerta["tipo"] == "imobilidade"
    assert alerta["duracao_min"] >= 0


# --------------------------------------------------------------------------- #
# Performance: carga alta processa rápido e sem explosão de saída              #
# --------------------------------------------------------------------------- #

def test_serie_grande_processa_em_tempo_linear() -> None:
    # ~50k amostras (paciente imóvel por dias). Deve completar bem abaixo do
    # teto e gerar exatamente 1 alerta (aberto) — a saída NÃO cresce com N.
    n = 50_000
    grade = _grade(["supino"] * n, passo_min=1)

    inicio = time.perf_counter()
    alertas = processar_alertas_lote(grade, "medio", "P1")
    decorrido = time.perf_counter() - inicio

    assert len(alertas) == 1
    assert alertas[0]["status"] == "aberto"
    # Teto generoso para não flakar em CI; o objetivo é pegar regressões
    # catastróficas (O(n²), cópia por amostra), não microbenchmark.
    assert decorrido < 10.0, f"processamento lento: {decorrido:.2f}s para {n} amostras"


def test_saida_limitada_sob_alternancia_frequente() -> None:
    # Ruído: postura alterna a cada passo. Isso nunca deve gerar um alerta por
    # amostra (seria uma tempestade de alertas). A saída fica limitada.
    n = 10_000
    posturas = ["supino" if i % 2 == 0 else "lateral_direito" for i in range(n)]
    alertas = processar_alertas_lote(_grade(posturas, passo_min=1), "medio", "P1")
    # Alternância constante não sustenta imobilidade → poucos ou nenhum alerta,
    # jamais proporcional a n.
    assert len(alertas) < 10
