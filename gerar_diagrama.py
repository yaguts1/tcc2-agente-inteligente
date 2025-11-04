#!/usr/bin/env python3
"""
Gerador de diagrama da arquitetura do sistema.
Cria um arquivo Mermaid para visualização da jornada de dados.
"""

MERMAID_DIAGRAM = """
```mermaid
flowchart TD
    Start([ESP32 com Sensores]) -->|WebSocket| Auth[Autenticação]
    Auth -->|device_id + cama_id| Register[Registrar Dispositivo]
    Register -->|Resolver Paciente| Loop{Loop de Eventos}
    
    Loop -->|Receber JSON| Parse[Parse Evento]
    Parse --> Validate{Validar Campos}
    
    Validate -->|Inválido| Reject[Rejeitar + Log]
    Reject --> SendNack[Enviar NACK]
    SendNack --> Loop
    
    Validate -->|Válido| Filter[Filtro de Qualidade]
    Filter --> FilterCheck{Passou no Filtro?}
    
    FilterCheck -->|Descartado| Log1[Log Motivo]
    Log1 --> SendAck[Enviar ACK]
    SendAck --> Loop
    
    FilterCheck -->|Bufferizado| Log2[Log Buffer]
    Log2 --> SendAck
    
    FilterCheck -->|Pronto| SaveDB[(Salvar no Banco)]
    SaveDB --> ProcessAlerts[Processar Alertas]
    
    ProcessAlerts --> CheckAlerts{Alertas Gerados?}
    
    CheckAlerts -->|Não| SendAck
    
    CheckAlerts -->|Sim| SaveAlerts[(Salvar Alertas)]
    SaveAlerts --> Broadcast[Broadcast WebSocket]
    Broadcast --> SendAck
    
    Broadcast -.->|ws://server/ws/alerts| Frontend[Frontend React]
    Frontend --> Display[Exibir Alerta em Tempo Real]
    
    style Start fill:#e1f5ff
    style Auth fill:#fff3cd
    style Filter fill:#d4edda
    style SaveDB fill:#cce5ff
    style ProcessAlerts fill:#f8d7da
    style Broadcast fill:#d1ecf1
    style Frontend fill:#e2e3e5
    style Display fill:#d4edda
```

```mermaid
sequenceDiagram
    participant ESP32
    participant WS as WebSocket Server
    participant Filter as Quality Filter
    participant DB as Database
    participant Engine as Alert Engine
    participant Broadcast as WS Manager
    participant Frontend as React Frontend
    
    Note over ESP32,Frontend: 1. Conexão e Autenticação
    ESP32->>WS: connect()
    WS-->>ESP32: accept()
    ESP32->>WS: {"device_id":"DEV-001","cama_id":"C-01"}
    WS->>DB: registrar_device()
    WS->>DB: resolver_paciente()
    WS-->>ESP32: {"status":"connected","paciente_id":"PAC-001"}
    
    Note over ESP32,Frontend: 2. Envio de Evento
    ESP32->>WS: {"seq":1,"tipo":"postura","valor":1,...}
    WS->>Filter: filtrar_evento()
    
    alt Evento válido
        Filter-->>WS: FiltroResultado(prontos=[evento])
        WS->>DB: inserir_eventos()
        WS->>Engine: processar_lote()
        
        alt Alerta gerado
            Engine-->>WS: [alerta]
            WS->>DB: inserir_alertas()
            WS->>Broadcast: broadcast(alerta)
            Broadcast->>Frontend: {"type":"alert_new",...}
            Frontend->>Frontend: Exibir notificação
        end
        
        WS-->>ESP32: {"status":"ok","seq":1,"alertas_gerados":1}
    else Evento descartado
        Filter-->>WS: FiltroResultado(descartado=true)
        WS-->>ESP32: {"status":"ok","seq":1,"descartado":true}
    end
    
    Note over ESP32,Frontend: 3. Loop contínuo
    loop Cada 5 minutos
        ESP32->>WS: Novo evento
        WS->>Filter: Processar
        Filter->>DB: Salvar
        DB->>Engine: Analisar
        Engine->>Broadcast: Notificar
        Broadcast->>Frontend: Atualizar UI
    end
```

```mermaid
graph LR
    subgraph ESP32["🔌 ESP32"]
        S1[Sensor Pressão 1]
        S2[Sensor Pressão 2]
        S3[Sensor Pressão 3]
        S4[Sensor Pressão 4]
    end
    
    subgraph Backend["⚙️ Backend FastAPI"]
        WS[WebSocket /ws/eventos]
        Filter[Quality Filter]
        DB[(SQLite Database)]
        Engine[Alert Engine]
        WSM[WebSocket Manager]
    end
    
    subgraph Frontend["🖥️ Frontend React"]
        Dashboard[Dashboard]
        Alerts[Alertas]
        Timeline[Timeline]
        Patients[Pacientes]
    end
    
    S1 --> WS
    S2 --> WS
    S3 --> WS
    S4 --> WS
    
    WS --> Filter
    Filter --> DB
    DB --> Engine
    Engine --> WSM
    
    WSM -->|WebSocket| Dashboard
    WSM -->|WebSocket| Alerts
    WSM -->|WebSocket| Timeline
    
    DB -->|REST API| Dashboard
    DB -->|REST API| Alerts
    DB -->|REST API| Timeline
    DB -->|REST API| Patients
    
    style ESP32 fill:#e1f5ff
    style Backend fill:#fff3cd
    style Frontend fill:#d4edda
```
"""

OUTPUT_FILE = "ARQUITETURA_DIAGRAMA.md"

def main():
    """Gera arquivo com diagramas Mermaid"""
    
    content = f"""# 🏗️ Arquitetura do Sistema - Diagramas

Este arquivo contém diagramas interativos da arquitetura do sistema.

## Como visualizar

1. **GitHub**: Os diagramas são renderizados automaticamente
2. **VS Code**: Instale a extensão "Markdown Preview Mermaid Support"
3. **Online**: Cole o código em https://mermaid.live/

---

## 📊 Diagrama 1: Fluxo de Processamento de Eventos

{MERMAID_DIAGRAM.split('```mermaid')[1].split('```')[0]}

---

## 🔄 Diagrama 2: Sequência de Comunicação

{MERMAID_DIAGRAM.split('```mermaid')[2].split('```')[0]}

---

## 🏛️ Diagrama 3: Arquitetura de Componentes

{MERMAID_DIAGRAM.split('```mermaid')[3].split('```')[0]}

---

## 📝 Legenda

### Cores
- 🔵 **Azul claro**: Entrada de dados (ESP32)
- 🟡 **Amarelo**: Processamento e validação
- 🟢 **Verde**: Armazenamento e sucesso
- 🔴 **Vermelho**: Alertas e notificações
- ⚪ **Cinza**: Frontend e visualização

### Componentes Principais

1. **ESP32**: Dispositivo com sensores de pressão
2. **WebSocket Server**: Recebe eventos em tempo real
3. **Quality Filter**: Valida e filtra dados ruidosos
4. **Database**: Persiste eventos e alertas
5. **Alert Engine**: Processa e gera alertas
6. **WebSocket Manager**: Faz broadcast para frontend
7. **Frontend React**: Interface do usuário

---

## 🔗 Endpoints

### WebSocket
- `ws://server:8000/api/ws/eventos` - ESP32 → Servidor
- `ws://server:8000/api/ws/alerts` - Servidor → Frontend

### REST API
- `GET /api/alerts` - Listar alertas
- `GET /api/pacientes` - Listar pacientes
- `GET /api/timeline` - Timeline de eventos
- `POST /api/eventos` - Inserir eventos (batch)
- `POST /api/alerts/:id/acknowledge` - Reconhecer alerta

---

## 📦 Tecnologias

### Backend
- **FastAPI**: Framework web assíncrono
- **WebSockets**: Comunicação bidirecional em tempo real
- **SQLite**: Banco de dados relacional
- **Pandas**: Processamento de dados
- **Structlog**: Logging estruturado

### Frontend
- **React**: UI reativa
- **TypeScript**: Tipagem estática
- **Vite**: Build tool
- **TailwindCSS**: Estilização
- **Lucide Icons**: Ícones

### ESP32
- **Arduino/ESP-IDF**: Framework de desenvolvimento
- **WebSocket Client**: Comunicação com servidor
- **JSON**: Serialização de dados

---

*Diagramas gerados automaticamente pelo script `gerar_diagrama.py`*
"""
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Diagrama gerado: {OUTPUT_FILE}")
    print(f"\n📖 Como visualizar:")
    print(f"   1. Abra o arquivo no GitHub (renderização automática)")
    print(f"   2. VS Code: Instale 'Markdown Preview Mermaid Support'")
    print(f"   3. Online: https://mermaid.live/")

if __name__ == "__main__":
    main()
