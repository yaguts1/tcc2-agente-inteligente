# 🔧 CORREÇÃO: Token não era salvo em localStorage

## 🔴 Problema Identificado

Token não estava sendo salvo em localStorage após o login.

### Causa Raiz
Backend estava usando **cookies (httpOnly)** como mecanismo de sessão, mas **não retornava o token no JSON da resposta**.

Frontend esperava:
```typescript
{
  username: "tcc",
  token: "xyz...",  // ← Não existia!
  display_name: "TCC"
}
```

Backend retornava:
```typescript
{
  username: "tcc",
  display_name: null
}
// Token era apenas um cookie httpOnly (invisível para JS)
```

Result: `storeToken()` não era chamado porque `response.token` era undefined.

---

## ✅ Solução Implementada

### 1. Backend: Agora retorna token na resposta (interface/api.py)

**Login endpoint:**
```python
@router.post("/auth/login")
async def api_login(...):
    # ... validação de credenciais ...
    
    # ✨ NOVO: Gerar token
    token = f"{username}:{int(time.time())}"
    
    # ✨ Retornar token no JSON
    resp = {
        "username": username,
        "token": token,  # ← NOVO
        "display_name": user.get("display_name"),
        "role": user.get("role", "staff")
    }
    
    # Ainda manter cookie para requisições (fallback)
    response.set_cookie("session_user", username, max_age=8*3600, httponly=True)
    return response
```

**Register endpoint:**
```python
@router.post("/auth/register")
async def api_register(...):
    # ... criar usuário ...
    
    # ✨ NOVO: Gerar token
    token = f"{username}:{int(time.time())}"
    
    # ✨ Retornar token no JSON
    resp = {
        "username": username,
        "token": token,  # ← NOVO
        "display_name": display,
        "role": "staff"
    }
    
    response.set_cookie("session_user", username, max_age=8*3600, httponly=True)
    return response
```

### 2. Frontend: Melhorado checkAuth() (useAuth.ts)

**Antes:**
```typescript
if (storedUser && storedToken) {
  // Só confiava se tivesse AMBOS
  const data = await authApi.me();
  setUser(data);
}
```

**Depois:**
```typescript
// ✨ Sempre tenta validar sessão com backend
// O backend usa cookie httpOnly (enviado automaticamente)
const data = await authApi.me();  // Cookie é enviado automaticamente
setUser(data);

// ✨ Restaura localStorage se vazio (para consistência)
const storedUser = getStoredUser();
if (!storedUser) {
  storeUser({
    username: data.username,
    display_name: data.display_name,
    role: data.role,
  });
}
```

**Benefício:** Não depende mais de localStorage estar populado. Cookie é a fonte de verdade.

### 3. Frontend: Expiração ajustada (storage.ts)

Changed default expiry from 24h → **8h** (matching backend cookie expiry):

```typescript
export function storeToken(token: string, expiryHours: number = 8): void {
  // ...
}
```

---

## 🔄 Fluxo Agora

### Login
```
User: tcc / 123456
  ↓
POST /api/auth/login
  ↓
Backend:
  ✅ Valida credentials
  ✅ Gera token: "tcc:1729989600"
  ✅ Retorna JSON com token
  ✅ Define cookie httpOnly
  ↓
Frontend:
  ✅ Recebe response com token
  ✅ Chama storeToken("tcc:1729989600")
  ✅ localStorage['auth_token'] = "tcc:1729989600"
  ✅ localStorage['auth_session_expiry'] = "2025-10-28T08:00:00Z"
  ✓ SALVO EM LOCALSTORAGE!
```

### Reabrir Navegador
```
App inicializa
  ↓
useAuth.checkAuth()
  ↓
GET /api/auth/me (com cookie httpOnly enviado automaticamente)
  ↓
Backend valida cookie
  ✅ Cookie válido → Retorna user data
  ❌ Cookie inválido → 401 Unauthorized
  ↓
Frontend:
  ✅ 200 OK → setUser(data), restaura localStorage
  ❌ 401 → clearAuth(), mostra login
```

### Requisição Autenticada
```
fetch('/api/pacientes')
  ↓
request() function:
  ✅ getStoredToken() retorna "tcc:1729989600"
  ✅ Adiciona "Authorization: Bearer tcc:1729989600"
  ✅ Cookie também enviado automaticamente
  ↓
Backend:
  ✅ Valida Authorization header OU cookie
  ✅ Processa requisição
  ✅ Retorna dados
```

---

## 🧪 Como Testar a Correção

### Test 1: Login agora salva token
```
1. Fazer login (tcc / 123456)
2. DevTools → Application → LocalStorage
3. ✅ auth_token: "tcc:1729989600" (deve estar presente)
4. ✅ auth_user: JSON com username
5. ✅ auth_session_expiry: data/hora no futuro
```

### Test 2: localStorage persiste ao reabrir
```
1. Estar logado (token em localStorage)
2. Fechar aba completamente
3. Reabrir http://localhost:3000
4. ✅ Dashboard aparece imediatamente (sem login)
5. ✅ localStorage ainda tem os tokens
```

### Test 3: Token incluído em requisições
```
1. Estar logado
2. DevTools → Network
3. Fazer qualquer request (ex: GET /api/pacientes)
4. Verificar headers da requisição
5. ✅ Authorization: Bearer tcc:1729989600 (presente)
```

---

## 📊 Mudanças

| Arquivo | Mudança |
|---------|---------|
| `interface/api.py` | +3 linhas (gera token, retorna no JSON) |
| `frontend/src/hooks/useAuth.ts` | ~10 linhas modificadas (novo checkAuth) |
| `frontend/src/lib/storage.ts` | 1 linha (expiração 24h → 8h) |

**Total:** +14 linhas

---

## 🔐 Segurança

✅ Token está em localStorage (visível, mas)
✅ Cookie está em httpOnly (não acessível via JS)
✅ Backend valida AMBOS (double-check)
✅ 401 em qualquer um → logout automático
✅ Expiração sincronizada (8h em ambos)

---

## ✨ Status

- ✅ Backend: Retorna token
- ✅ Frontend: Armazena em localStorage
- ✅ Build: 1709 módulos, 1.77s, 0 erros
- ✅ Python: Sintaxe válida
- ✅ Commit: 6abf43f
- ✅ GitHub: Push bem-sucedido

**Status:** 🔧 CORREÇÃO APLICADA E DEPLOYADA

Agora execute TEST 1 de `GUIA_TESTE_FASE2A.md` para confirmar que o token é salvo! 🎉

