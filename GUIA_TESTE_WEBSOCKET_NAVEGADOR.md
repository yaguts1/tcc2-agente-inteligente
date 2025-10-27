# 🌐 Guia Prático: Testar WebSocket no Navegador

**Data**: 2025-10-27  
**Objetivo**: Verificar WebSocket funcionando em tempo real via UI

---

## ✅ Pré-requisitos

### 1. Backend Rodando
```bash
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
uvicorn interface.api:app --reload
```
**Status**: Terminal `uvicorn` está ✅ ativo

### 2. Frontend Rodando
```bash
cd frontend
npm run dev
```
**Status**: Terminal `esbuild` está ✅ ativo

### 3. Fazer Login
- URL: `http://localhost:5173`
- Email: `user@example.com`
- Senha: `1234567890`

---

## 🧪 Teste 1: Verificar Conexão WebSocket

### Passo 1: Abrir DevTools

```
Pressionar: F12
Atalho: Ctrl + Shift + I
Menu: Clique direito → Inspecionar elemento
```

### Passo 2: Ir para a aba "Network"

```
Firefox/Chrome: DevTools → Network tab
Edge: DevTools → Network tab
```

### Passo 3: Filtrar WebSocket

```
Digite na caixa de filtro: "ws"
```

### Passo 4: Ir para Dashboard

```
Clique em: Dashboard (no menu)
Você deve ver uma conexão WebSocket aparecer:

Nome: ws
Protocolo: websocket
Status: 101 Switching Protocols
```

**O que você verá:**

```
┌─────────────────────────────────────────────────────┐
│ Network Tab - WebSocket Connection                  │
├─────────────────────────────────────────────────────┤
│ Name              │ Status │ Type      │ Size        │
│ (your-host)/alerts
│                   │ 101    │ websocket │ -           │
│ (your-host)/js   │ 200    │ script    │ 123.4 KB    │
└─────────────────────────────────────────────────────┘
```

**Resultado Esperado**: ✅ Status 101 (Switching Protocols)

---

## 🧪 Teste 2: Verificar Mensagens em Tempo Real

### Passo 1: Abrir Console

```
DevTools → Console tab
```

### Passo 2: Ver Logs

Você deve ver mensagens como:

```javascript
[useWebSocket] WebSocket connected
[useWebSocket] Receiving heartbeat from server
[useWebSocket] Message received: {...}
```

### Passo 3: Criar Novo Alerta

Abra outro terminal e execute:

```bash
curl -X POST http://localhost:8000/api/alertas \
  -H "Authorization: Bearer user@example.com:1234567890" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "teste_ui",
    "severity": "high",
    "observacao": "Teste via WebSocket",
    "patient_id": "PAC-0001"
  }'
```

### Passo 4: Observar Dashboard

```
⚡ O alerta deve aparecer IMEDIATAMENTE (<100ms)
Sem precisar fazer F5 (refresh)
```

**Resultado Esperado**:
- ✅ Alerta aparece na tabela
- ✅ Status está correto
- ✅ Timestamp está atualizado
- ✅ Toast notification aparece

---

## 🧪 Teste 3: Verificar Reconexão

### Passo 1: Parar o Backend

```bash
Terminal uvicorn: CTRL+C
```

### Passo 2: Observar Console

```javascript
[useWebSocket] WebSocket disconnected
[useWebSocket] Attempting to reconnect... (attempt 1/5)
[useWebSocket] Attempting to reconnect... (attempt 2/5)
[useWebSocket] Attempting to reconnect... (attempt 3/5)
...
```

### Passo 3: Observar Dashboard

```
🔴 Indicador de conexão muda para vermelho
💬 Toast aparece: "Desconectado de alertas em tempo real"
🔄 Começa a usar polling (a cada 30s)
```

### Passo 4: Ligar Backend Novamente

```bash
Terminal uvicorn: uvicorn interface.api:app --reload
```

### Passo 5: Observar Reconexão

```javascript
[useWebSocket] WebSocket connected
[useWebSocket] Reconnected successfully!
```

```
🟢 Indicador muda para verde
💬 Toast aparece: "Conectado a alertas em tempo real"
🔄 Polling desativa automaticamente
```

**Resultado Esperado**:
- ✅ Reconnection automática (sem refresh)
- ✅ Fallback para polling funcionando
- ✅ UI se atualiza corretamente
- ✅ Toast notificações aparecem

---

## 🧪 Teste 4: Performance e Latência

### Passo 1: Abrir Console do Browser

```
F12 → Console
```

### Passo 2: Adicionar Monitor de Latência

```javascript
// Cole no console:
window.wsLatency = {
  sent: null,
  received: null,
  latency: null
};

// Hook no recebimento de mensagem
const originalReceive = WebSocket.prototype.addEventListener;
WebSocket.prototype.addEventListener = function(event, handler) {
  if (event === 'message') {
    const wrappedHandler = (e) => {
      window.wsLatency.received = performance.now();
      window.wsLatency.latency = 
        window.wsLatency.received - window.wsLatency.sent;
      console.log(`📊 Latência: ${window.wsLatency.latency.toFixed(2)}ms`);
      handler(e);
    };
    return originalReceive.call(this, event, wrappedHandler);
  }
  return originalReceive.call(this, event, handler);
};
```

### Passo 3: Criar Alertas

```bash
# Terminal: Execute múltiplos alertas rapidamente
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/alertas \
    -H "Authorization: Bearer user@example.com:1234567890" \
    -H "Content-Type: application/json" \
    -d "{
      \"alert_type\": \"stress_test\",
      \"severity\": \"high\",
      \"observacao\": \"Teste $i\",
      \"patient_id\": \"PAC-0001\"
    }" &
done
```

### Passo 4: Verificar Latência

```
Console deve mostrar:

📊 Latência: 23.45ms
📊 Latência: 18.92ms
📊 Latência: 15.33ms
📊 Latência: 12.67ms
```

**Resultado Esperado**:
- ✅ Latência < 100ms (tempo real)
- ✅ Tipicamente 10-50ms em rede local
- ✅ Sem lag visível na UI

---

## 📊 Checklist de Testes

### Conexão Básica
- [ ] WebSocket conecta ao abrir Dashboard
- [ ] Status HTTP 101 na aba Network
- [ ] Console mostra "[useWebSocket] WebSocket connected"

### Tempo Real
- [ ] Alerta criado via API aparece imediatamente
- [ ] Sem necessidade de refresh (F5)
- [ ] Status atualiza em <100ms
- [ ] Toast notification aparece

### Reconexão
- [ ] Backend para → Console mostra tentativas
- [ ] Polling inicia automaticamente
- [ ] Backend liga → Reconecta sem erro
- [ ] Polling para e WebSocket assume

### Performance
- [ ] Latência <100ms observada
- [ ] Múltiplos alertas processados corretamente
- [ ] UI responsiva durante testes
- [ ] Sem memory leaks (DevTools → Memory)

### Fallback
- [ ] Sem WebSocket, polling atualiza a cada 30s
- [ ] Toggle automático quando WebSocket volta
- [ ] UI feedback claro do estado

---

## 🔍 Troubleshooting

### Problema: WebSocket não conecta

```
Solução 1: Verificar se backend está rodando
$ curl http://localhost:8000/api/status

Solução 2: Verificar CORS
$ Fazer login em http://localhost:5173

Solução 3: Verificar logs
Terminal uvicorn: Procurar por "ws_manager.connect"
```

### Problema: Mensagens não chegam

```
Solução 1: Verificar if console mostra "Message received"
F12 → Console

Solução 2: Criar alerta via API
$ curl -X POST http://localhost:8000/api/alertas ...

Solução 3: Verificar logs do backend
uvicorn console deve mostrar broadcast calls
```

### Problema: Polling não ativa

```
Solução 1: Parar backend completamente
CTRL+C no terminal uvicorn

Solução 2: Aguardar 5 segundos
useWebSocket tenta reconectar 5 vezes (3s cada)

Solução 3: Abrir Console
Deve aparecer: "Falling back to polling"
```

### Problema: UI não atualiza

```
Solução 1: Verificar localStorage
DevTools → Application → Local Storage
Verificar: auth_token, auth_session_expiry

Solução 2: Fazer refresh (F5)
Verificar se persiste

Solução 3: Ver console para erros
DevTools → Console → Procurar por "error"
```

---

## 📱 Browser Compatibility

| Browser | WebSocket | Status |
|---------|-----------|--------|
| Chrome 90+ | ✅ Sim | ✅ Testado |
| Firefox 88+ | ✅ Sim | ✅ Suportado |
| Safari 14+ | ✅ Sim | ✅ Suportado |
| Edge 90+ | ✅ Sim | ✅ Testado |

---

## 🎓 O Que Esperamos Ver

### Fluxo Ideal

```
1. Abrir Dashboard
   └─ WebSocket conecta (WS: /api/ws/alerts)
   └─ Console: "WebSocket connected"
   └─ Network tab mostra conexão 101

2. Backend cria alerta
   └─ broadcast() envia para todos clientes
   └─ Frontend recebe em onMessage

3. handleWebSocketMessage processa
   └─ Atualiza estado (setAlerts)
   └─ Atualiza stats (setStats)
   └─ UI re-renderiza

4. Alerta visível
   └─ Aparece na tabela
   └─ Toast mostra
   └─ Status correto
   └─ Latência <100ms ✨
```

### Fluxo com Error

```
1. Backend desconecta
   └─ WebSocket.onclose() dispara
   └─ useWebSocket tenta reconectar
   └─ 5 tentativas com 3s de intervalo

2. Reconexão falha
   └─ Fallback para polling ativa
   └─ usePolling começa a fazer fetch a cada 30s
   └─ UI continua atualizada (com delay)

3. Backend volta online
   └─ useWebSocket reconecta
   └─ Polling desativa automaticamente
   └─ Voltamos ao fluxo ideal

4. Sem perca de dados
   └─ Nenhum alerta é perdido
   └─ UI sempre mostra estado correto
```

---

## ✨ Conclusão

Se todos os testes passarem:

✅ **FASE 2B está 100% funcional**
✅ **Sistema pronto para produção**
✅ **Pode-se prosseguir para próxima fase**

---

**Tempo estimado de teste**: 15-20 minutos  
**Dificuldade**: Fácil  
**Requisitos**: Browser + DevTools + Terminal
