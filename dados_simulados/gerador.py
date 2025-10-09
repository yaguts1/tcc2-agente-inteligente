# -- coding: utf-8 --
# dados_simulados/gerador.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import random
import numpy as np
import pandas as pd
from typing import Tuple

POSTURAS = ["supino", "lateral_direito", "lateral_esquerdo", "prono"]

# Transições válidas (ajuste como quiser)
TRANSICOES_VALIDAS = {
    "supino": ["lateral_direito", "lateral_esquerdo"],
    "lateral_direito": ["supino", "prono"],
    "lateral_esquerdo": ["supino", "prono"],
    "prono": ["lateral_direito", "lateral_esquerdo"],
}

# (média_min, desvio_min) por postura
TEMPOS_POSTURA = {
    "supino": (90, 30),
    "lateral_direito": (120, 40),
    "lateral_esquerdo": (120, 40),
    "prono": (45, 20),
}

@dataclass
class PerfilPaciente:
    nome: str = "Paciente"
    limite_tempo_postura: int = 120      # min
    prob_falha_reposicao: float = 0.7    # prob de ultrapassar o limite quando deveria reposicionar
    horarios_refeicao: list[datetime] | None = None
    duracao_refeicao: int = 30           # min

    def horarios_refeicao_padrao(self, inicio: datetime) -> list[datetime]:
        # Se não passar, gera 3 refeições a partir da data de início
        base = inicio.replace(hour=6, minute=0, second=0, microsecond=0)
        return [base + timedelta(hours=h) for h in (6, 12, 18)]  # 12h, 18h e 24h a partir de 6h

def _normal_truncada(media: float, desvio: float, minimo: float = 1.0) -> float:
    """Sorteia valor ~N(media, desvio) com piso 'minimo'."""
    val = np.random.normal(media, desvio)
    return float(max(minimo, val))

def _escolher_proxima_postura(atual: str) -> str:
    opcoes = TRANSICOES_VALIDAS.get(atual, [p for p in POSTURAS if p != atual])
    return random.choice(opcoes)

def _gerar_eventos(
    inicio: datetime,
    fim: datetime,
    perfil: PerfilPaciente,
    seed: int,
) -> pd.DataFrame:
    """Gera eventos por blocos: (timestamp_inicio, postura, duracao_min, origem, falha)."""
    random.seed(seed)
    np.random.seed(seed)

    ts = inicio
    atual = "supino"
    eventos: list[dict] = []

    refeicoes = perfil.horarios_refeicao or perfil.horarios_refeicao_padrao(inicio)
    refeicoes_inseridas: set[datetime] = set()

    while ts < fim:
        # Se chegou em uma refeição ainda não inserida, força supino por X minutos
        refeicao_aplicada = False
        for h in refeicoes:
            if h not in refeicoes_inseridas and ts >= h and ts < h + timedelta(minutes=1):
                eventos.append(dict(timestamp=h, postura="supino",
                                    duracao_min=perfil.duracao_refeicao,
                                    origem="refeicao", falha=False))
                ts = h + timedelta(minutes=perfil.duracao_refeicao)
                atual = "supino"
                refeicoes_inseridas.add(h)
                refeicao_aplicada = True
                break
        if refeicao_aplicada:
            continue

        # Duração sorteada para a postura atual
        media, desvio = TEMPOS_POSTURA.get(atual, (90, 30))
        dur = _normal_truncada(media, desvio, minimo=5.0)

        # Possível falha em reposicionamento
        falha = False
        if dur > perfil.limite_tempo_postura:
            if random.random() < perfil.prob_falha_reposicao:
                # "estica" a permanência
                dur += _normal_truncada(media, desvio, minimo=5.0)
                falha = True

        # Ajusta para não passar do fim
        fim_bloco = ts + timedelta(minutes=dur)
        if fim_bloco > fim:
            dur = max(1.0, (fim - ts).total_seconds() / 60.0)
            fim_bloco = ts + timedelta(minutes=dur)

        eventos.append(dict(timestamp=ts, postura=atual,
                            duracao_min=dur, origem="normal", falha=falha))
        ts = fim_bloco

        # Próxima postura respeitando transições válidas
        proxima = _escolher_proxima_postura(atual)
        # Evita pulo direto supino â†’ prono
        if atual == "supino" and proxima == "prono":
            proxima = random.choice(["lateral_direito", "lateral_esquerdo"])
        atual = proxima

    return pd.DataFrame(eventos)

def _expandir_para_grade(df_eventos: pd.DataFrame, passo_min: int, inicio: datetime, fim: datetime) -> pd.DataFrame:
    """Converte eventos (intervalos) para amostras em grade regular (timestamp, postura)."""
    # Constrói a grade
    idx = pd.date_range(start=inicio, end=fim, freq=f"{passo_min}min", inclusive="left")
    out = []
    e_idx = 0

    # Pré-processa intervalos fim:
    ev = df_eventos.copy()
    ev["inicio"] = pd.to_datetime(ev["timestamp"])
    ev["fim"] = ev["inicio"] + pd.to_timedelta(ev["duracao_min"], unit="m")
    ev = ev.sort_values("inicio").reset_index(drop=True)

    for t in idx:
        # avança ponteiro até achar o evento que cobre 't'
        while e_idx < len(ev) - 1 and t >= ev.loc[e_idx, "fim"]:
            e_idx += 1
        postura = ev.loc[e_idx, "postura"]
        out.append({"timestamp": t.isoformat(), "postura": postura})

    return pd.DataFrame(out)

def gerar_sessao_simulada(
    duracao_horas: int = 24,
    seed: int = 42,
    passo_min: int = 5,
    inicio: datetime | None = None,
    perfil: PerfilPaciente | None = None,
) -> pd.DataFrame:
    """
    Gera série temporal de posturas (grade regular):
    - timestamp (ISO)
    - postura (str)
    """
    agora = datetime.now().replace(second=0, microsecond=0)
    if inicio is None:
        inicio = agora - timedelta(hours=duracao_horas)
    fim = inicio + timedelta(hours=duracao_horas)

    if perfil is None:
        perfil = PerfilPaciente()

    df_eventos = _gerar_eventos(inicio, fim, perfil, seed)
    df_grade = _expandir_para_grade(df_eventos, passo_min, inicio, fim)
    return df_grade

def gerar_eventos_sessao(
    duracao_horas: int = 24,
    seed: int = 42,
    inicio: datetime | None = None,
    perfil: PerfilPaciente | None = None,
) -> pd.DataFrame:
    """
    Gera os eventos brutos (intervalos) da sessão, com:
    - timestamp (datetime)
    - postura (str)
    - duracao_min (float)
    - origem (str: 'normal' | 'refeicao')
    - falha (bool)
    - inicio (datetime)
    - fim (datetime)
    """
    agora = datetime.now().replace(second=0, microsecond=0)
    if inicio is None:
        inicio = agora - timedelta(hours=duracao_horas)
    fim = inicio + timedelta(hours=duracao_horas)

    if perfil is None:
        perfil = PerfilPaciente()

    df = _gerar_eventos(inicio, fim, perfil, seed)
    # acrescenta colunas inicio/fim prontas (úteis pra inspeção)
    df["inicio"] = pd.to_datetime(df["timestamp"])
    df["fim"] = df["inicio"] + pd.to_timedelta(df["duracao_min"], unit="m")
    return df


def gerar_sessao_multi(
    pacientes: int,
    horas: float,
    passo_min: int,
    seed: int,
    perfil: str = "medio",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Gera grade e eventos para multiplos pacientes simulados."""
    if pacientes < 1:
        raise ValueError("O numero de pacientes deve ser pelo menos 1.")

    grade_frames: list[pd.DataFrame] = []
    eventos_frames: list[pd.DataFrame] = []

    for idx in range(pacientes):
        paciente_id = f"P{idx + 1}"
        perfil_paciente = PerfilPaciente()  # placeholder para personalizacao futura
        df_grade = gerar_sessao_simulada(
            duracao_horas=horas,
            seed=seed + idx,
            passo_min=passo_min,
            perfil=perfil_paciente,
        ).copy()
        df_grade.insert(0, "paciente_id", paciente_id)
        grade_frames.append(df_grade)

        df_eventos = gerar_eventos_sessao(
            duracao_horas=horas,
            seed=seed + idx,
            perfil=perfil_paciente,
        ).copy()
        df_eventos.insert(0, "paciente_id", paciente_id)
        eventos_frames.append(df_eventos)

    df_grade_all = pd.concat(grade_frames, ignore_index=True)
    df_grade_all = df_grade_all.sort_values(["paciente_id", "timestamp"]).reset_index(drop=True)

    df_eventos_all = pd.concat(eventos_frames, ignore_index=True)
    sort_cols = [col for col in ("inicio", "timestamp") if col in df_eventos_all.columns]
    if sort_cols:
        df_eventos_all = df_eventos_all.sort_values(["paciente_id", sort_cols[0]]).reset_index(drop=True)
    else:
        df_eventos_all = df_eventos_all.sort_values(["paciente_id"]).reset_index(drop=True)

    return df_grade_all, df_eventos_all
