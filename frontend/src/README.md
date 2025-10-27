# Monitor de Alertas de Reposicionamento

Sistema de gestão de alertas para prevenção de úlceras de pressão em pacientes hospitalizados.

## 📋 Visão Geral

Este é um frontend React + Vite que consome APIs REST de um backend existente. O sistema permite que equipes de cuidadores e enfermeiros monitorem quando pacientes com risco de úlcera de pressão precisam ser reposicionados.

## 🎨 Design System

### Tokens CSS

Todos os tokens de design estão definidos em `/styles/globals.css`:

```css
/* Cores Primárias */
--color-primary: #0B5FFF;
--color-success: #10B981;
--color-warning: #FBBF24;
--color-danger: #EF4444;

/* Cores Neutras */
--color-bg: #F8FAFC;
--color-surface: #FFFFFF;
--color-text: #0F172A;
--color-text-muted: #64748B;
--color-border: #E2E8F0;

/* Espaçamento */
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;

/* Raios de Borda */
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
```

### Tipografia

- **Família**: Inter (já configurada via Tailwind)
- **Pesos**: 400 (normal), 500 (medium), 600 (semi-bold), 700 (bold)
- **Escala**: Configurada automaticamente pelo Tailwind

## 🏗️ Estrutura de Componentes

### Organização de Pastas

```
/components
  /auth              - Componentes de autenticação
    AuthLayout.tsx
    LoginForm.tsx
    RegisterForm.tsx
  /layout            - Componentes de layout
    AppLayout.tsx
  /pages             - Páginas principais
    DashboardPage.tsx
    TimelinePage.tsx
    PatientsPage.tsx
    AdminPage.tsx
  /alerts            - Componentes de alertas
    AlertsTable.tsx
  /patients          - Componentes de pacientes
    PatientForm.tsx
  /shared            - Componentes compartilhados
    Spinner.tsx
    EmptyState.tsx
    ErrorBanner.tsx
    LoadingOverlay.tsx
    PollIndicator.tsx
  /ui                - Componentes UI base (shadcn/ui)
/hooks               - React Hooks customizados
  useAuth.ts
  usePolling.ts
/lib                 - Utilitários e serviços
  api.ts             - Cliente API REST
```

### Componentes Principais

#### Componentes Compartilhados

- **Spinner**: Indicador de carregamento com tamanhos sm/md/lg
- **EmptyState**: Estado vazio com ícone, título, descrição e ação opcional
- **ErrorBanner**: Banner de erro com tipos error/offline/warning e opções de retry/dismiss
- **LoadingOverlay**: Overlay de carregamento para modais/cards
- **PollIndicator**: Indicador de polling automático com timer e refresh manual

#### Variantes de Componentes

**Button**
- Variantes: `default`, `outline`, `ghost`, `destructive`, `secondary`
- Tamanhos: `default`, `sm`, `lg`, `icon`
- Estados: `disabled`, `hover`, `active`

**Badge**
- Variantes: `default`, `secondary`, `outline`, `destructive`
- Custom: warning (amarelo), success (verde)

**Input**
- Estados: `default`, `error`, `disabled`
- Auto-complete support

**Table**
- Responsivo com overflow-x-auto
- Skeleton loading states
- Empty states

## 🔌 Integração com API

### Base URL e Configuração

Todas as requisições usam caminhos relativos `/api/...` com `credentials: "same-origin"`.

Configure o Vite proxy em `vite.config.ts`:

```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // URL do backend
        changeOrigin: true,
      },
    },
  },
});
```

### Endpoints Implementados

#### Autenticação

```typescript
POST /api/auth/login
Body: { username: string, password: string }
Response: { username: string }

POST /api/auth/register
Body: { username: string, password: string, display_name?: string }
Response: { username: string }

GET /api/auth/me
Response: { username: string } | 401

POST /api/auth/logout
Response: 204
```

#### Alertas

```typescript
GET /api/frontend/alerts?horas={number}
Response: Alert[]

POST /api/frontend/alerts/{id}/acknowledge
Response: 204

POST /api/frontend/alerts/{id}/complete
Response: 204
```

**Alert Shape:**
```typescript
{
  id: string;
  patientName: string;
  room: string;
  bed: string;
  lastRepositioning: string; // ISO 8601
  nextRepositioning: string; // ISO 8601
  riskLevel: 'high' | 'medium' | 'low';
  status: 'pending' | 'acknowledged' | 'completed';
}
```

#### Timeline

```typescript
GET /api/timeline
Response: TimelineEvent[]
```

**TimelineEvent Shape:**
```typescript
{
  id: number;
  paciente_id: string;
  ts: string; // ISO 8601
  ts_ms: number;
  tipo: string; // 'alert_open' | 'alert_acknowledged' | 'alert_completed' | 'repositioning'
  descricao: string | null;
}
```

#### Pacientes

```typescript
GET /api/pacientes
Response: Patient[]

POST /api/pacientes
Body: CreatePatientRequest
Response: Patient

PATCH /api/pacientes/{id}
Body: Partial<CreatePatientRequest>
Response: Patient

DELETE /api/pacientes/{id}
Response: 204
```

**Patient Shape:**
```typescript
{
  id: string;
  name: string;
  room: string;
  bed: string;
  riskLevel: 'high' | 'medium' | 'low';
  repositioningInterval: number; // em horas
  createdAt: string;
  updatedAt: string;
}
```

#### Device Events (Admin)

```typescript
GET /api/device_events
Response: DeviceEvent[]

POST /api/device_events/reconcile
Response: 204

POST /admin/device_events/reconcile
Response: 204
```

**DeviceEvent Shape:**
```typescript
{
  id: number;
  device_id: string;
  event_type: string;
  event_data: any;
  processed_at: string | null;
  created_at: string;
}
```

## 🔄 Fluxo de Usuário

### 1. Login/Registro
- Usuário acessa o sistema
- Pode fazer login ou criar nova conta
- Sistema chama `GET /api/auth/me` ao montar para restaurar sessão
- Cookie HttpOnly é gerenciado automaticamente

### 2. Dashboard
- Visualiza estatísticas: alertas ativos, atrasados, reconhecidos
- Tabela de alertas ordenados por prioridade (atrasados primeiro)
- Ações: Reconhecer alerta, Marcar como reposicionado
- Polling automático a cada 30 segundos
- Optimistic updates para melhor UX

### 3. Timeline/Histórico
- Visualização cronológica de eventos
- Agrupado por dia
- Eventos com ícones e badges coloridos
- Tooltip com detalhes ao passar o mouse

### 4. Pacientes
- Lista de pacientes em cards
- Formulário de criação/edição
- Campos: nome, quarto, leito, nível de risco, intervalo de reposicionamento
- Exclusão com confirmação

### 5. Admin
- Lista de eventos de dispositivos IoT
- Status: pendente/processado
- Botão de reconciliação manual
- Atualização em tempo real

## 🎯 Estados e Tratamento de Erros

### Estados de Carregamento

- **Initial Load**: `<Skeleton>` components
- **Action in Progress**: Botões desabilitados + spinner
- **Full Page Load**: `<FullPageSpinner>`

### Estados de Erro

- **API Error**: `<ErrorBanner>` com botão "Tentar novamente"
- **Offline**: Banner especial "Conexão perdida"
- **Form Error**: Inline `<Alert>` no formulário
- **Toast Notifications**: Sucesso/erro em ações

### Estados Vazios

- **No Data**: `<EmptyState>` com CTA quando apropriado
- Exemplos: "Nenhum alerta ativo", "Nenhum paciente cadastrado"

## ♿ Acessibilidade

### Recursos Implementados

- ✅ Contraste mínimo AA (WCAG 2.1)
- ✅ Elementos focáveis por teclado
- ✅ Labels em todos os inputs
- ✅ ARIA attributes em componentes interativos
- ✅ Navegação por teclado em modais e dialogs
- ✅ Screen reader friendly
- ✅ Auto-complete attributes em formulários

### Navegação por Teclado

- `Tab`/`Shift+Tab`: Navegar entre elementos
- `Enter`/`Space`: Ativar botões/links
- `Esc`: Fechar modais/dialogs
- Sidebar totalmente navegável por teclado

## 📱 Responsividade

### Breakpoints

- Mobile: < 768px (menu hambúrguer)
- Tablet: 768px - 1024px
- Desktop: > 1024px (sidebar fixa)

### Layout Móvel

- Menu hambúrguer no header
- Menu expansível com navegação
- Cards em coluna única
- Tabelas com scroll horizontal

## 🔧 Configuração de Desenvolvimento

### Instalação

```bash
npm install
```

### Desenvolvimento

```bash
npm run dev
```

### Build

```bash
npm run build
```

### Preview

```bash
npm run preview
```

## 📦 Dependências Principais

- **React 18**: Framework UI
- **Vite**: Build tool
- **Tailwind CSS 4.0**: Styling
- **shadcn/ui**: Componentes UI
- **Lucide React**: Ícones
- **Sonner**: Toast notifications

## 🚀 Deploy

### Variáveis de Ambiente

Crie um arquivo `.env` (não commitar):

```env
VITE_API_BASE_URL=https://api.example.com
```

### Build de Produção

```bash
npm run build
```

Arquivos gerados em `/dist`

## 📝 Notas para o Time de Desenvolvimento

### Convenções de Nomenclatura

- **Componentes**: PascalCase (ex: `AlertsTable.tsx`)
- **Hooks**: camelCase com prefixo "use" (ex: `useAuth.ts`)
- **Utilitários**: camelCase (ex: `api.ts`)
- **CSS Variables**: kebab-case com prefixo (ex: `--color-primary`)

### Props de Componentes

Sempre definir interfaces TypeScript:

```typescript
interface ComponentProps {
  required: string;
  optional?: number;
  callback: (id: string) => void;
}
```

### Tratamento de Erros

Sempre usar try/catch com ApiException:

```typescript
try {
  await api.method();
  toast.success('Sucesso');
} catch (err) {
  if (err instanceof ApiException) {
    toast.error(err.message);
  } else {
    toast.error('Erro genérico');
  }
}
```

### Optimistic Updates

Para melhor UX, aplicar mudanças otimistas:

```typescript
// Update UI first
setData(optimisticData);

try {
  await api.update();
} catch {
  // Revert on error
  fetchData();
}
```

## 🔍 Gaps de API Identificados

### Campos Ausentes/Desejados

1. **Dashboard Stats Endpoint**: `GET /api/stats`
   - Seria útil um endpoint dedicado para estatísticas do dashboard
   - Atualmente calculado no frontend

2. **User Display Name**: 
   - Não retornado em `GET /api/auth/me`
   - Apenas username disponível

3. **Filtros de Alertas**:
   - Filtro por nível de risco
   - Filtro por status
   - Paginação para grandes volumes

4. **Timeline com Filtros**:
   - Filtro por paciente
   - Filtro por tipo de evento
   - Range de datas

5. **Notificações em Tempo Real**:
   - WebSocket para alertas em tempo real
   - Evitaria necessidade de polling

6. **Upload de Documentos**:
   - Endpoint para upload de documentos do paciente
   - Storage de arquivos

7. **Relatórios**:
   - Endpoint para geração de relatórios
   - Exportação CSV/PDF

## 📄 Licença

Propriedade da instituição. Uso interno apenas.

## 🤝 Contribuindo

1. Seguir as convenções de código
2. Testar em todos os breakpoints
3. Verificar acessibilidade
4. Documentar mudanças significativas
5. Atualizar este README quando necessário

---

**Última atualização**: Outubro 2025  
**Versão**: 1.0.0  
**Contato**: equipe-dev@hospital.com
