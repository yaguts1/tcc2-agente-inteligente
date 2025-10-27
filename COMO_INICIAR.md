# 🚀 Como Iniciar o Projeto (Fase 3.2)

## ⚠️ IMPORTANTE: Ordem Correta de Inicialização

O **backend DEVE ser iniciado ANTES do frontend**, senão o Vite vai tentar fazer proxy do WebSocket e ficará com erros de conexão.

---

## 🔧 Passo 1: Inicie o Backend

**Terminal 1 - Backend (FastAPI + WebSocket)**

```bash
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
python -m uvicorn interface.web:app --reload --host 127.0.0.1 --port 8000
```

**Esperado:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

✅ **Aguarde esta mensagem antes de iniciar o frontend!**

---

## 🎨 Passo 2: Inicie o Frontend

**Terminal 2 - Frontend (Vite + React)**

```bash
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente\frontend
npm run dev
```

**Esperado:**
```
VITE v6.3.5  ready in 184 ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
```

✅ **Abra http://localhost:3000 no navegador**

---

## ✅ Verificação

### Frontend conectado ao Backend?

1. Abra o navegador DevTools (F12)
2. Vá para **Network** → **WS** (WebSocket)
3. Você deve ver:
   - ✅ Conexão em `ws://localhost:3000/api/ws/alerts`
   - ✅ Status: **101 Switching Protocols** (ou similar)

### Se vir erro de conexão?

**Problema:** Vite mostra:
```
ws proxy socket error:
Error: read ECONNRESET
```

**Solução:**
1. Verifique se o backend está rodando (Terminal 1)
2. Verifique se está em `http://127.0.0.1:8000` (não localhost!)
3. Se ainda não funcionar, recarregue a página (Ctrl+R)

---

## 🧪 Teste Manual

### Teste 1: Verificar Backend

```bash
curl http://127.0.0.1:8000/api/stats
```

**Resultado esperado:** JSON com estatísticas

### Teste 2: Verificar WebSocket

**Browser Console:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws/alerts');
ws.onopen = () => console.log('✅ WebSocket Conectado!');
ws.onmessage = e => console.log('📨', JSON.parse(e.data));
```

### Teste 3: Teste em Tempo Real

1. Abra Dashboard em **2 abas do navegador**
2. **Aba 1:** Clique "Reconhecer" em um alerta
3. **Aba 2:** Veja o alerta ser atualizado **instantaneamente** ✨

---

## 📋 Troubleshooting

### ❌ "Backend não responde"

```bash
# Verifique se está rodando
curl http://127.0.0.1:8000/api/stats

# Se falhar, reinicie
python -m uvicorn interface.web:app --reload --host 127.0.0.1 --port 8000
```

### ❌ "WebSocket connect error"

1. Verifique se backend está rodando
2. Recarregue a página (Ctrl+R)
3. Veja DevTools → Console para logs

### ❌ "Port 3000 já em uso"

```bash
# Mude a porta no vite.config.ts ou:
npm run dev -- --port 3001
```

### ❌ "Port 8000 já em uso"

```bash
# Mude a porta no comando:
python -m uvicorn interface.web:app --port 8001
```

---

## 🎯 Ordem Correta (IMPORTANTE!)

```
1️⃣  Terminal 1: Inicie Backend (python -m uvicorn ...)
    └─ Aguarde: "Application startup complete"

2️⃣  Terminal 2: Inicie Frontend (npm run dev)
    └─ Aguarde: "ready in ... ms"

3️⃣  Browser: Abra http://localhost:3000
    └─ Verifique: DevTools → Network → WS
```

**🔴 NÃO faça ao contrário!** Se iniciar Frontend primeiro, o Vite vai tentar fazer proxy antes do backend estar pronto.

---

## 🚀 Modo Produção

Se quiser testar o WebSocket sem Vite proxy:

```bash
# Build frontend
cd frontend
npm run build

# Serve os arquivos estáticos via FastAPI
# (Adicione ao interface/web.py)
```

Mas durante desenvolvimento, sempre use a ordem acima.

---

## 📞 Referência Rápida

| Comando | Terminal | Porta | Status |
|---------|----------|-------|--------|
| `python -m uvicorn interface.web:app --reload` | 1 | 8000 | Backend ✅ |
| `npm run dev` | 2 | 3000 | Frontend ✅ |
| Browser | - | http://localhost:3000 | UI |

---

## ✨ Tudo funcionando?

- ✅ Backend rodando em http://127.0.0.1:8000
- ✅ Frontend rodando em http://localhost:3000
- ✅ WebSocket conectado (DevTools → Network → WS)
- ✅ Alertas atualizando em tempo real

**Parabéns! Fase 3.2 está funcionando!** 🎉

---

*Criado em 26/10/2025 - Para troubleshooting rápido*
