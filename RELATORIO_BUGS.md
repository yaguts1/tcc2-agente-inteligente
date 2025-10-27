# 🐛 RELATÓRIO DE BUGS E STATUS

**Data**: 26 de Outubro de 2025  
**Total de Issues Identificadas**: 12  
**Resolvidas**: 1 ✅  
**Planejadas**: 11  

---

## 🔴 CRÍTICA - BUG RESOLVIDO

### 1. ❌→✅ POST /api/pacientes retorna 405 "Method Not Allowed"

**Status**: 🟢 **RESOLVIDO**  
**Data de Resolução**: 26 de Outubro de 2025  
**Severidade**: 🔴 CRÍTICA  
**Impacto**: Frontend não consegue criar pacientes

#### Detalhes
- **Sintoma**: Ao clicar "Novo Paciente" e tentar salvar, retorna HTTP 405
- **Causa Raiz**: Backend tinha apenas `GET /api/pacientes`, não tinha `POST`, `PATCH`, `DELETE`
- **Contexto**: Arquitetura separava HTML forms (`/pacientes/salvar`) de JSON API (`/api/pacientes`)

#### Solução Implementada
```python
# interface/api.py
✅ POST   /api/pacientes           (criar paciente)
✅ GET    /api/pacientes/{id}      (ler um paciente)  
✅ PATCH  /api/pacientes/{id}      (atualizar paciente)
✅ DELETE /api/pacientes/{id}      (deletar paciente)

# interface/dao.py
✅ remover_paciente()              (DAO helper para cleanup)

# Modelos Pydantic
✅ FrontendCreatePatient
✅ FrontendPatient
✅ FrontendUpdatePatient
```

#### Mapeamento Frontend ↔ Backend
```
Frontend                Backend
─────────────────────────────────
name             ←→  nome
room + bed       ←→  cama_id (com split/join)
riskLevel        ←→  perfil (high/medium/low ← alto/médio/baixo)
createdAt        ←→  created_at
updatedAt        ←→  updated_at
```

#### Testes Validados
```bash
✅ 67 testes passando
✅ Cobertura: API, DAO, Engine, Multi-patient
✅ Sem regressões
```

#### Verificação Manual
```bash
# Criar paciente
curl -X POST http://localhost:8000/api/pacientes \
  -H 'Content-Type: application/json' \
  -d '{"name":"Maria","room":"201A","bed":"Leito 1","riskLevel":"high"}'
# Resultado: 201 Created

# Listar
curl http://localhost:8000/api/pacientes
# Resultado: 200 OK com lista de pacientes

# Obter um
curl http://localhost:8000/api/pacientes/PAC-0001
# Resultado: 200 OK com detalhe

# Atualizar
curl -X PATCH http://localhost:8000/api/pacientes/PAC-0001 \
  -H 'Content-Type: application/json' \
  -d '{"riskLevel":"low"}'
# Resultado: 200 OK

# Deletar
curl -X DELETE http://localhost:8000/api/pacientes/PAC-0001
# Resultado: 204 No Content
```

---

## 🟡 PLANEJADA - LACUNAS A IMPLEMENTAR

### 2. ❌ Display Name Ausente em `/api/auth/me`

**Status**: 🟡 **PLANEJADA PARA HOJE**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: ALTA (Fase 1)  
**Tempo Estimado**: 5 minutos  
**Arquivo**: `interface/api.py` (linhas ~130-145)

#### Problema
```json
// Retorno ATUAL
{ "username": "alice" }

// Retorno ESPERADO
{ "username": "alice", "display_name": "Alice Oliveira" }
```

#### Impacto
- Frontend não pode exibir nome completo do usuário
- Apenas username aparece em toda UI
- Logout mostra "alice" em vez de "Alice Oliveira"

#### Solução
Modificar endpoint para retornar `display_name`:
```python
return {"username": user, "display_name": display}  # ← ADD THIS
```

#### Teste
```bash
curl -b session_user=admin http://127.0.0.1:8000/api/auth/me
# Esperado:
# {"username":"admin","display_name":"Admin User"}
```

---

### 3. ❌ Endpoint `/api/stats` Não Implementado

**Status**: 🟡 **PLANEJADA PARA HOJE**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: ALTA (Fase 1)  
**Tempo Estimado**: 15 minutos  
**Arquivo**: `interface/api.py`

#### Problema
Frontend calcula estatísticas localmente:
- Deve baixar TODOS os alertas/eventos
- Filtra no JavaScript client-side
- Ineficiente para grandes volumes
- Sem cache no servidor

#### Impacto
- Latência alta no dashboard
- Carga desnecessária na rede
- Impossível de escalar

#### Solução
Novo endpoint:
```python
@router.get("/stats")
async def get_stats() -> dict:
    # Retorna estatísticas pré-calculadas no servidor
    return {
        "activeAlerts": int,
        "acknowledgedAlerts": int,
        "completedToday": int,
        "totalPatients": int,
        "completionRate": float
    }
```

#### Teste
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

### 4. ❌ Frontend Não Usa `/api/stats`

**Status**: 🟡 **PLANEJADA PARA HOJE**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: ALTA (Fase 1)  
**Tempo Estimado**: 15 minutos  
**Arquivo**: `frontend/src/components/pages/DashboardPage.tsx`

#### Problema
Após implementar `/api/stats`, frontend não o consome

#### Solução
Atualizar componente Dashboard:
```typescript
// Antes
const stats = useMemo(() => ({
  activeAlerts: alerts.filter(...).length,
  ...
}), [alerts]);

// Depois
const [stats, setStats] = useState(null);
useEffect(() => {
  const fetch = async () => {
    const data = await fetch('/api/stats').then(r => r.json());
    setStats(data);
  };
  fetch();
}, []);
```

---

### 5. ⚠️ Filtros Limitados em `/api/frontend/alerts`

**Status**: 🟡 **PLANEJADA ESTA SEMANA**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: MÉDIA (Fase 2)  
**Tempo Estimado**: 20 minutos  
**Arquivo**: `interface/api.py` (função `frontend_alerts`)

#### Problema
Apenas suportado:
```http
GET /api/frontend/alerts?horas=24
```

Frontend quer:
```http
GET /api/frontend/alerts?riskLevel=high&status=pending&room=201A&limit=20&offset=0
```

#### Impacto
- Sem filtros no backend, deve filtrar no client (menos eficiente)
- Sem paginação, carrega tudo sempre
- Sem ordenação customizada

#### Solução
Adicionar parâmetros de filtro:
```python
@router.get("/frontend/alerts")
async def frontend_alerts(
    horas: int | None = 24,
    riskLevel: str | None = None,  # high, medium, low
    status: str | None = None,      # pending, acknowledged, completed
    room: str | None = None,        # filtro por quarto
    limit: int = 100,
    offset: int = 0
) -> list[dict]:
    # Filtrar e retornar
```

---

### 6. ⚠️ Sem Rate Limiting em Auth Endpoints

**Status**: 🟡 **PLANEJADA ESTA SEMANA**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: MÉDIA (Fase 2)  
**Tempo Estimado**: 20 minutos  
**Arquivo**: `interface/api.py`

#### Problema
Endpoints de autenticação sem proteção contra força bruta:
- `POST /api/auth/login`
- `POST /api/auth/register`

#### Impacto
- Vulnerável a ataque de força bruta
- Alguém pode tentar múltiplas senhas/usernames
- Sem limite de tentativas por IP

#### Solução
Token bucket rate limiter específico para auth:
```python
# Máximo 5 tentativas por minuto por IP
@router.post("/auth/login")
async def api_login(request: Request, _: None = Depends(_check_auth_rate_limit)):
    # ...
```

---

### 7. ❌ Sem Security Headers

**Status**: 🟡 **PLANEJADA ESTA SEMANA**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: MÉDIA (Fase 2)  
**Tempo Estimado**: 10 minutos  
**Arquivo**: `interface/web.py`

#### Problema
Faltam headers HTTP de segurança:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: ...
```

#### Impacto
- Vulnerável a MIME type sniffing
- Pode ser embarcado em iframe (clickjacking)
- Menos proteção contra XSS

#### Solução
Adicionar middleware de segurança:
```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### 8. ❌ Sem System de Roles/Permissions

**Status**: 🟡 **PLANEJADA ESTA SEMANA**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: MÉDIA (Fase 2)  
**Tempo Estimado**: 30 minutos  
**Arquivo**: `interface/api.py`, `interface/dao.py`

#### Problema
Todos os usuários têm acesso total a tudo:
- Sem roles (admin, enfermeira, cuidador)
- Sem permissions granulares
- Cuidador pode deletar pacientes
- Visualizador pode editar alertas

#### Impacto
- Segurança: Falta de controle de acesso
- Conformidade: Não atende requisitos HIPAA/LGPD
- Operacional: Sem auditoria de permissões

#### Solução
Implementar roles simples:
```python
ROLES = {
    "admin": ["*"],  # todas as operações
    "enfermeira": ["read", "write", "ack", "complete"],
    "cuidador": ["read", "ack", "complete"],
    "viewer": ["read"]
}

# Adicionar middleware
@router.get("/pacientes/{id}")
async def get_patient(
    id: str,
    request: Request,
    _: None = Depends(require_permission("read"))
):
    # ...
```

---

### 9. ⚠️ Sem Testes E2E (Frontend-Backend)

**Status**: 🔵 **PLANEJADA PRÓXIMO SPRINT**  
**Severidade**: 🟡 MÉDIA  
**Prioridade**: BAIXA (Fase 3)  
**Tempo Estimado**: 2 horas  
**Arquivo**: `tests/e2e/` (novo diretório)

#### Problema
Apenas testes unitários backend (67 testes)
Sem testes end-to-end que validam fluxos:
- Login → Create Patient → Generate Alert → ACK → Complete

#### Impacto
- Risco de regressões não detectadas
- Integração frontend-backend não totalmente validada
- Difícil validar em staging sem testes

#### Solução
Implementar testes E2E com Playwright:
```typescript
test('fluxo completo: login → criar paciente → validar', async ({ page }) => {
  // 1. Login
  // 2. Criar paciente
  // 3. Validar no BD via API
  // 4. Verificar na UI
});
```

---

### 10. ⚠️ Sem WebSocket Real-time

**Status**: 🔵 **PLANEJADA PRÓXIMO SPRINT**  
**Severidade**: 🟢 BAIXA  
**Prioridade**: BAIXA (Fase 3)  
**Tempo Estimado**: 6 horas  
**Arquivo**: `interface/api.py`, `frontend/src/hooks/useAlerts.ts`

#### Problema
Sistema usa polling a cada 30 segundos
- Latência: até 30s para ver novo alerta
- Carga: múltiplos clientes fazem requisições desnecessárias
- Escalabilidade: não escala bem

#### Impacto
- UX: Alertas aparecem com delay até 30s
- Performance: Servidor recebe 2 requisições/min por usuário (com 100 users = 200 req/min)
- Experiência clínica: Pode comprometer tempo de resposta crítico

#### Solução
Implementar WebSocket:
```python
# Backend (FastAPI)
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    # Conectar
    # Enviar alertas novos em tempo real
    # Handle desconexão

# Frontend (React)
useEffect(() => {
    const ws = new WebSocket('ws://..../ws/alerts');
    ws.onmessage = (event) => {
        const alert = JSON.parse(event.data);
        setAlerts(prev => [alert, ...prev]);
    };
}, []);
```

---

### 11. ❌ Sem Batch Operations

**Status**: 🔵 **PLANEJADA PRÓXIMO SPRINT**  
**Severidade**: 🟢 BAIXA  
**Prioridade**: BAIXA (Fase 3)  
**Tempo Estimado**: 2 horas  
**Arquivo**: `interface/api.py`

#### Problema
Reconhecer/completar múltiplos alertas requer múltiplas requisições:
```
Para 10 alertas:
POST /api/frontend/alerts/1/acknowledge
POST /api/frontend/alerts/2/acknowledge
... (10 requisições)
```

#### Impacto
- UX lenta para operações em lote
- Rede: 10 requisições em vez de 1
- Backend: processamento em série

#### Solução
Endpoints de batch:
```python
POST /api/frontend/alerts/batch/acknowledge
Body: { "alertIds": ["id1", "id2", "id3"] }

POST /api/frontend/alerts/batch/complete
Body: { "alertIds": ["id1", "id2", "id3"] }
```

---

### 12. ⚠️ Sem Relatórios/Exportação

**Status**: 🔵 **PLANEJADA PRÓXIMO SPRINT**  
**Severidade**: 🟢 BAIXA  
**Prioridade**: BAIXA (Fase 3)  
**Tempo Estimado**: 4 horas  
**Arquivo**: `interface/api.py` (novo módulo `reports`)

#### Problema
Sem forma de exportar dados:
- Relatórios PDF
- CSVs para análise
- Auditoria

#### Impacto
- Compliance: Difícil gerar audit trails
- Análise: Sem dados exportáveis
- Relatórios: Manual ou inexistente

#### Solução
Endpoints de relatório:
```python
GET /api/reports/alerts?startDate=...&endDate=...&format=pdf
GET /api/reports/patients?format=csv
GET /api/reports/timeline?pacienteId=...&format=pdf
```

---

## 📊 RESUMO DE STATUS

| # | Descrição | Status | Sev | Fase | Tempo |
|---|-----------|--------|-----|------|-------|
| 1 | POST /api/pacientes (405) | ✅ DONE | 🔴 | 0 | - |
| 2 | Display name em /auth/me | 🟡 TODO | 🟡 | 1 | 5m |
| 3 | Endpoint /api/stats | 🟡 TODO | 🟡 | 1 | 15m |
| 4 | Frontend consome /api/stats | 🟡 TODO | 🟡 | 1 | 15m |
| 5 | Filtros em alertas | 🟡 TODO | 🟡 | 2 | 20m |
| 6 | Rate limiting auth | 🟡 TODO | 🟡 | 2 | 20m |
| 7 | Security headers | 🟡 TODO | 🟡 | 2 | 10m |
| 8 | Roles/permissions | 🟡 TODO | 🟡 | 2 | 30m |
| 9 | Testes E2E | 🔵 TODO | 🟢 | 3 | 2h |
| 10 | WebSocket real-time | 🔵 TODO | 🟢 | 3 | 6h |
| 11 | Batch operations | 🔵 TODO | 🟢 | 3 | 2h |
| 12 | Relatórios/Exportação | 🔵 TODO | 🟢 | 3 | 4h |

**Legenda**:
- ✅ = Resolvido
- 🟡 = Planejado (semanas)
- 🔵 = Futuro (sprints)
- 🔴 = Crítica
- 🟡 = Média
- 🟢 = Baixa

---

## 🎯 PRÓXIMOS PASSOS

### HOJE (30-40 min)
1. Implementar: Display name (5m)
2. Implementar: /api/stats (15m)
3. Atualizar: Frontend consome stats (15m)
4. Testar: pytest + navegador (5m)

### ESTA SEMANA (1h 30min)
1. Implementar: Filtros (20m)
2. Implementar: Rate limiting (20m)
3. Implementar: Security headers (10m)
4. Implementar: Roles básicas (30m)
5. Testar: E2E básico (30m)

### PRÓXIMO SPRINT (12h)
1. Implementar: WebSocket (6h)
2. Implementar: Batch operations (2h)
3. Implementar: Relatórios (4h)
4. Testar: Carga + stress

---

**Relatório preparado**: 26 de Outubro de 2025  
**Próxima revisão**: Após implementação de Fase 1

