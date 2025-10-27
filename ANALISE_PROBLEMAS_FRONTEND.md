# 🔧 ANÁLISE DE PROBLEMAS - Frontend Issues

**Data**: 27 de Outubro de 2025 - 19h30  
**Problemas Identificados**: 3 principais  
**Status**: Em investigação  

---

## 🚨 Problema #1: WebSocket Reconectando Repetidamente

### Sintoma
```
WebSocket connected
WebSocket disconnected
Attempting to reconnect (1/5)...
WebSocket connected
[repete continuamente]
```

### Causa Raiz
No arquivo `useWebSocket.ts`, o hook está configurado com:
- `reconnectInterval = 3000` (3 segundos)
- Está tentando reconectar mesmo quando deveria estar conectado
- O problema é que o intervalo de **heartbeat é de 30 segundos**, mas o timeout de reconexão é de **3 segundos**

### Arquivo Afetado
`frontend/src/hooks/useWebSocket.ts`

### Linha Problemática
```typescript
reconnectInterval = 3000,  // Muito agressivo
maxReconnectAttempts = 5,
```

### Solução
1. Aumentar `reconnectInterval` para 10000 (10 segundos)
2. Adicionar exponential backoff
3. Adicionar logging melhorado para diagnosticar desconexões

---

## ⚠️ Problema #2: React Ref Warning em AlertDialog

### Sintoma
```
Warning: Function components cannot be given refs. 
Attempts to access this ref will fail. 
Did you mean to use React.forwardRef()?
```

### Causa Raiz
O componente `AlertDialogOverlay` está tentando passar `ref` para um componente function sem usar `React.forwardRef()`.

### Arquivo Afetado
`frontend/src/components/ui/alert-dialog.tsx`

### Código Problemático
```typescript
function AlertDialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof AlertDialogPrimitive.Overlay>) {
  return (
    <AlertDialogPrimitive.Overlay
      data-slot="alert-dialog-overlay"
      className={cn(...)}
      {...props}  // ← Props incluem ref que não pode ser passada
    />
  );
}
```

### Solução
Usar `React.forwardRef()` para permitir refs:
```typescript
const AlertDialogOverlay = React.forwardRef(function AlertDialogOverlay({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Overlay
      ref={ref}
      data-slot="alert-dialog-overlay"
      className={cn(...)}
      {...props}
    />
  );
});
```

---

## 📊 Problema #3: Histórico (Timeline) Não Funcionando

### Sintoma
Menu mostra opção "Histórico" mas não há página implementada ou não funciona corretamente.

### Causa Raiz
Navegação está configurada em `AppLayout.tsx` com:
```typescript
{ id: 'timeline', name: 'Histórico', icon: History },
```

Mas provavelmente não há uma página de timeline/histórico implementada ou há problema com a navegação.

### Arquivo Afetado
- `frontend/src/components/layout/AppLayout.tsx`
- Provavelmente falta componente de timeline

### Solução
1. Verificar se existe componente de timeline
2. Implementar se não existir
3. Configurar navegação corretamente em `App.tsx`

---

## 📋 PLANO DE CORREÇÃO

### Tarefa 1: Corrigir WebSocket Reconexão (15 min)
```
1. Modificar useWebSocket.ts
2. Aumentar reconnectInterval
3. Adicionar exponential backoff
4. Testar reconexão
5. Commit
```

### Tarefa 2: Corrigir AlertDialog Ref Warning (10 min)
```
1. Adicionar React.forwardRef() aos componentes
2. Passar ref explicitamente
3. Testar se aviso desaparece
4. Commit
```

### Tarefa 3: Implementar/Corrigir Histórico (20 min)
```
1. Verificar se existe TimelinePage.tsx
2. Se não, criar componente
3. Configurar navegação em App.tsx
4. Testar navegação
5. Commit
```

---

## 🔍 Próximos Passos

### Imediato
1. Confirmar se quer que eu corrija estes 3 problemas
2. Executar as correções
3. Testar

### Ordem Recomendada
1. **Corrigir WebSocket** (alta prioridade - afeta UX)
2. **Corrigir AlertDialog** (média prioridade - aviso React)
3. **Corrigir Histórico** (se desejar esta feature)

---

**Aguardando confirmação para proceder com as correções!**
