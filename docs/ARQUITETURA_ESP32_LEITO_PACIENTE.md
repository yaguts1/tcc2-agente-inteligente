# 🏥 Arquitetura ESP32 ↔ Leito ↔ Paciente

## Visão Geral

Este documento descreve o modelo correto do sistema, onde **cada leito possui um ESP32 fixo** e não há necessidade de "device assignment" dinâmico.

## Modelo de Dados

```
┌─────────────────────────────────────────────────────────────┐
│                   ARQUITETURA FÍSICA                         │
└─────────────────────────────────────────────────────────────┘

Hospital
  ├── Quarto 101
  │     ├── Leito A  ← ESP32_101A (FIXO)
  │     └── Leito B  ← ESP32_101B (FIXO)
  │
  ├── Quarto 102
  │     ├── Leito A  ← ESP32_102A (FIXO)
  │     └── Leito B  ← ESP32_102B (FIXO)
  │
  └── Quarto 201
        └── Leito A  ← ESP32_201A (FIXO)
```

## Fluxo de Dados

### 1. ESP32 Envia Dados

O ESP32 está **fisicamente instalado no leito** e sempre envia o mesmo `cama_id`:

```json
{
  "cama_id": "101-A",
  "ts": 1730000000,
  "ts_ms": 1730000000000,
  "postura": "decubito_dorsal",
  "confianca": 95,
  "amostra_ms": 5000,
  "ts_utc": "2024-10-29T12:00:00Z"
}
```

### 2. Sistema Busca Paciente no Leito

```python
# interface/web.py ou interface/api.py
paciente = obter_ficha_por_cama(DB_PATH, cama_id="101-A")
```

**Endpoint**: `GET /api/pacientes/cama/{cama_id}`

### 3. Processamento

**Cenário A: Leito Ocupado**
```python
if paciente:
    # Processa automaticamente
    inserir_timeline_event(paciente_id, postura, ts, ...)
    check_alerts(paciente_id, postura, ...)
```

**Cenário B: Leito Vazio**
```python
else:
    # Evento órfão (esperado!)
    inserir_device_event(device_id, ts, payload)
    # Fica aguardando reconciliação manual
```

## Casos de Uso

### Caso 1: Paciente Internado

```
1. Paciente João chega ao hospital
2. Enfermeira cadastra no sistema:
   - Nome: João Silva
   - Quarto: 101
   - Leito: A
   - Perfil: Alto risco
   
3. ESP32_101A já está lá! Começa a processar automaticamente
```

### Caso 2: Paciente Muda de Leito

```
1. Paciente João precisa mudar de 101-A para 102-B
2. Enfermeira edita cadastro:
   - Quarto: 101 → 102
   - Leito: A → B
   
3. Sistema automaticamente:
   - Para de processar eventos do ESP32_101A para João
   - Começa a processar eventos do ESP32_102B para João
```

**IMPORTANTE**: Quando o paciente muda de leito, ele muda de ESP32 também!

### Caso 3: Paciente Recebe Alta

```
1. Paciente João recebe alta
2. Enfermeira deleta ou marca como inativo
3. ESP32_101A continua enviando dados
4. Eventos viram órfãos (normal!)
5. Quando novo paciente ocupar 101-A, processamento retoma
```

### Caso 4: Eventos Órfãos (Reconciliação)

```
Timeline:
──────────────────────────────────────────────────────────────
10:00  │ Leito 101-A vazio
       │ ESP32_101A envia evento → órfão (device_events)
       │
10:30  │ ESP32_101A envia evento → órfão (device_events)
       │
11:00  │ Paciente Maria internada no 101-A
       │ (cadastro criado no sistema)
       │
11:15  │ Admin detecta 2 eventos órfãos do ESP32_101A
       │ Enfermeira reconhece: "Ah, era a Maria antes de cadastrar!"
       │ Clica em "Reconciliar"
       │
       │ Sistema processa RETROATIVAMENTE:
       │ ├─▶ Cria timeline_events para Maria
       │ ├─▶ Cria alertas se necessário
       │ └─▶ Marca device_events como processed=1
       │
11:30  │ ESP32_101A envia novo evento
       │ → Processado automaticamente (Maria está cadastrada)
```

## Estrutura do Banco de Dados

### Tabela `pacientes` (ou `paciente_fichas`)

```sql
CREATE TABLE paciente_fichas (
    paciente_id TEXT PRIMARY KEY,
    nome TEXT,
    perfil TEXT,
    cama_id TEXT,  -- Ex: "101-A"
    ...
);
```

**Campo chave**: `cama_id` identifica univocamente o leito (e portanto o ESP32)

### Tabela `device_events`

```sql
CREATE TABLE device_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    ts TEXT,
    ts_ms INTEGER,
    payload TEXT,
    processed INTEGER DEFAULT 0,
    paciente_id TEXT
);
```

**Eventos órfãos**: `processed = 0` e `paciente_id IS NULL`

### Tabela `devices`

```sql
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    created_at TEXT
);
```

Apenas registra quais ESP32s existem no hospital.

## API Endpoints Relevantes

### 1. Buscar Paciente por Leito

```http
GET /api/pacientes/cama/{cama_id}
```

**Exemplo**: `GET /api/pacientes/cama/101-A`

**Resposta**:
```json
{
  "id": "PAC_123",
  "name": "João Silva",
  "cama_id": "101-A",
  "room": "101",
  "bed": "A",
  "riskLevel": "high",
  "repositioningInterval": 2
}
```

### 2. Listar Eventos Órfãos

```http
GET /api/device_events?limit=100
```

Filtra eventos com `processed = 0`

### 3. Reconciliar Evento Órfão

```http
POST /api/device_events/{event_id}/reconcile
```

Sistema:
1. Busca o evento em `device_events`
2. Extrai `cama_id` do payload
3. Busca paciente atual naquele leito
4. Processa retroativamente (cria timeline_event, alertas)
5. Marca `processed = 1`

## Validações Backend

### No WebSocket (`interface/web.py`)

```python
async def handle_esp32_event(payload):
    cama_id = payload.get("cama_id")
    
    # 1. Busca paciente neste leito
    paciente = obter_ficha_por_cama(DB_PATH, cama_id)
    
    if paciente:
        # 2. Processa automaticamente
        paciente_id = paciente["paciente_id"]
        inserir_timeline_event(...)
        check_alerts(...)
    else:
        # 3. Evento órfão (sem paciente no leito)
        device_id = f"ESP32_{cama_id.replace('-', '_')}"
        inserir_device_event(device_id, ts, payload)
```

## Comparação com Device Assignment (Removido)

| Aspecto | Device Assignment ❌ | Modelo Atual ✅ |
|---------|---------------------|-----------------|
| ESP32 | Móvel (precisa associar) | Fixo no leito |
| Complexidade | Alta (tabelas extras, endpoints) | Baixa (usa cama_id) |
| Mudança de Leito | Encerrar/criar assignment | Editar paciente |
| Eventos Órfãos | Reconcilia via assignment | Reconcilia via cama_id |
| Rastreabilidade | Via device_assignments | Via cama_id no payload |

## Boas Práticas

### ✅ DO

- **Cadastre pacientes com `room` e `bed` precisos**
- **Use cama_id no formato `{room}-{bed}`** (ex: "101-A", "202-B")
- **Reconcilie eventos órfãos** quando paciente for cadastrado retroativamente
- **Edite o cadastro do paciente** se ele mudar de leito

### ❌ DON'T

- **NÃO crie "device assignments"** - ESP32 é fixo!
- **NÃO tente "mover" ESP32s** - eles estão fisicamente instalados
- **NÃO ignore eventos órfãos** - podem ser dados válidos de pacientes não cadastrados ainda

## Fluxo de Trabalho Diário

### 1. Internação

```
Enfermeira → Sistema → Pacientes → Novo Paciente
  ├─ Nome: Maria Santos
  ├─ Quarto: 101
  ├─ Leito: A
  ├─ Perfil de Risco: Alto
  └─ Intervalo de Reposicionamento: 2h

ESP32_101A → Dados já processados automaticamente ✅
```

### 2. Mudança de Leito

```
Enfermeira → Sistema → Pacientes → Editar Maria
  ├─ Quarto: 101 → 102
  └─ Leito: A → B

ESP32_101A → Para de associar a Maria ✅
ESP32_102B → Começa a processar para Maria ✅
```

### 3. Alta

```
Enfermeira → Sistema → Pacientes → Deletar Maria

ESP32_102B → Eventos viram órfãos (esperado!) ✅
```

### 4. Monitoramento de Órfãos

```
Administrador → Admin → Ver Eventos Órfãos

Se reconhecer padrão suspeito:
  - Verificar se paciente foi cadastrado
  - Reconciliar manualmente
  - Investigar problema de hardware (se necessário)
```

## Diagramas

### Fluxo de Processamento

```
┌────────────┐
│   ESP32    │ Envia cama_id="101-A"
└─────┬──────┘
      │
      ▼
┌────────────────────────────┐
│ Sistema busca paciente     │
│ em cama_id="101-A"         │
└────────┬───────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌──────────┐
│ Ocupado│  │  Vazio   │
└───┬────┘  └────┬─────┘
    │            │
    ▼            ▼
┌────────────┐  ┌──────────────┐
│ Processa   │  │ Evento Órfão │
│ Timeline   │  │ device_events│
│ + Alertas  │  │ processed=0  │
└────────────┘  └──────────────┘
```

### Relacionamento de Tabelas

```
┌──────────────────┐
│ paciente_fichas  │
├──────────────────┤
│ paciente_id (PK) │
│ nome             │
│ cama_id ◄────────┼─── "101-A"
│ perfil           │
└──────────────────┘
         │
         │ 1:N
         ▼
┌──────────────────┐
│ timeline_events  │
├──────────────────┤
│ paciente_id (FK) │
│ postura          │
│ ts               │
└──────────────────┘

┌──────────────────┐
│ device_events    │ (Órfãos)
├──────────────────┤
│ device_id        │ ◄─── "ESP32_101A"
│ payload          │ ◄─── {"cama_id": "101-A", ...}
│ processed        │ ◄─── 0 (aguardando)
└──────────────────┘
```

---

**Resumo**: ESP32 é **fixo no leito**. Sistema usa `cama_id` para associar dados ao paciente. Mudança de leito = mudança de ESP32. Simples e eficiente! ✅

**Data**: 2024-10-29  
**Versão**: 1.0.0
