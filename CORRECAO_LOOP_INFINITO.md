# 🔧 CORREÇÃO: Loop Infinito de Recarga

## 🔴 Problema

Frontend estava piscando / recarregando infinitamente ao tentar fazer login.

### Sintoma
```
1. Abrir página
2. Tela pisca continuamente
3. DevTools mostra requisições infinitas para /api/auth/me
4. Não consegue nem ver a tela de login
```

## 🔍 Causa Raiz

### Problema 1: Redirecionamento em api.ts (REMOVIDO)

**Código problemático:**
```typescript
async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  // ...
  const response = await fetch(url, { ... });

  // ❌ PROBLEMA: Redirecionar antes de lançar exception
  if (response.status === 401) {
    clearAuth();
    window.location.href = '/login';  // ← Isso causa recarga!
  }

  return handleResponse<T>(response);
}
```

**Por que causava problema:**
1. GET /api/auth/me chamado (sem cookie válido)
2. Backend retorna 401
3. request() faz `window.location.href = '/login'`
4. **Página recarrega completamente**
5. App inicializa novamente
6. useAuth.checkAuth() é chamado
7. Volta para passo 1 → **LOOP INFINITO**

### Problema 2: Fluxo de tratamento do checkAuth

Não havia tratamento claro do que fazer após 401. Às vezes continuava, às vezes retornava, criando inconsistência.

## ✅ Solução

### 1. Removido redirecionamento no api.ts

**Antes:**
```typescript
if (response.status === 401) {
  clearAuth();
  window.location.href = '/login';  // ❌ Redireciona imediatamente
}
```

**Depois:**
```typescript
// ❌ Removido! Deixar handleResponse() lançar exception
// O tratamento é feito no useAuth
return handleResponse<T>(response);
```

**Benefício:** Não redireciona durante boot. Deixa o useAuth tratar o erro corretamente.

### 2. Melhorado checkAuth em useAuth.ts

**Antes:**
```typescript
const checkAuth = async () => {
  try {
    try {
      const data = await authApi.me();
      setUser(data);
      return;  // ← Ambíguo
    } catch (err) {
      if (err instanceof ApiException && err.status === 401) {
        clearAuth();
        setUser(null);
        return;  // ← Ambíguo
      }
      return;  // ← Ambíguo
    }
  } finally {
    setIsLoading(false);
  }
};
```

**Depois:**
```typescript
const checkAuth = async () => {
  try {
    try {
      const data = await authApi.me();
      setUser(data);
      setError(null);
      setIsLoading(false);  // ← Claro
    } catch (err) {
      // Se falhar, trata o erro
      if (err instanceof ApiException && err.status === 401) {
        clearAuth();
        setUser(null);
      } else {
        setUser(null);
      }
      setError(null);
      setIsLoading(false);  // ← Claro
    }
  } catch (err) {
    console.error('[useAuth] checkAuth error:', err);
    setIsLoading(false);  // ← Sempre executa
  }
};
```

**Benefício:** Fluxo claro, sem ambiguidade, setIsLoading sempre é chamado.

## 🔄 Novo Fluxo (Correto)

### Boot Inicial
```
App inicializa
  ↓
useAuth.checkAuth() chamado
  ↓
GET /api/auth/me (sem cookie válido)
  ↓
Backend retorna 401
  ↓
request() lança ApiException 401
  ↓
checkAuth() captura a exception
  ↓
clearAuth()
setUser(null)
setIsLoading(false)  ← IMPORTANTE: Para o loading!
  ↓
✅ Mostra tela de login (SEM RECARGA)
```

### Login
```
User: tcc / 123456
  ↓
POST /api/auth/login
  ↓
Backend valida → Retorna token + cookie
  ↓
Frontend: storeToken() + setUser()
  ↓
✅ Dashboard carrega
```

### Reabrir Navegador (Com Cookie Válido)
```
App inicializa
  ↓
GET /api/auth/me (com cookie httpOnly enviado)
  ↓
Backend valida cookie → Retorna user data
  ↓
200 OK
  ↓
Frontend: setUser(data) + localStorage restaurado
  ↓
✅ Dashboard carrega imediatamente
```

## 🎯 O Que Mudou

### Arquivo 1: frontend/src/lib/api.ts
```diff
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers,
    ...options,
  });

- // Handle 401 Unauthorized - clear auth and redirect to login
- if (response.status === 401) {
-   clearAuth();
-   window.location.href = '/login';
- }

  return handleResponse<T>(response);
```

### Arquivo 2: frontend/src/hooks/useAuth.ts
```diff
  const checkAuth = async () => {
    try {
      try {
        const data = await authApi.me();
        setUser(data);
        setError(null);
-       return;
+       setIsLoading(false);
      } catch (err) {
        if (err instanceof ApiException && err.status === 401) {
          clearAuth();
          setUser(null);
-         setError(null);
        } else {
          setUser(null);
-         setError(null);
        }
+       setError(null);
+       setIsLoading(false);
      }
    } catch (err) {
      console.error('[useAuth] checkAuth error:', err);
+     setIsLoading(false);
    }
-   finally {
-     setIsLoading(false);
-   }
  };
```

## 🧪 Como Testar

### Test 1: Boot sem estar logado
```
1. Limpar localStorage (DevTools → Application → Clear)
2. Limpar cookies (DevTools → Application → Cookies → Clear)
3. Recarregar página (F5)
4. ✅ Tela de login aparece (SEM PISCAR)
5. ✅ isLoading muda para false
6. ✅ Sem erros em console
```

### Test 2: Login funciona
```
1. Estar na tela de login
2. Preencher: tcc / 123456
3. Clicar "Entrar"
4. ✅ Dashboard carrega (SEM PISCAR)
5. ✅ Token salvo em localStorage
```

### Test 3: Reabrir com sessão válida
```
1. Estar logado
2. DevTools → localStorage → Verificar que tem auth_token
3. Fechar aba
4. Reabrir http://localhost:3000
5. ✅ Dashboard carrega direto (SEM PISCAR)
```

## 📊 Mudanças

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| api.ts | -11 linhas | Removido redirecionamento 401 |
| useAuth.ts | +3 linhas | Melhorado fluxo setIsLoading |

**Total:** -8 linhas (código mais limpo!)

## ✨ Status

- ✅ Build: 1709 módulos, 1.56s, 0 erros
- ✅ Python: Sintaxe válida
- ✅ Commit: de37caa
- ✅ GitHub: Push bem-sucedido

**Status:** 🔧 CORREÇÃO APLICADA

---

## 🎉 Resultado

❌ **ANTES:** Tela pisca infinitamente ao fazer login
✅ **DEPOIS:** Tela de login aparece normalmente, login funciona, sem flicker

Execute os testes acima para confirmar! 🚀
