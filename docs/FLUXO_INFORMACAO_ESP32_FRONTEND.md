# 🔄 Fluxo Completo da Informação: ESP32 → Frontend

**Data:** 27/10/2025  
**Branch:** feat/websocket-esp32

Este documento descreve **passo a passo** como a informação flui desde o sensor ESP32 até cada componente do frontend.

---

## 📊 Visão Geral do Fluxo

```
┌─────────────┐
│   ESP32     │ 1. WebSocket Connection
│  (Sensor)   │────────────────────────┐
└─────────────┘                        │
                                       ▼
                            ┌──────────────────────┐
                            │  FastAPI WebSocket   │
                            │  /ws/eventos         │
                            └──────────────────────┘
                                       │
                            2. Autenticação & Registro
                                       │
                            ┌──────────▼──────────┐
                            │  Quality Filter     │
                            │  (filtro.py)        │
                            └──────────┬──────────┘
                                       │
                            3. Evento Válido?
                                       │
                            ┌──────────▼──────────┐
                            │  Database SQLite    │
                            │  (eventos table)    │
                            └──────────┬──────────┘
                                       │
                            4. Processamento Incremental
                                       │
                            ┌──────────▼──────────┐
                            │  ProcessadorInc.    │
                            │  (incremental.py)   │
                            └──────────┬──────────┘
                                       │
                            5. Análise de Imobilidade
                                       │
                            ┌──────────▼──────────┐
                            │  Decisor (núcleo)   │
                            │  (decisor.py)       │
                            └──────────┬──────────┘
                                       │
                            6. Alertas Gerados?
                                       │
                            ┌──────────▼──────────┐
                            │  Database SQLite    │
                            │  (alertas table)    │
                            └──────────┬──────────┘
                                       │
                            7. Timeline Events
                                       │
                            ┌──────────▼──────────┐
                            │  Database SQLite    │
                            │ (timeline_events)   │
                            └──────────┬──────────┘
                                       │
                            8. Frontend Rendering
                                       │
              ┌────────────┬───────────┼───────────┬────────────┐
              ▼            ▼           ▼           ▼            ▼
         Dashboard    Timeline    Histórico   Exportação   Devices
         (HTMX)       (HTMX)      (HTMX)      (CSV/PDF)    (UI)
```

---

## 🔢 Fluxo Passo a Passo Detalhado

### **PASSO 1: ESP32 Estabelece Conexão WebSocket**

**Arquivo:** `firmware/esp32_replay/esp32_replay_websocket.ino`

#### 1.1. Inicialização do ESP32
```cpp
void setup() {
    Serial.begin(115200);
    conectarWiFi();  // Conecta ao WiFi "ZECA PAGODINHO"
}
```

**Estado:**
- ESP32 liga e conecta ao WiFi
- Obtém IP: `192.168.0.XXX`

#### 1.2. Conectar ao Servidor WebSocket
```cpp
void processarReplay() {
    webSocket.begin(
        "192.168.0.67",   // IP do servidor
        8000,              // Porta
        "/ws/eventos"      // Endpoint WebSocket
    );
    webSocket.onEvent(webSocketEvent);  // Callback para eventos
    webSocket.setReconnectInterval(5000);  // Reconectar a cada 5s se cair
}
```

**Estado:**
- WebSocket cliente criado
- Tentando conectar a `ws://192.168.0.67:8000/ws/eventos`

#### 1.3. Evento de Conexão
```cpp
void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
    case WStype_CONNECTED:
        Serial.println("[WS] ✅ Conectado ao servidor WebSocket");
        g_websocketConectado = true;
        
        // Enviar autenticação
        String auth = "{\"device_id\":\"DEV-001\",\"cama_id\":\"C-01\"}";
        webSocket.sendTXT(auth);
        break;
}
```

**Mensagem enviada:**
```json
{
    "device_id": "DEV-001",
    "cama_id": "C-01"
}
```

**Estado:**
- Conexão WebSocket estabelecida ✅
- Mensagem de autenticação enviada
- Aguardando resposta do servidor

---

### **PASSO 2: Servidor Recebe e Autentica ESP32**

**Arquivo:** `interface/api.py` (linha ~2027)

#### 2.1. WebSocket Endpoint Aceita Conexão
```python
@router.websocket("/ws/eventos")
async def websocket_eventos(websocket: WebSocket):
    await websocket.accept()
    
    # 1. Receber autenticação
    auth_msg = await websocket.receive_text()
    auth = json.loads(auth_msg)
    device_id = auth.get("device_id")  # "DEV-001"
    cama_id = auth.get("cama_id")      # "C-01"
```

**Estado:**
- WebSocket aceito pelo FastAPI
- Mensagem de autenticação parseada

#### 2.2. Registrar Dispositivo no Banco
```python
# 2. Registrar dispositivo
registrar_device(DB_PATH, device_id, meta={"cama_id": cama_id})
```

**SQL Executado:**
```sql
INSERT INTO devices (device_id, meta_json, ultima_vez_visto)
VALUES ('DEV-001', '{"cama_id": "C-01"}', '2025-10-27T14:30:00')
ON CONFLICT(device_id) DO UPDATE SET
    meta_json = excluded.meta_json,
    ultima_vez_visto = excluded.ultima_vez_visto
```

**Arquivo:** `interface/dao.py`

**Estado no Banco:**
```
devices table:
device_id  | meta_json              | ultima_vez_visto
DEV-001    | {"cama_id": "C-01"}   | 2025-10-27T14:30:00
```

#### 2.3. Resolver Paciente Associado à Cama
```python
# 3. Tentar resolver paciente da câmara
paciente_id = resolver_paciente_por_device_em(
    DB_PATH, 
    device_id, 
    int(time.time() * 1000)
)
```

**SQL Executado:**
```sql
SELECT paciente_id FROM device_assignments
WHERE device_id = 'DEV-001'
  AND start_ms <= 1730035800000
  AND (end_ms IS NULL OR end_ms >= 1730035800000)
ORDER BY start_ms DESC
LIMIT 1
```

**Estado:**
- Se houver assignment ativo: `paciente_id = "PAC-0001"`
- Se não houver: `paciente_id = None`

#### 2.4. Enviar ACK de Conexão para ESP32
```python
# 4. Enviar ACK de conexão
await websocket.send_json({
    "status": "connected",
    "device_id": device_id,
    "paciente_id": paciente_id,
    "message": "Conectado ao servidor de eventos"
})
```

**Mensagem enviada ao ESP32:**
```json
{
    "status": "connected",
    "device_id": "DEV-001",
    "paciente_id": "PAC-0001",
    "message": "Conectado ao servidor de eventos"
}
```

**Estado:**
- ESP32 recebe confirmação
- Pronto para enviar eventos

---

### **PASSO 3: ESP32 Envia Eventos de Postura**

#### 3.1. ESP32 Lê Arquivo de Eventos
```cpp
bool lerProximoEvento(EventoReplay &evento) {
    String linha = g_arquivoEventos.readStringUntil('\n');
    linha.trim();
    
    // Parsear JSON
    StaticJsonDocument<1536> doc;
    deserializeJson(doc, linha);
    
    // Enriquecer com metadados
    doc["device_id"] = "DEV-001";
    doc["paciente_id"] = "PAC-0001";
    doc["cama_id"] = "C-01";
    doc["seq"] = ++g_status.seqAtual;  // Sequência: 1, 2, 3...
    
    String out;
    serializeJson(doc, out);
    evento.payload = out;
    return true;
}
```

**Evento lido do arquivo** `/data/eventos.jsonl`:
```json
{
    "ts_utc": "2025-10-27T14:30:15Z",
    "tipo": "postura",
    "postura": "2",
    "valor": 2,
    "confianca": 0.95
}
```

**Evento enriquecido e enviado:**
```json
{
    "seq": 1,
    "device_id": "DEV-001",
    "paciente_id": "PAC-0001",
    "cama_id": "C-01",
    "ts_utc": "2025-10-27T14:30:15Z",
    "tipo": "postura",
    "postura": "2",
    "valor": 2,
    "confianca": 0.95
}
```

#### 3.2. ESP32 Envia via WebSocket
```cpp
bool enviarEvento(const EventoReplay &evento) {
    webSocket.sendTXT(evento.payload);
    g_status.totalEnviados++;
    Serial.printf("[ENVIADO] seq=%u\n", evento.seq);
    return true;
}
```

**Estado:**
- Evento enviado via WebSocket
- ESP32 aguarda ACK do servidor

---

### **PASSO 4: Servidor Recebe e Filtra Evento**

#### 4.1. Receber Evento no WebSocket
```python
# 5. Loop de processamento de eventos
while True:
    data = await websocket.receive_text()
    evento_json = json.loads(data)
    seq = evento_json.get("seq", 0)  # seq=1
```

**Evento recebido:**
```python
{
    "seq": 1,
    "device_id": "DEV-001",
    "paciente_id": "PAC-0001",
    "cama_id": "C-01",
    "ts_utc": "2025-10-27T14:30:15Z",
    "tipo": "postura",
    "postura": "2",
    "valor": 2,
    "confianca": 0.95
}
```

#### 4.2. Normalizar Evento
```python
# Normalizar evento
if "device_id" not in evento_json:
    evento_json["device_id"] = device_id
if "paciente_id" not in evento_json and paciente_id:
    evento_json["paciente_id"] = paciente_id
```

#### 4.3. Aplicar Filtro de Qualidade

**Arquivo:** `quality/filtro.py`

```python
# Processar evento através do filtro
resultado = filtrar_evento(evento_json)
```

**Lógica do Filtro:**
1. **Verificar confiança:** `confianca >= 0.5` ✅
2. **Verificar tipo:** `tipo in ["postura", "movimento"]` ✅
3. **Verificar postura válida:** `postura in ["1", "2", "3", "4"]` ✅
4. **Verificar timestamp:** Não está no futuro ✅
5. **Verificar duplicatas:** Não é duplicata ✅

**Resultado:**
```python
FiltroResultado(
    descartado=False,
    motivo=None,
    prontos=[evento_json],
    metadata={}
)
```

**Estado:**
- Evento passou no filtro ✅
- Pronto para inserir no banco

---

### **PASSO 5: Persistir Evento no Banco de Dados**

#### 5.1. Inserir Evento na Tabela `eventos`

**Arquivo:** `interface/dao.py`

```python
if not resultado.descartado and resultado.prontos:
    inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])
    metricas.registrar_recebido()
```

**SQL Executado:**
```sql
INSERT INTO eventos (
    paciente_id, 
    timestamp, 
    tipo, 
    postura, 
    valor, 
    confianca, 
    meta_json
) VALUES (
    'PAC-0001',
    '2025-10-27T14:30:15',
    'postura',
    '2',
    2,
    0.95,
    '{"device_id":"DEV-001","cama_id":"C-01","seq":1}'
)
```

**Estado no Banco:**
```
eventos table:
id | paciente_id | timestamp           | tipo    | postura | valor | confianca | meta_json
1  | PAC-0001    | 2025-10-27T14:30:15 | postura | 2       | 2     | 0.95      | {...}
```

#### 5.2. Enviar ACK para ESP32
```python
await websocket.send_json({
    "status": "ok",
    "seq": seq,
    "processados": eventos_processados,
    "descartado": resultado.descartado
})
```

**Mensagem enviada ao ESP32:**
```json
{
    "status": "ok",
    "seq": 1,
    "processados": 1,
    "descartado": false
}
```

**Estado:**
- ESP32 recebe ACK
- Pode enviar próximo evento

---

### **PASSO 6: Processamento Incremental (Análise de Imobilidade)**

#### 6.1. Trigger de Processamento

**IMPORTANTE:** O processamento incremental NÃO ocorre automaticamente no WebSocket. Ele ocorre em um dos seguintes cenários:

**Opção A: Batch Processing (Periódico)**
```python
# Executado via cron job ou task agendada
processador = ProcessadorIncremental(db_path=DB_PATH)
alertas = processador.processar_lote(eventos_novos)
```

**Opção B: Manual via API**
```python
# POST /api/processar
# Executado manualmente pelo operador
```

**Opção C: Stream Processing (Futuro)**
```python
# Após inserir evento, processar imediatamente
resultado_filtro = filtrar_evento(evento_json)
if resultado_filtro.prontos:
    processador.processar_amostra(evento_json)
```

**Para este exemplo, vamos assumir processamento batch:**

#### 6.2. Buscar Eventos Novos do Paciente

**Arquivo:** `servicos/processamento_incremental.py`

```python
def processar_lote(self, eventos: Iterable[Mapping[str, object]]) -> list:
    alertas_emitidos = []
    
    for evento in eventos:
        paciente_id = evento["paciente_id"]  # "PAC-0001"
        postura = evento["postura"]          # "2"
        timestamp = evento["ts_utc"]         # "2025-10-27T14:30:15Z"
        confianca = evento["confianca"]      # 0.95
```

#### 6.3. Verificar Estado do Decisor

```python
estado = self._estado_cache.get(paciente_id)
if estado is None:
    # Criar novo estado para este paciente
    perfil = self._resolver_perfil(paciente_id)  # "medio"
    estado = EstadoDecisor.criar(perfil, paciente_id)
```

**Estado inicial do decisor:**
```python
EstadoDecisor(
    perfil="medio",
    paciente_id="PAC-0001",
    janela_min=120,          # 2 horas para perfil médio
    cooldown_min=30,
    histerese_min=5.0,
    alerta_atual=None,       # Nenhum alerta ativo
    alerta_inicio=None,
    baseline_postura=None,   # Primeira postura
    ultimo_timestamp=None
)
```

#### 6.4. Processar Evento Incremental

**Arquivo:** `nucleo/decisor.py`

```python
novo_estado, alertas = processar_alertas_incremental(
    estado,
    {"timestamp": timestamp, "postura": postura}
)
```

**Lógica do Decisor:**

**Evento 1: Postura "2" às 14:30:15**
- Primeira observação
- Define `baseline_postura = "2"`
- Define `run_postura = "2"`
- Define `run_inicio = 14:30:15`
- **Nenhum alerta** (precisa ficar 120 min na mesma postura)

**Evento 2: Postura "2" às 14:31:15**
- Mesma postura que baseline
- Incrementa run (60 segundos)
- **Nenhum alerta** (ainda faltam 119 min)

**...(eventos continuam)...**

**Evento 121: Postura "2" às 16:31:15**
- Mesma postura por 121 minutos! ⚠️
- **ALERTA DISPARADO!**

```python
alerta = {
    "paciente_id": "PAC-0001",
    "inicio": "2025-10-27T14:30:15",
    "fim": None,
    "status": "aberto",
    "perfil": "medio",
    "janela_min": 120,
    "duracao_min": 121,
    "postura": "2"
}
```

#### 6.5. Atualizar Estado
```python
self._estado_cache[paciente_id] = novo_estado
self._persistir_estado(paciente_id)
```

**Estado persistido:**
```sql
INSERT INTO estado_incremental (paciente_id, estado_json, atualizado_em)
VALUES (
    'PAC-0001',
    '{"perfil":"medio","alerta_atual":{...},"alerta_inicio":"2025-10-27T14:30:15",...}',
    '2025-10-27T16:31:15'
)
```

---

### **PASSO 7: Persistir Alerta no Banco**

#### 7.1. Inserir Alerta na Tabela `alertas`

**Arquivo:** `interface/dao.py`

```python
inserir_alertas(DB_PATH, "PAC-0001", [alerta])
```

**SQL Executado:**
```sql
INSERT INTO alertas (
    paciente_id,
    inicio,
    fim,
    status,
    perfil,
    janela_min,
    duracao_min,
    postura
) VALUES (
    'PAC-0001',
    '2025-10-27T14:30:15',
    NULL,
    'aberto',
    'medio',
    120,
    121,
    '2'
)
```

**Estado no Banco:**
```
alertas table:
id | paciente_id | inicio              | fim  | status  | perfil | janela_min | duracao_min | postura
42 | PAC-0001    | 2025-10-27T14:30:15 | NULL | aberto  | medio  | 120        | 121         | 2
```

#### 7.2. Criar Evento na Timeline

**Arquivo:** `interface/dao.py`

```python
inserir_timeline_event(
    db_path=DB_PATH,
    paciente_id="PAC-0001",
    tipo="alert_open",
    descricao="Alerta de imobilidade aberto (postura 2 por 121 min)",
    ts="2025-10-27T16:31:15",
    ts_ms=1730039475000,
    meta={
        "alert_id": "PAC-0001_2025-10-27T14:30:15",
        "postura": "2",
        "duracao_min": 121
    }
)
```

**SQL Executado:**
```sql
INSERT INTO timeline_events (
    paciente_id,
    tipo,
    descricao,
    ts,
    ts_ms,
    meta_json
) VALUES (
    'PAC-0001',
    'alert_open',
    'Alerta de imobilidade aberto (postura 2 por 121 min)',
    '2025-10-27T16:31:15',
    1730039475000,
    '{"alert_id":"PAC-0001_2025-10-27T14:30:15","postura":"2","duracao_min":121}'
)
```

**Estado no Banco:**
```
timeline_events table:
id | paciente_id | tipo       | descricao                      | ts                  | ts_ms         | meta_json
15 | PAC-0001    | alert_open | Alerta de imobilidade aberto... | 2025-10-27T16:31:15 | 1730039475000 | {...}
```

---

### **PASSO 8: Frontend Consome Dados**

Agora vamos ver **como o frontend moderno (React/TypeScript)** consome e exibe essa informação:

---

## 🖥️ FRONTEND MODERNO (React/TypeScript)

**Localização:** `frontend/src/`  
**Tecnologia:** React 18.3 + TypeScript + Vite + Radix UI + TailwindCSS

---

## 📊 FRONTEND: Dashboard (Alertas Ativos)

**Arquivo:** `frontend/src/components/pages/DashboardPage.tsx`

### 8.1. Componente Dashboard

```tsx
export function DashboardPage() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    
    // Polling automático a cada 2 segundos
    useEffect(() => {
        const fetchAlerts = async () => {
            const response = await fetch('/api/alerts/recent?hours=24');
            const data = await response.json();
            setAlerts(data.alerts);
            setIsLoading(false);
        };
        
        fetchAlerts();
        const interval = setInterval(fetchAlerts, 2000);
        return () => clearInterval(interval);
    }, []);
    
    return (
        <div className="space-y-6">
            <AlertsTable alerts={alerts} isLoading={isLoading} />
        </div>
    );
}
```

### 8.2. Requisição ao Backend

**Endpoint:** `GET /api/alerts/recent?hours=24`

**Arquivo Backend:** `interface/api.py`

```python
@router.get("/alerts/recent")
async def get_recent_alerts(hours: int = 24):
    alertas = selecionar_alertas_janela(
        db_path=DB_PATH,
        horas=hours
    )
    return {"alerts": alertas}
```

**SQL Executado:**
```sql
SELECT 
    paciente_id,
    inicio,
    fim,
    status,
    perfil,
    janela_min,
    duracao_min,
    postura
FROM alertas
WHERE inicio >= datetime('now', '-24 hours')
ORDER BY inicio DESC
LIMIT 100
```

**Resposta JSON:**
```json
{
    "alerts": [
        {
            "paciente_id": "PAC-0001",
            "inicio": "2025-10-27T14:30:15",
            "fim": null,
            "status": "aberto",
            "perfil": "medio",
            "janela_min": 120,
            "duracao_min": 121,
            "postura": "2"
        }
    ]
}
```

### 8.3. Renderização da Tabela

**Arquivo:** `frontend/src/components/dashboard/AlertsTable.tsx`

```tsx
export function AlertsTable({ alerts }: { alerts: Alert[] }) {
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Paciente</TableHead>
                    <TableHead>Início</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Tempo (min)</TableHead>
                    <TableHead>Ações</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {alerts.map((alert) => (
                    <TableRow key={alert.alert_id} className={getStatusClass(alert.status)}>
                        <TableCell>{alert.paciente_id}</TableCell>
                        <TableCell>{formatDate(alert.inicio)}</TableCell>
                        <TableCell>
                            <Badge variant={getStatusVariant(alert.status)}>
                                {alert.status}
                            </Badge>
                        </TableCell>
                        <TableCell>{alert.duracao_min}</TableCell>
                        <TableCell>
                            <Button 
                                size="sm"
                                onClick={() => handleAcknowledge(alert.alert_id)}
                            >
                                Reconhecer
                            </Button>
                        </TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
}
```

**Visualização no Browser:**

```
┌────────────────────────────────────────────────────────────────┐
│ Paciente  │ Início              │ Status    │ Tempo │ Ações   │
├────────────────────────────────────────────────────────────────┤
│ PAC-0001  │ 2025-10-27 14:30:15 │ [Aberto]  │ 121   │ [Btn]   │
│           │                     │ (amarelo) │       │         │
└────────────────────────────────────────────────────────────────┘
```

**Estilo TailwindCSS:**
```tsx
const getStatusClass = (status: string) => {
    switch (status) {
        case 'aberto': return 'bg-yellow-50';
        case 'reconhecido': return 'bg-blue-50';
        case 'fechado': return 'bg-gray-50';
        default: return '';
    }
};
```

---

## 📜 FRONTEND: Timeline (Histórico Visual)

**Arquivo:** `frontend/src/components/pages/TimelinePage.tsx`

### 8.4. Componente Timeline

```tsx
export function TimelinePage() {
    const [events, setEvents] = useState<TimelineEvent[]>([]);
    const [selectedPatient, setSelectedPatient] = useState<string | null>(null);
    
    useEffect(() => {
        const fetchTimeline = async () => {
            const params = new URLSearchParams({
                hours: '24',
                ...(selectedPatient && { patient_id: selectedPatient })
            });
            
            const response = await fetch(`/api/timeline?${params}`);
            const data = await response.json();
            setEvents(data.events);
        };
        
        fetchTimeline();
        const interval = setInterval(fetchTimeline, 5000);
        return () => clearInterval(interval);
    }, [selectedPatient]);
    
    return (
        <div className="space-y-6">
            <TimelineVisualizer events={events} />
            <TimelineEventList events={events} />
        </div>
    );
}
```

### 8.5. Requisição ao Backend

**Endpoint:** `GET /api/timeline?hours=24&patient_id=PAC-0001`

**Arquivo Backend:** `interface/api.py`

```python
@router.get("/timeline")
async def get_timeline(
    hours: Optional[int] = 24,
    patient_id: Optional[str] = None
):
    eventos = selecionar_timeline(
        db_path=DB_PATH,
        paciente_id=patient_id,
        horas=hours
    )
    return {"events": eventos}
```

**SQL Executado:**
```sql
SELECT 
    paciente_id,
    tipo,
    descricao,
    ts,
    ts_ms,
    meta_json
FROM timeline_events
WHERE ts >= datetime('now', '-24 hours')
  AND (paciente_id = 'PAC-0001' OR 'PAC-0001' IS NULL)
ORDER BY ts_ms DESC
```

**Resposta JSON:**
```json
{
    "events": [
        {
            "paciente_id": "PAC-0001",
            "tipo": "alert_open",
            "descricao": "Alerta de imobilidade aberto",
            "ts": "2025-10-27T16:31:15",
            "ts_ms": 1730039475000,
            "meta_json": {
                "alert_id": "PAC-0001_2025-10-27T14:30:15",
                "postura": "2",
                "duracao_min": 121
            }
        }
    ]
}
```

### 8.6. Visualização Timeline

**Arquivo:** `frontend/src/components/timeline/TimelineVisualizer.tsx`

```tsx
export function TimelineVisualizer({ events }: { events: TimelineEvent[] }) {
    const segments = calculateSegments(events);
    
    return (
        <div className="relative h-16 bg-gray-100 rounded-lg overflow-hidden">
            {segments.map((segment, idx) => (
                <div
                    key={idx}
                    className={cn(
                        "absolute top-0 h-full opacity-80 transition-all",
                        getSegmentColor(segment.type)
                    )}
                    style={{
                        left: `${segment.leftPct}%`,
                        width: `${segment.widthPct}%`
                    }}
                    title={segment.description}
                />
            ))}
            
            {/* Cursor "Agora" */}
            <div 
                className="absolute top-0 w-0.5 h-full bg-black"
                style={{ left: `${getCurrentPosition()}%` }}
            />
        </div>
    );
}

const getSegmentColor = (type: string) => {
    switch (type) {
        case 'alert_open': return 'bg-yellow-400';
        case 'alert_ack': return 'bg-blue-400';
        case 'alert_close': return 'bg-gray-400';
        default: return 'bg-gray-300';
    }
};
```

**Visualização no Browser:**
```
┌─────────────────────────────────────────────┐
│░░░░░░░░░░░░░░█████████████░░░░│░░░░░░░░░░░░│
│              (amarelo)         ↑            │
└─────────────────────────────────────────────┘
              Alerta Aberto    Agora
```

---

## 📋 FRONTEND: Pacientes (Gestão Completa)

**Arquivo:** `frontend/src/components/pages/PatientsPage.tsx`

### 8.7. Componente de Pacientes

```tsx
export function PatientsPage() {
    const [patients, setPatients] = useState<Patient[]>([]);
    const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
    
    useEffect(() => {
        const fetchPatients = async () => {
            const response = await fetch('/api/frontend/patients');
            const data = await response.json();
            setPatients(data.patients);
        };
        
        fetchPatients();
    }, []);
    
    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1">
                <PatientList 
                    patients={patients} 
                    onSelect={setSelectedPatient}
                />
            </div>
            
            <div className="lg:col-span-2">
                {selectedPatient ? (
                    <PatientDetail patient={selectedPatient} />
                ) : (
                    <EmptyState message="Selecione um paciente" />
                )}
            </div>
        </div>
    );
}
```

### 8.8. Detalhes do Paciente

```tsx
export function PatientDetail({ patient }: { patient: Patient }) {
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    
    useEffect(() => {
        const fetchPatientTimeline = async () => {
            const response = await fetch(
                `/api/timeline?patient_id=${patient.id}`
            );
            const data = await response.json();
            setTimeline(data.events);
        };
        
        fetchPatientTimeline();
    }, [patient.id]);
    
    return (
        <Card>
            <CardHeader>
                <CardTitle>{patient.id} - {patient.nome}</CardTitle>
            </CardHeader>
            <CardContent>
                <Tabs defaultValue="timeline">
                    <TabsList>
                        <TabsTrigger value="timeline">Histórico</TabsTrigger>
                        <TabsTrigger value="alerts">Alertas</TabsTrigger>
                        <TabsTrigger value="schedule">Agenda</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="timeline">
                        <TimelineEventList events={timeline} />
                    </TabsContent>
                </Tabs>
            </CardContent>
        </Card>
    );
}
```

**Visualização no Browser:**
```
┌─────────────────────────────────────────────┐
│ PAC-0001 - João da Silva                   │
├─────────────────────────────────────────────┤
│ [Histórico] [Alertas] [Agenda]             │
├─────────────────────────────────────────────┤
│ 🔴 alert_open                               │
│ 2025-10-27 16:31:15                         │
│ Alerta de imobilidade aberto (postura 2)    │
│                                             │
│ 🔵 alert_ack                                │
│ 2025-10-27 16:35:00                         │
│ Alerta reconhecido pela equipe              │
└─────────────────────────────────────────────┘
```

---

---

## 📤 FRONTEND: Exportação (CSV/PDF)

**Arquivo:** `frontend/src/components/dashboard/ExportButton.tsx`

### 8.10. Botão de Exportação

```tsx
export function ExportButton() {
    const [isExporting, setIsExporting] = useState(false);
    
    const handleExport = async (format: 'csv' | 'pdf') => {
        setIsExporting(true);
        
        try {
            const params = new URLSearchParams({
                patient_id: selectedPatient,
                start_date: startDate,
                format: format
            });
            
            const response = await fetch(`/api/alerts/export/${format}?${params}`);
            const blob = await response.blob();
            
            // Download automático
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `alerts_${Date.now()}.${format}`;
            a.click();
            window.URL.revokeObjectURL(url);
            
            toast.success(`Exportação ${format.toUpperCase()} concluída!`);
        } catch (error) {
            toast.error('Erro ao exportar');
        } finally {
            setIsExporting(false);
        }
    };
    
    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button disabled={isExporting}>
                    <Download className="mr-2 h-4 w-4" />
                    Exportar
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
                <DropdownMenuItem onClick={() => handleExport('csv')}>
                    Exportar CSV
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport('pdf')}>
                    Exportar PDF
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
```

### 8.11. Endpoint Backend

```python
@router.get("/alerts/export/csv")
async def export_alerts_csv(
    patient_id: Optional[str] = None,
    start_date: Optional[str] = None,
    ...
):
    # Criar filtros
    filters = ExportFilters(
        start_date=datetime.fromisoformat(start_date),
        patient_id=patient_id,
        limit=10000
    )
    
    # Gerar CSV
    export_service = ExportService(DB_PATH)
    csv_content = export_service.export_to_csv(filters)
    
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alerts_PAC-0001.csv"}
    )
```

**Arquivo:** `ferramentas/exportador.py`

```python
def export_to_csv(self, filters: ExportFilters) -> str:
    # Buscar alertas
    alertas = selecionar_alertas_janela(
        db_path=self.db_path,
        horas=24,  # ✅ CORRIGIDO (antes era None)
        paciente_id=filters.patient_id
    )
    
    # Converter para CSV
    df = pd.DataFrame(alertas)
    csv_content = df.to_csv(index=False)
    return csv_content
```

**SQL Executado:**
```sql
SELECT * FROM alertas
WHERE paciente_id = 'PAC-0001'
  AND inicio >= datetime('now', '-24 hours')
ORDER BY inicio DESC
```

**CSV Gerado:**
```csv
paciente_id,inicio,fim,status,perfil,janela_min,duracao_min,postura
PAC-0001,2025-10-27T14:30:15,,aberto,medio,120,121,2
```

**Visualização no Browser:**
- Navegador baixa arquivo `alerts_PAC-0001.csv`
- Usuário pode abrir no Excel

---

---

## 🔧 FRONTEND: Admin (Gestão de Sensores)

**Arquivo:** `frontend/src/components/pages/AdminPage.tsx`

### 8.12. Componente de Administração

```tsx
export function AdminPage() {
    const [devices, setDevices] = useState<Device[]>([]);
    
    useEffect(() => {
        const fetchDevices = async () => {
            const response = await fetch('/api/devices');
            const data = await response.json();
            setDevices(data.devices);
        };
        
        fetchDevices();
        const interval = setInterval(fetchDevices, 5000);
        return () => clearInterval(interval);
    }, []);
    
    return (
        <Card>
            <CardHeader>
                <CardTitle>Dispositivos Conectados</CardTitle>
            </CardHeader>
            <CardContent>
                <DevicesList devices={devices} />
            </CardContent>
        </Card>
    );
}
```

### 8.13. Endpoint Backend

```python
@router.get("/devices")
def list_devices():
    devices = listar_devices(DB_PATH)
    return {"devices": devices}
```

**SQL Executado:**
```sql
SELECT 
    device_id,
    meta_json,
    ultima_vez_visto
FROM devices
ORDER BY ultima_vez_visto DESC
```

**Resultado:**
```python
[
    {
        "device_id": "DEV-001",
        "meta_json": {"cama_id": "C-01"},
        "ultima_vez_visto": "2025-10-27T16:35:00"
    }
]
```

### 8.14. Lista de Dispositivos

**Arquivo:** `frontend/src/components/admin/DevicesList.tsx`

```tsx
export function DevicesList({ devices }: { devices: Device[] }) {
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Device ID</TableHead>
                    <TableHead>Cama</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Último Ping</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {devices.map((device) => (
                    <TableRow key={device.device_id}>
                        <TableCell className="font-mono">
                            {device.device_id}
                        </TableCell>
                        <TableCell>
                            {device.meta_json?.cama_id || '—'}
                        </TableCell>
                        <TableCell>
                            <Badge variant={getDeviceStatus(device).variant}>
                                {getDeviceStatus(device).icon}
                                {getDeviceStatus(device).label}
                            </Badge>
                        </TableCell>
                        <TableCell>
                            {formatRelativeTime(device.ultima_vez_visto)}
                        </TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
}

const getDeviceStatus = (device: Device) => {
    const lastSeen = new Date(device.ultima_vez_visto);
    const minutesAgo = (Date.now() - lastSeen.getTime()) / 1000 / 60;
    
    if (minutesAgo < 2) {
        return { 
            variant: 'success', 
            icon: '🟢', 
            label: 'Online' 
        };
    } else if (minutesAgo < 10) {
        return { 
            variant: 'warning', 
            icon: '🟡', 
            label: 'Inativo' 
        };
    } else {
        return { 
            variant: 'destructive', 
            icon: '🔴', 
            label: 'Offline' 
        };
    }
};
```

**Visualização no Browser:**
```
┌──────────────────────────────────────────────────────────┐
│ Device ID │ Cama  │ Status         │ Último Ping        │
├──────────────────────────────────────────────────────────┤
│ DEV-001   │ C-01  │ 🟢 Online      │ há 30 segundos     │
│ DEV-002   │ C-02  │ 🟡 Inativo     │ há 5 minutos       │
│ DEV-003   │ C-03  │ 🔴 Offline     │ há 2 horas         │
└──────────────────────────────────────────────────────────┘
```

---

## 🎨 Componentes UI Compartilhados

O frontend moderno utiliza uma biblioteca de componentes baseada em **Radix UI** + **TailwindCSS**:

### Componentes Principais:

1. **`Button`** - Botões com variantes (primary, secondary, destructive)
2. **`Card`** - Containers com header/content/footer
3. **`Table`** - Tabelas responsivas com sort/filter
4. **`Badge`** - Tags coloridas para status
5. **`Dialog`** - Modais para formulários
6. **`Tabs`** - Navegação por abas
7. **`Tooltip`** - Dicas contextuais
8. **`Toast`** - Notificações temporárias (via Sonner)
9. **`DropdownMenu`** - Menus suspensos
10. **`Select`** - Campos de seleção customizados

**Localização:** `frontend/src/components/ui/`

---

## 🔄 Gerenciamento de Estado

O frontend moderno utiliza **React Hooks** para gerenciamento de estado:

### Custom Hooks:

**`useAuth()`** - Autenticação e sessão
```tsx
export function useAuth() {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    
    const login = async (username: string, password: string) => {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        if (response.ok) {
            const data = await response.json();
            setUser(data.user);
            return true;
        }
        return false;
    };
    
    return { user, isLoading, login, logout };
}
```

**`useAlerts()`** - Gestão de alertas
```tsx
export function useAlerts(hours: number = 24) {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    
    useEffect(() => {
        const fetchAlerts = async () => {
            const response = await fetch(`/api/alerts/recent?hours=${hours}`);
            const data = await response.json();
            setAlerts(data.alerts);
            setIsLoading(false);
        };
        
        fetchAlerts();
        const interval = setInterval(fetchAlerts, 2000);
        return () => clearInterval(interval);
    }, [hours]);
    
    return { alerts, isLoading };
}
```

**Localização:** `frontend/src/hooks/`

---

## 📱 Responsividade

O frontend moderno é **totalmente responsivo** com TailwindCSS:

```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {/* Layout adapta automaticamente:
        - Mobile (< 768px): 1 coluna
        - Tablet (768-1024px): 2 colunas
        - Desktop (> 1024px): 3 colunas
    */}
</div>
```

**Breakpoints:**
- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px
- `2xl`: 1536px

---

## 📊 Resumo: Informação em Cada Componente

| Componente | Fonte de Dados | Atualização | Tecnologia | Informação Exibida |
|------------|----------------|-------------|------------|-------------------|
| **Dashboard** | `GET /api/alerts/recent` | 2s (React useEffect) | React + TypeScript | Alertas ativos últimas 24h |
| **Timeline** | `GET /api/timeline` | 5s (React useEffect) | React + Recharts | Visualização temporal de eventos |
| **Pacientes** | `GET /api/frontend/patients` | On-demand | React + Tabs | Detalhes completos do paciente |
| **Exportação** | `GET /api/alerts/export/{format}` | On-demand | React + Blob API | Download CSV/PDF |
| **Admin** | `GET /api/devices` | 5s (React useEffect) | React + Table | Status de sensores ESP32 |

---

## 🔄 Fluxo Completo Resumido

```
ESP32 (Hardware)
    ↓ WiFi + WebSocket
Servidor FastAPI (/ws/eventos)
    ↓ Autenticação
Tabela `devices` (Registro)
    ↓ Filtro de Qualidade
Tabela `eventos` (Persistência)
    ↓ Processamento Incremental
Núcleo/Decisor (Análise)
    ↓ Alerta Detectado?
Tabela `alertas` (Alertas)
    ↓ Timeline Event
Tabela `timeline_events` (Histórico)
    ↓ REST API (JSON)
Frontend React/TypeScript:
    - Dashboard (DashboardPage.tsx)
    - Timeline (TimelinePage.tsx)
    - Pacientes (PatientsPage.tsx)
    - Exportação (ExportButton.tsx)
    - Admin (AdminPage.tsx)
```

---

## ⚠️ IMPORTANTE: Frontend Legado (DESCONTINUADO)

### 🚫 Não Usar Mais

**Localização:** `interface/templates/` (Jinja2 templates)  
**Tecnologia:** HTMX + Server-Side Rendering  
**Status:** ❌ **LEGADO - NÃO MANTER**

Este frontend antigo **não deve mais ser usado ou mantido**. Todas as funcionalidades foram reimplementadas no frontend moderno React/TypeScript.

**Razões para descontinuação:**
- ❌ Tecnologia antiga (server-side rendering)
- ❌ Difícil manutenção (templates espalhados)
- ❌ Sem TypeScript (prone a bugs)
- ❌ Performance inferior (full page reloads)
- ❌ UX limitada (sem SPA transitions)

**Frontend Moderno (USAR):**
- ✅ React 18.3 + TypeScript
- ✅ Vite (build rápido)
- ✅ Radix UI + TailwindCSS (componentes modernos)
- ✅ SPA (Single Page Application)
- ✅ Hot Module Replacement
- ✅ Testes E2E (Cypress)

---

## 🎯 Pontos-Chave

1. **Frontend Moderno:** React/TypeScript na pasta `frontend/`
2. **WebSocket bidirecional:** ESP32 ↔ Servidor (conexão persistente)
3. **REST API JSON:** Servidor ↔ Frontend (stateless)
4. **Polling React:** useEffect + setInterval (2-5s)
5. **3 tabelas principais:** `eventos` (bruto), `alertas` (processado), `timeline_events` (auditoria)
6. **Componentização:** UI reutilizável com Radix UI
7. **Type Safety:** TypeScript previne bugs em tempo de compilação
8. **Build otimizado:** Vite bundle com tree-shaking
9. **Responsivo:** Mobile-first com TailwindCSS
10. **Janela temporal consistente:** 24h em todos os componentes

---

**Última atualização:** 27/10/2025  
**Autor:** GitHub Copilot  
**Frontend:** React 18.3 + TypeScript + Vite ✅  
**Revisão:** Corrigido para refletir frontend moderno 🎯
