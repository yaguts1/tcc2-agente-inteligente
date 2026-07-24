# 🔄 JORNADA DA INFORMAÇÃO: ESP32 → Servidor

## 📊 Visão Geral

```
ESP32 → WebSocket → Filtro → Banco de Dados → Motor de Alertas → WebSocket Frontend
  ↓        ↓          ↓            ↓                 ↓                    ↓
Sensor   /ws/eventos Quality     eventos          alertas          /ws/alerts
                     Filter      tabela           tabela
```

---

## 1️⃣ **ESP32: Captura de Dados**

### 📍 Localização
- Hardware: ESP32 com sensores de pressão/postura
- Firmware: `firmware/esp32_replay/`

### 📤 O que envia
```json
{
  "seq": 1,
  "device_id": "DEV-001",
  "paciente_id": "PAC-001",
  "cama_id": "C-01",
  "ts_utc": "2025-10-29T14:30:00Z",
  "tipo": "postura",
  "valor": 1,
  "confianca": 0.95,
  "amostra_ms": 300000
}
```

### 🔗 Protocolo
- **WebSocket** para comunicação bidirecional
- **Endpoint**: `ws://servidor:8000/api/ws/eventos`

---

## 2️⃣ **Servidor: Recepção via WebSocket**

### 📍 Arquivo
`interface/api.py` - Função `websocket_eventos()`

### 🔄 Fluxo de Processamento

#### **Passo 1: Handshake e Autenticação**
```python
# ESP32 envia primeiro:
{"device_id": "DEV-001", "cama_id": "C-01"}

# Servidor responde:
{
  "status": "connected",
  "device_id": "DEV-001",
  "paciente_id": "PAC-001",
  "message": "Conectado ao servidor de eventos"
}
```

**Código:**
```python
@router.websocket("/ws/eventos")
async def websocket_eventos(websocket: WebSocket):
    await websocket.accept()
    
    # 1. Autenticação
    auth_msg = await websocket.receive_text()
    auth = json.loads(auth_msg)
    device_id = auth.get("device_id")
    cama_id = auth.get("cama_id")
    
    # 2. Registrar dispositivo
    registrar_device(DB_PATH, device_id, meta={"cama_id": cama_id})
    
    # 3. Resolver paciente pela câmara
    paciente_id = resolver_paciente_por_device_em(DB_PATH, device_id, timestamp)
    
    # 4. ACK de conexão
    await websocket.send_json({
        "status": "connected",
        "device_id": device_id,
        "paciente_id": paciente_id
    })
```

#### **Passo 2: Loop de Eventos**
```python
while True:
    # Receber evento
    data = await websocket.receive_text()
    evento_json = json.loads(data)
    
    # Normalizar campos
    evento_json["device_id"] = device_id
    evento_json["paciente_id"] = paciente_id
    
    # ✅ PONTO CRÍTICO 1: Filtro de Qualidade
    resultado = filtrar_evento(evento_json)
    
    if not resultado.descartado and resultado.prontos:
        # ✅ PONTO CRÍTICO 2: Salvar no banco
        inserir_eventos(DB_PATH, paciente_id, [evento_json])
        
        # ✅ PONTO CRÍTICO 3: Processar alertas
        alertas_gerados = PROCESSADOR.processar_lote(resultado.prontos)
        
        # ✅ PONTO CRÍTICO 4: Broadcast alertas
        for alerta in alertas_gerados:
            asyncio.create_task(ws_manager_optimized.broadcast(alerta))
    
    # Enviar ACK ao ESP32
    await websocket.send_json({
        "status": "ok",
        "seq": seq,
        "alertas_gerados": len(alertas_gerados)
    })
```

---

## 3️⃣ **Filtro de Qualidade**

### 📍 Arquivo
`quality/filtro.py`

### 🎯 Função
Remove dados ruidosos, duplicados ou inválidos

### 🔍 Verificações
```python
class FiltroResultado:
    descartado: bool       # Se true, evento foi rejeitado
    motivo: str | None     # Razão da rejeição
    prontos: list[dict]    # Eventos validados prontos para processar
    buffered: bool         # Se evento foi bufferizado
```

### ✅ Critérios de Validação
- ✓ Confiança >= limiar configurado
- ✓ Campos obrigatórios presentes
- ✓ Timestamp válido
- ✓ Não é duplicata
- ✓ Não é ruído (mudanças muito rápidas)

---

## 4️⃣ **Persistência no Banco de Dados**

### 📍 Arquivo
`interface/dao.py` - Função `inserir_eventos()`

### 🗄️ Tabela
```sql
CREATE TABLE eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    device_id TEXT,
    inicio TEXT NOT NULL,
    fim TEXT,
    tipo TEXT NOT NULL,
    confianca REAL,
    amostra_ms INTEGER,
    meta TEXT
)
```

### 💾 Operação
```python
def inserir_eventos(db_path, paciente_id, eventos):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for evento in eventos:
        cursor.execute("""
            INSERT INTO eventos 
            (paciente_id, device_id, inicio, tipo, confianca, amostra_ms, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id,
            evento.get("device_id"),
            evento.get("ts_utc"),
            evento.get("tipo"),
            evento.get("confianca"),
            evento.get("amostra_ms"),
            json.dumps(evento.get("meta", {}))
        ))
    
    conn.commit()
    conn.close()
```

---

## 5️⃣ **Motor de Alertas**

### 📍 Arquivo
`servicos/processamento_incremental.py`

### ⚙️ Processamento
```python
class ProcessadorIncremental:
    def processar_lote(self, eventos: list) -> list:
        """Processa eventos e gera alertas"""
        
        # 1. Agrupar por paciente
        por_paciente = self._agrupar_eventos(eventos)
        
        # 2. Para cada paciente, verificar alertas
        alertas = []
        for paciente_id, evts in por_paciente.items():
            # Obter perfil do paciente
            perfil = obter_perfil_paciente(paciente_id)
            
            # Processar com motor de alertas
            _, novos_alertas = processar_alertas(
                evts, 
                perfil, 
                paciente_id
            )
            
            alertas.extend(novos_alertas)
        
        return alertas
```

### 🔔 Tipos de Alerta
- **Imobilidade**: Paciente sem mudança de postura por X minutos
- **Postura inadequada**: Postura de risco mantida
- **Pressão excessiva**: Pontos de pressão críticos

### 📊 Perfis de Risco
```python
PERFIS = {
    "baixo": {"janela_min": 180, "limiar_mudancas": 3},
    "medio": {"janela_min": 120, "limiar_mudancas": 4},
    "alto":  {"janela_min": 60,  "limiar_mudancas": 6}
}
```

---

## 6️⃣ **Broadcast para Frontend**

### 📍 Arquivo
`interface/ws_manager_optimized.py`

### 🌐 Endpoint
`ws://servidor:8000/api/ws/alerts`

### 📤 Mensagem Enviada
```json
{
  "type": "alert_new",
  "alert_id": "2025-10-29T14:30:00Z",
  "patient_id": "PAC-001",
  "timestamp": "2025-10-29T14:30:00Z",
  "status": "pending",
  "severity": "critical",
  "data": {
    "paciente_id": "PAC-001",
    "inicio": "2025-10-29T14:30:00Z",
    "tipo": "imobilidade",
    "perfil": "alto",
    "janela_min": 60
  }
}
```

### 🎯 Filtros Inteligentes
```python
class WebSocketFilter:
    """Clientes recebem apenas alertas relevantes"""
    
    severities: set       # Ex: {"high", "critical"}
    patient_id: str       # Ex: "PAC-001"
    alert_types: set      # Ex: {"imobilidade"}
```

**Vantagens:**
- ✅ Reduz bandwidth (envia só o necessário)
- ✅ Clientes não precisam filtrar
- ✅ Escalável (muitos clientes diferentes)

---

## 7️⃣ **Frontend: Exibição em Tempo Real**

### 📍 Arquivos
- `frontend/src/pages/AlertsPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`

### 🔌 Conexão WebSocket
```typescript
const ws = new WebSocket('ws://localhost:8000/api/ws/alerts');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'alert_new') {
    // Adicionar alerta à lista
    setAlerts(prev => [data, ...prev]);
    
    // Tocar som de notificação
    playAlertSound(data.severity);
    
    // Mostrar notificação
    showNotification(data);
  }
};
```

---

## ✅ **VERIFICAÇÕES DE FUNCIONAMENTO**

### 1. **WebSocket ESP32 → Servidor**
```bash
# Testar conexão
python scripts_demo/test_simple_ws.py
```

**Resultado Esperado:**
```
✅ Conectado a ws://localhost:8000/api/ws/eventos
✅ Autenticação aceita
✅ Evento enviado
✅ ACK recebido
```

### 2. **Filtro de Qualidade**
```python
from quality.filtro import filtrar_evento

evento = {
    "device_id": "DEV-001",
    "paciente_id": "PAC-001",
    "ts_utc": "2025-10-29T14:30:00Z",
    "tipo": "supino",
    "confianca": 0.95
}

resultado = filtrar_evento(evento)
assert not resultado.descartado
assert len(resultado.prontos) > 0
```

### 3. **Persistência no Banco**
```python
from interface.dao import inserir_eventos, listar_eventos

inserir_eventos("dados.db", "PAC-001", [evento])
eventos = listar_eventos("dados.db", "PAC-001")
assert len(eventos) > 0
```

### 4. **Motor de Alertas**
```python
from servicos.processamento_incremental import ProcessadorIncremental

processador = ProcessadorIncremental()
alertas = processador.processar_lote([evento])
# Se paciente ficou muito tempo imóvel, deve gerar alerta
```

### 5. **Broadcast WebSocket**
```bash
# Terminal 1: Iniciar servidor
uvicorn interface.web:app --reload

# Terminal 2: Conectar cliente WebSocket
python -c "
import asyncio
import websockets
import json

async def test():
    uri = 'ws://localhost:8000/api/ws/alerts'
    async with websockets.connect(uri) as ws:
        print('✅ Conectado')
        msg = await ws.recv()
        print(f'✅ Mensagem recebida: {msg}')

asyncio.run(test())
"
```

---

## 🔧 **PONTOS DE FALHA E RECUPERAÇÃO**

### 1. **ESP32 perde conexão**
- ✅ Reconexão automática
- ✅ Buffer de eventos no ESP32
- ✅ Reenvio após reconexão

### 2. **Servidor reinicia**
- ✅ Estado persistido no banco
- ✅ Clientes reconectam automaticamente
- ✅ Processamento incremental retoma

### 3. **Banco de dados indisponível**
- ✅ Eventos bufferizados em memória
- ✅ Retry automático
- ✅ Logs de erro detalhados

### 4. **Frontend desconecta**
- ✅ Reconexão automática
- ✅ Busca alertas perdidos via REST API
- ✅ Indicador visual de conexão

---

## 📈 **MÉTRICAS E MONITORAMENTO**

### Prometheus Metrics
```python
# /metrics endpoint
eventos_recebidos_total
eventos_descartados_total
alertas_gerados_total
websocket_connections_active
websocket_messages_sent_total
```

### Logs Estruturados
```json
{
  "event": "ws_evento_salvo",
  "device_id": "DEV-001",
  "seq": 123,
  "paciente_id": "PAC-001",
  "timestamp": "2025-10-29T14:30:00Z"
}
```

---

## 🎯 **CONFIGURAÇÕES IMPORTANTES**

### `.env` ou variáveis de ambiente
```bash
# Banco de dados
UPP_DB_PATH=dados.db

# Filtro de qualidade
CONF_LIMIAR=0.80
FILTRO_BUFFER_SIZE=100

# WebSocket
DEVICE_RECONCILE_INTERVAL=30

# Alertas
DEFAULT_PERFIL=medio
```

### Perfis de Paciente
```sql
-- Tabela pacientes
CREATE TABLE pacientes (
    id TEXT PRIMARY KEY,
    nome TEXT,
    perfil_risco TEXT,  -- 'baixo', 'medio', 'alto'
    meta TEXT
)
```

---

## 🚀 **COMO TESTAR A JORNADA COMPLETA**

### Script de Teste Completo
```bash
# 1. Iniciar servidor
uvicorn interface.web:app --reload

# 2. Em outro terminal, enviar evento simulado
python -c "
import asyncio
import websockets
import json
from datetime import datetime

async def test():
    uri = 'ws://localhost:8000/api/ws/eventos'
    
    async with websockets.connect(uri) as ws:
        # 1. Autenticação
        await ws.send(json.dumps({
            'device_id': 'DEV-TEST',
            'cama_id': 'C-01'
        }))
        resp = await ws.recv()
        print(f'Auth: {resp}')
        
        # 2. Enviar evento
        for i in range(25):  # 25 eventos = 2h (5min cada)
            evento = {
                'seq': i+1,
                'device_id': 'DEV-TEST',
                'paciente_id': 'PAC-0001',
                'cama_id': 'C-01',
                'ts_utc': datetime.now().isoformat(),
                'tipo': 'postura',
                'valor': 1,  # supino
                'confianca': 0.95
            }
            await ws.send(json.dumps(evento))
            resp = await ws.recv()
            print(f'Evento {i+1}: {resp}')

asyncio.run(test())
"
```

---

## ✅ **CONCLUSÃO**

A jornada da informação está **completa e funcional**:

1. ✅ ESP32 → WebSocket → Servidor
2. ✅ Filtro de qualidade valida dados
3. ✅ Persistência no banco de dados
4. ✅ Motor de alertas processa incrementalmente
5. ✅ Broadcast para frontend via WebSocket
6. ✅ Frontend exibe em tempo real

**Todos os pontos críticos foram verificados e estão operacionais.**

