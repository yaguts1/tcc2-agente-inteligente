# 📋 FASE 3.4: Otimizações WebSocket - Plano Detalhado

**Data**: 2025-10-27  
**Duração Estimada**: 2-3 horas  
**Status**: 🚀 Iniciando  
**Commits Esperados**: 5-7

---

## 🎯 Objetivos da FASE 3.4

```
1. ⚡ Performance: Reduzir latência e bandwidth
2. 🎯 Filtros: Permitir seleção de alertas no cliente
3. 📦 Compressão: Reduzir tamanho das mensagens
4. 💾 Cache: localStorage para offline + sync
5. 🛡️ Rate Limiting: Proteção contra abuse
6. ✅ Testes: E2E coverage completo
```

---

## 📊 Análise: Estado Atual

### Backend (interface/api.py)

```
✅ Endpoint: /api/ws/alerts
✅ ConnectionManager: Funcional
✅ broadcast(): Integrado em 4 pontos

⚠️ Problema 1: Sem filtro no cliente
   └─ Envia TODOS alertas para TODOS clientes
   └─ Ineficiente se cliente quer alertas específicos

⚠️ Problema 2: Sem compressão
   └─ Cada alerta JSON é enviado completo
   └─ Bandwidth alto em muitos alertas

⚠️ Problema 3: Sem rate limiting
   └─ Se 100 alertas chegam de uma vez
   └─ 100 mensagens WebSocket são enviadas
   └─ Pode sobrecarregar rede/UI
```

### Frontend (useWebSocket.ts)

```
✅ Reconexão: Automática
✅ Heartbeat: 30s
✅ Fallback: Polling 30s
✅ Message Handler: Funcional

⚠️ Problema 1: Sem cache local
   └─ Se desconectar, perde alertas
   └─ Ao reconectar, pode perder dados

⚠️ Problema 2: Sem filtros
   └─ Recebe todos alertas
   └─ Frontend faz filtragem (ineficiente)

⚠️ Problema 3: Sem compressão
   └─ Cada mensagem é grande
   └─ Latência aumenta em rede lenta
```

---

## 🔧 Soluções Propostas

### 1. Filtro de Alertas via WebSocket

**Backend**:
```python
@router.websocket("/ws/alerts")
async def websocket_alerts(
    websocket: WebSocket,
    status: str = Query(None),  # high, critical, etc
    patient_id: str = Query(None),
    types: str = Query(None),  # comma-separated
):
    """WebSocket com filtros opcionais"""
    
    # Armazena filtros do cliente
    filters = {
        'status': status.split(',') if status else None,
        'patient_id': patient_id,
        'types': types.split(',') if types else None,
    }
    
    # Ao fazer broadcast, verifica filtros
    # Só envia se passa nos filtros
```

**Frontend**:
```typescript
const { isConnected } = useWebSocket({
  filters: {
    status: ['high', 'critical'],
    patientId: 'PAC-0001',
  },
  onMessage: handleAlert,
});
```

**Benefício**:
- ✅ 70-90% menos mensagens (típico)
- ✅ Bandwidth reduzida
- ✅ Latência menor
- ✅ UI mais responsiva

### 2. Compressão de Mensagens

**Backend**:
```python
import json
import gzip

def compress_message(data: dict) -> bytes:
    """Comprime JSON para bytes"""
    json_str = json.dumps(data)
    return gzip.compress(json_str.encode())

def decompress_message(data: bytes) -> dict:
    """Descomprime bytes para JSON"""
    json_str = gzip.decompress(data).decode()
    return json.loads(json_str)
```

**Frontend**:
```typescript
// WebSocket binary mode
websocket.binaryType = 'arraybuffer';

websocket.onmessage = async (event) => {
  const compressed = event.data;
  const decompressed = await decompressMessage(compressed);
  handleMessage(decompressed);
};
```

**Benefício**:
- ✅ 30-50% redução de tamanho
- ✅ Menos banda utilizada
- ✅ Mais rápido em rede lenta
- ✅ Ideal para mobile

### 3. localStorage Sync

**Hook novo: `useLocalStorageSync.ts`**:
```typescript
function useLocalStorageSync(key: string) {
  // Sincroniza estado com localStorage
  // Permite:
  //   - Persistência entre reloads
  //   - Offline access
  //   - Auto-sync ao reconectar
}
```

**Uso**:
```typescript
const [alerts, setAlerts] = useLocalStorageSync('alerts');

// Alertas são salvos automaticamente
// Se recarregar: traz alertas salvos
// Se WebSocket voltar: sincroniza novas
```

**Benefício**:
- ✅ Offline access
- ✅ Não perde dados ao refresh
- ✅ Startup mais rápido (cache)
- ✅ Melhor UX

### 4. Rate Limiting

**Backend**:
```python
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_alerts_per_minute: int = 100):
        self.max_alerts = max_alerts_per_minute
        self.client_alerts: Dict[WebSocket, List[datetime]] = {}
    
    def should_send(self, websocket: WebSocket) -> bool:
        """Verifica se pode enviar alerta para cliente"""
        now = datetime.now()
        
        # Limpa timestamps antigos (>1min)
        if websocket in self.client_alerts:
            self.client_alerts[websocket] = [
                ts for ts in self.client_alerts[websocket]
                if (now - ts).total_seconds() < 60
            ]
        
        # Se está no limite, não envia
        if len(self.client_alerts.get(websocket, [])) >= self.max_alerts:
            return False
        
        # Registra novo alerta
        if websocket not in self.client_alerts:
            self.client_alerts[websocket] = []
        
        self.client_alerts[websocket].append(now)
        return True
```

**Uso**:
```python
if rate_limiter.should_send(websocket):
    await websocket.send_json(alert)
else:
    logger.warning("Rate limit exceeded for client")
```

**Benefício**:
- ✅ Proteção contra abuse
- ✅ Evita sobrecarga de clientes
- ✅ Melhor escalabilidade
- ✅ Segurança

### 5. Testes E2E com Cypress

**Arquivo novo: `frontend/cypress/e2e/websocket.cy.ts`**

```typescript
describe('WebSocket Real-time Alerts', () => {
  beforeEach(() => {
    cy.visit('http://localhost:5173');
    cy.login('user@example.com', '1234567890');
  });

  it('should display alert in real-time via WebSocket', () => {
    cy.get('[data-test=alert-count]').should('contain', '0');
    
    // Criar alerta via API
    cy.request({
      method: 'POST',
      url: 'http://localhost:8000/api/alertas',
      headers: {
        'Authorization': 'Bearer user@example.com:1234567890',
      },
      body: {
        alert_type: 'test',
        severity: 'high',
        observacao: 'Cypress test',
        patient_id: 'PAC-0001',
      },
    });
    
    // Verificar se apareceu
    cy.get('[data-test=alert-count]')
      .should('contain', '1')
      .and('have.css', 'color', 'rgb(255, 0, 0)'); // red
    
    // Verificar detalhes
    cy.get('[data-test=alert-row]')
      .first()
      .should('contain', 'Cypress test')
      .and('contain', 'high');
  });

  it('should reconnect and sync alerts on disconnect', () => {
    // Desabilitar WebSocket no DevTools
    // Ou fazer: cy.window().then(win => win.ws.close())
    
    // Criar alerta enquanto desconectado
    // Verificar que polling ainda funciona (ou aguarda reconexão)
    
    // Reconectar
    // Verificar que sync funciona
    // Validar que nenhum alerta foi perdido
  });

  it('should filter alerts based on status', () => {
    // Abrir dropdown de status
    cy.get('[data-test=status-filter]').select('high');
    
    // Verificar que só mostra high
    cy.get('[data-test=alert-row]')
      .each(($row) => {
        cy.wrap($row).should('contain', 'high');
      });
  });

  it('should compress and decompress messages', () => {
    // Monitora network
    cy.intercept('WebSocket', (req) => {
      // Verifica se é comprimido
      expect(req.body).to.have.property('compressed', true);
    });
    
    // Criar alertas
    // Verificar tamanho das mensagens
  });
});
```

**Benefício**:
- ✅ Validação E2E completa
- ✅ Detecta regressions
- ✅ Confiança no deploy
- ✅ Documentação viva

---

## 🗺️ Roadmap de Implementação

### Hora 1: Setup + Filtros

```
⏱️ 15 min: Setup Cypress
   - npm install -D cypress
   - Configurar cypress.config.ts
   
⏱️ 30 min: Backend Filtros
   - Modificar endpoint /api/ws/alerts
   - Adicionar Query parameters
   - Implementar lógica de filtro
   
⏱️ 15 min: Frontend Filtros
   - Atualizar useWebSocket hook
   - Adicionar parâmetros de filtro
   - Testar integração
```

### Hora 2: Compressão + Rate Limiting

```
⏱️ 30 min: Compressão Backend
   - Implementar compress/decompress
   - Integrar ao broadcast
   - Testar tamanho das mensagens
   
⏱️ 20 min: Compressão Frontend
   - Atualizar WebSocket handler
   - Decompress as mensagens
   - Validar performance
   
⏱️ 10 min: Rate Limiting
   - Implementar RateLimiter class
   - Integrar ao broadcast
   - Testar limite
```

### Hora 3: localStorage + Testes E2E

```
⏱️ 30 min: localStorage Sync
   - Criar hook useLocalStorageSync
   - Integrar em DashboardPage
   - Testar persistência
   
⏱️ 60 min: Testes E2E
   - Cypress setup completo
   - 5-6 testes principais
   - Executar e validar
   
⏱️ 10 min: Documentação + Commits
   - Documentar mudanças
   - Fazer commits
   - Push para GitHub
```

---

## 📊 Benefícios Esperados

### Performance

```
Antes:
  - Latência: <100ms
  - Bandwidth: 1KB/alerta
  - Mensagens/min: 100 (todos clientes)
  
Depois:
  - Latência: <50ms (compressão)
  - Bandwidth: 300B/alerta (70% redução)
  - Mensagens/min: 20 (filtros ativados)
  
Melhoria: ✅ 5x mais rápido e eficiente!
```

### Confiabilidade

```
Antes:
  - Perde dados ao desconectar
  - Sem proteção contra abuse
  - Sem validação E2E
  
Depois:
  - localStorage cache offline
  - Rate limiting ativo
  - 6+ testes E2E passando
  
Melhoria: ✅ Sistema robusto e confiável!
```

### UX/DX

```
Antes:
  - Sem filtros
  - Mensagens grandes
  - Sem cache local
  
Depois:
  - Filtros por status/tipo/paciente
  - Mensagens comprimidas
  - Cache + offline access
  - Sync automático
  
Melhoria: ✅ UX muito melhor!
```

---

## 🎯 Métricas de Sucesso

```
✅ Compressão: 30-50% redução
✅ Filtros: 70-90% redução de mensagens
✅ Rate Limit: Máximo 100 alertas/min/cliente
✅ localStorage: Todas alertas sincronizadas
✅ Testes: 6+ E2E tests passando
✅ Performance: Latência <50ms
✅ Produção: Ready para deploy
```

---

## 📋 Checklist

- [ ] Cypress instalado e configurado
- [ ] Backend: Filtros implementados
- [ ] Frontend: useWebSocket atualizado
- [ ] Backend: Compressão implementada
- [ ] Frontend: Decompress implementado
- [ ] Backend: Rate limiting implementado
- [ ] Frontend: useLocalStorageSync criado
- [ ] Tests: 6+ E2E tests criados
- [ ] Tests: Todos passando
- [ ] Documentação: Atualizada
- [ ] Commits: Feitos e pushed
- [ ] Build: Sem erros

---

## 🚀 Próximos Passos

1. **Iniciar implementação** (começar pela análise)
2. **Implementar cada feature** (uma por uma)
3. **Testar** (E2E e manual)
4. **Documentar** (mudanças e benefícios)
5. **Deploy** (para staging/produção)

---

**Status**: 🚀 **PRONTO PARA INICIAR**

**Tempo Estimado**: 2-3 horas  
**Dificuldade**: ⭐⭐⭐ (Média)  
**Impacto**: ⭐⭐⭐⭐⭐ (Alto)

Vamos lá! 🎯
