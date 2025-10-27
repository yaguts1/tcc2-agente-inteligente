# 📊 Análise Completa da Simulação de Dados de Úlceras de Pressão

## Resumo Executivo

Este documento analisa as diferentes formas de geração de dados para simulação de pacientes em risco de úlceras de pressão (pressure ulcers - PU). O sistema simula o comportamento de repouso de pacientes internados, detectando imobilidade prolongada que pode levar ao desenvolvimento de úlceras de pressão.

**Foco Principal:** Identificar inconsistências na geração de dados e na lógica de simulação que afetam a precisão do modelo acadêmico.

---

## 📋 Índice

1. [Componentes Principais](#componentes-principais)
2. [Fluxo de Geração de Dados](#fluxo-de-geração-de-dados)
3. [Modelos de Simulação](#modelos-de-simulação)
4. [Inconsistências Identificadas](#inconsistências-identificadas)
5. [Recomendações](#recomendações)

---

## 1. Componentes Principais

### 1.1 Pipeline de Geração

```
┌─────────────────────────────────────────────────────────┐
│ Geração de Dados                                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  PerfilPaciente (Parâmetros)                           │
│       ↓                                                 │
│  _gerar_eventos()  → Eventos em Intervalos            │
│       ↓                                                 │
│  _expandir_para_grade() → Grade Regular (2-5 min)     │
│       ↓                                                 │
│  Salvar CSV (generate_ui.py)                          │
│       ↓                                                 │
│  Registrar via API (generate_alerts.py)               │
│       ↓                                                 │
│  Motor de Alertas (engine.py + decisor.py)            │
│       ↓                                                 │
│  Alertas de Imobilidade                               │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Arquivos Principais

| Arquivo | Função | Critério |
|---------|--------|----------|
| `dados_simulados/gerador.py` | Core de geração | 370 linhas |
| `dados_simulados/generate_ui.py` | Interface/CLI | 110 linhas |
| `scripts/generate_alerts.py` | Integração DB | 70 linhas |
| `modulo_alerta/engine.py` | Motor de alertas | 40 linhas |
| `nucleo/decisor.py` | Lógica de decisão | 240 linhas |

---

## 2. Fluxo de Geração de Dados

### 2.1 Função Principal: `gerar_sessao_simulada()`

```python
def gerar_sessao_simulada(
    duracao_horas: int = 24,
    seed: int = 42,
    passo_min: int = 5,
    inicio: datetime | None = None,
    perfil: PerfilPaciente | None = None,
) -> pd.DataFrame:
```

**O que faz:**
1. Define período inicial (se não fornecido: `now - duracao_horas`)
2. Gera eventos em intervalos (`_gerar_eventos()`)
3. Expande para grade regular com amostragem (`_expandir_para_grade()`)

**Saída:**
- DataFrame com colunas: `timestamp` (ISO), `postura` (string)
- Frequência: 5-10 minutos (configurável)

---

### 2.2 Função Central: `_gerar_eventos()`

Gera os eventos brutos que representam **mudanças de postura**.

**Algoritmo:**

```
1. Inicializa ts = inicio, atual = "supino"
2. Enquanto ts < fim:
   
   a) Verifica se caiu em horário de refeição
      → Se sim: força supino por 30 min
      → Se não: continua
   
   b) Sorteia duração para postura atual
      - Usa distribuição normal truncada N(μ, σ)
      - μ varia por postura (ver tabela abaixo)
      - Mínimo: 5 minutos
   
   c) Simula "falha de reposicionamento"
      - Se dur > limite (120 min):
        - Probability p_falha = 0.7
        - Se ocorre falha: estende duração em +N(μ, σ)
   
   d) Escolhe próxima postura aleatória
      - Respeita grafo de transições válidas
      - Bloqueia supino → prono direto
   
   e) Registra evento
      - timestamp, postura, duração, origem, falha
```

**Tempos Esperados por Postura:**

| Postura | Média | Desvio | Tempo Real | Observações |
|---------|-------|--------|-----------|-------------|
| Supino | 90 min | 30 | 3h/dia | Maior conforto, mais tempo |
| Lateral Direito | 120 min | 40 | 4h/dia | Inclinação natural |
| Lateral Esquerdo | 120 min | 40 | 4h/dia | Simétrico |
| Prono | 45 min | 20 | 1.5h/dia | Desconfortável, pouco tempo |

**Limite de Imobilidade (Janela de Detecção):**

Configurável por perfil (ver `configuracao.py`):
- **Perfil Baixo:** 120 minutos
- **Perfil Médio:** 90 minutos
- **Perfil Alto:** 60 minutos

---

### 2.3 Transições de Postura (Grafo)

```
TRANSICOES_VALIDAS = {
    "supino":            → ["lateral_direito", "lateral_esquerdo"]
    "lateral_direito":   → ["supino", "prono"]
    "lateral_esquerdo":  → ["supino", "prono"]
    "prono":             → ["lateral_direito", "lateral_esquerdo"]
}

Bloqueio Adicional:
- supino → prono (DIRETO) é proibido
  ├─ Força transição por lateral
  └─ Simula limitação fisiológica real
```

**Validação:** Todas as transições mantêm ciclos válidos. ✅

---

### 2.4 Conceito de "Refeição"

**Horários Padrão (se não fornecidos):**
```
base = dia 6:00
refeições = [6h, 12h, 18h]
           = [início+6h, início+12h, início+18h]
```

**Durante Refeição:**
- Força postura `supino` por 30 minutos
- Marca `origem="refeicao"` no evento
- Não conta como "falha"

**Problema 1:** Horários fixos não consideram variabilidade clínica ⚠️

---

### 2.5 Função: `_expandir_para_grade()`

Converte eventos (intervalos) → grade regular (amostras).

**Algoritmo:**

```python
# Cria grade com frequência passo_min (ex: 5 min)
idx = pd.date_range(start, end, freq="5min")

for t in idx:
    # Encontra qual evento cobre o timestamp t
    postura = evento.loc[t]
    # Adiciona amostra à grade
    out.append({"timestamp": t, "postura": postura})
```

**Comportamento:**
- Grade **contínua** e **regular**
- Cada timestamp tem exatamente uma postura
- Preserva mudanças de postura

**Problema 2:** Pode não preservar exatamente a mudança instantânea ⚠️

---

## 3. Modelos de Simulação

### 3.1 Variantes de Geração

#### A) Single Patient (`generate_single()`)

```python
generate_single(
    paciente_id: str = "PAC-0001",
    horas: int = 36,
    passo: int = 2,
    seed: int = 42
)
```

**Saída:**
- `PAC-0001_grade_36h_2m_seed42_YYYYMMDD_HHMMSS.csv`
- `PAC-0001_eventos_36h_seed42_YYYYMMDD_HHMMSS.csv`

**Características:**
- 1 paciente
- Determinístico (usa seed)
- Ideal para teste/validação

---

#### B) Multi-Patient (`generate_multi()`)

```python
generate_multi(
    n: int = 3,
    horas: int = 36,
    passo: int = 2,
    seed: int = 42
)
```

**Saída:**
- `multi_grade_3p_36h_2m_seed42_YYYYMMDD_HHMMSS.csv`
- `multi_eventos_3p_36h_seed42_YYYYMMDD_HHMMSS.csv`

**Características:**
- `n` pacientes (P1, P2, ..., Pn)
- Cada um com seed diferente (`seed + idx`)
- Perfis **idênticos** para todos ← **PROBLEMA 3**
- Concatenados e ordenados por paciente_id

---

#### C) Geração com Registrazione (`generate_alerts.py`)

```python
main(
    patients: int = 3,
    hours: int = 6,
    passo_min: int = 5,
    seed: int = 42
)
```

**Diferenças:**
1. Cria registros `Paciente` no banco de dados
2. Para cada amostra da grade, chama `/api/eventos`
3. Injeta dados incrementalmente (stream-like)
4. Confiança: `random.uniform(0.8, 1.0)` ← **PROBLEMA 4**

---

### 3.2 Motor de Alertas (`decisor.py`)

**Algoritmo de Detecção:**

```
Estado: EstadoDecisor(perfil, paciente_id)
  ├─ alerta_atual: None ou dict
  ├─ run_postura: postura atual
  ├─ run_inicio: quando começou
  └─ baseline_postura: postura do alerta

Para cada amostra (timestamp, postura):
  
  1. Se mudança de postura:
     └─ reset run_inicio = timestamp
  
  2. Se em alerta E movimento detectado:
     └─ Se movimento ≥ histerese (5 min):
        ├─ Fecha alerta
        ├─ Ativa cooldown (10 min)
  
  3. Se SEM alerta E postura > janela:
     └─ Abre NOVO alerta
        ├─ baseline = postura atual
        ├─ inicio = run_inicio + janela
```

**Parâmetros:**

| Parâmetro | Valor | Tipo |
|-----------|-------|------|
| janela_min | 60-120 | perfil-dependente |
| histerese_min | 5 | fixo |
| cooldown_min | 10 | fixo |

**Exemplo com Perfil Médio (janela = 90 min):**

```
00:00  Postura X inicia
01:30  +90 min → Alerta "ABERTO"
02:00  Muda para Y
02:05  +5 min de movimento → Alerta "FECHADO"
02:15  Cooldown expira
```

---

## 4. Inconsistências Identificadas

### ⚠️ PROBLEMA 1: Horários de Refeição Fixos

**Localização:** `dados_simulados/gerador.py:38-40`

```python
def horarios_refeicao_padrao(self, inicio: datetime) -> list[datetime]:
    base = inicio.replace(hour=6, minute=0, second=0, microsecond=0)
    return [base + timedelta(hours=h) for h in (6, 12, 18)]
    # Produz: 12h, 18h, 00h (próx dia)
```

**Problemas:**
- ✗ Assume refeições em horário fixo (6h-12h-18h)
- ✗ Não varia com variabilidade do paciente
- ✗ Não modela internação real (pode ter refeições diferentes)
- ✗ Não respeita refeições noturnasadministradas por sonda

**Impacto:** Reduz realismo da simulação para pacientes críticos/noturnos.

**Recomendação:**
```python
class PerfilPaciente:
    # Adicionar
    refeicoes_variavel: bool = False  # Se True, sorteia horários
    probabilidade_refeicao_noturna: float = 0.2
```

---

### ⚠️ PROBLEMA 2: Discretização de Grade Pode Perder Eventos

**Localização:** `dados_simulados/gerador.py:160-178`

```python
def _expandir_para_grade(df_eventos, passo_min, inicio, fim):
    idx = pd.date_range(start=inicio, end=fim, freq=f"{passo_min}min")
    # Problema: Se evento dura 5 min com passo de 2 min
    # Pode não amostrar a transição corretamente
```

**Exemplo:**
```
Evento: Supino 00:00-00:05, depois Lateral 00:05-01:00
Grade (passo=2):
00:00 → Supino
00:02 → Supino
00:04 → Supino
00:06 → Lateral      ← Pula a transição em 00:05!
```

**Impacto:** Motor de alertas pode não detectar mudanças rápidas.

**Recomendação:**
```python
# Adicionar timestamps de mudança explicitamente
ts_mudancas = [evento['timestamp'] for evento in eventos]
idx_expanded = sorted(set(idx) | set(ts_mudancas))
```

---

### ⚠️ PROBLEMA 3: Perfis Idênticos em Multi-Patient

**Localização:** `dados_simulados/gerador.py:205-212`

```python
for idx in range(pacientes):
    paciente_id = f"P{idx + 1}"
    perfil_paciente = PerfilPaciente()  # Sempre padrão!
    # Problema: Todos os pacientes têm MESMO perfil
```

**O que deveria fazer:**
```python
PERFIS_DISPONIVEIS = {
    "baixo": PerfilPaciente(
        limite_tempo_postura=150,
        prob_falha_reposicao=0.5,
    ),
    "medio": PerfilPaciente(
        limite_tempo_postura=120,
        prob_falha_reposicao=0.7,
    ),
    "alto": PerfilPaciente(
        limite_tempo_postura=90,
        prob_falha_reposicao=0.9,
    ),
}

# Usar:
perfil_paciente = PERFIS_DISPONIVEIS[
    ["baixo", "medio", "alto"][idx % 3]
]
```

**Impacto:** Simulação não representa heterogeneidade clínica (alguns pacientes têm MAIOR risco).

---

### ⚠️ PROBLEMA 4: Confiança Aleatória sem Correlação

**Localização:** `scripts/generate_alerts.py:50-52`

```python
"confianca": float(random.uniform(0.8, 1.0))
# Problema: Completamente aleatória, não correlata com:
# - Postura (lateral é mais confiável que supino)
# - Movimento (transições causam incerteza)
# - Paciente individual
```

**Impacto:** 
- Sensor ruidoso irrealista
- Não testa robustez do sistema a ruído correlado

**Recomendação:**
```python
class SensorCaracteristicas:
    confianca_por_postura: dict = {
        "supino": 0.95,
        "lateral_direito": 0.92,
        "lateral_esquerdo": 0.92,
        "prono": 0.88,
    }
    noise_durante_transicao: float = 0.15
    
    def confidence_for(postura, em_transicao=False):
        base = self.confianca_por_postura[postura]
        if em_transicao:
            base -= noise_durante_transicao
        return base + normal(0, 0.02)  # Add small jitter
```

---

### ⚠️ PROBLEMA 5: Distribuição Normal Pode Gerar Valores Negativos

**Localização:** `dados_simulados/gerador.py:50-51`

```python
def _normal_truncada(media, desvio, minimo=1.0):
    val = np.random.normal(media, desvio)
    return float(max(minimo, val))
```

**Análise:**
- Para `supino: N(90, 30)`, P(X < 1) ≈ 0.00001 → OK
- Para `prono: N(45, 20)`, P(X < 1) ≈ 0.0001 → OK
- Mas para `prono`, P(X < 10) ≈ 0.1% → Trunca 1 em 1000

**Impacto:** Menor impacto, mas viola pressupostos de distribuição.

**Recomendação:**
```python
def _normal_truncada(media, desvio, minimo=1.0):
    # Usar Beta escalada para garantir semântica
    # Ou usar lognormal
    return float(
        np.random.lognormal(
            mean=np.log(media),
            sigma=desvio/media
        )
    )
```

---

### ⚠️ PROBLEMA 6: Falta de Validação de Coerência

Não há validação de:
1. ✗ Soma das durações = tempo total?
2. ✗ Transições respeitam grafo?
3. ✗ Refeições não sobrescrevem eventos?
4. ✗ Datas em ordem crescente?

**Recomendação:** Adicionar função `validar_sessao()`.

---

### ⚠️ PROBLEMA 7: Parameter Coupling em Geração Multi

**Localização:** `scripts/generate_alerts.py:36-42`

```python
def main(patients: int, hours: int, passo_min: int, seed: int):
    grade_df, eventos_df = gerar_sessao_multi(
        pacientes=patients,
        horas=hours,
        passo_min=passo_min,
        seed=seed
    )
```

Problema: Se 2 execuções com `--seed 42` geram mesmo resultado? 
- ✓ SIM (seed é determinístico)

Mas se user quer 2 cohorts diferentes?
- ✗ NÃO há forma de variar sem mudar seed

**Recomendação:** Adicionar paramêtro de "cohort_id".

---

## 5. Recomendações

### 5.1 Curto Prazo (Correções Críticas)

#### R1: Adicionar Validação de Sessão
```python
def validar_sessao(df_eventos):
    """Valida coerência da sessão gerada."""
    assert df_eventos["timestamp"].is_monotonic_increasing
    assert set(df_eventos["postura"]).issubset(POSTURAS)
    assert df_eventos["duracao_min"].min() > 0
    # + outros testes
```

#### R2: Corrigir Perfis Multi-Patient
```python
# Em gerar_sessao_multi()
for idx in range(pacientes):
    perfil_paciente = PERFIS[perfil][idx % len(PERFIS[perfil])]
    # Usa perfis parametrizados
```

#### R3: Melhorar Modelagem de Confiança
```python
class SensorNoise:
    @staticmethod
    def confidence_for(postura, em_transicao):
        # Ver PROBLEMA 4 acima
```

---

### 5.2 Médio Prazo (Melhorias Acadêmicas)

#### R4: Adicionar Fatores de Risco
```python
@dataclass
class FatorRisco:
    tipo: str  # "mobilidade", "nutricao", "incontinencia"
    severidade: float  # 0-1
    efeito: Callable  # Como afeta simulação

class PerfilPaciente:
    fatores_risco: List[FatorRisco] = field(default_factory=list)
```

#### R5: Modelar Intervenções
```python
class Intervencao:
    tipo: str  # "reposicionamento", "mobilizacao"
    inicio: datetime
    duracao_min: int
    eficacia: float
    
    def aplicar(self, estado: EstadoDecisor):
        # Reset contadores de imobilidade
```

#### R6: Adicionar Variabilidade Circadiana
```python
class RitmoCicardiano:
    """Modela atividade/sono 24h."""
    atividade_por_hora = [0.2, 0.1, 0.1, ..., 0.8]
    
    def prob_reposicionamento(self, hora: int) -> float:
        # Pacientes se mexem menos à noite
```

---

### 5.3 Longo Prazo (Pesquisa)

#### R7: Calibração com Dados Reais
- Comparar `TEMPOS_POSTURA` com coorte real
- Ajustar `prob_falha_reposicao` baseado em evidência clínica
- Validar `janela_min` com sensibilidade/especificidade

#### R8: Modelo Hierárquico Bayesiano
```
population_level → PerfilPaciente → Sessao Individual
     (prior)      (observed data)   (inference)
```

#### R9: Teste de Robustez
- Variar parâmetros sistematicamente
- Medir viés do motor de alertas
- Documentar sensibilidade

---

## 6. Tabela de Severidade

| ID | Problema | Severidade | Esforço | Impacto | Status |
|----|----------|-----------|--------|--------|--------|
| 1 | Refeições fixas | 🟡 Média | 2h | Realismo | Pendente |
| 2 | Grade discretização | 🔴 Alta | 4h | Precisão | Pendente |
| 3 | Perfis idênticos | 🔴 Alta | 1h | Validação | Pendente |
| 4 | Confiança aleatória | 🟡 Média | 3h | Robustez | Pendente |
| 5 | Normal truncada | 🟢 Baixa | 1h | Técnico | Opcional |
| 6 | Falta validação | 🔴 Alta | 2h | Confiabilidade | Pendente |
| 7 | Parameter coupling | 🟡 Média | 1h | Usabilidade | Pendente |

---

## 7. Exemplo de Execução Corrigida

```python
# Novo workflow proposto
from dados_simulados.gerador import (
    gerar_sessao_multi,
    PerfilPaciente,
    validar_sessao  # Nova função
)

# Perfis heterogêneos
perfis = {
    "alto_risco": PerfilPaciente(
        limite_tempo_postura=60,
        prob_falha_reposicao=0.9,
        refeicoes_variavel=True,
    ),
    "medio_risco": PerfilPaciente(
        limite_tempo_postura=120,
        prob_falha_reposicao=0.7,
    ),
    "baixo_risco": PerfilPaciente(
        limite_tempo_postura=150,
        prob_falha_reposicao=0.5,
    ),
}

# Gerar com validação
df_grade, df_eventos = gerar_sessao_multi(
    pacientes=3,
    horas=36,
    passo_min=2,
    seed=42,
    perfis_customizados=[
        perfis["alto_risco"],
        perfis["medio_risco"],
        perfis["baixo_risco"],
    ]
)

# Validar
validar_sessao(df_eventos)

# Usar
for idx, row in df_grade.iterrows():
    _registrar_evento(row)
```

---

## 8. Conclusão

A simulação atual é **funcional** mas possui **inconsistências acadêmicas** que limitam sua validez como modelo de comportamento real. As principais correções (Problemas 2, 3, 6) são críticas para uma publicação/defesa acadêmica.

**Prioridade 1 (Fazer antes da defesa):**
- ✅ Problema 3: Perfis heterogêneos
- ✅ Problema 6: Validação de coerência

**Prioridade 2 (Desejável):**
- Problema 2: Grade discretização
- Problema 4: Confiança correlada

**Prioridade 3 (Futuro):**
- Problema 1: Refeições variáveis
- Problemas 5, 7: Otimizações técnicas

---

**Data de Análise:** 2025-10-26  
**Analisador:** GitHub Copilot  
**Versão do Projeto:** feat/frontend-replace-site  
**Status:** ✅ Análise Completa
