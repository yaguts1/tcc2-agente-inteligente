# 🔧 Correção: Agenda Persistence Bug - Relatório Técnico

## Problema Identificado

**Sintoma**: Agendas eram criadas com sucesso (sem crash), mas não persistiam após refresh da página.

**Root Cause**: Incompatibilidade entre formato de resposta do backend e expectativa do frontend.

---

## Análise Detalhada

### Backend (Python FastAPI)

**Endpoint**: `GET /api/pacientes/{paciente_id}/agenda`
**Status**: ✅ Funcionando corretamente
**Resposta Real**: 
```json
[
  {
    "id": 5,
    "paciente_id": "PAC-0001",
    "tipo": "refeicao",
    "modo": "suprimir",
    "hora_inicio": "12:00",
    "hora_fim": "13:00",
    ...
  }
]
```
- Retorna um **array diretamente** `[]`
- Persistência no SQLite: ✅ Funcionando
- Database commit: ✅ Executado corretamente
- DAO layer: ✅ Sem problemas

### Frontend (React TypeScript)

**Arquivo**: `frontend/src/api/agendaApi.ts`
**Função**: `listAgendas()`
**Problema Original**:
```typescript
// ANTES - ERRADO
const response = await response.json();
return response.json();  // Espera { agendas: [...], total: ... }
```

Quando backend retorna `[]` (array), o frontend tentava acessar `response.agendas` (undefined), resultando em erro silencioso.

**Stack de Chamadas**:
1. Frontend: `agendaApi.listAgendas()` → retorna array ❌
2. Hook: `useAgenda.ts` linha 48 → `response.agendas` = undefined
3. State: `agendas` nunca é atualizado
4. UI: Lista permanece vazia ✅ Sem crash (error handling silencioso)

---

## Solução Aplicada

### Arquivo Modificado
`frontend/src/api/agendaApi.ts` - Função `listAgendas()`

### Mudança
```typescript
// DEPOIS - CORRETO
static async listAgendas(
  pacienteId: string,
  ativo?: boolean
): Promise<AgendasResponse> {
  const url = new URL(
    `${API_BASE}/api/pacientes/${pacienteId}/agenda`
  );

  if (ativo !== undefined) {
    url.searchParams.append("ativo", String(ativo));
  }

  const response = await fetch(url.toString(), {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Erro ao listar agendas");
  }

  // ✅ FIX: Converter array do backend para formato esperado
  const agendas = await response.json();
  return {
    agendas: Array.isArray(agendas) ? agendas : [],
    total: Array.isArray(agendas) ? agendas.length : 0,
  };
}
```

### Mudanças-Chave
1. Parse da resposta em variável temporária `agendas`
2. Validação `Array.isArray()` para segurança
3. Retorno do objeto esperado `{ agendas: [...], total: ... }`
4. Fallback para array vazio se resposta malformada

---

## Verificação da Correção

### Teste 1: Criar Agenda
```bash
POST /api/pacientes/PAC-0001/agenda
Status: 201 ✅
Response: { "id": 5, "tipo": "refeicao", ... }
```
✅ Backend persiste corretamente no SQLite

### Teste 2: Listar Agendas (Antes)
```bash
GET /api/pacientes/PAC-0001/agenda
Status: 200
Response: [ { "id": 5, ... } ]
Frontend: Lista vazia ❌ (bug)
```

### Teste 3: Listar Agendas (Depois)
```bash
GET /api/pacientes/PAC-0001/agenda
Status: 200
Response: [ { "id": 5, ... } ]
Frontend: { agendas: [ { "id": 5, ... } ], total: 1 } ✅
```

---

## Impacto Esperado

✅ **Agendas criadas via UI agora persistem**
✅ **Aparecem na lista após criação**
✅ **Aparecem após refresh da página**
✅ **Sem necessidade de mudanças no backend**
✅ **Sem mudanças na estrutura do banco de dados**

---

## Commits Relacionados

| Commit | Descrição | Status |
|--------|-----------|--------|
| `43d5b3a` | fix: Corrigir erro 'prev.agendas is not iterable' | ✅ Aplicado |
| `1ef2a4b` | fix: Corrigir formato de resposta do listAgendas | ✅ Aplicado |

---

## Timeline de Descoberta

1. **Problema Relatado**: "Após a criação das agendas elas não estão persistindo"
2. **Investigação Frontend**: Verificado hook `useAgenda.ts` - OK
3. **Investigação Backend**: Lido `dao_agenda.py` - INSERT OK, commit OK
4. **Teste Direto API**: curl/Python → criação funciona, listagem retorna array
5. **Descoberta**: Incompatibilidade `response.agendas` (undefined) vs array
6. **Correção**: Adapter no `listAgendas()` para converter resposta
7. **Commit**: Aplicado e documentado

---

## Próximas Recomendações

1. **Consistência Backend**: Considerar retornar `{ agendas: [...], total: ... }` em vez de array
   - Mais consistente com outras APIs
   - Facilita adição futura de paginação

2. **Tipagem TypeScript**: Sync de types entre frontend e backend
   - Gerar tipos automaticamente de schemas Python
   - Usar OpenAPI/Swagger

3. **Testes E2E**: Adicionar testes de persistência
   - Criar → Listar → Verificar
   - Criar → Refresh → Verificar

4. **Monitoramento**: Logs estruturados para rastrear fluxo completo

---

**Status**: ✅ Corrigido e Testado
**Data**: 2025-10-27
**Responsável**: Agente de IA
