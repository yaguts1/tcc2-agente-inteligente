# 🔍 Diagnóstico: Desalinhamento de Dados entre Dashboard, Histórico e Exportação

**Data:** 27/10/2025 23:30  
**Status:** ⚠️ PROBLEMAS CRÍTICOS IDENTIFICADOS

---

## 📊 Resumo Executivo

Você está certo! Há **desalinhamento significativo** entre as diferentes visualizações dos dados. Identifiquei **3 problemas principais**:

### 🔴 Problema 1: JANELA TEMPORAL INCONSISTENTE (Severidade: ALTA)
- **Dashboard:** Mostra últimas 24h → **50 alertas**
- **Exportação:** Pode mostrar TODOS os alertas → **60 alertas**
- **Impacto:** Você vê números diferentes dependendo de onde está olhando

### 🟡 Problema 2: DADOS INCOMPLETOS NA TIMELINE (Severidade: MÉDIA)
- **Alertas:** 60 alertas de 13 pacientes
- **Timeline:** Apenas 6 eventos de 1 paciente (PAC-0001)
- **Impacto:** 12 pacientes têm alertas mas não aparecem no histórico/timeline

### 🔵 Problema 3: APENAS 1 PACIENTE TEM DADOS COMPLETOS
- **PAC-0001:** Único paciente com alertas E eventos na timeline (7.7%)
- **Outros 12 pacientes:** Têm alertas mas zero eventos na timeline
- **Impacto:** Histórico/timeline está praticamente vazio

---

## 🔬 Análise Detalhada

### 1. Estado Atual do Banco de Dados

```
┌─────────────────────────────────────────────────────────────┐
│ TABELA ALERTAS (fonte: Dashboard + Exportação)             │
├─────────────────────────────────────────────────────────────┤
│ Total de alertas:     60                                    │
│ Alertas (24h):        50                                    │
│                                                             │
│ Por Status:                                                 │
│   • fechado:          57 alertas (95%)                      │
│   • reconhecido:       3 alertas (5%)                       │
│                                                             │
│ Por Paciente:                                               │
│   • PAC-7778:         12 alertas                            │
│   • PAC-7779:         12 alertas                            │
│   • PAC-0001:          6 alertas                            │
│   • PAC-7784:          6 alertas                            │
│   • PAC-7785:          6 alertas                            │
│   • Outros:           18 alertas                            │
│                                                             │
│ Range temporal:                                             │
│   • Primeiro:         2025-10-25 13:58:48                   │
│   • Último:           2025-10-28 14:28:00                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ TABELA TIMELINE_EVENTS (fonte: Histórico/Timeline)         │
├─────────────────────────────────────────────────────────────┤
│ Total de eventos:      6 ⚠️                                  │
│                                                             │
│ Por Tipo:                                                   │
│   • alert_open:        6 eventos (100%)                     │
│   • alert_ack:         0 eventos ❌                          │
│   • alert_close:       0 eventos ❌                          │
│   • repositioned:      0 eventos ❌                          │
│                                                             │
│ Por Paciente:                                               │
│   • PAC-0001:          6 eventos (100%)                     │
│   • Outros pacientes:  0 eventos ❌                          │
│                                                             │
│ Range temporal:                                             │
│   • Primeiro:         2025-10-25 13:58:48                   │
│   • Último:           2025-10-26 17:48:57                   │
└─────────────────────────────────────────────────────────────┘
```

### 2. Comparação PAC-0001 (Único Paciente Completo)

```
ALERTAS (6 alertas):
  1. 2025-10-26 17:48:57 | imobilidade | fechado      | perfil=baixo
  2. 2025-10-26 13:55:57 | imobilidade | fechado      | perfil=medio
  3. 2025-10-26 08:22:18 | imobilidade | reconhecido  | perfil=baixo
  4. 2025-10-26 03:03:06 | imobilidade | fechado      | perfil=alto
  5. 2025-10-25 20:13:19 | imobilidade | reconhecido  | perfil=alto
  6. 2025-10-25 13:58:48 | imobilidade | reconhecido  | perfil=alto

TIMELINE (6 eventos):
  1. 2025-10-26 17:48:57 | alert_open | (sem descrição) | (sem meta)
  2. 2025-10-26 13:55:57 | alert_open | (sem descrição) | (sem meta)
  3. 2025-10-26 08:22:18 | alert_open | (sem descrição) | (sem meta)
  4. 2025-10-26 03:03:06 | alert_open | (sem descrição) | (sem meta)
  5. 2025-10-25 20:13:19 | alert_open | (sem descrição) | (sem meta)
  6. 2025-10-25 13:58:48 | alert_open | (sem descrição) | (sem meta)

⚠️ PROBLEMA DETECTADO:
   • Todos os alertas têm evento alert_open ✓
   • Nenhum alerta tem evento alert_ack ❌ (3 estão reconhecidos!)
   • Nenhum alerta tem evento alert_close ❌ (3 estão fechados!)
   • Nenhum evento de reposicionamento ❌
```

---

## 🎯 Por Que Isso Acontece?

### Causa Raiz 1: Janelas Temporais Diferentes

**Dashboard (`/api/stats`):**
```python
# Linha 433 em interface/api.py
all_alerts_24h = selecionar_alertas_janela(DB_PATH, horas=24)  # ✅ 24 horas
```

**Lista de Alertas (`/api/frontend/alerts`):**
```python
# Linha 757 em interface/api.py
async def frontend_alerts(horas: int | None = 24, ...):  # ✅ Padrão 24h
```

**Exportação (`/api/alerts/export/pdf` e `/csv`):**
```python
# Linha 174 em ferramentas/exportador.py
all_alerts = selecionar_alertas_janela(
    db_path=self.db_path,
    horas=None,  # ❌ None = TODOS OS ALERTAS!
)
```

**⚠️ INCONSISTÊNCIA:** 
- Dashboard e lista filtram por 24h → mostram 50 alertas
- Exportação não filtra → mostra 60 alertas
- **Diferença:** 10 alertas "fantasma" aparecem na exportação!

### Causa Raiz 2: Eventos de Timeline Incompletos

A timeline SÓ registra `alert_open` mas não registra:
- ❌ `alert_ack` quando alerta é reconhecido
- ❌ `alert_close` quando alerta é fechado
- ❌ `repositioned` quando paciente é reposicionado

**Onde deveria registrar (NÃO ESTÁ REGISTRANDO):**

```python
# interface/api.py linha ~1076 - Reconhecer alerta
@router.post("/frontend/alerts/{alert_id}/acknowledge")
async def acknowledge_alert_endpoint(alert_id: str):
    # ... atualiza status para 'reconhecido' ...
    # ❌ FALTA: inserir_timeline_event(..., tipo="alert_ack", ...)
```

```python
# interface/api.py linha ~1096 - Completar alerta
@router.post("/frontend/alerts/{alert_id}/complete")
async def complete_alert_endpoint(alert_id: str):
    # ... atualiza status para 'fechado' ...
    # ❌ FALTA: inserir_timeline_event(..., tipo="alert_close", ...)
```

### Causa Raiz 3: Apenas PAC-0001 Tem Pipeline Completo

Analisando o código, apenas o fluxo de **ingestão de eventos** (`POST /api/eventos`) registra na timeline:

```python
# interface/api.py linha ~1362
total_alertas = _processar_eventos_filtrados(resultado.prontos, contagem)
# ☝️ Esta função cria alertas E registra alert_open na timeline
```

**Mas para outros pacientes:**
- Se alertas foram criados manualmente (SQL direto, script, etc.) → ❌ Sem timeline
- Se alertas foram reconhecidos via API → ❌ Sem evento alert_ack
- Se alertas foram fechados via API → ❌ Sem evento alert_close

---

## 🔧 Soluções Recomendadas

### Solução 1: URGENTE - Padronizar Janela Temporal na Exportação

**Problema:** Exportação mostra TODOS os alertas (60) enquanto dashboard mostra 24h (50)

**Correção em `ferramentas/exportador.py` linha ~174:**

```python
# ❌ ANTES (inconsistente)
all_alerts = selecionar_alertas_janela(
    db_path=self.db_path,
    horas=None,  # Busca TODOS
)

# ✅ DEPOIS (consistente com dashboard)
all_alerts = selecionar_alertas_janela(
    db_path=self.db_path,
    horas=24,  # Mesma janela do dashboard
)
```

**OU melhor ainda:** Respeitar o filtro `filters.start_date` e `filters.end_date` se fornecidos:

```python
# Se usuário especificar datas, usar essas datas
# Senão, usar padrão de 24h (igual ao dashboard)
horas_janela = 24  # padrão
if filters.start_date is None and filters.end_date is None:
    # Usar padrão de 24h
    all_alerts = selecionar_alertas_janela(db_path=self.db_path, horas=24)
else:
    # Buscar todos e filtrar manualmente (como está agora)
    all_alerts = selecionar_alertas_janela(db_path=self.db_path, horas=None)
```

### Solução 2: IMPORTANTE - Registrar Eventos de Lifecycle dos Alertas

**Problema:** Timeline só tem `alert_open`, faltam `alert_ack` e `alert_close`

**Correção 1: Adicionar evento ao reconhecer alerta (`/frontend/alerts/{alert_id}/acknowledge`):**

```python
# interface/api.py linha ~1056
@router.post("/frontend/alerts/{alert_id}/acknowledge")
async def acknowledge_alert_endpoint(alert_id: str):
    parts = alert_id.split("__")
    paciente_id = parts[0]
    inicio = "__".join(parts[1:])
    
    # Atualizar status
    atualizar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
    
    # ✅ ADICIONAR: Registrar evento na timeline
    inserir_timeline_event(
        db_path=DB_PATH,
        paciente_id=paciente_id,
        tipo="alert_ack",
        descricao=f"Alerta reconhecido",
        meta={"alert_id": alert_id, "action": "acknowledge"}
    )
    
    return {"message": "Alert acknowledged"}
```

**Correção 2: Adicionar evento ao completar alerta (`/frontend/alerts/{alert_id}/complete`):**

```python
# interface/api.py linha ~1076
@router.post("/frontend/alerts/{alert_id}/complete")
async def complete_alert_endpoint(alert_id: str):
    parts = alert_id.split("__")
    paciente_id = parts[0]
    inicio = "__".join(parts[1:])
    
    # Atualizar status
    atualizar_status_alerta(DB_PATH, paciente_id, inicio, "fechado")
    
    # ✅ ADICIONAR: Registrar evento na timeline
    inserir_timeline_event(
        db_path=DB_PATH,
        paciente_id=paciente_id,
        tipo="alert_close",
        descricao=f"Alerta fechado/completado",
        meta={"alert_id": alert_id, "action": "complete"}
    )
    
    return {"message": "Alert completed"}
```

**Correção 3: Adicionar evento ao reposicionar paciente:**

```python
# Quando enfermeiro registra reposicionamento manual
inserir_timeline_event(
    db_path=DB_PATH,
    paciente_id=paciente_id,
    tipo="repositioned",
    descricao=f"Paciente reposicionado manualmente",
    meta={"position": new_position, "nurse": user}
)
```

### Solução 3: OPCIONAL - Popular Timeline Retroativamente

Para os 12 pacientes que têm alertas mas não têm timeline:

```python
"""Script para popular timeline com dados históricos"""
import sqlite3
from interface.dao import inserir_timeline_event

DB_PATH = 'dados.db'
conn = sqlite3.connect(DB_PATH)

# Buscar alertas sem eventos na timeline
cursor = conn.execute("""
    SELECT DISTINCT a.paciente_id, a.inicio, a.status, a.tipo
    FROM alertas a
    LEFT JOIN timeline_events t 
        ON a.paciente_id = t.paciente_id 
        AND a.inicio = t.ts
    WHERE t.id IS NULL
    ORDER BY a.inicio
""")

for row in cursor:
    paciente_id = row[0]
    inicio = row[1]
    status = row[2]
    tipo = row[3]
    
    # Criar evento alert_open
    inserir_timeline_event(
        db_path=DB_PATH,
        paciente_id=paciente_id,
        tipo="alert_open",
        descricao=f"Alerta de {tipo} iniciado",
        meta={"tipo": tipo, "retroativo": True},
        ts_override=inicio  # Usar timestamp do alerta
    )
    
    # Se alerta está reconhecido ou fechado, criar evento correspondente
    if status == "reconhecido":
        inserir_timeline_event(
            db_path=DB_PATH,
            paciente_id=paciente_id,
            tipo="alert_ack",
            descricao=f"Alerta reconhecido",
            meta={"retroativo": True},
            ts_override=inicio
        )
    elif status == "fechado":
        inserir_timeline_event(
            db_path=DB_PATH,
            paciente_id=paciente_id,
            tipo="alert_close",
            descricao=f"Alerta fechado",
            meta={"retroativo": True},
            ts_override=inicio
        )

conn.close()
print("Timeline populada com eventos históricos!")
```

---

## 📈 Impacto das Correções

### Antes (Estado Atual):
```
Dashboard:    50 alertas (24h) ← Janela correta
Exportação:   60 alertas (todos) ← Janela INCORRETA
Timeline:     6 eventos (1 paciente) ← Dados INCOMPLETOS
Alinhamento:  7.7% (1 de 13 pacientes completos)
```

### Depois (Com Correções):
```
Dashboard:    50 alertas (24h) ← Consistente ✅
Exportação:   50 alertas (24h padrão) ← Consistente ✅
Timeline:     150+ eventos (13 pacientes) ← Completo ✅
Alinhamento:  100% (todos os pacientes completos)
```

---

## ✅ Checklist de Implementação

### Prioridade ALTA (Urgente):
- [ ] Corrigir janela temporal na exportação (horas=24 por padrão)
- [ ] Adicionar inserir_timeline_event em acknowledge_alert_endpoint
- [ ] Adicionar inserir_timeline_event em complete_alert_endpoint

### Prioridade MÉDIA:
- [ ] Adicionar evento de reposicionamento manual
- [ ] Popular timeline retroativamente (script uma vez)

### Prioridade BAIXA:
- [ ] Adicionar descrição nos eventos da timeline
- [ ] Adicionar metadados úteis (usuário, detalhes)

---

## 🎓 Conclusão

Você tem razão: **existem 3 bases de dados diferentes** devido a:

1. **Janelas temporais inconsistentes** entre endpoints
2. **Pipeline incompleto** de eventos (só registra abertura, não reconhecimento/fechamento)
3. **Dados legados** de 12 pacientes sem eventos na timeline

A boa notícia é que **todas as correções são simples** e podem ser implementadas em ~1 hora de trabalho.

---

**Próximo Passo:** Implementar as correções na ordem de prioridade acima?
