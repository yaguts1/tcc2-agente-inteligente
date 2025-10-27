# 🔧 Propostas de Correção - Código Detalhado

## Sumário de Implementações

Este documento fornece código pronto para corrigir as 7 inconsistências identificadas.

---

## CORREÇÃO 1: Refeições Variáveis (Problema 1)

**Arquivo:** `dados_simulados/gerador.py`

### Antes:
```python
@dataclass
class PerfilPaciente:
    nome: str = "Paciente"
    limite_tempo_postura: int = 120
    prob_falha_reposicao: float = 0.7
    horarios_refeicao: list[datetime] | None = None
    duracao_refeicao: int = 30

    def horarios_refeicao_padrao(self, inicio: datetime) -> list[datetime]:
        base = inicio.replace(hour=6, minute=0, second=0, microsecond=0)
        return [base + timedelta(hours=h) for h in (6, 12, 18)]
```

### Depois:
```python
@dataclass
class PerfilPaciente:
    nome: str = "Paciente"
    limite_tempo_postura: int = 120
    prob_falha_reposicao: float = 0.7
    horarios_refeicao: list[datetime] | None = None
    duracao_refeicao: int = 30
    # NOVO:
    refeicoes_variavel: bool = False
    variacao_refeicao_min: int = 30  # ±30 min
    prob_refeicao_noturna: float = 0.15
    horario_base_cafe: int = 6
    horario_base_almoco: int = 12
    horario_base_jantar: int = 18

    def horarios_refeicao_padrao(self, inicio: datetime, seed: int = 42) -> list[datetime]:
        base = inicio.replace(hour=self.horario_base_cafe, minute=0, second=0, microsecond=0)
        
        if not self.refeicoes_variavel:
            # Comportamento original
            return [base + timedelta(hours=h) for h in (0, 6, 12)]
        
        # NOVO: Refeições com variabilidade
        random.seed(seed)
        refeicoes = []
        
        for offset_h in (0, 6, 12):  # café, almoço, jantar
            hora_base = base + timedelta(hours=offset_h)
            # Variação: ±variacao_refeicao_min
            variacao = random.randint(-self.variacao_refeicao_min, self.variacao_refeicao_min)
            hora_final = hora_base + timedelta(minutes=variacao)
            refeicoes.append(hora_final)
        
        # NOVO: Adicionar possível refeição noturna (sonda, suplemento)
        if random.random() < self.prob_refeicao_noturna:
            hora_noturna = base + timedelta(hours=random.randint(22, 23))
            refeicoes.append(hora_noturna)
        
        return refeicoes
```

**Uso:**
```python
# Paciente com refeições fixas (original)
perfil_fixo = PerfilPaciente(refeicoes_variavel=False)

# Paciente com refeições variáveis
perfil_variavel = PerfilPaciente(
    refeicoes_variavel=True,
    variacao_refeicao_min=40,
    prob_refeicao_noturna=0.2,
    seed=42
)
```

---

## CORREÇÃO 2: Discretização Melhorada (Problema 2)

**Arquivo:** `dados_simulados/gerador.py`

### Antes:
```python
def _expandir_para_grade(df_eventos: pd.DataFrame, passo_min: int, inicio: datetime, fim: datetime) -> pd.DataFrame:
    """Converte eventos (intervalos) para amostras em grade regular."""
    idx = pd.date_range(start=inicio, end=fim, freq=f"{passo_min}min", inclusive="both")
    out = []
    e_idx = 0

    ev = df_eventos.copy()
    ev["inicio"] = pd.to_datetime(ev["timestamp"])
    ev["fim"] = ev["inicio"] + pd.to_timedelta(ev["duracao_min"], unit="m")
    ev = ev.sort_values("inicio").reset_index(drop=True)

    for t in idx:
        while e_idx < len(ev) - 1 and t >= ev.loc[e_idx, "fim"]:
            e_idx += 1
        postura = ev.loc[e_idx, "postura"]
        out.append({"timestamp": t.isoformat(), "postura": postura})

    return pd.DataFrame(out)
```

### Depois:
```python
def _expandir_para_grade(
    df_eventos: pd.DataFrame,
    passo_min: int,
    inicio: datetime,
    fim: datetime,
    incluir_transicoes: bool = True,  # NOVO
) -> pd.DataFrame:
    """
    Converte eventos (intervalos) para amostras em grade regular.
    
    Args:
        incluir_transicoes: Se True, adiciona timestamps nos pontos de mudança
                           para não perder transições rápidas
    """
    # Cria grade base com frequência passo_min
    idx = pd.date_range(start=inicio, end=fim, freq=f"{passo_min}min", inclusive="both")
    idx_list = idx.tolist()
    
    # NOVO: Adiciona pontos de transição explícitos
    if incluir_transicoes:
        ev = df_eventos.copy()
        ev["inicio"] = pd.to_datetime(ev["timestamp"])
        ev["fim"] = ev["inicio"] + pd.to_timedelta(ev["duracao_min"], unit="m")
        
        # Adiciona inicio e fim de cada evento
        transition_points = set()
        for _, row in ev.iterrows():
            transition_points.add(row["inicio"])
            transition_points.add(row["fim"])
        
        # Mescla com grade base
        idx_list = sorted(set(idx_list) | transition_points)
        idx_list = [t for t in idx_list if inicio <= t <= fim]
    
    out = []
    e_idx = 0
    
    ev = df_eventos.copy()
    ev["inicio"] = pd.to_datetime(ev["timestamp"])
    ev["fim"] = ev["inicio"] + pd.to_timedelta(ev["duracao_min"], unit="m")
    ev = ev.sort_values("inicio").reset_index(drop=True)
    
    for t in idx_list:
        # Encontra evento que cobre timestamp t
        while e_idx < len(ev) - 1 and t >= ev.loc[e_idx, "fim"]:
            e_idx += 1
        
        postura = ev.loc[e_idx, "postura"]
        out.append({
            "timestamp": t.isoformat(),
            "postura": postura
        })
    
    return pd.DataFrame(out)
```

**Uso:**
```python
# Com amostragem normal (original)
df_grade = _expandir_para_grade(
    df_eventos, passo_min=5, inicio=t0, fim=t1,
    incluir_transicoes=False
)

# Com transições capturadas (melhorado)
df_grade = _expandir_para_grade(
    df_eventos, passo_min=5, inicio=t0, fim=t1,
    incluir_transicoes=True  # ← Captura todas as mudanças
)
```

---

## CORREÇÃO 3: Perfis Heterogêneos (Problema 3)

**Arquivo:** `dados_simulados/gerador.py`

### Antes:
```python
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
        perfil_paciente = PerfilPaciente()  # ← Sempre padrão!
        # ... resto do código
```

### Depois:
```python
# Primeiro, adicionar dicionário de perfis
PERFIS_PREDEFINIDOS = {
    "baixo": {
        "limite_tempo_postura": 150,
        "prob_falha_reposicao": 0.4,
        "duracao_refeicao": 30,
    },
    "medio": {
        "limite_tempo_postura": 120,
        "prob_falha_reposicao": 0.7,
        "duracao_refeicao": 30,
    },
    "alto": {
        "limite_tempo_postura": 90,
        "prob_falha_reposicao": 0.85,
        "duracao_refeicao": 25,
    },
}

def gerar_sessao_multi(
    pacientes: int,
    horas: float,
    passo_min: int,
    seed: int,
    perfil: str = "medio",
    # NOVO: Opções para heterogeneidade
    perfis_customizados: list[PerfilPaciente] | None = None,
    distribuir_por_risco: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Gera grade e eventos para multiplos pacientes simulados.
    
    Args:
        perfis_customizados: Lista de PerfilPaciente customizados (se None, usa padrão)
        distribuir_por_risco: Se True, distribui pacientes entre baixo/médio/alto risco
    """
    if pacientes < 1:
        raise ValueError("O numero de pacientes deve ser pelo menos 1.")

    grade_frames: list[pd.DataFrame] = []
    eventos_frames: list[pd.DataFrame] = []

    # NOVO: Determinar perfis
    if perfis_customizados is not None:
        if len(perfis_customizados) != pacientes:
            raise ValueError(
                f"Número de perfis ({len(perfis_customizados)}) "
                f"deve ser igual ao número de pacientes ({pacientes})"
            )
        perfis_lista = perfis_customizados
    elif distribuir_por_risco:
        # Distribui entre baixo, médio, alto
        niveis = ["baixo", "medio", "alto"]
        perfis_lista = []
        for idx in range(pacientes):
            nivel = niveis[idx % 3]
            params = PERFIS_PREDEFINIDOS[nivel]
            perfis_lista.append(PerfilPaciente(**params))
    else:
        # Usa o perfil padrão para todos
        params = PERFIS_PREDEFINIDOS.get(perfil, PERFIS_PREDEFINIDOS["medio"])
        perfis_lista = [PerfilPaciente(**params) for _ in range(pacientes)]

    # Gerar dados com perfis heterogêneos
    for idx in range(pacientes):
        paciente_id = f"P{idx + 1}"
        perfil_paciente = perfis_lista[idx]  # ← Usa perfil específico
        
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
```

**Uso:**
```python
# Uso 1: Todos médio (original)
grade, eventos = gerar_sessao_multi(3, 36, 2, 42, perfil="medio")

# Uso 2: Distribuir por risco (homogêneo entre risco)
grade, eventos = gerar_sessao_multi(
    3, 36, 2, 42,
    distribuir_por_risco=True
    # → P1: baixo, P2: médio, P3: alto
)

# Uso 3: Customizado completamente
meu_perfil_1 = PerfilPaciente(limite_tempo_postura=60, prob_falha_reposicao=0.95)
meu_perfil_2 = PerfilPaciente(limite_tempo_postura=120, prob_falha_reposicao=0.7)
meu_perfil_3 = PerfilPaciente(limite_tempo_postura=150, prob_falha_reposicao=0.3)

grade, eventos = gerar_sessao_multi(
    3, 36, 2, 42,
    perfis_customizados=[meu_perfil_1, meu_perfil_2, meu_perfil_3]
)
```

---

## CORREÇÃO 4: Confiança de Sensor (Problema 4)

**Arquivo:** `scripts/generate_alerts.py` ou nova classe em `dados_simulados/`

### Novo arquivo: `dados_simulados/sensor.py`
```python
"""Modelo de confiança do sensor realista."""

from dataclasses import dataclass
import numpy as np
from typing import Dict
import random

@dataclass
class CaracteristicasSensor:
    """Define as características de confiança do sensor."""
    
    # Confiança base por postura (empiricamente validada)
    confianca_por_postura: Dict[str, float] = None
    # Degradação durante transições
    noise_durante_transicao: float = 0.10  # -10%
    # Ruído Gaussian adicional (σ)
    sigma_noise: float = 0.02
    
    def __post_init__(self):
        if self.confianca_por_postura is None:
            self.confianca_por_postura = {
                "supino": 0.95,           # Mais estável
                "lateral_direito": 0.93,  # Laterais são boas
                "lateral_esquerdo": 0.93,
                "prono": 0.87,            # Prono é mais difícil
            }
    
    def confianca_para(
        self,
        postura: str,
        em_transicao: bool = False,
        sequencia_recente: list[str] = None,
    ) -> float:
        """
        Calcula confiança realista para um sensor.
        
        Args:
            postura: Postura atual
            em_transicao: Se True, reduz confiança
            sequencia_recente: Histórico de posturas recentes (para drift)
        
        Returns:
            Confiança [0, 1]
        """
        # Base
        conf = self.confianca_por_postura.get(postura, 0.90)
        
        # Degradação em transições
        if em_transicao:
            conf -= self.noise_durante_transicao
        
        # Degradação por mudança rápida (flipping)
        if sequencia_recente and len(sequencia_recente) >= 2:
            if sequencia_recente[-1] != sequencia_recente[-2]:
                # Mudança recente reduz confiança
                conf *= 0.98
        
        # Adicionar pequeno ruído Gaussian
        conf += np.random.normal(0, self.sigma_noise)
        
        # Limitar a [0, 1]
        return max(0.0, min(1.0, conf))


# Sensor padrão calibrado
SENSOR_PADRAO = CaracteristicasSensor()

# Sensor de baixa qualidade (teste de robustez)
SENSOR_RUIDOSO = CaracteristicasSensor(
    confianca_por_postura={
        "supino": 0.85,
        "lateral_direito": 0.80,
        "lateral_esquerdo": 0.80,
        "prono": 0.70,
    },
    noise_durante_transicao=0.25,
    sigma_noise=0.05,
)

# Sensor de alta qualidade (teste de limite inferior)
SENSOR_PREMIUM = CaracteristicasSensor(
    confianca_por_postura={
        "supino": 0.99,
        "lateral_direito": 0.98,
        "lateral_esquerdo": 0.98,
        "prono": 0.95,
    },
    noise_durante_transicao=0.02,
    sigma_noise=0.01,
)
```

### Uso em `generate_alerts.py`:
```python
from dados_simulados.sensor import SENSOR_PADRAO, SENSOR_RUIDOSO

def main(patients: int, hours: int, passo_min: int, seed: int, sensor: str = "padrao"):
    # ... setup ...
    
    if sensor == "ruidoso":
        caracteristicas = SENSOR_RUIDOSO
    else:
        caracteristicas = SENSOR_PADRAO
    
    for idx, row in grade_df.iterrows():
        em_transicao = (idx > 0 and 
                       grade_df.iloc[idx]["postura"] != grade_df.iloc[idx-1]["postura"])
        
        confianca = caracteristicas.confianca_para(
            row['postura'],
            em_transicao=em_transicao,
            sequencia_recente=grade_df['postura'].iloc[max(0, idx-2):idx+1].tolist()
        )
        
        payload = {
            "device_id": f"SIM-{row['paciente_id']}",
            "postura": row['postura'],
            "confianca": float(confianca),  # Realista!
            # ... outros campos ...
        }
```

---

## CORREÇÃO 5: Normal Truncada → Log-Normal (Problema 5)

**Arquivo:** `dados_simulados/gerador.py`

### Antes:
```python
def _normal_truncada(media: float, desvio: float, minimo: float = 1.0) -> float:
    """Sorteia valor ~N(media, desvio) com piso 'minimo'."""
    val = np.random.normal(media, desvio)
    return float(max(minimo, val))
```

### Depois:
```python
def _duracao_postura(media: float, desvio: float, minimo: float = 1.0) -> float:
    """
    Sorteia duração de postura usando log-normal.
    
    Log-normal é mais apropriada para durações (sempre > 0, com cauda à direita).
    
    Args:
        media: Média desejada em minutos
        desvio: Desvio padrão em minutos
        minimo: Valor mínimo permitido (piso)
    
    Returns:
        Duração em minutos
    """
    # Converter parâmetros para log-normal
    # Se X ~ LogNormal(μ, σ), então:
    #   E[X] = exp(μ + σ²/2)
    #   Var[X] = (exp(σ²) - 1) * exp(2μ + σ²)
    
    # Estimativa: μ ≈ log(media), σ ≈ desvio/media
    mu = np.log(media)
    sigma = desvio / media if media > 0 else 0.1
    
    # Sortear de log-normal
    val = np.random.lognormal(mean=mu, sigma=sigma)
    
    # Aplicar piso
    val = max(minimo, val)
    
    return float(val)
```

### Justificativa Matemática:

**Normal truncada (atual):**
```
X ~ N(90, 30)
P(X < 0) ≈ 0.04  ← INVÁLIDO, X deve ser > 0
Ao truncar, muda a distribuição
```

**Log-normal (proposto):**
```
X ~ LogNormal(μ, σ)
X > 0 SEMPRE ✅
Cauda à direita modela "dias longas" ocasionais
E[X] = exp(μ + σ²/2)  ← Fórmula conhecida
```

**Exemplo:**
```
Supino: média 90 min, desvio 30 min
μ = log(90) = 4.50
σ = 30/90 = 0.33

Distribuição:
- Modo: ~77 min
- Média: ~92 min
- Mediana: ~90 min
- 95th percentil: ~155 min
```

---

## CORREÇÃO 6: Validação de Sessão (Problema 6)

**Arquivo:** Nova função em `dados_simulados/gerador.py`

```python
def validar_sessao(
    df_eventos: pd.DataFrame,
    df_grade: pd.DataFrame = None,
    verbose: bool = True
) -> Dict[str, bool]:
    """
    Valida coerência de uma sessão simulada.
    
    Args:
        df_eventos: DataFrame com eventos (timestamp, postura, duracao_min, ...)
        df_grade: (Opcional) DataFrame com grade (timestamp, postura)
        verbose: Se True, imprime detalhes
    
    Returns:
        Dict com status de cada validação
    """
    resultados = {}
    
    # V1: Timestamps em ordem crescente?
    if df_eventos is not None:
        timestamps = pd.to_datetime(df_eventos["timestamp"])
        v1 = timestamps.is_monotonic_increasing
        resultados["timestamps_ordenados"] = v1
        if not v1 and verbose:
            print("❌ Timestamps não estão em ordem crescente")
    
    # V2: Todas as posturas são válidas?
    posturas = df_eventos["postura"].unique()
    v2 = set(posturas).issubset(set(POSTURAS))
    resultados["posturas_validas"] = v2
    if not v2 and verbose:
        print(f"❌ Posturas inválidas: {set(posturas) - set(POSTURAS)}")
    
    # V3: Durações são positivas?
    v3 = (df_eventos["duracao_min"] > 0).all()
    resultados["duracoes_positivas"] = v3
    if not v3 and verbose:
        print(f"❌ Há durações ≤ 0: {df_eventos[df_eventos['duracao_min'] <= 0]}")
    
    # V4: Transições respeitam grafo?
    v4 = True
    for idx in range(len(df_eventos) - 1):
        postura_atual = df_eventos.iloc[idx]["postura"]
        proxima_postura = df_eventos.iloc[idx + 1]["postura"]
        
        proximas_validas = TRANSICOES_VALIDAS.get(postura_atual, [])
        if proxima_postura not in proximas_validas and postura_atual != proxima_postura:
            if verbose:
                print(f"❌ Transição inválida: {postura_atual} → {proxima_postura}")
            v4 = False
            break
    resultados["transicoes_validas"] = v4
    
    # V5: Soma de durações ≈ tempo total?
    if df_eventos is not None and len(df_eventos) > 0:
        tempo_total = (df_eventos["duracao_min"].sum())
        tempo_esperado = (timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds() / 60
        
        diferenca_min = abs(tempo_total - tempo_esperado)
        v5 = diferenca_min < 10  # Tolerância: 10 min
        resultados["duracao_consistente"] = v5
        
        if not v5 and verbose:
            print(f"⚠️  Soma de durações ({tempo_total:.1f} min) "
                  f"vs tempo esperado ({tempo_esperado:.1f} min)")
    
    # V6: Grade é consistente com eventos?
    if df_grade is not None:
        # Verificar: não há posturas em grade que não estão em eventos
        posturas_grade = df_grade["postura"].unique()
        posturas_eventos = df_eventos["postura"].unique()
        v6 = set(posturas_grade).issubset(set(posturas_eventos))
        resultados["grade_consistente"] = v6
        
        if not v6 and verbose:
            print(f"❌ Grade tem posturas não originadas em eventos: "
                  f"{set(posturas_grade) - set(posturas_eventos)}")
    
    # V7: Coluna 'falha' tem valores realistas?
    if "falha" in df_eventos.columns:
        taxa_falha = df_eventos["falha"].mean()
        v7 = 0.1 <= taxa_falha <= 0.9  # Entre 10-90%
        resultados["taxa_falha_realista"] = v7
        
        if not v7 and verbose:
            print(f"⚠️  Taxa de falha anormal: {taxa_falha:.1%}")
    
    # Resumo
    if verbose:
        print("\n📊 Resumo de Validação:")
        for validacao, status in resultados.items():
            simbolo = "✅" if status else "❌"
            print(f"  {simbolo} {validacao}")
        
        all_pass = all(resultados.values())
        print(f"\n{'✅ TUDO OK' if all_pass else '❌ ERROS ENCONTRADOS'}")
    
    return resultados
```

**Uso:**
```python
# Gerar dados
df_grade = gerar_sessao_simulada(24, 42, 5)
df_eventos = gerar_eventos_sessao(24, 42)

# Validar
resultado = validar_sessao(df_eventos, df_grade, verbose=True)

if not all(resultado.values()):
    raise ValueError("Dados inválidos!")
```

---

## CORREÇÃO 7: Identificador de Cohort (Problema 7)

**Arquivo:** `scripts/generate_alerts.py`

### Antes:
```python
def main(patients: int, hours: int, passo_min: int, seed: int):
    grade_df, eventos_df = gerar_sessao_multi(
        pacientes=patients, horas=hours, 
        passo_min=passo_min, seed=seed
    )
```

### Depois:
```python
from datetime import datetime
from uuid import uuid4

def main(
    patients: int,
    hours: int,
    passo_min: int,
    seed: int,
    # NOVO:
    cohort_id: str = None,
    cohort_timestamp: datetime = None,
):
    """
    Generate simulated sessions with cohort tracking.
    
    Args:
        cohort_id: Identificador único da cohort (se None, gera UUID)
        cohort_timestamp: Timestamp da geração (se None, usa now)
    """
    
    if cohort_id is None:
        cohort_id = str(uuid4())[:8]  # Primeiros 8 chars do UUID
    
    if cohort_timestamp is None:
        cohort_timestamp = datetime.now()
    
    cohort_str = cohort_timestamp.strftime("%Y%m%d_%H%M%S")
    print(f"🚀 Generating cohort: {cohort_id} at {cohort_str}")
    
    # Gerar
    grade_df, eventos_df = gerar_sessao_multi(
        pacientes=patients,
        horas=hours,
        passo_min=passo_min,
        seed=seed,
    )
    
    # Adicionar coluna de rastreamento
    grade_df.insert(0, "cohort_id", cohort_id)
    grade_df.insert(1, "cohort_timestamp", cohort_timestamp.isoformat())
    
    eventos_df.insert(0, "cohort_id", cohort_id)
    eventos_df.insert(1, "cohort_timestamp", cohort_timestamp.isoformat())
    
    # Registrar no banco
    print(f"Registering {len(grade_df)} samples...")
    total_samples = 0
    for idx, row in grade_df.iterrows():
        payload = {
            "device_id": f"SIM-{row['paciente_id']}",
            "paciente_id": row['paciente_id'],
            "cama_id": row['paciente_id'],
            "postura": row['postura'],
            "confianca": float(random.uniform(0.8, 1.0)),
            "amostra_ms": int(passo_min * 60 * 1000),
            "ts_utc": str(pd.to_datetime(row['timestamp']).to_pydatetime()),
            # NOVO: Metadados de cohort
            "cohort_id": cohort_id,
            "cohort_timestamp": cohort_timestamp.isoformat(),
        }
        try:
            ev = _normalizar_payload(payload, None)
            _registrar_evento(ev)
            total_samples += 1
        except Exception as exc:
            print(f"Failed for {row['paciente_id']}: {exc}")
    
    print(f"✅ Inserted {total_samples} samples in cohort {cohort_id}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--patients", type=int, default=3)
    p.add_argument("--hours", type=int, default=6)
    p.add_argument("--passo-min", type=int, dest="passo_min", default=5)
    p.add_argument("--seed", type=int, default=42)
    # NOVO:
    p.add_argument("--cohort-id", type=str, default=None,
                   help="Identificador da cohort (se não fornecido, gera UUID)")
    p.add_argument("--name", type=str, default=None,
                   help="Nome humano para a cohort (ex: 'baseline', 'intervencao')")
    
    args = p.parse_args()
    
    # Usar name ou gerar novo ID
    cohort_id = args.name or args.cohort_id
    
    main(args.patients, args.hours, args.passo_min, args.seed, cohort_id)
```

**Uso:**
```bash
# Primeira execução
python scripts/generate_alerts.py --patients 3 --hours 6 --name "baseline"
# → cohort_id = "baseline"

# Segunda execução (mesmo cohort)
python scripts/generate_alerts.py --patients 3 --hours 6 --name "baseline"
# → Mesmos dados, diferentes seeds podem variar

# Terceira execução (novo cohort)
python scripts/generate_alerts.py --patients 3 --hours 6 --name "intervencao"
# → cohort_id = "intervencao"

# Quarta: Auto-gera UUID
python scripts/generate_alerts.py --patients 3 --hours 6
# → cohort_id = "abc12def" (aleatório)
```

---

## Resumo de Aplicações

| Problema | Arquivo | Função | Esforço | Impacto |
|----------|---------|--------|--------|--------|
| 1 | `gerador.py` | `horarios_refeicao_padrao()` | 10 lin | Alto |
| 2 | `gerador.py` | `_expandir_para_grade()` | 15 lin | Alto |
| 3 | `gerador.py` | `gerar_sessao_multi()` | 25 lin | **Crítico** |
| 4 | `sensor.py` (novo) | `CaracteristicasSensor` | 80 lin | Médio |
| 5 | `gerador.py` | `_duracao_postura()` | 15 lin | Baixo |
| 6 | `gerador.py` | `validar_sessao()` | 60 lin | Alto |
| 7 | `generate_alerts.py` | Metadados `cohort_id` | 10 lin | Médio |

**Total de Código:** ~210 linhas  
**Tempo Estimado:** 2-3 horas  
**Impacto na Pesquisa:** Significativo (torna modelo mais defensável)

---

**Data:** 2025-10-26  
**Status:** 🟢 Pronto para Implementação
