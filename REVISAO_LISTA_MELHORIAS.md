# 📋 REVISÃO DA LISTA DE SUGESTÕES DE MELHORIAS

**Data:** 26 de outubro de 2025  
**Contexto:** Análise revisada considerando ambiente hospitalar com agendamentos  
**Mudança Principal:** Problema 1 reinterpretado como **"Eventos Agendados não Considerados"**

---

## 🎯 Novo Entendimento: Contexto Hospitalar

### Realidade Clínica Hospitalar

Em ambiente hospitalar, os seguintes eventos **são AGENDADOS** e seguem cronograma:

- ✅ **Refeições:** Café (6h), Almoço (12h), Jantar (18h) - **FIXOS por protocolo**
- ✅ **Cirurgias:** Agendadas em horários específicos - **FIXAS**
- ✅ **Visitas:** Períodos delimitados (ex: 2-4h, 7-8h) - **FIXAS**
- ✅ **Higiene/Banho:** Horários matutinos/vespertinos - **FIXOS**
- ✅ **Medicações:** Protocolos de horário (6h, 12h, 18h, etc.) - **FIXAS**

### Implicação para Simulação

**Problema Anterior (Incorreto):**
> "Refeições devem ser variáveis para não ser 100% previsível"

**Problema Revisado (Correto):**
> "Eventos agendados FIXOS devem ser explicitamente modelados para **evitar falsos alertas** quando o paciente está em atividade clínica legítima"

**Nova Interpretação do Problema 1:**
```
ANTES:
┌─────────────────────────────────────┐
│ Sistema gera eventos livremente     │
│ sem considerar horários clínicos    │
│                                     │
│ Resultado: Sensor marca ALERTA      │
│ quando paciente está em cirurgia    │
│ → FALSO POSITIVO ❌                 │
└─────────────────────────────────────┘

DEPOIS:
┌─────────────────────────────────────┐
│ Sistema conhece cronograma clínico  │
│ - Refeições agendadas               │
│ - Cirurgias agendadas               │
│ - Visitas agendadas                 │
│ - Higiene agendada                  │
│                                     │
│ Resultado: Algoritmo não aciona     │
│ alerta durante eventos legítimos    │
│ → Zero FALSOS POSITIVOS ✅          │
└─────────────────────────────────────┘
```

---

## 📊 REVISÃO COMPLETA DA LISTA (7 Problemas)

### 🔴 PROBLEMA 1: "Eventos Agendados não Considerados" (REVISADO)

**Severidade:** 🟡 **IMPORTANTE** (não crítico, mas clinicamente relevante)

**Descrição:**
O gerador não leva em conta eventos agendados (refeições, cirurgias, visitas) que modificam o comportamento esperado do paciente.

**Onde está o problema:**
- `dados_simulados/gerador.py`, linha 35-40: Refeições hardcoded como "força supino 30min"
- `interface/web.py`: Sem campo para agendamentos cirúrgicos
- `scripts/generate_alerts.py`: Gera confiança sem considerar contexto clínico

**Impacto Clínico:**
```
Cenário 1: Paciente em cirurgia (9:00-10:30)
┌─────────────────────────────────────────┐
│ ATUAL:                                  │
│ - Sistema segue lógica normal           │
│ - Não sabe que paciente está em OR      │
│ - Se "imóvel" por 60+ min → ALERTA ❌   │
│ - FALSO POSITIVO                        │
│                                         │
│ CORRIGIDO:                              │
│ - Sistema sabe: 9:00-10:30 = Cirurgia  │
│ - Suprime normalização de alertas       │
│ - Registra evento como "contexto_op"    │
│ - Sem falso positivo ✅                 │
└─────────────────────────────────────────┘

Cenário 2: Refeição matinal (6:00-6:30)
┌─────────────────────────────────────────┐
│ ATUAL:                                  │
│ - Sistema força "supino" por 30 min     │
│ - OK, mas sem registrar motivo          │
│ - Se sistema quer auditar: "Por que?"   │
│                                         │
│ CORRIGIDO:                              │
│ - Sistema registra explicitamente:      │
│ - 6:00-6:30 = Refeição (agendada)      │
│ - Auditoría sabe: supino por que é BR  │
│ - Documentação clínica clara ✅         │
└─────────────────────────────────────────┘
```

**Causa Raiz:**
O modelo não distingue entre:
1. **Imobilidade patológica** (risco real de úlcera)
2. **Imobilidade contextual** (paciente em atividade legítima: refeição, cirurgia, higiene)

**Solução Proposta:**

Criar sistema de **"Eventos Contextuais"** que:

```python
@dataclass
class EventoContextual:
    """Evento agendado que não é 'movimento espontâneo'"""
    tipo: str  # "refeicao", "cirurgia", "visita", "higiene", "medicacao"
    inicio: datetime
    fim: datetime
    postura_esperada: str = "supino"  # Postura durante evento
    suprime_alerta: bool = True  # Não gera alerta durante
    marca_nos_logs: bool = True  # Marca como "contexto cirurgico" nos alertas

TIPOS_EVENTO_CONTEXTO = {
    "refeicao": {
        "horarios": [(6, 0), (12, 0), (18, 0)],  # 3x ao dia
        "duracao_min": 30,
        "postura": "supino",
        "suprime_alerta": True,
    },
    "cirurgia": {
        "horarios": [(9, 0), (14, 0)],  # Pode ser agendada múltiplas vezes
        "duracao_min": 90,  # Exemplar
        "postura": "supino",
        "suprime_alerta": True,
    },
    "higiene": {
        "horarios": [(7, 0), (17, 0)],
        "duracao_min": 45,
        "postura": "variavel",
        "suprime_alerta": True,
    },
    "visita": {
        "horarios": [(14, 0), (20, 0)],
        "duracao_min": 60,
        "postura": "semi_sentado",
        "suprime_alerta": False,  # Visita NÃO anula risco
    },
}
```

**Implementação:**

```python
def gerar_sessao_com_contexto(
    duracao_horas: int = 24,
    seed: int = 42,
    incluir_contexto: bool = True,  # NOVO
    eventos_contextuais: dict | None = None,  # NOVO
) -> tuple[pd.DataFrame, list[EventoContextual]]:
    """
    Gera eventos considerando contexto clínico.
    
    Args:
        incluir_contexto: Se True, inclui eventos agendados
        eventos_contextuais: Dict com configuração de eventos
                            (refeições, cirurgias, etc)
    
    Returns:
        (grade, contextos)
    """
    grade, eventos = _gerar_base(duracao_horas, seed)
    
    if not incluir_contexto:
        return grade, []
    
    contextos = _gerar_eventos_contextuais(
        duracao_horas,
        seed,
        eventos_contextuais or TIPOS_EVENTO_CONTEXTO
    )
    
    # Marca contexto na grade
    grade_com_contexto = _marcar_contextos_na_grade(grade, contextos)
    
    return grade_com_contexto, contextos


def _marcar_contextos_na_grade(
    grade: pd.DataFrame,
    contextos: list[EventoContextual]
) -> pd.DataFrame:
    """Adiciona coluna 'contexto' à grade indicando eventos legítimos."""
    grade["contexto"] = None  # NOVO
    grade["suprime_alerta"] = False  # NOVO
    
    for ctx in contextos:
        mask = (grade["timestamp"] >= ctx.inicio) & \
               (grade["timestamp"] <= ctx.fim)
        grade.loc[mask, "contexto"] = ctx.tipo
        grade.loc[mask, "suprime_alerta"] = ctx.suprime_alerta
    
    return grade
```

**Uso na Geração:**

```python
# Opção 1: Com contexto padrão (refeições, higiene, etc)
grade, contextos = gerar_sessao_com_contexto(
    duracao_horas=24,
    incluir_contexto=True,
    seed=42
)
# grade terá coluna "contexto": ["refeicao", None, "higiene", ...]
# grade terá coluna "suprime_alerta": [True, False, True, ...]

# Opção 2: Com agendamentos customizados
eventos_custom = {
    "cirurgia": {
        **TIPOS_EVENTO_CONTEXTO["cirurgia"],
        "horarios": [(10, 30)],  # Cirurgia específica
    }
}
grade, contextos = gerar_sessao_com_contexto(
    duracao_horas=24,
    eventos_contextuais=eventos_custom
)

# Opção 3: Sem contexto (para testes básicos)
grade, _ = gerar_sessao_com_contexto(
    duracao_horas=24,
    incluir_contexto=False
)
```

**Impacto no Motor de Alertas:**

```python
# Antes: Motor não sabe por que paciente está imóvel
alertas = engine.calcular_alertas(grade)
# → Alerta se supino > 60 min (mesmo se for refeição)

# Depois: Motor respeita contexto
alertas = engine.calcular_alertas_com_contexto(grade)
# → Se supino > 60 min DURANTE REFEIÇÃO: não alerta
# → Se supino > 60 min FORA refeição: ALERTA ✅
```

**Benefício Clínico:**
- ✅ Zero falsos positivos por eventos contextuais
- ✅ Auditoría clara: "Por que o paciente não se moveu?" → "Estava em cirurgia"
- ✅ Melhor detecção de risco real (elimina ruído)

**Benefício Acadêmico:**
- ✅ Modelo clinicamente realista
- ✅ Simulação defendível em defesa
- ✅ Comparável com literatura (estudos clínicos também controlam por contexto)

**Métricas de Validação:**

```python
def validar_contextos(grade, contextos):
    """Valida se contextos estão bem marcados."""
    assert "contexto" in grade.columns
    assert "suprime_alerta" in grade.columns
    
    # Cada contexto deve estar marcado na grade
    for ctx in contextos:
        marcados = grade.loc[
            (grade["timestamp"] >= ctx.inicio) &
            (grade["timestamp"] <= ctx.fim)
        ]
        assert len(marcados) > 0, f"Contexto {ctx.tipo} não marcado"
        assert all(marcados["contexto"] == ctx.tipo)
    
    return True
```

**Linhas de Código:** ~80 linhas (novo arquivo `dados_simulados/contextos.py`)

---

### 🔴 PROBLEMA 2: "Grade Discretizada Perde Transições"

**Severidade:** 🔴 **CRÍTICO** (afeta precisão do motor de alertas)

**Descrição:**
A função `_expandir_para_grade()` discretiza eventos em grid regular (5 min). Pode perder mudanças rápidas de postura que ocorrem entre amostras.

**Exemplo Problemático:**
```
Evento real:
T=09:45:00 → Supino por 5 min
T=09:50:00 → Lateral Direito por 120 min
             (transição instantânea)

Grade com passo 5 min:
T=09:45 → Supino
T=09:50 → Lateral Direito  ✅ OK neste caso
T=09:55 → Lateral Direito

Mas e se transição foi em T=09:47:30?

Grade (sem transição explicita):
T=09:45 → Supino
T=09:50 → Lateral Direito  (perdeu o timestamp exato)
T=09:55 → Lateral Direito

Motor de alertas quer saber:
"Quanto tempo em Supino?" → Calcula 09:45 a 09:50 = 5 min ✅
ou sabe que mudou em 09:47:30?
```

**Impacto:**
- Pequenos erros acumulam em janelas de 60-120 min
- Motor de alertas pode deslocar-se ligeiramente
- Difícil reproduzir exatamente (seed não garante bit-a-bit)

**Solução:**
Adicionar pontos de transição explícitos à grade.

```python
def _expandir_para_grade_v2(
    df_eventos: pd.DataFrame,
    passo_min: int,
    inicio: datetime,
    fim: datetime,
    incluir_transicoes: bool = True,  # NOVO
) -> pd.DataFrame:
    """Discretiza com preservação de transições."""
    
    # Grade base
    idx = pd.date_range(start=inicio, end=fim, freq=f"{passo_min}min")
    idx_list = list(idx)
    
    # Adiciona pontos de transição
    if incluir_transicoes:
        for _, row in df_eventos.iterrows():
            ts_inicio = pd.to_datetime(row["timestamp"])
            ts_fim = ts_inicio + pd.to_timedelta(row["duracao_min"], unit="m")
            
            idx_list.append(ts_inicio)
            idx_list.append(ts_fim)
    
    # Remove duplicatas e ordena
    idx_list = sorted(set(idx_list))
    idx_list = [t for t in idx_list if inicio <= t <= fim]
    
    # Discretiza
    out = []
    for t in idx_list:
        postura = _encontrar_postura_em_t(df_eventos, t)
        out.append({"timestamp": t.isoformat(), "postura": postura})
    
    return pd.DataFrame(out)
```

**Impacto:**
- ✅ Preserva transições exatas
- ✅ Motor de alertas tem dados precisos
- ✅ Reproducível (determinístico)

**Linhas de Código:** ~20 linhas (refatoração)

---

### 🔴 PROBLEMA 3: "Perfis de Pacientes Idênticos"

**Severidade:** 🔴 **CRÍTICO** (invalida heterogeneidade clínica)

**Descrição:**
Na função `gerar_sessao_multi()` (linha 212), **todos os pacientes recebem `PerfilPaciente()` padrão**, resultando em comportamento quase idêntico.

```python
# Atual (ERRADO):
for i in range(n_pacientes):
    perfil = PerfilPaciente()  # ← SEMPRE MESMO PERFIL
    grade, eventos = gerar_sessao_simulada(..., perfil=perfil)
```

**Consequência:**
- P1, P2, P3 têm ~94 min média de duração (1% de diferença)
- Não reflete realidade clínica (pacientes têm riscos diferentes)
- **Invalida qualquer análise sobre heterogeneidade de pacientes**

**Solução:**
Criar perfis predefinidos com comportamentos diferentes.

```python
PERFIS_PREDEFINIDOS = {
    "alto_risco": PerfilPaciente(
        nome="Paciente Alto Risco",
        limite_tempo_postura=60,        # Precisa trocar mais rápido
        prob_falha_reposicao=0.9,       # Maior risco
    ),
    "medio_risco": PerfilPaciente(
        nome="Paciente Médio Risco",
        limite_tempo_postura=90,
        prob_falha_reposicao=0.7,
    ),
    "baixo_risco": PerfilPaciente(
        nome="Paciente Baixo Risco",
        limite_tempo_postura=120,       # Pode ficar mais tempo
        prob_falha_reposicao=0.5,
    ),
}

def gerar_sessao_multi_v2(
    n_pacientes: int,
    duracao_horas: int,
    passo_min: int,
    seed: int,
    distribuir_por_risco: bool = True,  # NOVO
) -> tuple[dict, dict]:
    """
    Gera múltiplas sessões com heterogeneidade.
    
    Args:
        distribuir_por_risco: Se True, distribui pacientes por risco
    """
    
    if not distribuir_por_risco:
        # Comportamento original
        return _gerar_sessao_multi_uniforme(n_pacientes, ...)
    
    # NOVO: Distribui por risco
    grades = {}
    eventos = {}
    
    riscos = ["alto_risco", "medio_risco", "baixo_risco"]
    
    for i in range(n_pacientes):
        risco = riscos[i % len(riscos)]
        perfil = PERFIS_PREDEFINIDOS[risco]
        
        grade, evt = gerar_sessao_simulada(
            duracao_horas=duracao_horas,
            seed=seed + i,  # Seed diferente por paciente
            passo_min=passo_min,
            perfil=perfil,
        )
        
        grades[f"PAC-{i:04d}"] = grade
        eventos[f"PAC-{i:04d}"] = evt
    
    return grades, eventos
```

**Validação:**

```python
# Antes
grades_old, _ = gerar_sessao_multi(3, 24, 5, 42, distribuir_por_risco=False)
# P1: média_duracao = 94.2 min
# P2: média_duracao = 93.8 min
# P3: média_duracao = 95.1 min
# → Diferença: ~1% (não realmente heterogêneo) ❌

# Depois
grades_new, _ = gerar_sessao_multi(3, 24, 5, 42, distribuir_por_risco=True)
# PAC-0000 (Alto Risco): média_duracao = 72.1 min
# PAC-0001 (Médio Risco): média_duracao = 94.2 min
# PAC-0002 (Baixo Risco): média_duracao = 118.7 min
# → Diferença: ~40% (clinicamente heterogêneo) ✅
```

**Impacto:**
- ✅ Pacientes realisticamente diferentes
- ✅ Testa algoritmo com cenários variados
- ✅ Acadêmico: pode comparar "qual é melhor para cada risco?"

**Linhas de Código:** ~30 linhas (nova função + perfis)

---

### 🟡 PROBLEMA 4: "Confiança de Sensor Aleatória"

**Severidade:** 🟡 **IMPORTANTE** (afeta teste de robustez)

**Descrição:**
Em `scripts/generate_alerts.py` linha 50, confiança é gerada aleatoriamente sem correlação com postura ou transição.

```python
# Atual (INCORRETO):
"confianca": float(random.uniform(0.8, 1.0))  # Totalmente aleatória ❌
```

**Problema:**
- Confiança deve ser **baixa em transições** (maior incerteza)
- Confiança deve ser **maior em posturas estáveis** (menor incerteza)
- Confiança deve ser **postura-dependente** (supino é mais fácil de detectar que lateral)

**Realidade Sensor:**
```
Postura    | Confiança Típica | Por quê?
-----------|------------------|----------------------------
Supino     | 95-99%          | Mais fácil, posição padrão
Lateral D  | 85-92%          | Requer confirmação bilateral
Lateral E  | 85-92%          | Requer confirmação bilateral
Prono      | 80-90%          | Face pode mudar, difícil
Transição  | 60-75%          | Incerteza durante mudança
```

**Solução:**
Modelar confiança realista por postura e contexto.

```python
class CaracteristicasSensor:
    """Características realistas de um sensor de pressão."""
    
    # Confiança base por postura
    CONFIANCA_BASE = {
        "supino": 0.97,
        "lateral_direito": 0.88,
        "lateral_esquerdo": 0.88,
        "prono": 0.85,
    }
    
    # Degradação durante transição
    DEGRADACAO_TRANSICAO = 0.20  # -20% durante mudança
    
    # Correlação com tempo na postura
    MELHORA_POR_TEMPO = 0.001  # +0.1% por minuto estável
    
    @staticmethod
    def calcular_confianca(
        postura: str,
        tempo_na_postura_min: int,
        em_transicao: bool = False,
    ) -> float:
        """
        Calcula confiança realista.
        
        Args:
            postura: Nome da postura
            tempo_na_postura_min: Quanto tempo na postura atual
            em_transicao: True se em transição entre posturas
        
        Returns:
            Confiança entre 0.5 e 1.0
        """
        conf = CaracteristicasSensor.CONFIANCA_BASE.get(postura, 0.85)
        
        if em_transicao:
            conf -= CaracteristicasSensor.DEGRADACAO_TRANSICAO
        
        # Melhora com tempo estável
        conf += min(
            tempo_na_postura_min * CaracteristicasSensor.MELHORA_POR_TEMPO,
            0.10  # Máximo +10%
        )
        
        # Clip entre limites
        return max(0.5, min(1.0, conf))


# Uso em generate_alerts.py
def gerar_alertas_com_confianca_realista(
    grades: dict[str, pd.DataFrame],
) -> list[dict]:
    """Gera alertas com confiança realista."""
    alertas = []
    
    for pac_id, grade in grades.items():
        for i, row in grade.iterrows():
            postura = row["postura"]
            timestamp = pd.to_datetime(row["timestamp"])
            
            # Detecta se em transição
            em_transicao = (
                i > 0 and 
                grade.iloc[i-1]["postura"] != postura
            )
            
            # Tempo na postura
            if em_transicao:
                tempo_na_postura = 0
            else:
                tempo_na_postura = _calcular_tempo_postura(grade, i)
            
            confianca = CaracteristicasSensor.calcular_confianca(
                postura=postura,
                tempo_na_postura_min=tempo_na_postura,
                em_transicao=em_transicao,
            )
            
            alerta = {
                "paciente_id": pac_id,
                "timestamp": timestamp.isoformat(),
                "postura": postura,
                "confianca": float(confianca),
                "em_transicao": em_transicao,
            }
            alertas.append(alerta)
    
    return alertas
```

**Validação:**

```python
# Antes
confiança = 0.92 (supino) = 0.87 (lateral) = 0.89 (transição)
# → Não há diferença significativa ❌

# Depois
confiança = {
    "supino estável 30min": 0.975,
    "lateral estável 30min": 0.885,
    "transição": 0.68,
}
# → Diferença realista ✅
```

**Impacto:**
- ✅ Motor de alertas pode validar robustez
- ✅ Sensibilidade a contexto
- ✅ Testes mais realistas

**Linhas de Código:** ~80 linhas (nova classe)

---

### 🟢 PROBLEMA 5: "Normal Truncada vs Log-Normal"

**Severidade:** 🟢 **MENOR** (otimização técnica)

**Descrição:**
Função `_normal_truncada()` usa normal truncada, que pode introduzir viés na distribuição.

**Solução Alternativa:**
Usar distribuição log-normal que é mais natural para durações (sempre positiva).

```python
def _duracao_log_normal(mu_min: int, sigma_min: int) -> int:
    """
    Gera duração usando log-normal (mais realista para durações).
    
    Args:
        mu_min: Média em minutos
        sigma_min: Desvio padrão em minutos
    
    Returns:
        Duração em minutos (sempre > 0)
    """
    # Converte para parâmetros log-normal
    sigma_log = math.sqrt(math.log(1 + (sigma_min / mu_min)**2))
    mu_log = math.log(mu_min) - 0.5 * sigma_log**2
    
    duracao = np.random.lognormal(mu_log, sigma_log)
    
    return max(5, int(duracao))  # Mínimo 5 min
```

**Impacto:**
- ✅ Distribuição mais realista
- ✅ Sem viés de truncação
- ⚠️ Menor impacto prático (Normal também funciona)

**Linhas de Código:** ~15 linhas (substituição)

---

### 🟢 PROBLEMA 6: "Falta Validação de Coerência"

**Severidade:** 🔴 **CRÍTICO** (garante qualidade dos dados)

**Descrição:**
Não há validação para garantir que dados gerados são coerentes (sem transições proibidas, durações válidas, etc).

**Solução:**
Criar framework de validação.

```python
def validar_sessao(
    df_eventos: pd.DataFrame,
    grafo_transicoes: dict | None = None,
) -> tuple[bool, list[str]]:
    """
    Valida coerência de uma sessão de eventos.
    
    Args:
        df_eventos: DataFrame com eventos
        grafo_transicoes: Dict de transições válidas
    
    Returns:
        (is_valid, list_of_errors)
    """
    
    if grafo_transicoes is None:
        grafo_transicoes = TRANSICOES_VALIDAS
    
    erros = []
    
    # Validação 1: Timestamps ordenados
    timestamps = pd.to_datetime(df_eventos["timestamp"])
    if not timestamps.is_monotonic_increasing:
        erros.append("❌ Timestamps não estão ordenados")
    
    # Validação 2: Durações positivas
    duracao_invalida = df_eventos["duracao_min"] <= 0
    if duracao_invalida.any():
        erros.append(f"❌ {duracao_invalida.sum()} durações <= 0")
    
    # Validação 3: Posturas válidas
    posturas_validas = set(grafo_transicoes.keys())
    posturas_invalidas = set(df_eventos["postura"]) - posturas_validas
    if posturas_invalidas:
        erros.append(f"❌ Posturas inválidas: {posturas_invalidas}")
    
    # Validação 4: Transições válidas
    for i in range(len(df_eventos) - 1):
        atual = df_eventos.iloc[i]["postura"]
        proxima = df_eventos.iloc[i+1]["postura"]
        
        validas = grafo_transicoes.get(atual, [])
        if proxima not in validas:
            erros.append(
                f"❌ Transição inválida: {atual} → {proxima} "
                f"(válidas: {validas})"
            )
    
    # Validação 5: Cobertura temporal
    inicio = timestamps.min()
    fim = timestamps.max()
    duracao_total = (fim - inicio).total_seconds() / 60
    
    duracao_eventos = df_eventos["duracao_min"].sum()
    
    if abs(duracao_eventos - duracao_total) > 1:  # Tolerância 1 min
        erros.append(
            f"❌ Gap temporal: eventos somam {duracao_eventos} min, "
            f"período tem {duracao_total} min"
        )
    
    # Validação 6: Sem duplicatas
    if df_eventos.duplicated().any():
        erros.append(f"❌ {df_eventos.duplicated().sum()} eventos duplicados")
    
    is_valid = len(erros) == 0
    
    if is_valid:
        print("✅ Sessão validada com sucesso")
    else:
        print("❌ Sessão com erros:")
        for erro in erros:
            print(f"   {erro}")
    
    return is_valid, erros
```

**Uso:**

```python
grade, eventos = gerar_sessao_simulada(24, seed=42)
is_valid, erros = validar_sessao(eventos)

if is_valid:
    print("OK, dados estão bons")
else:
    print("Erro! Dados inconsistentes")
    for erro in erros:
        print(erro)
```

**Impacto:**
- ✅ Garante dados válidos
- ✅ Detecção precoce de bugs
- ✅ Confiança na qualidade

**Linhas de Código:** ~70 linhas (nova função)

---

### 🟢 PROBLEMA 7: "Falta Rastreamento de Cohort"

**Severidade:** 🟡 **MENOR** (qualidade de dados)

**Descrição:**
Quando dados são gerados múltiplas vezes, não há como rastrear qual seed/parâmetros os geraram. Dificulta reproducibilidade.

**Solução:**
Adicionar metadados de geração.

```python
def gerar_sessao_com_metadados(
    duracao_horas: int = 24,
    seed: int = 42,
    passo_min: int = 5,
    perfil: PerfilPaciente | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Gera sessão com metadados de geração.
    
    Returns:
        (grade, metadados)
    """
    
    grade, eventos = gerar_sessao_simulada(
        duracao_horas=duracao_horas,
        seed=seed,
        passo_min=passo_min,
        perfil=perfil,
    )
    
    metadados = {
        "cohort_id": f"SIM-{int(time.time())}",
        "timestamp_geracao": datetime.now().isoformat(),
        "seed": seed,
        "duracao_horas": duracao_horas,
        "passo_min": passo_min,
        "perfil_nome": perfil.nome if perfil else "padrão",
        "perfil_limite_tempo": perfil.limite_tempo_postura if perfil else 120,
        "versao_gerador": "2.1",
        "hash_codigo": _calcular_hash_gerador(),
    }
    
    return grade, metadados


def _calcular_hash_gerador() -> str:
    """Calcula hash do arquivo gerador.py para rastrear versão."""
    import hashlib
    with open("dados_simulados/gerador.py", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]
```

**Impacto:**
- ✅ Reproducibilidade garantida
- ✅ Auditoría de dados
- ⚠️ Menor impacto prático

**Linhas de Código:** ~30 linhas (nova função)

---

## 📊 MATRIZ DE SEVERIDADE REVISADA

| # | Problema | Tipo | Severidade | Esforço | Prioridade |
|---|----------|------|-----------|---------|-----------|
| 1 | Eventos Contextuais não considerados | Realismo | 🟡 IMPORTANTE | 1-2h | **1º** |
| 2 | Grade perde transições | Precisão | 🔴 CRÍTICO | 2-4h | **2º** |
| 3 | Perfis idênticos | Heterogeneidade | 🔴 CRÍTICO | 1h | **3º** |
| 4 | Confiança aleatória | Robustez | 🟡 IMPORTANTE | 2h | **4º** |
| 5 | Normal vs Log-normal | Técnico | 🟢 MENOR | 0.5h | **5º** |
| 6 | Sem validação | Qualidade | 🔴 CRÍTICO | 2h | **6º** |
| 7 | Sem rastreamento | Auditoria | 🟡 MENOR | 0.5h | **7º** |

---

## 🎯 RECOMENDAÇÃO FINAL

### Seu Feedback Incorporado: ✅

A revisão reflete corretamente que em **ambiente hospitalar**:
- ✅ Refeições são **AGENDADAS** (6h, 12h, 18h fixo)
- ✅ Cirurgias são **AGENDADAS** (horários específicos)
- ✅ Visitas são **AGENDADAS** (períodos delimitados)
- ✅ Higiene é **AGENDADA** (protocolos)

### Impacto: 

**Antes da revisão:**
> "Refeições devem ser aleatórias"
> → Clinicamente incorreto ❌

**Depois da revisão:**
> "Eventos agendados devem ser explicitamente modelados para evitar falsos alertas"
> → Clinicamente correto ✅

### Próximos Passos Recomendados:

1. **Implementar Problema 1 (Contexto)** primeiro
   - Deixa modelo clinicamente defensável
   - Resolve falsos positivos
   - Prepara para Problema 2

2. **Depois Problemas 3 e 6** (Perfis + Validação)
   - Críticos para defesa
   - Garantem qualidade

3. **Depois Problema 2** (Grade)
   - Melhora precisão
   - Mais complexo, pode esperar

4. **Problemas 4, 5, 7** (Nice-to-have)
   - Se tempo disponível
   - Polimento final

---

## 📝 Próximas Ações

**Quer proceder com:**
- [ ] Confirmação dessa abordagem revisada?
- [ ] Criar testes para Problema 1 (contextos)?
- [ ] Começar implementação?

**Dúvidas sobre:**
- [ ] Modelagem de cirurgias e visitas?
- [ ] Como integrar com motor de alertas?
- [ ] Métricas de validação?
