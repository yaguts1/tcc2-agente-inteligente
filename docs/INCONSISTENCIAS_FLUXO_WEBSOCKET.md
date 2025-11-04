# ⚠️ INCONSISTÊNCIAS CRÍTICAS NO FLUXO ESP32 → BACKEND → FRONTEND

**Data**: 28 de outubro de 2025  
**Severidade**: 🔴 **CRÍTICA**  
**Impacto**: Sistema não gera alertas em tempo real via WebSocket

---

## 📋 Sumário Executivo

O fluxo de informação do ESP32 até o frontend está **QUEBRADO** em 3 pontos críticos:

1. ❌ **WebSocket `/ws/eventos` NÃO processa alertas**
2. ❌ **Sem integração entre `/ws/eventos` e `/ws/alerts`**
3. ❌ **`ProcessadorIncremental` não é usado no WebSocket**

**Resultado**: Eventos do ESP32 são salvos no DB, mas alertas **NUNCA são gerados em tempo real**.

---

## 🔍 Análise Detalhada

### Fluxo Esperado (Como DEVERIA Funcionar)

```
┌─────────────┐
│   ESP32     │  1. Envia evento via WebSocket
│  (Sensor)   │     {"ts_utc": "...", "postura": 1, "device_id": "DEV-001"}
└─────────────┘
       │
       ▼ WS /ws/eventos
┌─────────────────────────────────────┐
│   Backend (FastAPI)                 │
│   interface/api.py:websocket_eventos│
│                                     │
│   2. Filtra evento (quality/filtro) │ ✅ IMPLEMENTADO
│   3. Salva no DB (inserir_eventos)  │ ✅ IMPLEMENTADO
│   4. Processa alertas               │ ❌ NÃO IMPLEMENTADO
│   5. Broadcast via WebSocket        │ ❌ NÃO IMPLEMENTADO
└─────────────────────────────────────┘
       │
       ▼ (4) Processar alertas (FALTANDO!)
┌─────────────────────────────────────┐
│  ProcessadorIncremental             │
│  ou modulo_alerta.engine            │
│                                     │
│  • Detecta imobilidade              │
│  • Gera alerta se > janela_minutos  │
│  • Salva alerta no DB               │
└─────────────────────────────────────┘
       │
       ▼ (5) Broadcast (FALTANDO!)
┌─────────────────────────────────────┐
│  ws_manager_optimized.broadcast()   │
│                                     │
│  Envia para todos clientes em       │
│  /ws/alerts                          │
└─────────────────────────────────────┘
       │
       ▼ WS /ws/alerts
┌─────────────────────────────────────┐
│   Frontend React                    │
│   hooks/useWebSocket.ts             │
│                                     │
│   • Recebe notificação              │
│   • Atualiza UI em tempo real       │
│   • Toast de alerta                 │
└─────────────────────────────────────┘
```

---

### Fluxo Atual (Como REALMENTE Funciona)

```
┌─────────────┐
│   ESP32     │  1. Envia evento via WebSocket
└─────────────┘
       │
       ▼ WS /ws/eventos
┌─────────────────────────────────────┐
│   Backend                           │
│   2. Filtra evento          ✅      │
│   3. Salva no DB            ✅      │
│   4. Envia ACK para ESP32   ✅      │
│                                     │
│   ⚠️ PARA AQUI!                     │
│   Alertas NÃO são processados       │
└─────────────────────────────────────┘
       │
       │ (Frontend precisa fazer POLLING)
       ▼
┌─────────────────────────────────────┐
│   Frontend React                    │
│   • useQuery com refetchInterval    │
│   • GET /api/alerts/recent?hours=24 │
│   • Polling a cada 30 segundos      │
│                                     │
│   ❌ WebSocket /ws/alerts NUNCA     │
│      recebe dados!                  │
└─────────────────────────────────────┘
```

**Consequência**: Frontend depende de **POLLING** mesmo com WebSocket conectado!

---

## 🐛 Inconsistências Detalhadas

### Inconsistência #1: WebSocket `/ws/eventos` Não Processa Alertas

**Arquivo**: `interface/api.py`  
**Função**: `websocket_eventos()` (linha 2028)  
**Linhas**: 2090-2130

**Código Atual**:
```python
while True:
    data = await websocket.receive_text()
    try:
        evento_json = json.loads(data)
        seq = evento_json.get("seq", 0)
        
        # Normalizar evento
        if "device_id" not in evento_json:
            evento_json["device_id"] = device_id
        if "paciente_id" not in evento_json and paciente_id:
            evento_json["paciente_id"] = paciente_id
        
        # Processar evento através do filtro
        resultado = filtrar_evento(evento_json)
        
        if not resultado.descartado and resultado.prontos:
            # Inserir no banco de dados
            try:
                inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])
                metricas.registrar_recebido()
                eventos_processados += 1
            except Exception as e:
                logger.warning("ws_insert_erro", device_id=device_id, seq=seq, error=str(e))
        
        # ❌ FALTANDO: Processar alertas!
        # ❌ FALTANDO: Broadcast via WebSocket!
        
        # Enviar ACK
        await websocket.send_json({
            "status": "ok",
            "seq": seq,
            "processados": eventos_processados,
            "descartado": resultado.descartado
        })
```

**O que deveria ter**:
```python
if not resultado.descartado and resultado.prontos:
    # Inserir no banco de dados
    inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])
    metricas.registrar_recebido()
    eventos_processados += 1
    
    # ✅ ADICIONAR: Processar alertas
    alertas = PROCESSADOR.processar_lote(resultado.prontos)
    
    if alertas:
        # ✅ ADICIONAR: Salvar alertas
        inserir_alertas(DB_PATH, evento_json["paciente_id"], alertas)
        
        # ✅ ADICIONAR: Broadcast para clientes
        for alerta in alertas:
            asyncio.create_task(ws_manager_optimized.broadcast({
                "type": "alert_new",
                "alert_id": alerta.get("inicio"),
                "patient_id": alerta.get("paciente_id"),
                "timestamp": alerta.get("inicio"),
                "status": "pending",
                "data": alerta
            }))
```

---

### Inconsistência #2: Nenhuma Ponte Entre `/ws/eventos` e `/ws/alerts`

**Situação**:
- ESP32 → `/ws/eventos` (recebe eventos)
- Frontend → `/ws/alerts` (espera alertas)

**Problema**: Não há comunicação entre os dois!

**Endpoint `/ws/alerts`** (linha 2318):
```python
@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Connects a client to the alert broadcast stream."""
    
    await ws_manager_optimized.connect(websocket, filters=None)
    
    try:
        while True:
            # ⚠️ Apenas mantém conexão viva, NUNCA envia dados!
            await asyncio.sleep(10)
    
    except WebSocketDisconnect:
        await ws_manager_optimized.disconnect(websocket)
```

**Problema**: Este endpoint **NUNCA envia dados** ativamente!

**Como deveria funcionar**:
- `ws_manager_optimized.broadcast()` deveria ser chamado por `/ws/eventos`
- Mensagens seriam propagadas para todos clientes conectados em `/ws/alerts`

**Onde `broadcast()` É Usado Atualmente**:

✅ **POST `/api/frontend/alerts/{id}/acknowledge`** (linha 1138):
```python
await ws_manager_optimized.broadcast({
    "type": "alert_update",
    "alert_id": alerta_id,
    "status": "acknowledged",
    # ...
})
```

✅ **POST `/api/frontend/alerts/{id}/complete`** (linha 1188):
```python
await ws_manager_optimized.broadcast({
    "type": "alert_update",
    "alert_id": alerta_id,
    "status": "completed",
    # ...
})
```

❌ **NUNCA usado quando novos alertas são gerados** (via `/ws/eventos`)

---

### Inconsistência #3: `ProcessadorIncremental` Existe mas Não É Usado

**Instância Global** (linha 661):
```python
PROCESSADOR = ProcessadorIncremental(
    db_path=DB_PATH,
    estrategia=os.getenv("UPP_ESTADO_ESTRATEGIA", "estado_em_memoria"),
    redis_url=os.getenv("REDIS_URL"),
)
```

**Onde É Usado**:
- ✅ POST `/api/eventos` (REST API)
- ✅ POST `/api/grade` (batch upload)
- ✅ Simulação de pacientes

**Onde NÃO É Usado** (mas deveria):
- ❌ `/ws/eventos` ← **ESP32 em tempo real**

**Comparação**:

**POST `/api/eventos` (CORRETO)** (linha ~850):
```python
# 1. Filtrar
resultado = filtrar_evento(evento)

# 2. Processar alertas com PROCESSADOR
alertas = PROCESSADOR.processar_lote(resultado.prontos)

# 3. Salvar eventos
inserir_eventos(DB_PATH, paciente_id, resultado.prontos)

# 4. Salvar alertas
if alertas:
    inserir_alertas(DB_PATH, paciente_id, alertas)
    
    # 5. Broadcast
    asyncio.create_task(ws_manager_optimized.broadcast({
        "type": "alert_new",
        # ...
    }))
```

**WS `/ws/eventos` (INCOMPLETO)**:
```python
# 1. Filtrar ✅
resultado = filtrar_evento(evento_json)

# 2. Salvar eventos ✅
inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])

# 3. ❌ FALTANDO: Processar alertas
# 4. ❌ FALTANDO: Salvar alertas
# 5. ❌ FALTANDO: Broadcast
```

---

## 🎯 Impacto no Sistema

### Funcionalidades Quebradas

1. ❌ **Alertas em Tempo Real**: Não funcionam via WebSocket
2. ❌ **Notificações Push**: Frontend nunca recebe broadcasts
3. ❌ **Dashboard Dinâmico**: Precisa fazer polling (ineficiente)
4. ❌ **ESP32 Real**: Eventos salvos mas alertas não gerados

### O Que Ainda Funciona

1. ✅ **REST API**: Alertas gerados via POST `/api/eventos`
2. ✅ **Batch Upload**: Processamento via `/api/grade`
3. ✅ **Simulação**: Geração de alertas na simulação
4. ✅ **Frontend Polling**: GET `/api/alerts/recent` funciona

### Workaround Atual

**Frontend** (`DashboardPage.tsx` linha 179-182):
```typescript
// Polling as fallback (disabled if WebSocket is working, but kept for resilience)
const { data: alerts } = useQuery({
  queryKey: ['alerts', 'recent'],
  enabled: !wsConnected, // Only enable polling if WebSocket not connected
  refetchInterval: POLL_INTERVAL, // 30 seconds
});
```

**Problema**: Frontend **SEMPRE usa polling** porque `wsConnected` nunca recebe dados reais!

---

## ✅ Solução Proposta

### Passo 1: Corrigir `/ws/eventos`

**Arquivo**: `interface/api.py`  
**Função**: `websocket_eventos()`  
**Linha**: ~2105

**Código Corrigido**:
```python
if not resultado.descartado and resultado.prontos:
    # 1. Inserir eventos no banco
    try:
        inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])
        metricas.registrar_recebido()
        eventos_processados += 1
    except Exception as e:
        logger.warning("ws_insert_erro", device_id=device_id, seq=seq, error=str(e))
    
    # 2. ✅ NOVO: Processar alertas incrementalmente
    try:
        alertas = PROCESSADOR.processar_lote(resultado.prontos)
        
        if alertas:
            # 3. ✅ NOVO: Salvar alertas no banco
            inserir_alertas(DB_PATH, evento_json["paciente_id"], alertas)
            
            # 4. ✅ NOVO: Broadcast para clientes conectados em /ws/alerts
            for alerta in alertas:
                asyncio.create_task(ws_manager_optimized.broadcast({
                    "type": "alert_new",
                    "alert_id": alerta.get("inicio"),
                    "patient_id": alerta.get("paciente_id"),
                    "timestamp": alerta.get("inicio"),
                    "status": "pending",
                    "severity": _calcular_severidade(alerta),
                    "data": alerta
                }))
                
            logger.info(
                "ws_alertas_gerados",
                device_id=device_id,
                seq=seq,
                quantidade=len(alertas)
            )
    
    except Exception as e:
        logger.error("ws_processar_alertas_erro", device_id=device_id, error=str(e))
```

**Helper Function**:
```python
def _calcular_severidade(alerta: dict) -> str:
    """Calcula severidade baseado no perfil do paciente."""
    perfil = alerta.get("perfil", "medio").lower()
    if perfil == "alto":
        return "critical"
    elif perfil == "medio":
        return "high"
    else:
        return "medium"
```

---

### Passo 2: Testar Fluxo Completo

**Teste End-to-End**:

1. **ESP32 envia evento**:
   ```json
   {
     "seq": 1,
     "device_id": "DEV-001",
     "paciente_id": "PAC-0001",
     "ts_utc": "2025-10-28T10:00:00Z",
     "postura": 1,
     "confianca": 0.95
   }
   ```

2. **Backend processa**:
   - ✅ Filtra evento
   - ✅ Salva no DB (`eventos`)
   - ✅ **NOVO**: Processa alertas
   - ✅ **NOVO**: Salva no DB (`alertas`)
   - ✅ **NOVO**: Broadcast via WebSocket

3. **Frontend recebe**:
   ```json
   {
     "type": "alert_new",
     "alert_id": "2025-10-28T10:00:00",
     "patient_id": "PAC-0001",
     "timestamp": "2025-10-28T10:00:00",
     "status": "pending",
     "severity": "high",
     "data": { ... }
   }
   ```

4. **UI atualiza**:
   - Toast: "Novo alerta para PAC-0001"
   - Dashboard atualiza contador
   - Timeline adiciona evento

---

### Passo 3: Remover Polling do Frontend (Opcional)

Após correção, o polling pode ser **completamente desabilitado**:

**Frontend** (`DashboardPage.tsx`):
```typescript
// ❌ REMOVER: Polling não é mais necessário
// const { data: alerts } = useQuery({
//   queryKey: ['alerts', 'recent'],
//   enabled: !wsConnected,
//   refetchInterval: POLL_INTERVAL,
// });

// ✅ USAR: Apenas WebSocket
const { isConnected: wsConnected } = useWebSocket({
  url: '/api/ws/alerts',
  onMessage: handleWebSocketMessage,
});
```

**Benefícios**:
- Reduz carga no servidor (sem polling a cada 30s)
- Latência menor (notificações instantâneas)
- Menos consumo de banda

---

## 📊 Comparação: Antes vs Depois

### Antes (Situação Atual)

| Componente | Status | Observação |
|-----------|--------|------------|
| ESP32 → `/ws/eventos` | ✅ Funcionando | Envia eventos |
| Filtro de qualidade | ✅ Funcionando | Valida eventos |
| Salvar eventos (DB) | ✅ Funcionando | Persistência OK |
| **Processar alertas** | ❌ **QUEBRADO** | Não é executado |
| **Salvar alertas (DB)** | ❌ **QUEBRADO** | Não acontece |
| **Broadcast `/ws/alerts`** | ❌ **QUEBRADO** | Nunca envia dados |
| Frontend polling | ⚠️ Workaround | Compensa a falha |

**Fluxo de Dados**: ESP32 → DB → ~~(nada)~~ → Frontend faz polling

---

### Depois (Proposta de Correção)

| Componente | Status | Observação |
|-----------|--------|------------|
| ESP32 → `/ws/eventos` | ✅ Funcionando | Envia eventos |
| Filtro de qualidade | ✅ Funcionando | Valida eventos |
| Salvar eventos (DB) | ✅ Funcionando | Persistência OK |
| **Processar alertas** | ✅ **CORRIGIDO** | `PROCESSADOR.processar_lote()` |
| **Salvar alertas (DB)** | ✅ **CORRIGIDO** | `inserir_alertas()` |
| **Broadcast `/ws/alerts`** | ✅ **CORRIGIDO** | `ws_manager.broadcast()` |
| Frontend WebSocket | ✅ Funcionando | Recebe notificações |
| Frontend polling | ❌ Removido | Não é mais necessário |

**Fluxo de Dados**: ESP32 → DB → Processamento → Broadcast → Frontend em tempo real

---

## 🧪 Como Testar

### Teste 1: Verificar Broadcast Funciona

**Terminal 1 (Backend)**:
```bash
uvicorn interface.web:app --reload
```

**Terminal 2 (WebSocket Client - Python)**:
```python
import asyncio
import websockets
import json

async def test_ws_alerts():
    uri = "ws://localhost:8000/api/ws/alerts"
    async with websockets.connect(uri) as ws:
        print("Conectado a /ws/alerts")
        
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Recebido: {data}")

asyncio.run(test_ws_alerts())
```

**Terminal 3 (Enviar Evento via REST - deve gerar broadcast)**:
```bash
curl -X POST http://localhost:8000/api/eventos \
  -H "Content-Type: application/json" \
  -d '{
    "paciente_id": "PAC-0001",
    "postura": 1,
    "ts_utc": "2025-10-28T10:00:00Z",
    "confianca": 0.95
  }'
```

**Resultado Esperado**:
- Terminal 2 deve receber JSON com `type: "alert_new"`

---

### Teste 2: ESP32 WebSocket Completo

**Arduino IDE (ESP32)**:
```cpp
// Usar firmware/esp32_replay/esp32_replay_websocket.ino
// Configurar:
// - hostServidor = "192.168.X.X"
// - endpoint = "/api/ws/eventos"
// - deviceId = "DEV-TEST"
// - camaId = "C-01"

// Upload e monitorar Serial
```

**Terminal (WebSocket Client)**:
```python
# Mesmo código acima para monitorar /ws/alerts
```

**Resultado Esperado**:
- ESP32 envia eventos
- Backend processa e gera alertas
- WebSocket client recebe broadcasts

---

## 🚨 Prioridade

**Severidade**: 🔴 **CRÍTICA**  
**Impacto**: Sistema real (ESP32) não gera alertas  
**Esforço**: ⚡ **BAIXO** (15-30 minutos de código)  
**Risco**: 🟢 **BAIXO** (mudança localizada, sem side effects)

### Próximos Passos Imediatos

1. ✅ Implementar correção em `/ws/eventos` (15 min)
2. ✅ Testar com curl + WebSocket client (10 min)
3. ✅ Testar com ESP32 real (5 min)
4. ✅ Commit e deploy

---

## 📝 Checklist de Implementação

- [ ] Adicionar `PROCESSADOR.processar_lote()` em `/ws/eventos`
- [ ] Adicionar `inserir_alertas()` em `/ws/eventos`
- [ ] Adicionar `ws_manager.broadcast()` em `/ws/eventos`
- [ ] Adicionar logs estruturados
- [ ] Testar com curl + WebSocket client
- [ ] Testar com ESP32 real
- [ ] Atualizar documentação
- [ ] Remover polling do frontend (opcional)
- [ ] Criar testes automatizados

---

## 📚 Referências

- **Código**: `interface/api.py` (linha 2028, 2318)
- **WebSocket Manager**: `interface/ws_manager_optimized.py`
- **Processador**: `servicos/processamento_incremental.py`
- **Frontend Hook**: `frontend/src/hooks/useWebSocket.ts`
- **Dashboard**: `frontend/src/components/pages/DashboardPage.tsx`

---

**Criado por**: GitHub Copilot  
**Data**: 28/10/2025  
**Status**: 🔴 **PENDENTE DE CORREÇÃO**
