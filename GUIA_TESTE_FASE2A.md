# GUIA DE TESTES - FASE 2A: Persistência de Autenticação

## Preparação

### Pre-requisitos
- ✅ Backend rodando: `uvicorn interface.api:router --reload`
- ✅ Frontend rodando: `npm run dev` (na pasta frontend)
- ✅ Navegador aberto em `http://localhost:3000`
- ✅ DevTools aberto (F12)

### Verificar Início
1. Abrir DevTools → Application → LocalStorage
2. Deve estar vazio (início da sessão)
3. Console limpo (sem erros)

---

## TESTES MANUAIS

### ✅ TEST 1: Login Salva Token em localStorage

**Passos:**
1. Ir para tela de login (se não estiver)
2. DevTools → Application → LocalStorage → `http://localhost:3000`
3. Notar que está vazio
4. Preencher formulário:
   - Username: `tcc`
   - Password: `123456`
5. Clicar "Entrar"
6. **Verificação:**
   - [ ] Dashboard carrega (login bem-sucedido)
   - [ ] localStorage contém 3 chaves:
     - [ ] `auth_token`: começa com algum valor (JWT ou token)
     - [ ] `auth_user`: JSON com `{username: "tcc", ...}`
     - [ ] `auth_session_expiry`: data/hora no futuro

**Resultado esperado:** ✅ Todas as chaves presentes e preenchidas

---

### ✅ TEST 2: Sessão Persistida ao Reabrir

**Passos:**
1. Completar TEST 1 (estar logado com localStorage preenchido)
2. DevTools → Application → LocalStorage
3. Copiar valores de `auth_token` e `auth_session_expiry`
4. **Fechar completamente a aba** (Ctrl+W ou botão X)
   - ⚠️ Não fazer logout! Fechar só a aba.
5. Reabrir `http://localhost:3000` em nova aba
6. **Verificação:**
   - [ ] Página carrega RÁPIDO (não mostra tela de loading longa)
   - [ ] Dashboard aparece (já está logado)
   - [ ] Username no canto superior = `tcc`
   - [ ] localStorage contém os mesmos tokens
   - [ ] Sem mensagem de erro

**Resultado esperado:** ✅ Autenticado automaticamente, sem fazer login novamente

**Se falhar:**
- ❌ Tela de login aparece → Verificar console (F12 → Console)
  - Procurar por erro 401 ou "Session not valid"
  - Verificar se backend está rodando
- ❌ Dashboard carrega mas vazio → API error
  - Verificar Network tab, Authorization header presente?

---

### ✅ TEST 3: Token Incluído em Requisições

**Passos:**
1. Estar logado (TEST 1)
2. DevTools → Network tab
3. Limpar requests (botão circulatório)
4. Clicar em "Pacientes" (recarrega dados)
5. Procurar by na Network qualquer request para `/api/`
   - Ex: `GET /api/frontend/patients`
6. Clicar nessa request
7. Ir para aba "Headers"
8. **Verificação:**
   - [ ] Request Headers contém:
     ```
     Authorization: Bearer xyz123...
     ```
   - [ ] Valor começa com "Bearer "
   - [ ] Valor continua com o token do localStorage

**Resultado esperado:** ✅ Token presente em Authorization header

**Se falhar:**
- ❌ Authorization header ausente → Token não recuperado
  - Verificar se `getStoredToken()` retorna null
  - Verificar se localStorage tem `auth_token`

---

### ✅ TEST 4: Logout Limpa localStorage

**Passos:**
1. Estar logado (TEST 1)
2. DevTools → Application → LocalStorage
3. Confirmar que token está lá
4. Clicar em nome do usuário (canto superior direito)
5. Clicar "Logout"
6. Aguardar redirecionamento para /login
7. **Verificação:**
   - [ ] Tela de login aparece
   - [ ] localStorage está VAZIO
     - [ ] auth_token: removido
     - [ ] auth_user: removido
     - [ ] auth_session_expiry: removido

**Resultado esperado:** ✅ Todas as chaves removidas, tela de login

---

### ✅ TEST 5: Simular Expiração de Sessão (Manual)

**Passos (Simulação):**
1. Estar logado (TEST 1)
2. DevTools → Console
3. Executar este código:
   ```javascript
   // Simular expiração em 1 minuto
   const expiry = new Date();
   expiry.setSeconds(expiry.getSeconds() + 60);
   localStorage.setItem('auth_session_expiry', expiry.toISOString());
   console.log('Expiração agendada para:', expiry.toISOString());
   ```
4. Clicar Enter
5. **Verificação (primeiros 30s):**
   - [ ] Página segue funcionando
   - [ ] Sem mensagem na tela
6. **Aguardar ~30 segundos**
7. **Verificação (momento do warning):**
   - [ ] Notificação AMARELA aparece no canto inferior direito
   - [ ] Texto: "Sessão Expirando"
   - [ ] Mostra tempo restante (ex: "30s")
   - [ ] Botões: "Estender Sessão" e "Logout"
8. **Aguardar mais ~30 segundos** (total 60s)
9. **Verificação (expiração):**
   - [ ] Notificação muda para VERMELHA
   - [ ] Texto: "Sessão Expirada"
   - [ ] Mensagem: "Por favor, faça login novamente"
   - [ ] Botão: "Voltar ao Login"
10. **Clique automático ou manual:**
    - Página pode redirecionar automaticamente para /login
    - OU botão para clicar manualmente

**Resultado esperado:** ✅ Warnings corretos, redirecionamento funcionando

**Se falhar:**
- ❌ Notificação nunca aparece → SessionExpirationAlert não montado
  - Verificar se `<SessionExpirationAlert />` em App.tsx
  - Verificar console por erros de renderização
- ❌ Notificação não desaparece → Callback não acionado
  - Verificar logs de useSessionMonitor

---

### ✅ TEST 6: Estender Sessão

**Passos:**
1. Executar TEST 5 até ter notificação amarela
2. Anotar o tempo mostrado (ex: "2m 30s")
3. Clicar botão "Estender Sessão"
4. **Verificação:**
   - [ ] Página recarrega (reload visual)
   - [ ] Notificação desaparece
   - [ ] Dashboard continua acessível
   - [ ] Está ainda logado (nome do usuário visível)
   - [ ] localStorage updated:
     - [ ] `auth_session_expiry` tem nova data (24h no futuro)
5. **Simular expiração novamente:**
   - Repetir código do TEST 5
6. Aguardar e verificar que notificação aparece novamente (ciclo se repete)

**Resultado esperado:** ✅ Extensão funciona, session refreshed

---

### ✅ TEST 7: Logout Durante Warning

**Passos:**
1. Executar TEST 5 até ter notificação amarela
2. Clicar botão "Logout" na notificação
3. **Verificação:**
   - [ ] localStorage limpo
   - [ ] Redireciona para tela de login
   - [ ] Notificação desaparece
   - [ ] Username no canto superior desaparece

**Resultado esperado:** ✅ Logout imediato, sem erros

---

### ✅ TEST 8: Token Inválido Detectado

**Passos:**
1. Estar logado (TEST 1)
2. DevTools → Console
3. Executar:
   ```javascript
   // Invalidar o token
   localStorage.setItem('auth_token', 'invalid_token_' + Math.random());
   console.log('Token invalidado');
   ```
4. Clicar Enter
5. Recarregar página (F5 ou Ctrl+R)
6. **Verificação:**
   - [ ] Tela de login aparece (não dashboard)
   - [ ] localStorage limpado automaticamente
     - [ ] auth_token removido
     - [ ] auth_user removido
     - [ ] auth_session_expiry removido
   - [ ] Sem mensagem de erro assustadora
   - [ ] Experiência suave (detecção silenciosa)

**Resultado esperado:** ✅ Token inválido detectado e limpo

**Se falhar:**
- ❌ Dashboard ainda mostra → Token validation não está ocorrendo
  - Backend pode estar aceitando token inválido
  - Ou checkAuth() não está validando com /api/auth/me
- ❌ Mensagem de erro → Deveria ser silencioso

---

### ✅ TEST 9: Session Expiry via Backend

**Passos (Requer Coordenação Backend):**
1. Estar logado (TEST 1)
2. Verificar `auth_session_expiry` em localStorage
3. Verificar backend logs para confirmar token recebido
4. **Backend Ação:** Invalidar manualmente o token no servidor
   - Delete da lista de tokens válidos
   - Ou diminua o TTL no session store
5. Tentar fazer uma ação (clicar em Pacientes, Timeline, etc)
6. **Verificação:**
   - [ ] Request retorna 401 Unauthorized
   - [ ] request() intercepta 401
   - [ ] clearAuth() é chamado
   - [ ] Redireciona para /login
   - [ ] localStorage limpo

**Resultado esperado:** ✅ 401 interceptado e tratado corretamente

---

## TESTES DE CENÁRIOS ESPECIAIS

### 🔐 TEST 10: Múltiplas Abas (Sincronização)

**Passos:**
1. Estar logado em uma aba (TEST 1)
2. Abrir segunda aba: `http://localhost:3000`
3. **Verificação Aba 2:**
   - [ ] Já está logado (localStorage compartilhado)
   - [ ] Dashboard carrega rapidamente
4. Ir para Aba 1, fazer logout
5. **Verificação Aba 2:**
   - [ ] localStorage limpado
   - [ ] Aba 2 ainda mostra conteúdo (cache local)
   - [ ] Se fazer nova requisição → 401 e redireciona

**Resultado esperado:** ✅ localStorage compartilhado entre abas, logout é global

---

### 🌐 TEST 11: Login Durante Offline

**Passos:**
1. Estar offline (DevTools → Network → Offline)
2. Tentar fazer login
3. **Verificação:**
   - [ ] Mensagem de erro "Erro de conexão"
   - [ ] localStorage não é modificado
   - [ ] Está na tela de login

**Resultado esperado:** ✅ Graceful degradation, sem corrupção de state

---

### ⚡ TEST 12: Rapid Session Changes

**Passos:**
1. Estar logado
2. Abrir console e executar rapidamente:
   ```javascript
   // Simular múltiplas mudanças
   for (let i = 0; i < 5; i++) {
     const exp = new Date();
     exp.setSeconds(exp.getSeconds() + (i+1)*60);
     localStorage.setItem('auth_session_expiry', exp.toISOString());
     console.log('Set expiry', i);
   }
   ```
3. Verificar se UI não "flutua" com múltiplos alerts

**Resultado esperado:** ✅ UI estável, sem artifacts visuais

---

## VERIFICAÇÃO DE CÓDIGO

### 1. Verificar storage.ts

```bash
# Verificar se arquivo existe
ls -la frontend/src/lib/storage.ts

# Verificar funções exportadas
grep "export function" frontend/src/lib/storage.ts
```

**Esperado:**
- ✅ getStoredToken
- ✅ storeToken
- ✅ getStoredUser
- ✅ storeUser
- ✅ isSessionValid
- ✅ getSessionTimeRemaining
- ✅ clearAuth

### 2. Verificar api.ts modificado

```bash
# Verificar import de storage
grep "import.*storage" frontend/src/lib/api.ts

# Verificar Authorization header
grep -n "Authorization" frontend/src/lib/api.ts
```

**Esperado:**
- ✅ Import do storage.ts
- ✅ `Authorization: Bearer ${token}`

### 3. Verificar useAuth.ts modificado

```bash
# Verificar getStoredUser usage
grep "getStoredUser" frontend/src/hooks/useAuth.ts

# Verificar getSessionInfo
grep "getSessionInfo" frontend/src/hooks/useAuth.ts
```

**Esperado:**
- ✅ Chama getStoredUser no checkAuth
- ✅ Retorna getSessionInfo()

### 4. Verificar SessionExpirationAlert

```bash
# Verificar arquivo existe
ls -la frontend/src/components/common/SessionExpirationAlert.tsx

# Verificar integração em App.tsx
grep "SessionExpirationAlert" frontend/src/App.tsx
```

**Esperado:**
- ✅ Arquivo existe
- ✅ Importado em App.tsx
- ✅ Renderizado no JSX

---

## MATRIZ DE TESTES

| # | Teste | Descrição | Status |
|---|-------|-----------|--------|
| 1 | Login Salva Token | Verificar localStorage após login | ⏳ |
| 2 | Sessão Persistida | Reabrir sem fazer login novamente | ⏳ |
| 3 | Token em Requisições | Authorization header presente | ⏳ |
| 4 | Logout Limpa | localStorage vazio após logout | ⏳ |
| 5 | Expiração Simulada | Warnings corretos após 5 min | ⏳ |
| 6 | Estender Sessão | Botão estende o tempo | ⏳ |
| 7 | Logout Durante Warning | Logout funciona no alerta | ⏳ |
| 8 | Token Inválido | Detecta e limpa silenciosamente | ⏳ |
| 9 | Session Expiry Backend | 401 interceptado corretamente | ⏳ |
| 10 | Múltiplas Abas | Sincronização de estado | ⏳ |
| 11 | Offline | Sem corrupção de state | ⏳ |
| 12 | Rapid Changes | UI estável sob mudanças rápidas | ⏳ |

---

## Instruções de Execução

### Ambiente de Teste

```powershell
# Terminal 1: Backend
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
python -m uvicorn interface.api:router --reload

# Terminal 2: Frontend
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente\frontend
npm run dev

# Browser
http://localhost:3000
DevTools: F12
```

### Quick Checklist Antes de Merged

- [ ] TEST 1: Login salva token
- [ ] TEST 2: Sessão persiste
- [ ] TEST 3: Token em requisições
- [ ] TEST 4: Logout limpa
- [ ] TEST 5: Warnings aparecem
- [ ] TEST 8: Token inválido detectado
- [ ] Sem erros em console (F12)
- [ ] Sem 401 inesperados em Network tab
- [ ] Build sucesso: `npm run build`

---

## Troubleshooting

### Problema: "localStorage não muda após login"

**Causa provável:** Backend não retorna token

**Solução:**
1. Verificar backend response:
   - DevTools → Network → POST /api/auth/login
   - Ver se Response contém campo `token`
2. Verificar authApi.login() em api.ts:
   - Está chamando `storeToken(response.token)`?
3. Verify backend logs para erros

---

### Problema: "Página não persiste após reabrir"

**Causa provável:** checkAuth() não valida corretamente

**Solução:**
1. Verificar localStorage:
   - DevTools → Application → LocalStorage
   - auth_token presente?
   - auth_session_expiry no futuro?
2. Verificar console para erros
3. Verificar se GET /api/auth/me retorna 200 (Network tab)

---

### Problema: "Token nunca expira"

**Causa provável:** SessionExpirationAlert não montado ou useSessionMonitor não funciona

**Solução:**
1. Verificar App.tsx contém `<SessionExpirationAlert />`
2. Verificar console para erros de renderização
3. Verificar useSessionMonitor logs
4. Executar manual test (TEST 5) com código console

---

## Conclusão

✅ FASE 2A implementa persistência robusta de autenticação com:
- localStorage para token
- Validação automática
- Warnings de expiração
- Tratamento de 401
- Sincronização entre abas

**Próximo:** FASE 2B - WebSocket para alertas real-time

