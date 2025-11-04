# 📋 Análise: Confronto entre Texto e Implementação Real

## Sumário Executivo

Esta análise compara o texto descritivo do projeto com a implementação real no código. Identificamos **discrepâncias significativas** em múltiplas áreas: geração de dados, comunicação, estrutura de eventos e mecanismos de simulação.

---

## 🔴 Discrepâncias Críticas

### 1. **Comunicação WebSocket vs HTTP**

**Texto afirma:**
> "publicando continuamente eventos ao servidor via HTTP (POST), **além de suportar envio contínuo por WebSocket**"

**Realidade no código:**

```python
# dados_simulados/gerador.py - NÃO HÁ implementação de WebSocket
# Busca por "WebSocket" retorna 0 resultados no módulo de simulação
```

```cpp
// firmware/esp32_replay/esp32_replay.ino
// Implementa APENAS HTTP POST
bool enviarEvento(const EventoReplay &evento) {
  String url = montarUrlEventos(); 
  g_http.begin(g_client, url); 
  g_http.addHeader("Content-Type","application/json");
  int status = g_http.POST(evento.payload); // ← APENAS HTTP POST
  // ...
}
```

**Existe:** `esp32_replay_websocket.ino` (arquivo separado para WebSocket)

**Conclusão:** ✅ WebSocket existe, mas é **implementação alternativa**, não "além de HTTP". São dois modos distintos, não simultâneos.

**Correção sugerida:**
> "publicando continuamente eventos ao servidor via HTTP (POST). **Uma implementação alternativa** suporta envio contínuo por WebSocket para cenários de latência reduzida."

---

### 2. **Esquema JSON do Evento**

**Texto lista campos:**
- `paciente_id` ✅
- `cama_id` ✅
- `postura` ✅
- `confianca` ✅
- `pressao_pico` ✅
- `amostra_ms` ✅
- `ts_utc` ✅

**Código implementado:**

```python
# interface/api.py - EventPayload (modelo Pydantic)
class EventPayload(BaseModel):
    device_id: str          # ← NÃO MENCIONADO NO TEXTO!
    paciente_id: str | None
    cama_id: str | None
    postura: str
    confianca: float
    amostra_ms: int
    ts_utc: datetime
    pressao_pico: float | None
```

**Discrepância:** O texto **omite o campo `device_id`**, que é **obrigatório** (`Field(..., min_length=1)`).

**Impacto:** O `device_id` é essencial para:
1. Rastreamento de qual ESP32 enviou o evento
2. Reconciliação de eventos órfãos (sem `paciente_id`)
3. Auditoria e debugging

**Correção sugerida:**
> "Cada evento é encapsulado em JSON com o seguinte esquema: **device_id (identificador único do ESP32),** paciente_id, cama_id, postura, confianca, pressao_pico, amostra_ms e ts_utc."

---

### 3. **Geração de Dados no Simulador Python**

**Texto afirma:**
> "O simulador foi implementado em Python 3.11"
> "publicando continuamente eventos ao servidor via HTTP (POST)"

**Realidade:**

```python
# dados_simulados/gerador.py
def gerar_sessao_simulada(
    duracao_horas: int = 24,
    seed: int = 42,
    passo_min: int = 5,
    # ...
) -> tuple[pd.DataFrame, list[EventoContextual]]:
    """Gera série temporal de posturas (grade regular) com contextos."""
    # ...
    return df_grade, contextos  # ← Retorna DataFrame, NÃO envia HTTP!
```

**Busca por "requests", "http.client", "POST" no módulo `dados_simulados/`:**
- ❌ 0 resultados

**Conclusão:** O simulador Python **NÃO envia eventos via HTTP**. Ele apenas **gera DataFrames** que são:
1. Salvos no banco de dados via `inserir_grade()`
2. Processados localmente via `processar_alertas()`

**Quem envia eventos via HTTP:** O firmware ESP32 (`esp32_replay.ino`), que lê arquivos `.jsonl` do SPIFFS.

**Correção sugerida:**
> "O simulador foi implementado em Python 3.11 para gerar séries temporais sintéticas de posturas. **Os dados gerados são persistidos diretamente no banco de dados para testes e validação.** Para emular dispositivos reais, utiliza-se firmware ESP32 que **lê eventos pré-gerados de arquivos JSONL e os transmite via HTTP POST**, reproduzindo a cadência de um dispositivo conectado por Wi-Fi."

---

### 4. **Perfis de Risco: Implementação vs Descrição**

**Texto descreve 3 mecanismos:**
1. ✅ Perfis de risco (baixo, médio, alto)
2. ✅ Variação de períodos de imobilidade
3. ❌ **Inserção de ruído controlado**

**Implementação dos perfis:**

```python
# dados_simulados/gerador.py
PERFIS_PREDEFINIDOS = {
    "baixo": {
        "limite_tempo_postura": 150,      # min
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
        "prob_falha_reposicao": 0.85,      # ← Maior probabilidade de falha
        "duracao_refeicao": 25,
    },
}
```

**Campos do perfil:**
- `limite_tempo_postura` (min): Tempo máximo recomendado antes de reposicionamento
- `prob_falha_reposicao`: Probabilidade de **não** ser reposicionado quando deveria
- `duracao_refeicao` (min): Tempo em supino durante refeições

**Discrepância 1:** O texto sugere que "pacientes de alto risco permanecem mais tempo em supino", mas a implementação usa **probabilidade de falha de reposicionamento**, não **distribuições de postura diferentes**.

**Discrepância 2:** Não há parâmetros como:
- `prob_decubito_dorsal` (mencionado em código antigo, mas removido)
- `prob_decubito_lateral`
- `prob_sentado_deitado`

**Implementação real de variação temporal:**

```python
# dados_simulados/gerador.py - TEMPOS_POSTURA (média, desvio)
TEMPOS_POSTURA = {
    "supino": (90, 30),              # μ=90min, σ=30min
    "lateral_direito": (120, 40),
    "lateral_esquerdo": (120, 40),
    "prono": (45, 20),
}

def _normal_truncada(media: float, desvio: float, minimo: float = 1.0) -> float:
    """Sorteia valor ~N(media, desvio) com piso 'minimo'."""
    val = np.random.normal(media, desvio)
    return float(max(minimo, val))
```

**Conclusão:** A variação temporal é implementada via **distribuição normal truncada** com parâmetros fixos por postura, **NÃO modulada por perfil de risco**.

---

### 5. **Ruído Controlado: NÃO IMPLEMENTADO**

**Texto afirma:**
> "o ruído (eventos com confianca abaixo do limiar configurado) é introduzido para testar os filtros de qualidade"

**Busca no código:**

```bash
# dados_simulados/ - Busca por "confianca" ou "ruido"
❌ 0 resultados
```

```python
# O campo "confianca" existe no modelo EventPayload, mas:
# 1. NÃO é gerado pelo simulador Python
# 2. NÃO há lógica de inserção de ruído
```

**Onde `confianca` é usado:**

```python
# interface/api.py - filtrar_evento()
def filtrar_evento(evento: dict) -> dict:
    """Aplica filtro de qualidade."""
    conf = evento.get("confianca", 1.0)
    if conf < LIMIAR_CONFIANCA:  # LIMIAR_CONFIANCA = 0.7
        metricas.registrar_descartado()
        return {"aceito": False, "razao": "confianca_baixa"}
    # ...
```

**Conclusão:** O filtro de confiança **existe no backend**, mas o simulador **não gera eventos com ruído**. Logo, **não há teste automatizado** dessa funcionalidade.

**Correção sugerida:**
> "O sistema implementa filtros de qualidade que descartam eventos com `confianca` abaixo de 0.7. **Para validação em cenários reais, o firmware ESP32 pode gerar eventos com variação de confiança**, permitindo teste da robustez do pipeline de ingestão."

---

### 6. **Posturas: Nomenclatura Inconsistente**

**Texto menciona:**
> "postura (categórica: supino, lateral direito, lateral esquerdo ou prono)"

**Implementação:**

```python
# dados_simulados/gerador.py
POSTURAS = ["supino", "lateral_direito", "lateral_esquerdo", "prono"]
#                      ^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^
#                      UNDERSCORES, não espaços!
```

**Validação no backend:**

```python
# interface/api.py - EventPayload
postura: str = Field(..., min_length=1, max_length=64)
# Aceita qualquer string, não valida enum
```

**Impacto:** Inconsistência pode causar problemas em:
1. Dashboards (se esperam "lateral direito" com espaço)
2. Queries no banco de dados
3. Documentação vs código

**Correção sugerida:** Usar enum consistente:
```python
class Postura(str, Enum):
    SUPINO = "supino"
    LATERAL_DIREITO = "lateral_direito"
    LATERAL_ESQUERDO = "lateral_esquerdo"
    PRONO = "prono"
```

---

## 🟡 Discrepâncias Menores

### 7. **Distribuições Probabilísticas**

**Texto afirma:**
> "intervalos de duração distintos, controlados por distribuições probabilísticas"

**Implementação:** ✅ Correto - usa `np.random.normal()` truncada

**Porém:** Não há menção explícita de que são **distribuições normais**, o que seria tecnicamente mais preciso.

---

### 8. **Horários de Refeição**

**Texto não menciona**, mas código implementa:

```python
@dataclass
class PerfilPaciente:
    horarios_refeicao: list[datetime] | None = None
    duracao_refeicao: int = 30  # min
    
    def horarios_refeicao_padrao(self, inicio: datetime) -> list[datetime]:
        base = inicio.replace(hour=6, minute=0, second=0, microsecond=0)
        return [base + timedelta(hours=h) for h in (6, 12, 18)]  
        # 12h, 18h e 24h (café, almoço, jantar)
```

**Impacto:** Refeições forçam postura `supino` por 25-30min, criando **padrões determinísticos** que podem influenciar alertas.

---

## 🟢 Aspectos Corretos

1. ✅ **Python 3.11** - Confirmado
2. ✅ **pandas e NumPy** - Usados extensivamente
3. ✅ **JSON como formato** - Confirmado (`application/json`)
4. ✅ **ISO 8601 timestamps** - Confirmado (`ts_utc: datetime`)
5. ✅ **Perfis de risco** - Implementados (com diferenças nos parâmetros)
6. ✅ **Variação temporal** - Implementada (distribuições normais)
7. ✅ **Transições entre posturas** - Implementadas (`TRANSICOES_VALIDAS`)

---

## 📊 Tabela Resumo de Discrepâncias

| # | Aspecto | Texto Afirma | Código Implementa | Severidade |
|---|---------|--------------|-------------------|------------|
| 1 | WebSocket | "além de suporte HTTP" | Implementações separadas (HTTP OU WebSocket) | 🟡 Média |
| 2 | Campo `device_id` | Não mencionado | **Obrigatório** no schema | 🔴 Alta |
| 3 | Envio HTTP pelo simulador Python | Simulator envia HTTP POST | Simulator **apenas gera DataFrames** | 🔴 Alta |
| 4 | Perfis modulam posturas | Perfis mudam distribuições de postura | Perfis mudam **probabilidade de falha** | 🟡 Média |
| 5 | Inserção de ruído | Ruído controlado inserido | **NÃO implementado** no simulador | 🔴 Alta |
| 6 | Nomenclatura posturas | "lateral direito" (com espaço) | `"lateral_direito"` (underscore) | 🟡 Baixa |
| 7 | Tipo de distribuição | "distribuições probabilísticas" | Especificamente **normal truncada** | 🟢 Baixa |
| 8 | Refeições | Não mencionadas | Implementadas com padrão determinístico | 🟡 Média |

---

## 🎯 Recomendações

### Correções Essenciais

1. **Remover afirmação de WebSocket simultâneo:**
   - Esclarecer que são implementações **alternativas**
   - Mencionar arquivo `esp32_replay_websocket.ino` separado

2. **Incluir `device_id` na descrição do schema:**
   - Fundamental para rastreamento e reconciliação
   - Atualmente omitido no texto

3. **Corrigir descrição do simulador Python:**
   - NÃO envia HTTP (apenas gera dados)
   - ESP32 firmware é quem envia HTTP POST
   - Separar claramente: geração sintética vs emulação de hardware

4. **Esclarecer mecanismo de perfis:**
   - Perfis controlam **probabilidade de falha de reposicionamento**
   - NÃO controlam distribuições de postura diretamente
   - Durações são fixas por postura (distribuição normal)

5. **Remover ou qualificar menção a "ruído controlado":**
   - Sistema suporta filtro de confiança
   - Simulador NÃO gera ruído automaticamente
   - Adicionar nota: "funcionalidade planejada" ou remover

### Melhorias Opcionais

6. **Especificar tipo de distribuição:**
   - Trocar "distribuições probabilísticas" por "distribuição normal truncada"

7. **Padronizar nomenclatura:**
   - Usar enum para posturas
   - Documentar convenção de underscore vs espaço

8. **Mencionar refeições:**
   - Explicar padrão determinístico (3x/dia)
   - Impacto em análise de alertas

---

## 📝 Texto Corrigido Sugerido

**Versão revisada do parágrafo:**

> O simulador foi implementado em Python 3.11 para manter consistência tecnológica com os demais componentes do sistema e facilitar manutenção, testes e integração. A escolha viabiliza o uso nativo de bibliotecas de manipulação de dados (pandas e NumPy) e simplifica a geração controlada de séries temporais sintéticas. **Os dados gerados são persistidos diretamente no banco de dados SQLite para validação funcional do motor de alertas.** Para emular cenários realistas de conectividade, implementou-se **firmware ESP32** que reproduz dispositivos IoT em ambiente hospitalar: eventos pré-gerados (armazenados em arquivos JSONL no sistema de arquivos SPIFFS) são transmitidos ao servidor via **HTTP POST** (implementação principal) ou **WebSocket** (implementação alternativa para latência reduzida), respeitando a cadência temporal original e simulando condições de rede Wi-Fi.
>
> Cada evento é encapsulado em JSON (padrão amplo em aplicações web), com o seguinte esquema: **device_id** (identificador único do ESP32), paciente_id (referência ao indivíduo monitorado), cama_id (vínculo do paciente ao leito), postura (categórica: supino, lateral_direito, lateral_esquerdo ou prono), confianca (probabilidade atribuída à classificação, entre 0.0 e 1.0), pressao_pico (opcional, valor máximo detectado em mmHg), amostra_ms (duração da coleta em milissegundos) e ts_utc (timestamp em ISO 8601, UTC). Esse conjunto de atributos atende simultaneamente a requisitos técnicos (validação de entrada, ordenação cronológica, deduplicação via device_id+ts_utc, auditoria e reconciliação de eventos órfãos) e clínicos, ao preservar informações relevantes para análise posterior, como a confiança da classificação e indicadores de pressão de pico.
>
> O comportamento do gerador de dados sintéticos é governado por três mecanismos centrais: (i) perfis de risco, (ii) variação de períodos de imobilidade via distribuições normais truncadas e (iii) **padrões contextuais hospitalares** (refeições, procedimentos). Os perfis de risco clínico (baixo, médio, alto) modulam **a probabilidade de falha de reposicionamento**: pacientes de alto risco (prob_falha = 0.85) tendem a permanecer imobilizados mesmo após ultrapassar o limite recomendado (90 minutos), enquanto pacientes de baixo risco (prob_falha = 0.4, limite = 150min) são reposicionados mais frequentemente. A variação temporal é implementada por **distribuições normais truncadas** específicas por postura: supino (μ=90min, σ=30min), laterais (μ=120min, σ=40min) e prono (μ=45min, σ=20min), gerando intervalos heterogêneos que vão de minutos até horas. **Padrões contextuais, como refeições (3x/dia, 25-30min em supino), introduzem comportamento determinístico que aproxima a simulação de cenários reais.** O sistema também implementa **filtros de qualidade** que descartam eventos com confiança abaixo de 0.7, validando a robustez do pipeline de ingestão. Em conjunto, esses mecanismos permitem validação do fluxo completo (ingestão → filtro → decisão → alerta), além de ajustes de parâmetros (limiares, histerese, cooldown) com base em evidências geradas sinteticamente.

---

## ✅ Checklist de Validação

- [ ] Revisar texto com base nas discrepâncias identificadas
- [ ] Adicionar `device_id` ao esquema JSON descrito
- [ ] Esclarecer simulador Python vs firmware ESP32
- [ ] Corrigir mecanismo de perfis (probabilidade de falha)
- [ ] Remover ou qualificar "ruído controlado"
- [ ] Padronizar nomenclatura de posturas
- [ ] Mencionar tipo de distribuição (normal truncada)
- [ ] Incluir refeições na descrição de mecanismos
- [ ] Separar HTTP POST (principal) de WebSocket (alternativo)

---

**Data da análise:** 04/11/2025  
**Versão do código analisada:** Commit atual da branch `feat/websocket-esp32`  
**Arquivos analisados:**
- `dados_simulados/gerador.py`
- `interface/api.py`
- `firmware/esp32_replay/esp32_replay.ino`
- `firmware/esp32_replay/esp32_replay_websocket.ino`
