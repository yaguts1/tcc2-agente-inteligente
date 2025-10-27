# 🔧 AJUSTES NECESSÁRIOS - Guia Prático

**Prioridade**: Crítico → Importante → Desejável  
**Tempo total estimado**: ~2 horas para fase crítica

---

## 🔴 FASE 1: CRÍTICO (Fazer HOJE - ~35 min)

### 1. Adicionar `display_name` em `/api/auth/me`

**Arquivo**: `interface/api.py` (linhas ~130-145)

**Mudança**:
```python
@router.get("/auth/me", status_code=status.HTTP_200_OK)
async def api_me(request: Request) -> dict:
    user = request.cookies.get("session_user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated"})
    # try to include display_name when available
    try:
        u = obter_usuario_por_nome(DB_PATH, user)
        display = None if u is None else u.get("display_name")
    except Exception:
        display = None
    # IMPORTANTE: Retornar display_name também
    return {"username": user, "display_name": display}  # ← ADICIONAR display
```

**Impacto**: Frontend mostra nome completo em vez de apenas username

**Teste**:
```bash
curl -b session_user=admin http://127.0.0.1:8000/api/auth/me
# Esperado:
# {"username":"admin","display_name":null}  (ou nome se criado com display_name)
```

---

### 2. Implementar `/api/stats` (Endpoint Novo)

**Arquivo**: `interface/api.py` (adicionar ao final, antes de outros endpoints do frontend)

**Código a adicionar**:

```python
@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats() -> dict:
    """Retorna estatísticas do dashboard para o frontend.
    
    Retorna: activeAlerts, overdueAlerts, completedToday, totalPatients
    """
    try:
        # Buscar alertas da última semana
        all_alerts = selecionar_alertas_janela(DB_PATH, horas=168)  # 1 semana
        
        # Contar alertas abertos (pending)
        active_alerts = len([a for a in all_alerts if a.get("status") == "aberto"])
        
        # Contar alertas reconhecidos (acknowledged)
        acked_alerts = len([a for a in all_alerts if a.get("status") == "reconhecido"])
        
        # Contar alertas fechados (completed) de hoje
        from datetime import datetime, timedelta
        agora = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        completed_today = len([
            a for a in all_alerts 
            if a.get("status") == "fechado" and a.get("fim") is not None
            and datetime.fromisoformat(a.get("fim")[:19]) >= agora
        ])
        
        # Contar pacientes totais
        fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
        total_patients = len(fichas)
        
        # Calcular taxa de conclusão (fechados / (abertos + reconhecidos + fechados))
        total_relevant = active_alerts + acked_alerts + completed_today
        completion_rate = (
            (completed_today / total_relevant * 100) 
            if total_relevant > 0 else 0
        )
        
        return {
            "activeAlerts": active_alerts,
            "acknowledgedAlerts": acked_alerts,
            "completedToday": completed_today,
            "totalPatients": total_patients,
            "completionRate": round(completion_rate, 1)
        }
    except Exception as exc:
        logger.exception("stats_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "stats_error", "message": str(exc)}
        ) from exc
```

**Localização exata**: Adicione após a função `get_stats()` em `interface/api.py`, antes do endpoint `/pacientes`.

**Impacto**: Frontend não precisa mais calcular stats localmente

**Teste**:
```bash
curl http://127.0.0.1:8000/api/stats
# Esperado:
# {
#   "activeAlerts": 5,
#   "acknowledgedAlerts": 2,
#   "completedToday": 10,
#   "totalPatients": 15,
#   "completionRate": 66.7
# }
```

---

### 3. Atualizar Frontend para Usar `/api/stats`

**Arquivo**: `frontend/src/components/pages/DashboardPage.tsx` (ou análogo)

**Mudança**: 
```typescript
// ANTES: Calcula stats localmente
const stats = {
  activeAlerts: alerts.filter(a => a.status === 'pending').length,
  ...
}

// DEPOIS: Buscar do backend
const [stats, setStats] = useState(null);

useEffect(() => {
  const fetchStats = async () => {
    try {
      const data = await fetch('/api/stats').then(r => r.json());
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats', err);
    }
  };
  fetchStats();
}, []);
```

**Ou usar a função já existente em `api.ts`**:
```typescript
// Verificar se statsApi já existe em frontend/src/lib/api.ts
// Se sim, usar: const stats = await statsApi.getStats();
```

---

## 🟡 FASE 2: IMPORTANTE (Esta Semana - ~1h 30min)

### 4. Adicionar Filtros em `/api/frontend/alerts`

**Arquivo**: `interface/api.py` (função `frontend_alerts`, linha ~540)

**Mudança**:
```python
@router.get("/frontend/alerts", status_code=status.HTTP_200_OK)
async def frontend_alerts(
    horas: int | None = 24,
    # NOVOS PARÂMETROS:
    riskLevel: str | None = None,  # 'high', 'medium', 'low'
    status: str | None = None,      # 'pending', 'acknowledged', 'completed'
    room: str | None = None,        # Filtrar por quarto
    limit: int = 100,               # Paginação
    offset: int = 0
) -> list[dict]:
    """Return alerts in a shape convenient for the React frontend.
    
    Query params:
    - horas: int (último tempo em horas)
    - riskLevel: 'high'|'medium'|'low' - filtra por perfil
    - status: 'pending'|'acknowledged'|'completed'
    - room: string - filtra por quarto
    - limit: int - paginação
    - offset: int - paginação
    """
    raw_alerts = selecionar_alertas_janela(DB_PATH, horas)
    results: list[dict] = []
    
    for a in raw_alerts:
        paciente_id = a.get("paciente_id")
        inicio = a.get("inicio")
        janela_min = int(a.get("janela_min") or 0)
        perfil = str(a.get("perfil") or "medio")
        status_raw = str(a.get("status") or "aberto")

        ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
        patient_name = ficha.get("nome") if ficha else paciente_id
        cama_id = (ficha.get("cama_id") if ficha else None) or ""
        
        room = cama_id
        bed = ""
        if cama_id and "/" in cama_id:
            parts = [p.strip() for p in cama_id.split("/")]
            room = parts[0]
            if len(parts) > 1:
                bed = parts[1]

        # Mapear perfil para frontend
        risk_map = {"alto": "high", "medio": "medium", "baixo": "low"}
        risk_level = risk_map.get(perfil, "medium")

        status_map = {"aberto": "pending", "reconhecido": "acknowledged", "fechado": "completed"}
        status_val = status_map.get(status_raw, "pending")

        # APLICAR FILTROS
        if riskLevel and risk_level != riskLevel:
            continue
        if status and status_val != status:
            continue
        if room and not (room.lower().startswith(room.lower())):  # fuzzy match
            continue

        aid = f"{paciente_id}__{inicio}"
        
        # ... resto do código para montar resultado ...
        results.append({
            "id": aid,
            "patientName": patient_name,
            "room": room,
            "bed": bed,
            "lastRepositioning": ...,
            "nextRepositioning": ...,
            "riskLevel": risk_level,
            "status": status_val,
        })
    
    # APLICAR PAGINAÇÃO
    return results[offset:offset+limit]
```

**Teste**:
```bash
# Apenas alertas altos e pending
curl "http://127.0.0.1:8000/api/frontend/alerts?riskLevel=high&status=pending"

# Apenas quarto 201A
curl "http://127.0.0.1:8000/api/frontend/alerts?room=201A"

# Com paginação
curl "http://127.0.0.1:8000/api/frontend/alerts?limit=10&offset=0"
```

---

### 5. Rate Limiting em Endpoints de Auth

**Arquivo**: `interface/api.py` (nova função)

**Adicionar**:
```python
# Adicionar novo rate limiter para auth
_auth_attempts = {}  # {ip: [(timestamp, count)]}
_auth_lock = asyncio.Lock()

async def _check_auth_rate_limit(request: Request) -> None:
    """Rate limiting específico para login/register (5 tentativas por minuto)."""
    client_ip = request.client.host if request.client else "unknown"
    agora = time.time()
    
    async with _auth_lock:
        # Limpar tentativas antigas (> 60s)
        if client_ip in _auth_attempts:
            _auth_attempts[client_ip] = [
                (ts, count) for ts, count in _auth_attempts[client_ip]
                if agora - ts < 60
            ]
        
        # Contar tentativas no último minuto
        attempts = sum(count for ts, count in _auth_attempts.get(client_ip, []))
        
        if attempts >= 5:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "rate_limited", "message": "Muitas tentativas. Tente novamente em 1 minuto."}
            )
        
        # Registrar nova tentativa
        if client_ip not in _auth_attempts:
            _auth_attempts[client_ip] = []
        _auth_attempts[client_ip].append((agora, 1))

# Adicionar dependency a endpoints de auth
@router.post("/auth/login", status_code=status.HTTP_200_OK)
async def api_login(request: Request, _: None = Depends(_check_auth_rate_limit)) -> dict:
    # ... resto do código ...
```

---

### 6. Adicionar Headers de Segurança

**Arquivo**: `interface/web.py` (na inicialização da app FastAPI)

**Adicionar**:
```python
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

# Na app FastAPI:
app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Adicionar origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🟢 FASE 3: DESEJÁVEL (Sprint Seguinte - ~2h)

### 7. Implementar Roles e Permissions Básicas

**Opção 1: Simples (30 min)**
- Adicionar coluna `role` em tabela `users` (admin, enfermeira, cuidador)
- Retornar role em `/api/auth/me`
- Adicionar middleware simples que verifica role em endpoints críticos

**Opção 2: Completa (2h)**
- Criar tabelas: `roles` e `permissions`
- Implementar middleware de autorização
- Adicionar checks em endpoints (ex: só admin pode deletar pacientes)

---

### 8. Testes E2E Frontend-Backend

**Usar**: Playwright ou Cypress

```typescript
// test-criar-paciente.e2e.ts
test('criar paciente completo', async ({ page }) => {
  // 1. Login
  await page.goto('http://localhost:5173/login');
  await page.fill('input[name=username]', 'testuser');
  await page.fill('input[name=password]', 'password123');
  await page.click('button:has-text("Entrar")');
  
  // 2. Navegar para pacientes
  await page.goto('http://localhost:5173/pacientes');
  
  // 3. Criar novo paciente
  await page.click('button:has-text("Novo Paciente")');
  await page.fill('input[name=name]', 'João Silva');
  await page.fill('input[name=room]', '201A');
  await page.fill('input[name=bed]', 'Leito 1');
  await page.selectOption('select[name=riskLevel]', 'high');
  await page.click('button:has-text("Salvar")');
  
  // 4. Verificar sucesso
  await expect(page.locator('text=João Silva')).toBeVisible();
  
  // 5. Verificar no BD (via API)
  const resp = await page.request.get('/api/pacientes');
  const patients = await resp.json();
  expect(patients.some(p => p.name === 'João Silva')).toBe(true);
});
```

---

## 📋 CHECKLIST DE IMPLEMENTAÇÃO

### Fase 1 (Hoje - ~35 min)
- [ ] Adicionar `display_name` em `/api/auth/me`
- [ ] Implementar `/api/stats`
- [ ] Atualizar frontend para usar `/api/stats`
- [ ] Rodar testes: `pytest -v`
- [ ] Testar manualmente no navegador

### Fase 2 (Esta Semana - ~1h 30min)
- [ ] Adicionar filtros em `/api/frontend/alerts`
- [ ] Rate limiting em auth endpoints
- [ ] Security headers middleware
- [ ] Testar todos os novos endpoints
- [ ] Documentar mudanças em API_GAPS.md

### Fase 3 (Sprint Seguinte - ~2h)
- [ ] Implementar roles/permissions
- [ ] Criar testes E2E
- [ ] Deploy em staging
- [ ] Teste de carga

---

## 🧪 VALIDAÇÃO RÁPIDA

### Depois de cada mudança, rodar:

```bash
# 1. Backend tests
pytest -v

# 2. Frontend build
npm run build

# 3. Verificar tipos TypeScript
npm run type-check

# 4. Testar endpoints manualmente
curl http://127.0.0.1:8000/api/stats
curl http://127.0.0.1:8000/api/pacientes

# 5. Verificar no navegador (dev tools → Network)
# Abrir http://localhost:5173/dashboard
# Verificar que /api/stats é chamado
# Verificar que stats aparecem na tela
```

---

## 🚨 PROBLEMAS COMUNS

### Problema: "ModuleNotFoundError" após mudança em dao.py
**Solução**: Reiniciar servidor FastAPI
```bash
# Terminal Python
# Ctrl+C para parar
# python -m uvicorn interface.web:app --reload
```

### Problema: Frontend mostra erro 500 em /api/stats
**Solução**: Verificar logs do servidor
```bash
# Terminal Python mostrará o erro exato
# Copiar stack trace e revisar código em interface/api.py
```

### Problema: Testes falham após mudança
**Solução**: 
```bash
pytest -xvs tests/test_api.py::test_nome_do_teste
# -x: para no primeiro erro
# -v: verbose
# -s: mostra prints
```

---

## 📞 SUPORTE

Se encontrar problemas:
1. Verificar logs do servidor (terminal Python)
2. Verificar console do navegador (F12 → Console)
3. Rodar testes isolados: `pytest -xvs tests/test_específico.py`
4. Verificar chamadas HTTP: `curl -v http://...`

---

**Tempo total estimado**: 
- Fase 1 (Crítica): 35 minutos
- Fase 2 (Importante): 1h 30min
- Fase 3 (Desejável): 2 horas

**Total**: ~4 horas para implementar todas as melhorias.

**Recomendação**: Fazer Fase 1 hoje, Fase 2 esta semana, Fase 3 no próximo sprint.
