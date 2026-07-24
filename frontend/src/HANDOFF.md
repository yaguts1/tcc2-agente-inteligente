# Frontend Handoff - Monitor de Alertas de Reposicionamento

## 📦 Entrega

Este documento contém todas as informações necessárias para o time de desenvolvimento implementar e manter o sistema.

## 🎨 Design Tokens

### Cores

Todas as cores estão disponíveis como CSS variables em `/styles/globals.css`:

| Token | Valor | Uso |
|-------|-------|-----|
| `--color-primary` | #0B5FFF | Ações primárias, links, elementos interativos |
| `--color-success` | #10B981 | Sucesso, confirmações, alertas completados |
| `--color-warning` | #FBBF24 | Avisos, alertas reconhecidos |
| `--color-danger` | #EF4444 | Erros, alertas críticos, exclusões |
| `--color-bg` | #F8FAFC | Background da aplicação |
| `--color-surface` | #FFFFFF | Cards, modais, superfícies |
| `--color-text` | #0F172A | Texto principal |
| `--color-text-muted` | #64748B | Texto secundário |
| `--color-border` | #E2E8F0 | Bordas |

### Espaçamento

| Token | Valor | Uso |
|-------|-------|-----|
| `--space-1` | 4px | Espaçamento mínimo |
| `--space-2` | 8px | Padding interno pequeno |
| `--space-3` | 12px | Gap entre elementos relacionados |
| `--space-4` | 16px | Padding padrão |
| `--space-5` | 24px | Margin entre seções |
| `--space-6` | 32px | Margin entre blocos |

### Bordas

| Token | Valor | Uso |
|-------|-------|-----|
| `--radius-sm` | 4px | Badges, tags |
| `--radius-md` | 8px | Botões, inputs |
| `--radius-lg` | 12px | Cards |
| `--radius-xl` | 16px | Modais, drawers |

## 📁 Estrutura de Componentes

### Hierarquia

```
App.tsx (Root)
├── AuthLayout
│   ├── LoginForm
│   └── RegisterForm
└── AppLayout
    ├── DashboardPage
    │   ├── StatCard (×4)
    │   └── AlertsTable
    │       ├── AlertRow (×N)
    │       └── ConfirmDialog
    ├── TimelinePage
    │   └── TimelineEvent (×N)
    ├── PatientsPage
    │   ├── PatientCard (×N)
    │   └── PatientForm
    └── AdminPage
        └── DeviceEventsTable
```

### Componentes Reutilizáveis

#### Spinner

```tsx
import { Spinner } from './components/shared/Spinner';

// Props
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

// Uso
<Spinner size="md" />
<FullPageSpinner /> // Página completa
```

#### EmptyState

```tsx
import { EmptyState } from './components/shared/EmptyState';

// Props
interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

// Uso
<EmptyState
  icon={Users}
  title="Nenhum paciente"
  description="Adicione pacientes para começar"
  action={{
    label: 'Adicionar Paciente',
    onClick: handleAdd
  }}
/>
```

#### ErrorBanner

```tsx
import { ErrorBanner } from './components/shared/ErrorBanner';

// Props
interface ErrorBannerProps {
  title?: string;
  message: string;
  type?: 'error' | 'offline' | 'warning';
  onRetry?: () => void;
  onDismiss?: () => void;
}

// Uso
<ErrorBanner
  type="offline"
  title="Conexão perdida"
  message="Verifique sua conexão com a internet"
  onRetry={fetchData}
  onDismiss={() => setError(null)}
/>
```

#### PollIndicator

```tsx
import { PollIndicator } from './components/shared/PollIndicator';

// Props
interface PollIndicatorProps {
  isPolling: boolean;
  interval: number; // milliseconds
  onManualRefresh?: () => void;
}

// Uso
<PollIndicator
  isPolling={isPolling}
  interval={30000}
  onManualRefresh={fetchAlerts}
/>
```

### Componentes UI (shadcn/ui)

Todos localizados em `/components/ui/`:

- **Button**: Ações primárias e secundárias
- **Input**: Campos de texto
- **Card**: Containers de conteúdo
- **Table**: Tabelas de dados
- **Badge**: Tags e status
- **Alert**: Mensagens inline
- **Dialog**: Modais
- **Skeleton**: Loading states
- **Toast (Sonner)**: Notificações

Consulte a documentação shadcn/ui para props completas.

## 🔌 Integração com Backend

### Configuração

1. Copiar `vite.config.example.ts` para `vite.config.ts`
2. Ajustar URL do backend:

```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8000', // Seu backend aqui
    changeOrigin: true,
  }
}
```

### Cliente API

Localizado em `/lib/api.ts`. Todas as chamadas já configuradas:

```typescript
import { alertsApi } from '../lib/api';

// Exemplo de uso
const alerts = await alertsApi.getAlerts();
await alertsApi.acknowledge(alertId);
```

### Tratamento de Erros

Sempre usar ApiException:

```typescript
import { ApiException } from '../lib/api';

try {
  await api.method();
} catch (err) {
  if (err instanceof ApiException) {
    // Erro da API com status code
    console.log(err.status, err.message);
  } else {
    // Erro de rede ou outro
    console.error('Erro desconhecido');
  }
}
```

## 🎯 Estados e Fluxos

### Loading States

1. **Initial Load**: Usar `<Skeleton>` components
   ```tsx
   {isLoading ? (
     <Skeleton className="h-16 w-full" />
   ) : (
     <ActualContent />
   )}
   ```

2. **Action in Progress**: Desabilitar + spinner
   ```tsx
   <Button disabled={isLoading}>
     {isLoading ? <Spinner size="sm" /> : 'Salvar'}
   </Button>
   ```

3. **Full Page**: `<FullPageSpinner />`

### Error States

1. **Banner**: Erros de carregamento
2. **Inline Alert**: Erros de formulário
3. **Toast**: Feedback de ações

### Empty States

Sempre usar `<EmptyState>` quando não há dados.

## 🎨 Variantes de Componentes

### Button

```tsx
// Variantes
<Button variant="default">Primary</Button>
<Button variant="outline">Secondary</Button>
<Button variant="ghost">Subtle</Button>
<Button variant="destructive">Delete</Button>

// Tamanhos
<Button size="sm">Small</Button>
<Button size="default">Default</Button>
<Button size="lg">Large</Button>

// Com ícone
<Button>
  <Plus className="w-4 h-4 mr-2" />
  Adicionar
</Button>
```

### Badge

```tsx
// Variantes built-in
<Badge variant="default">Default</Badge>
<Badge variant="secondary">Secondary</Badge>
<Badge variant="outline">Outline</Badge>
<Badge variant="destructive">Error</Badge>

// Custom colors
<Badge className="bg-success text-success-foreground">
  Sucesso
</Badge>
<Badge className="bg-warning text-warning-foreground">
  Aviso
</Badge>
```

### Input

```tsx
// States
<Input type="text" placeholder="Normal" />
<Input disabled placeholder="Disabled" />
<Input className="border-destructive" /> // Error

// Com label
<div className="space-y-2">
  <Label htmlFor="name">Nome</Label>
  <Input id="name" />
</div>
```

## ♿ Acessibilidade

### Checklist

- [ ] Todos os botões têm labels visíveis ou aria-label
- [ ] Todos os inputs têm labels associados
- [ ] Navegação por teclado funciona
- [ ] Modais podem ser fechados com ESC
- [ ] Foco visível em elementos interativos
- [ ] Contraste mínimo AA (4.5:1 para texto)
- [ ] Imagens têm alt text

### Exemplos

```tsx
// Button com aria-label
<Button aria-label="Fechar modal">
  <X className="w-4 h-4" />
</Button>

// Input com label
<Label htmlFor="email">Email</Label>
<Input id="email" type="email" />

// Dialog acessível
<Dialog>
  <DialogContent>
    <DialogTitle>Título do Modal</DialogTitle>
    {/* Conteúdo */}
  </DialogContent>
</Dialog>
```

## 📱 Responsividade

### Breakpoints Tailwind

- `sm`: 640px
- `md`: 768px (tablet)
- `lg`: 1024px (desktop - sidebar aparece)
- `xl`: 1280px
- `2xl`: 1536px

### Padrões

```tsx
// Grid responsivo
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

// Hide/Show por breakpoint
<div className="hidden lg:block">Desktop only</div>
<div className="lg:hidden">Mobile only</div>

// Flex direction
<div className="flex flex-col lg:flex-row">
```

## 🔄 Hooks Customizados

### useAuth

```typescript
import { useAuth } from '../hooks/useAuth';

const {
  user,           // { username: string } | null
  isLoading,      // boolean
  error,          // string | null
  login,          // (username, password) => Promise<boolean>
  register,       // (username, password, displayName) => Promise<boolean>
  logout,         // () => Promise<void>
  isAuthenticated // boolean
} = useAuth();
```

### usePolling

```typescript
import { usePolling } from '../hooks/usePolling';

const { isPolling, toggle, start, stop } = usePolling({
  interval: 30000,  // 30 seconds
  enabled: true,
  onPoll: fetchData,
});
```

## 🚀 Deploy

### Checklist

1. Configurar variáveis de ambiente
2. Ajustar URL do backend em produção
3. Build: `npm run build`
4. Testar: `npm run preview`
5. Deploy da pasta `/dist`

### Variáveis de Ambiente

Criar `.env.production`:

```env
VITE_API_BASE_URL=https://api.producao.com
```

Usar no código:

```typescript
const API_URL = import.meta.env.VITE_API_BASE_URL || '';
```

## 📊 Dados de Exemplo (Mock)

### Alert

```json
{
  "id": "PAC-0001__2025-10-25T15:56:54",
  "patientName": "Maria Silva",
  "room": "201A",
  "bed": "Leito 1",
  "lastRepositioning": "2025-10-25T13:00:00",
  "nextRepositioning": "2025-10-25T15:56:54",
  "riskLevel": "high",
  "status": "pending"
}
```

### TimelineEvent

```json
{
  "id": 1,
  "paciente_id": "PAC-0001",
  "ts": "2025-10-25T15:56:54",
  "ts_ms": 1740000000000,
  "tipo": "alert_open",
  "descricao": null
}
```

### Patient

```json
{
  "id": "PAC-0001",
  "name": "Maria Silva",
  "room": "201A",
  "bed": "Leito 1",
  "riskLevel": "high",
  "repositioningInterval": 2,
  "createdAt": "2025-10-25T10:00:00",
  "updatedAt": "2025-10-25T10:00:00"
}
```

### DeviceEvent

```json
{
  "id": 1,
  "device_id": "sensor-001",
  "event_type": "motion_detected",
  "event_data": { "intensity": 75 },
  "processed_at": null,
  "created_at": "2025-10-25T15:56:54"
}
```

## 🐛 Troubleshooting

### Cookie não está sendo enviado

Verificar:
- Backend está configurando cookie com `SameSite=Lax` ou `None`
- Frontend usa `credentials: 'same-origin'`
- Domínios são compatíveis (ou use proxy em dev)

### Polling não funciona

Verificar:
- `usePolling` está recebendo função estável (useCallback)
- `enabled` está true
- Não há erros no console bloqueando o interval

### Sidebar não aparece em mobile

Esperado! Sidebar só aparece em `lg:` (1024px+). Em mobile use menu hambúrguer.

### Formulário não valida

Verificar:
- Inputs têm `required` attribute
- Form tem `onSubmit` com `e.preventDefault()`
- Validação de senha no frontend (min 6 chars, etc)

## 📞 Suporte

**Perguntas sobre o frontend:**
- Consultar este documento
- Ver exemplos em `/components`
- Verificar README.md principal

**Perguntas sobre API:**
- Consultar documentação do backend
- Ver shapes de dados em `/lib/api.ts`

---

**Versão do Handoff**: 1.0  
**Data**: Outubro 2025  
**Próximos Passos**: Integrar com backend real e testar fluxos completos
