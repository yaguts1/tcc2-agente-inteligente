# 🎬 Quick Start: Testar WebSocket em 5 Minutos

**Tempo**: 5 minutos  
**Dificuldade**: ⭐ Fácil  
**Resultado**: Validação WebSocket funcionando

---

## 📋 Checklist Rápido

```
[ ] Backend rodando (uvicorn)
[ ] Frontend rodando (npm run dev)
[ ] Browser aberto em http://localhost:5173
[ ] Fazer login
[ ] Abrir DevTools (F12)
```

---

## 🚀 Instruções Rápidas

### Passo 1: Verificar Servidores (30 seg)

Terminal uvicorn:
```
✅ Procurar por: "Application startup complete"
```

Terminal esbuild:
```
✅ Procurar por: "[vite] ready in"
```

### Passo 2: Abrir Dashboard (1 min)

```
1. Browser: http://localhost:5173
2. Fazer login:
   Email: user@example.com
   Senha: 1234567890
3. Ir para: Dashboard (menu)
```

### Passo 3: Abrir DevTools (30 seg)

```
Pressionar: F12
Ir para: Network tab
Filtrar: "ws"
```

### Passo 4: Verificar Conexão (1 min)

Você deve ver:

```
Name:       ws (WebSocket)
Status:     101 Switching Protocols
Size:       -
Type:       websocket
Initiated:  your-ip:port
```

✅ **Se vê 101 = WebSocket está conectado!**

### Passo 5: Criar Alerta (30 seg)

```bash
# Em outro terminal:
curl -X POST http://localhost:8000/api/alertas \
  -H "Authorization: Bearer user@example.com:1234567890" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "teste",
    "severity": "high",
    "observacao": "Teste WebSocket",
    "patient_id": "PAC-0001"
  }'
```

### Passo 6: Verificar Dashboard (30 seg)

```
✅ Alerta deve aparecer IMEDIATAMENTE
✅ Sem fazer F5 (refresh)
✅ Status deve estar correto
✅ Timestamp deve estar atualizado
```

---

## 📊 O Que Esperar Ver

### Network Tab

```
✅ Conexão WebSocket com status 101
✅ Protocolo: websocket
✅ Size: - (streaming)
```

### Console

```
✅ Nenhum erro vermelho
✅ Pode ver debug logs
✅ Mensagens do useWebSocket
```

### Dashboard

```
✅ Alertas carregados
✅ Novo alerta aparece em <100ms
✅ Stats atualizados
✅ Toast notification aparece
```

---

## ⚠️ Se Algo Não Funcionar

### Problema: WebSocket não conecta (sem 101)

```
1. Verificar se backend está online:
   curl http://localhost:8000/api/status

2. Se offline:
   Terminal uvicorn: uvicorn interface.api:app --reload

3. Se frontend não conecta:
   Browser: CTRL+Shift+Delete (limpar cache)
   F5 para reload
```

### Problema: Alerta não aparece

```
1. Verificar Console (F12) para erros
2. Verificar se curl retornou status 201
3. Criar novo alerta e tentar novamente
```

### Problema: UI não atualiza

```
1. F5 para recarregar
2. Verificar localStorage:
   DevTools → Application → Local Storage
   Deve ter: auth_token
3. Fazer login novamente
```

---

## ✅ Conclusões Possíveis

### Se Todos Testes Passam ✅

```
🎉 WebSocket está 100% funcional!
   └─ Pode fazer deploy
   └─ Pode prosseguir para FASE 3.4
```

### Se Alguns Testes Falham ⚠️

```
📖 Consultar: GUIA_TESTE_WEBSOCKET_NAVEGADOR.md
   └─ Troubleshooting section
   └─ Instruções detalhadas
```

---

## 🎯 Próximo Passo

Depois de validar:

```
1. FASE 3.4 - Otimizações (2h)
   └─ Performance e escalabilidade

2. Ou: Deploy para homolog (30 min)
   └─ git merge feat/websocket-esp32 → main
```

---

**Tempo total: 5 minutos**  
**Dificuldade: ⭐ Fácil**  
**Risco: Nenhum (apenas testes)**

🚀 **Vamos validar?**
