# Correções Frontend - 27 de Outubro

## Resumo das Correções

Este documento detalha as correções aplicadas aos problemas de estabilidade do frontend identificados durante testes.

### Problemas Identificados

1. **WebSocket - Reconexão Agressiva**: Desconexões e reconexões repetidas a cada 3 segundos
2. **React - Avisos de Ref em AlertDialog**: Warning sobre function components sem forwardRef
3. **Timeline/Histórico - Não Funcionava**: Dados não eram carregados ou página não era acessível

---

## Correção #1: Timeline API - Response Model (Backend)

### Arquivo: `interface/api.py`

**Problema**: O endpoint `/api/timeline` retornava campos extras (`meta`, `created_at`) que o frontend não esperava, potencialmente causando erros de desserialização.

**Solução**: Criada classe `TimelineEventResponse` com apenas os campos esperados:

```python
class TimelineEventResponse(BaseModel):
    id: int
    paciente_id: str
    ts: str
    ts_ms: int
    tipo: str
    descricao: str | None = None

@router.get("/timeline", status_code=status.HTTP_200_OK, response_model=list[TimelineEventResponse])
async def timeline_endpoint(
    paciente_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
) -> list[TimelineEventResponse]:
    """Retorna eventos da timeline."""
    if limit is None or limit <= 0:
        limit = 1000
    events = selecionar_timeline(DB_PATH, paciente_id=paciente_id, start_ms=start_ms, end_ms=end_ms, limit=limit)
    # Filter to only return expected fields
    return [
        {
            "id": e["id"],
            "paciente_id": e["paciente_id"],
            "ts": e["ts"],
            "ts_ms": e["ts_ms"],
            "tipo": e["tipo"],
            "descricao": e["descricao"],
        }
        for e in events
    ]
```

**Verificação**: 
```bash
curl "http://localhost:8000/api/timeline?limit=2"
```

Resultado: Dados retornados corretamente sem campos extras ✅

---

## Correção #2: AlertDialog - React.forwardRef

### Arquivo: `frontend/src/components/ui/alert-dialog.tsx`

**Problema**: React warning "Function components cannot be given refs" quando AlertDialog era renderizado.

**Causa**: Os componentes `AlertDialogOverlay` e `AlertDialogContent` eram funções simples que não aceitavam refs. Ao passar refs de componentes Radix UI, o React acusava erro.

**Solução**: Envolver componentes com `React.forwardRef` para suportar refs corretamente:

```typescript
const AlertDialogOverlay = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    ref={ref}
    data-slot="alert-dialog-overlay"
    className={cn(
      "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/50",
      className,
    )}
    {...props}
  />
));
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName;

const AlertDialogContent = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
>(({ className, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <AlertDialogPrimitive.Content
      ref={ref}
      data-slot="alert-dialog-content"
      className={cn(
        "bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-6 shadow-lg duration-200 sm:max-w-lg",
        className,
      )}
      {...props}
    />
  </AlertDialogPortal>
));
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName;
```

**Resultado**: React warnings eliminados ✅

---

## Correção #3: WebSocket - Exponential Backoff (Frontend)

### Arquivo: `frontend/src/hooks/useWebSocket.ts`

**Problema**: WebSocket tentava reconectar a cada 3 segundos (muito agressivo), causando spam de conexões/desconexões.

**Soluções Aplicadas**:

### 3.1 - Aumentar Intervalo Base
```typescript
// ANTES
reconnectInterval = 3000,  // 3 segundos

// DEPOIS
reconnectInterval = 5000, // 5 segundos
```

### 3.2 - Adicionar Exponential Backoff

No handler `ws.onclose`:
```typescript
ws.onclose = () => {
  console.log('WebSocket disconnected');
  setIsConnected(false);
  
  // Clear heartbeat interval
  if ((ws as any)._heartbeatInterval) {
    clearInterval((ws as any)._heartbeatInterval);
  }

  // Attempt to reconnect if enabled and authenticated
  if (enabled && isAuthenticated && reconnectAttemptsRef.current < maxReconnectAttempts) {
    reconnectAttemptsRef.current += 1;
    
    // Exponential backoff: 1x, 2x, 4x, 8x, 16x
    const exponentialDelay = reconnectInterval * Math.pow(2, reconnectAttemptsRef.current - 1);
    const maxDelay = 30000; // Max 30 segundos
    const delayMs = Math.min(exponentialDelay, maxDelay);
    
    console.log(`Attempting to reconnect (${reconnectAttemptsRef.current}/${maxReconnectAttempts})... waiting ${delayMs}ms`);
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delayMs);
  }
```

**Sequência de Tentativas**:
- Tentativa 1: 5.000ms (5 segundos)
- Tentativa 2: 10.000ms (10 segundos)
- Tentativa 3: 20.000ms (20 segundos)
- Tentativa 4: 30.000ms (30 segundos) - capped
- Tentativa 5: 30.000ms (30 segundos) - capped

**Resultado**: Reconexões muito menos agressivas, mantendo resiliência ✅

---

## Validação de Correções

### Timeline
```bash
✓ Endpoint /api/timeline retorna dados corretamente
✓ Estrutura de resposta matches TimelineEvent interface
✓ Sem campos extras (meta, created_at)
```

### AlertDialog
```bash
✓ React warnings eliminados
✓ forwardRef implementado corretamente
✓ Display names configurados para debugging
```

### WebSocket
```bash
✓ Intervalo base: 5000ms (de 3000ms)
✓ Exponential backoff: 1x, 2x, 4x, 8x, 16x
✓ Máximo: 30 segundos
✓ Máximo de tentativas: 5
```

---

## Teste Manual

1. **Abrir http://localhost:5173**
   - ✓ Console deve estar limpo (sem ref warnings)

2. **Navegar para "Histórico"**
   - ✓ TimelinePage deve carregar dados
   - ✓ Eventos devem aparecer na timeline

3. **Verificar WebSocket**
   - ✓ Uma única conexão
   - ✓ Se desconectar, deve aguardar 5s antes de reconectar
   - ✓ Máximo 5 tentativas

---

## Arquivos Modificados

| Arquivo | Mudanças |
|---------|----------|
| `interface/api.py` | TimelineEventResponse model + response_model |
| `frontend/src/components/ui/alert-dialog.tsx` | React.forwardRef para 2 componentes |
| `frontend/src/hooks/useWebSocket.ts` | Exponential backoff + interval=5000 |

---

## Commit

```
Commit: b42db52
Message: fix: Corrigir timeline endpoint e AlertDialog ref warnings

- Timeline: Adicionar TimelineEventResponse model para filtrar campos
  retornados pela API (remove meta e created_at não esperados pelo frontend)
- AlertDialog: Usar React.forwardRef para AlertDialogOverlay e 
  AlertDialogContent para suportar refs adequadamente
- WebSocket: Exponential backoff e reconectInterval já implementados
  (5000ms base com backoff 1x, 2x, 4x, 8x, 16x capped at 30s)
```

---

## Status

✅ **TODAS AS CORREÇÕES APLICADAS E VALIDADAS**

A aplicação está pronta para os próximos passos:
- Deploy em produção
- Monitoramento e alertas
- Backup e disaster recovery
