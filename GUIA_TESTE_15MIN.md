# 🧪 GUIA RÁPIDO DE TESTE - 15 MINUTOS

Você tem 15 minutos para testar o sistema procurando por bugs. Aqui está o roteiro otimizado.

---

## ⏱️ TIMELINE: 15 MINUTOS

### 0-1 min: Preparação
```bash
# Terminal 1: Backend
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
uvicorn interface.web:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev  # vai rodar em localhost:3000
```

### 1-2 min: Carregar Aplicação
- [ ] Abrir http://localhost:3000
- [ ] Página login deve carregar
- [ ] Console deve estar limpo (F12 → Console)

### 2-3 min: Teste de Login
- [ ] Click em "Criar Conta" (ou usar conta teste se tiver)
- [ ] Preencher: username, password, display name
- [ ] Submit
- [ ] Verificar redirecionamento para login
- [ ] Fazer login com credenciais criadas
- [ ] Dashboard deve carregar

### 3-5 min: Teste WebSocket
- [ ] Em "Dashboard", verificar se alertas em tempo real funcionam
- [ ] Abrir F12 → Network → WS
- [ ] Procurar por conexão WebSocket em `ws://localhost:3000/api/ws/alerts`
- [ ] Status: Connected ✅
- [ ] **NÃO deve haver múltiplas conexões abertas e fechadas rapidamente**

### 5-7 min: Teste Timeline/Histórico
- [ ] Click em "Histórico" (navbar esquerda)
- [ ] **Problema anterior**: Não carregava
- [ ] **Esperado agora**: Timeline deve carregar com eventos
- [ ] Scroll e verificar se há eventos listados
- [ ] **NÃO deve haver spinner infinito ou erro na aba Network**

### 7-9 min: Teste Pacientes
- [ ] Click em "Pacientes"
- [ ] Deve mostrar lista de pacientes
- [ ] Tentar expandir um paciente
- [ ] Verificar que documentos e rotinas carregam
- [ ] Procurar por data/hora sem erro

### 9-11 min: Teste Agendas
- [ ] Encontrar seção de Agendas (pode estar em Admin ou Pacientes)
- [ ] Criar novo agenda
- [ ] Preencher dados (paciente, tipo, horário)
- [ ] Submit
- [ ] **Verificar que agenda foi criada e persiste** (reload página)
- [ ] Editar agenda
- [ ] Deletar agenda
- [ ] **Sem erros de rede**

### 11-13 min: Verificar Console
- [ ] Abrir F12 → Console
- [ ] **Procurar por**:
  - ✅ Nenhum error (vermelho)
  - ✅ Nenhum warning sobre refs (amarelo)
  - ✅ Nenhum "Attempting to reconnect" repetido
- [ ] Se houver erros, screenshot e notar

### 13-15 min: Teste Responsividade
- [ ] Redimensionar janela (F11 para fullscreen, depois resize)
- [ ] Mobile view (F12 → Toggle device toolbar)
- [ ] Testar em iPhone
- [ ] **Nenhum layout quebrado**
- [ ] Click em alguns botões

---

## 🔴 RED FLAGS - Se Encontrar Algo Assim, É BUG

```
❌ "Function components cannot be given refs"
❌ "Attempting to reconnect... (1/5)"
❌ Múltiplas WebSocket connections abertas
❌ Timeline não carregando (spinner infinito)
❌ AgendaForm lançando erro
❌ Refresh da página perde dados
❌ 404 em alguma rota importante
❌ Console cheia de warnings
❌ Layout quebrado em mobile
```

---

## ✅ GREEN FLAGS - Se Ver Isso, É BOM SINAL

```
✅ Login/Logout funciona
✅ Dashboard carrega com dados
✅ WebSocket conectado uma única vez
✅ Timeline mostra eventos
✅ Pacientes listam corretamente
✅ Agendas persistem (reload OK)
✅ Console limpo (sem warnings)
✅ Responsive bem
✅ Sem 404s
✅ Performance OK
```

---

## 🔧 Se Encontrar Bug

1. **Reproduza exatamente**
   - Passo-a-passo
   - O que esperava
   - O que aconteceu

2. **Gather Evidence**
   - Screenshot
   - Console log (F12 copy)
   - Network tab (F12 → Network)

3. **Report Format**
   ```
   BUG TITLE: [descrição curta]
   
   STEPS:
   1. ...
   2. ...
   
   EXPECTED: ...
   ACTUAL: ...
   
   CONSOLE: [paste erro]
   ```

---

## 💪 Performance Notes

Se tudo estiver rápido:
- ✅ Backend responses < 500ms
- ✅ Frontend loads < 3s
- ✅ No lag em inputs
- ✅ Smooth animations

---

## 📍 Shortcuts Úteis

| Ação | Comando |
|------|---------|
| Reload | F5 ou Ctrl+Shift+R (hard reload) |
| DevTools | F12 |
| Network tab | F12 → Network |
| Console | F12 → Console |
| Mobile view | F12 → Toggle device |
| Responsive | Ctrl+Shift+M |

---

## 🎯 Tempo Ideal por Teste

- Login: 1 min
- WebSocket: 1 min
- Timeline: 1 min
- Pacientes: 2 min
- Agendas: 2 min
- Console: 1 min
- Mobile: 2 min
- **Buffer**: 2 min

---

## 📋 Checklist Final

- [ ] Dashboard carrega
- [ ] WebSocket conecta (sem spam)
- [ ] Timeline mostra eventos
- [ ] Pacientes listam
- [ ] Agendas funcionam e persistem
- [ ] Console limpo
- [ ] Mobile responsivo
- [ ] Sem 404s
- [ ] Performance OK
- [ ] Botões funcionam

---

## 🚀 RESULTADO

Se tudo acima passar: **✅ PRONTO PARA PRODUÇÃO**

Se encontrou bugs: Abra issue no GitHub com as informações acima.

---

**BOA SORTE! 15 MINUTOS COMEÇANDO... AGORA! ⏱️**
