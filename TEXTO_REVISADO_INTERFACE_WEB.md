# 3.4 Interface Web

A interface web constitui o principal meio de interação entre a equipe de enfermagem e o sistema de monitoramento desenvolvido neste trabalho. Trata-se de uma aplicação single-page (SPA) construída com tecnologias modernas, oferecendo experiência responsiva, atualizações em tempo real e interface intuitiva adequada ao ambiente clínico hospitalar. Esta seção descreve a arquitetura, funcionalidades e decisões de design da interface, alinhando cada aspecto técnico com requisitos clínicos identificados durante o desenvolvimento.

## 3.4.1 Arquitetura e Stack Tecnológico

A interface web foi desenvolvida utilizando **React 18** com **TypeScript**, combinando tipagem estática com o ecossistema de componentes reativos do React. A escolha por TypeScript reduz erros em tempo de execução e melhora a manutenibilidade do código, aspecto crítico em sistemas de saúde onde bugs podem ter consequências diretas no cuidado ao paciente.

### Stack Tecnológico Completo:

- **Framework Frontend**: React 18.3.1 com hooks modernos (`useState`, `useEffect`, `useCallback`, `useRef`)
- **Linguagem**: TypeScript (tipagem estática)
- **Build Tool**: Vite 6.3.5 (bundler moderno com hot module replacement)
- **Biblioteca de Componentes**: shadcn/ui baseada em Radix UI (componentes acessíveis e customizáveis)
- **Estilização**: Tailwind CSS (utility-first CSS framework)
- **Gerenciamento de Estado**: React hooks nativos (sem Redux ou Context API global)
- **Comunicação com Backend**: Fetch API com abstração custom (`lib/api.ts`)
- **WebSocket**: API WebSocket nativa para comunicação bidirecional em tempo real
- **Notificações**: Sonner (biblioteca toast moderna e acessível)
- **Ícones**: Lucide React (biblioteca de ícones SVG consistente)
- **Testes E2E**: Cypress 15.5.0

### Motivações para Escolhas Tecnológicas:

**React 18**: Oferece concurrent rendering e automatic batching, melhorando performance em aplicações com atualizações frequentes (crítico para dashboard de alertas em tempo real).

**Vite**: Build extremamente rápido (~100ms para hot reload) melhora experiência de desenvolvimento. Em produção, gera bundle otimizado com code splitting automático.

**shadcn/ui + Radix UI**: Componentes acessíveis por padrão (suporte a screen readers, navegação por teclado, ARIA labels), fundamental para atender requisitos de acessibilidade em sistemas de saúde.

**Tailwind CSS**: Permite desenvolvimento rápido sem overhead de CSS customizado. Classes utilitárias facilitam manutenção e consistência visual.

**TypeScript**: Tipagem estática reduz bugs relacionados a dados inconsistentes (ex: perfil de risco com valor inválido, timestamps em formato incorreto), prevenindo erros que poderiam causar falhas silenciosas no dashboard.

## 3.4.2 Arquitetura de Componentes

A aplicação segue arquitetura baseada em componentes funcionais, organizados hierarquicamente:

```
src/
├── components/
│   ├── alerts/          # Componentes de alertas
│   │   ├── AlertsTable.tsx        # Tabela principal de alertas
│   │   ├── FilterBar.tsx          # Barra de filtros
│   │   └── BulkActionBar.tsx      # Ações em lote
│   ├── auth/            # Autenticação
│   │   ├── LoginForm.tsx
│   │   ├── RegisterForm.tsx
│   │   └── AuthLayout.tsx
│   ├── layout/          # Layout geral
│   │   └── AppLayout.tsx          # Shell principal
│   ├── pages/           # Páginas principais
│   │   ├── DashboardPage.tsx      # Dashboard principal
│   │   ├── PatientsPage.tsx       # Gestão de pacientes
│   │   ├── TimelinePage.tsx       # Timeline de eventos
│   │   └── AdminPage.tsx          # Administração
│   ├── patients/        # Gestão de pacientes
│   │   ├── PatientForm.tsx        # Formulário de cadastro
│   │   └── AgendaPanel.tsx        # Gestão de agendas
│   ├── shared/          # Componentes compartilhados
│   │   ├── ErrorBanner.tsx
│   │   ├── EmptyState.tsx
│   │   └── Spinner.tsx
│   └── ui/              # Componentes de UI base (shadcn)
│       ├── button.tsx
│       ├── card.tsx
│       ├── table.tsx
│       └── ... (30+ componentes)
├── hooks/               # Hooks customizados
│   ├── useAuth.ts              # Autenticação
│   ├── useWebSocket.ts         # Conexão WebSocket
│   ├── useCriticalAlerts.ts    # Alertas críticos
│   ├── usePolling.ts           # Polling como fallback
│   └── useAlertFilters.ts      # Filtros de alertas
├── lib/
│   ├── api.ts           # Cliente API HTTP
│   └── storage.ts       # LocalStorage helpers
└── App.tsx              # Componente raiz
```

### Separação de Responsabilidades:

**Componentes de Página**: Contêm lógica de negócio, gerenciam estado local, orquestram chamadas à API e coordenam componentes filhos.

**Componentes de UI**: Puramente apresentacionais, recebem dados via props, não fazem chamadas à API, facilitam reutilização e testabilidade.

**Hooks Customizados**: Encapsulam lógica complexa (WebSocket, autenticação, polling), promovendo reusabilidade e separação de concerns.

**Camada de API**: Abstração sobre Fetch API, centraliza tratamento de erros, autenticação via tokens JWT e transformação de dados.

## 3.4.3 Dashboard Principal

O dashboard (`DashboardPage.tsx`) é a tela central do sistema, onde a equipe de enfermagem monitora alertas de reposicionamento em tempo real. Sua arquitetura prioriza **visibilidade imediata de situações críticas** e **facilidade de ação**.

### Elementos do Dashboard:

#### 1. **Cards de Métricas (KPIs)**

Quatro cartões no topo da página exibem indicadores-chave:

- **Alertas Ativos**: Alertas com status "pending", aguardando reconhecimento
- **Reconhecidos**: Alertas já visualizados pela equipe (status "acknowledged")
- **Completados Hoje**: Alertas finalizados (paciente reposicionado) nas últimas 24h
- **Taxa de Conclusão**: Percentual de alertas completados em relação ao total

```tsx
// Exemplo de Card de Métrica
<Card className="p-6">
  <div className="flex items-center gap-3">
    <div className="bg-primary/10 p-2 rounded-lg">
      <Bell className="w-5 h-5 text-primary" />
    </div>
    <div>
      <p className="text-sm text-muted-foreground">Alertas Ativos</p>
      <p className="text-2xl font-bold">{stats.activeAlerts}</p>
    </div>
  </div>
</Card>
```

**Justificativa clínica**: Métricas visíveis permitem que coordenadores avaliem carga de trabalho da equipe rapidamente. Taxa de conclusão serve como indicador de qualidade do cuidado.

#### 2. **Barra de Filtros**

Sistema de filtros multi-dimensional permite que a equipe localize alertas específicos:

- **Severidade**: Alto, Médio, Baixo (baseado no perfil de risco do paciente)
- **Status**: Pendente, Reconhecido, Completado
- **Paciente**: Seleção por nome (dropdown com autocomplete)
- **Busca por Texto**: Filtra por nome de paciente, quarto ou leito
- **Intervalo de Datas**: Filtra alertas por período de próximo reposicionamento

```tsx
// Implementação de filtro por severidade
const filteredAlerts = alerts.filter((alert) => {
  if (filters.severity) {
    const alertSeverity = alert.riskLevel === 'high' ? 'HIGH' : 
                         alert.riskLevel === 'medium' ? 'MEDIUM' : 'LOW';
    if (alertSeverity !== filters.severity) {
      return false;
    }
  }
  // ... outros filtros
  return true;
});
```

**Contador de Filtros Ativos**: Badge visual mostra quantos filtros estão aplicados, com botão "Limpar Filtros" para resetar visualização.

**Justificativa clínica**: Enfermeiros frequentemente precisam priorizar pacientes de alto risco ou localizar alertas por ala/quarto. Filtros flexíveis reduzem tempo de busca.

#### 3. **Tabela de Alertas**

Componente central do dashboard, exibe alertas em formato tabular com colunas:

- **Checkbox**: Seleção múltipla para ações em lote
- **Paciente**: Nome completo
- **Localização**: Quarto / Leito (ex: "201 / A")
- **Risco**: Badge colorido (Vermelho: Alto, Amarelo: Médio, Cinza: Baixo)
- **Status**: Badge de estado (Pendente, Reconhecido, Completado)
- **Próximo Reposicionamento**: Timestamp + indicador de atraso
  - Verde: "Em 45min" (dentro do prazo)
  - Vermelho: "Atrasado 12min" (prazo excedido)
- **Ações**: Botões "Reconhecer" e "Reposicionar"

```tsx
// Cálculo dinâmico de tempo até próximo reposicionamento
const getTimeUntil = (dateString: string) => {
  const date = new Date(dateString);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const minutes = Math.floor(Math.abs(diff) / 60000);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;

  if (diff < 0) {
    // Atrasado
    return hours > 0 ? `Atrasado ${hours}h ${mins}min` : `Atrasado ${mins}min`;
  } else {
    // No prazo
    return hours > 0 ? `Em ${hours}h ${mins}min` : `Em ${mins}min`;
  }
};
```

**Comportamento dos Botões**:

- **Reconhecer**: Muda status de "pending" → "acknowledged", indica que equipe está ciente do alerta. Botão fica **desabilitado** (grayed out) após reconhecimento, mas **permanece visível** para clareza de estado.
- **Reposicionar**: Muda status para "completed", remove alerta da tabela, registra timestamp de reposicionamento no histórico.

```tsx
// Lógica de botões (ambos sempre visíveis, com disable condicional)
<div className="flex gap-2">
  <Button 
    disabled={alert.status === 'acknowledged' || isProcessing}
    onClick={() => handleAcknowledge(alert.id)}
  >
    Reconhecer
  </Button>
  <Button 
    disabled={isProcessing}
    onClick={() => handleComplete(alert.id)}
  >
    Reposicionar
  </Button>
</div>
```

**Justificativa clínica**: Botão "Reconhecer" permanece visível mesmo desabilitado para comunicar claramente o estado do alerta. Ausência do botão causava confusão (usuário não sabia se alerta já havia sido reconhecido ou se houve erro na interface).

#### 4. **Estado Vazio**

Quando não há alertas (após aplicar filtros ou em situação de zero alertas ativos), componente `EmptyState` exibe mensagem amigável com ícone ilustrativo:

```tsx
<EmptyState
  icon={<AlertTriangle className="w-12 h-12" />}
  title="Nenhum alerta encontrado"
  description="Não há alertas ativos no momento ou seus filtros não retornaram resultados."
/>
```

**Justificativa de UX**: Estados vazios confusos causam incerteza ("há um erro?" vs "realmente não há alertas?"). Mensagem explícita reduz ansiedade do usuário.

## 3.4.4 Comunicação em Tempo Real

### Arquitetura Híbrida: WebSocket + Polling Fallback

A interface implementa comunicação bidirecional via **WebSocket** para atualizações em tempo real, com **polling HTTP** como fallback para ambientes onde WebSocket não está disponível (ex: proxies corporativos que bloqueiam upgrade de conexão).

#### WebSocket (`useWebSocket.ts`)

Hook customizado gerencia conexão WebSocket com backend:

```tsx
const { isConnected } = useWebSocket({
  enabled: true,
  onMessage: handleWebSocketMessage,
  reconnectInterval: 5000,
  maxReconnectAttempts: 5,
});
```

**Funcionalidades**:

1. **Conexão Automática**: Inicia conexão ao montar componente (se autenticado)
2. **Heartbeat**: Envia ping a cada 30 segundos para manter conexão ativa
3. **Reconexão Exponencial**: Tenta reconectar com backoff (5s, 10s, 20s, 40s, até max 30s)
4. **Graceful Degradation**: Se backend não responde, desiste após 5 tentativas e deixa polling assumir

```tsx
// Heartbeat implementation
ws.onopen = () => {
  console.log('WebSocket connected');
  setIsConnected(true);
  toast.success('Conectado a alertas em tempo real');
  
  const heartbeatInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 30000);
  
  (ws as any)._heartbeatInterval = heartbeatInterval;
};
```

**Mensagens Recebidas**:

Quando backend envia atualização de alerta, WebSocket dispara `onMessage`:

```tsx
const handleWebSocketMessage = (message: any) => {
  if (message.type === 'alert_update') {
    const { alert_id, status } = message;
    if (status === 'completed') {
      // Remove alerta completado da lista
      setAlerts((prev) => prev.filter((alert) => alert.id !== alert_id));
    } else {
      // Atualiza status (pending → acknowledged)
      setAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alert_id ? { ...alert, status } : alert
        )
      );
    }
    
    // Atualiza métricas
    statsApi.getStats().then(setStats);
  }
};
```

**Justificativa técnica**: WebSocket elimina latência de polling (30s → imediato). Crítico para alertas de alto risco onde atraso de notificação pode significar atraso no cuidado.

#### Polling Fallback (`usePolling.ts`)

Hook de polling ativa automaticamente quando WebSocket não conecta:

```tsx
const { isPolling } = usePolling({
  interval: 30000, // 30 segundos
  enabled: !wsConnected, // Só ativa se WebSocket falhar
  onPoll: fetchAlerts,
});
```

**Comportamento**:

- Polling é **desabilitado** se WebSocket está conectado (evita requisições duplicadas)
- Requisições HTTP a cada 30 segundos (trade-off entre atualização e carga no servidor)
- Indicador visual mostra quando sistema está em modo polling (vs tempo real)

**Justificativa arquitetural**: Fallback garante que sistema funcione mesmo em redes restritas. Polling de 30s é aceitável para maioria dos casos clínicos (janelas de reposicionamento são de 60-120min).

### Indicador de Modo de Operação

Componente `PollIndicator` mostra estado da comunicação:

```tsx
<PollIndicator
  isPolling={isPolling}
  interval={30000}
  onManualRefresh={fetchAlerts}
/>
```

- **WebSocket conectado**: Ícone de raio verde + "Tempo real"
- **Polling ativo**: Ícone de relógio amarelo + "Atualizando a cada 30s"
- **Botão de atualização manual**: Permite forçar refresh imediato

## 3.4.5 Sistema de Alertas Críticos

Hook `useCriticalAlerts` monitora alertas de alto risco e dispara notificações:

```tsx
const {
  criticalAlerts,
  totalCritical,
  highRisk,
  acknowledgedMedium,
  hasNewCritical,
} = useCriticalAlerts(alerts, {
  enabled: true,
  soundEnabled: true,
  notificationsEnabled: true,
});
```

### Critérios de Criticidade:

Um alerta é considerado **crítico** se:
1. Perfil de risco = "high" (alto risco), OU
2. Perfil de risco = "medium" (médio risco) **E** status = "acknowledged" (reconhecido mas não completado)

**Justificativa clínica**: Pacientes de alto risco requerem atenção imediata. Pacientes de médio risco reconhecidos mas não reposicionados indicam possível esquecimento ou sobrecarga da equipe.

### Notificações Multi-Canal:

Quando novo alerta crítico é detectado, sistema aciona:

#### 1. **Notificação Desktop** (Notification API)

```tsx
const sendNotification = async (alert: Alert) => {
  if (Notification.permission === 'granted') {
    const imobilizadoMin = Math.floor(
      (Date.now() - new Date(alert.lastRepositioning).getTime()) / 60000
    );
    const location = alert.room && alert.bed 
      ? `${alert.room} / ${alert.bed}`
      : alert.bed || alert.room || 'Sem leito';
    const riskPT = { 'high': 'ALTO', 'medium': 'MÉDIO', 'low': 'BAIXO' }[alert.riskLevel];

    const notification = new Notification(
      `🚨 Alerta Crítico - ${alert.patientName}`,
      {
        body: `📍 ${location}\n⏱️ Imobilizado há ${imobilizadoMin}min\n⚠️ Perfil: ${riskPT}\n🔄 Próximo reposicionamento: ${new Date(alert.nextRepositioning).toLocaleTimeString('pt-BR')}`,
        icon: '/icon-alert.png',
        requireInteraction: true, // Notificação persiste até usuário fechar
        tag: `critical-alert-${alert.id}`, // Evita duplicatas
      }
    );

    notification.addEventListener('click', () => {
      window.focus();
      window.scrollTo(0, 0);
    });
  }
};
```

**Comportamento**:
- Solicita permissão ao usuário no primeiro alerta crítico
- Notificação persiste na tela até ser fechada manualmente (`requireInteraction: true`)
- Clicar na notificação foca janela do navegador e scrolla para topo (dashboard)
- Tag única previne duplicação quando mesmo alerta dispara múltiplas vezes

#### 2. **Som de Alerta** (Web Audio API)

```tsx
const playAlertSound = async () => {
  const ctx = new AudioContext();
  const now = ctx.currentTime;
  const duration = 0.5;
  const frequencies = [800, 1200]; // Hz

  for (let i = 0; i < 2; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.frequency.value = frequencies[i % 2];
    gain.gain.setValueAtTime(0.3, now + i * duration);
    gain.gain.exponentialRampToValueAtTime(0.01, now + (i + 1) * duration);

    osc.start(now + i * duration);
    osc.stop(now + (i + 1) * duration);
  }
};
```

**Características do som**:
- Dois beeps curtos (0.5s cada) com frequências diferentes (800Hz e 1200Hz)
- Volume moderado (30%) para não assustar, mas chamar atenção
- Apenas para novos alertas (não repete se alerta já estava na tela)

**Justificativa UX**: Som é essencial em ambiente hospitalar onde usuários podem não estar olhando para tela constantemente. Dois beeps distintos são reconhecíveis mas não agressivos.

#### 3. **Toast Notifications** (Sonner)

Notificações in-app para ações do usuário e feedback de operações:

```tsx
toast.success('Alerta reconhecido');
toast.error('Erro ao completar alerta');
toast.info('Conectado a alertas em tempo real');
```

- Aparecem no canto superior direito
- Desaparecem automaticamente após 3-5 segundos
- Empilham quando múltiplas notificações ocorrem simultaneamente
- Não bloqueiam interação com interface (não-modais)

## 3.4.6 Gestão de Pacientes

Página `PatientsPage` permite cadastro, edição e remoção de pacientes, além de configuração de agendas clínicas.

### Formulário de Paciente

Campos obrigatórios:
- **Nome Completo**: Texto livre
- **Quarto**: Número do quarto
- **Leito**: Identificador do leito (ex: A, B, C)
- **Perfil de Risco**: Dropdown (Alto, Médio, Baixo)
- **Observações**: Texto livre (opcional)

```tsx
<PatientForm
  patient={editingPatient}
  onSubmit={async (data) => {
    if (editingPatient) {
      await patientsApi.updatePatient(editingPatient.id, data);
      toast.success('Paciente atualizado');
    } else {
      await patientsApi.createPatient(data);
      toast.success('Paciente cadastrado');
    }
    fetchPatients();
    setShowForm(false);
  }}
  onCancel={() => setShowForm(false)}
/>
```

**Validações**:
- Nome: mínimo 3 caracteres
- Quarto/Leito: não-vazios
- Perfil de risco: deve ser um dos valores válidos (high/medium/low)

**Justificativa clínica**: Dados mínimos necessários para identificar paciente e determinar janela de reposicionamento. Observações permitem anotações contextuais (ex: "paciente em pós-operatório", "preferir decúbito lateral esquerdo").

### Sistema de Agendas

Subpainel `AgendaPanel` permite configurar períodos onde alertas devem ser suprimidos, reduzidos ou mantidos normalmente.

**Casos de uso**:
- **Cirurgia**: Suprimir alertas durante procedimento (paciente sob anestesia, monitoramento direto pela equipe cirúrgica)
- **Fisioterapia**: Reduzir janela de alerta (paciente em movimento, mas ainda requer monitoramento)
- **Exames**: Suprimir temporariamente (paciente fora do leito monitorado)

**Campos do formulário de agenda**:
- **Tipo de Procedimento**: Dropdown (Cirurgia, Exame, Fisioterapia, Outro)
- **Data/Hora Início**: DateTime picker
- **Data/Hora Fim**: DateTime picker
- **Modo de Supressão**: Radio buttons
  - **Suprimir**: Descarta alertas completamente
  - **Reduzir**: Aumenta janela em X minutos (ex: de 60min para 80min)
  - **Monitorar**: Mantém alertas normais (usado para agendar futuro sem alterar comportamento)
- **Redução de Janela**: Input numérico (apenas se modo = Reduzir)
- **Observações**: Texto livre

```tsx
<AgendaPanel
  patientId={patient.id}
  patientName={patient.name}
  onBack={() => setSelectedPatientForAgenda(null)}
/>
```

**Validações**:
- Data/hora de fim deve ser posterior a início
- Redução de janela deve ser >= 5 minutos e <= janela original do perfil
- Não permitir sobreposição de agendas do mesmo tipo

**Integração com motor de decisão**: Quando motor gera alerta, backend consulta agendas ativas para aquele paciente naquele timestamp. Se agenda está ativa, aplica regra de supressão antes de persistir/notificar alerta.

## 3.4.7 Timeline de Eventos

Página `TimelinePage` exibe histórico cronológico de eventos de postura e alertas para análise retrospectiva.

**Filtros disponíveis**:
- **Paciente**: Dropdown de seleção
- **Intervalo de datas**: Date range picker
- **Tipo de evento**: Postura / Alerta / Reposicionamento

**Visualização**:
- Lista cronológica reversa (mais recente no topo)
- Cada evento mostra:
  - Timestamp
  - Tipo (ícone + cor)
  - Descrição (ex: "Paciente movido para decúbito lateral direito")
  - Duração (para eventos de postura)

**Casos de uso clínicos**:
- Auditar histórico de reposicionamento para documentação médica
- Investigar padrões (ex: "paciente sempre tem alertas no turno da noite")
- Validar que reposicionamentos foram realizados conforme prescrição médica

## 3.4.8 Autenticação e Controle de Acesso

### Sistema de Autenticação

Interface implementa autenticação via **JWT (JSON Web Tokens)** armazenados em `localStorage`.

**Fluxo de login**:
1. Usuário insere username/password em `LoginForm`
2. Frontend envia POST `/api/auth/login`
3. Backend valida credenciais, retorna token JWT + dados do usuário
4. Frontend armazena token em `localStorage` e dados do usuário em state
5. Todas as requisições subsequentes incluem header `Authorization: Bearer <token>`

```tsx
// Hook useAuth
export function useAuth() {
  const login = async (username: string, password: string) => {
    const response = await authApi.login({ username, password });
    storeToken(response.token);
    storeUser({ username: response.username, role: response.role });
    setUser({ username: response.username, role: response.role });
    setIsAuthenticated(true);
  };

  const logout = () => {
    clearAuth(); // Remove token e dados do localStorage
    setUser(null);
    setIsAuthenticated(false);
  };

  return { user, isAuthenticated, login, logout, ... };
}
```

### Expiração de Sessão

Componente `SessionExpirationAlert` monitora validade do token e exibe aviso quando sessão está próxima de expirar:

```tsx
<SessionExpirationAlert showWarning={true} />
```

- **Aviso**: 5 minutos antes da expiração
- **Auto-logout**: Quando token expira
- **Mensagem**: "Sua sessão vai expirar em 5 minutos. Salve seu trabalho."

**Justificativa de segurança**: Tokens JWT têm tempo de vida limitado (ex: 8 horas). Avisar usuário previne perda de trabalho não salvo ao ser deslogado abruptamente.

### Proteção de Rotas

Componente `App.tsx` verifica autenticação antes de renderizar interface:

```tsx
if (!isAuthenticated) {
  return <AuthLayout><LoginForm /></AuthLayout>;
}

return (
  <AppLayout>
    {renderPage()} {/* Dashboard, Patients, Timeline, Admin */}
  </AppLayout>
);
```

Usuários não autenticados são redirecionados para tela de login. Token inválido ou expirado também força re-login.

## 3.4.9 Tratamento de Erros e Estados de Loading

### Error Boundaries

Componente `ErrorBoundary` captura erros não tratados em árvore de componentes:

```tsx
<ErrorBoundary>
  <AppLayout>
    <DashboardPage />
  </AppLayout>
</ErrorBoundary>
```

Quando erro ocorre, exibe mensagem amigável com opção de recarregar página, evitando que aplicação inteira quebre.

### Banners de Erro Contextual

Componente `ErrorBanner` exibe erros específicos de operações:

```tsx
<ErrorBanner
  type="offline" // ou "error"
  title="Conexão perdida"
  message="Não foi possível conectar ao servidor. Verifique sua conexão."
  onRetry={fetchAlerts}
  onDismiss={() => setError(null)}
/>
```

**Tipos de erro**:
- **offline**: Conexão de rede perdida
- **error**: Erro de API (500, 404, validação, etc.)

**Botões**:
- **Tentar Novamente**: Refaz operação que falhou
- **Fechar**: Oculta banner (erro persiste em log)

### Estados de Loading

Componentes exibem skeletons enquanto carregam dados:

```tsx
{isLoading ? (
  <Skeleton className="h-8 w-32" />
) : (
  <p>{stats.activeAlerts}</p>
)}
```

**Skeleton UI**: Placeholders animados que mantêm layout estável durante carregamento, prevenindo "content shift" (deslocamento abrupto quando dados carregam).

**Justificativa de UX**: Skeletons comunicam que conteúdo está carregando, reduzindo percepção de lentidão. Manter layout estável previne cliques acidentais quando conteúdo desloca.

## 3.4.10 Acessibilidade

### Conformidade WCAG 2.1 AA

Interface implementa práticas de acessibilidade conforme Web Content Accessibility Guidelines:

1. **Contraste de Cores**: Todos os pares texto/fundo atendem razão de contraste mínima 4.5:1
2. **Navegação por Teclado**: Todos os elementos interativos acessíveis via Tab/Shift+Tab
3. **ARIA Labels**: Elementos complexos (badges, ícones, tabelas) têm labels descritivos
4. **Focus Visible**: Indicador visual de foco em todos os elementos interativos
5. **Screen Reader Support**: Radix UI garante anúncios corretos de estados e mudanças

### Exemplos de Implementação:

```tsx
// Button com ARIA label descritivo
<Button aria-label={`Reconhecer alerta do paciente ${alert.patientName}`}>
  Reconhecer
</Button>

// Badge com role semântico
<Badge role="status" aria-label={`Risco ${alert.riskLevel}`}>
  {alert.riskLevel === 'high' ? 'Alto Risco' : 'Médio Risco'}
</Badge>

// Tabela com cabeçalhos associados
<Table>
  <TableHeader>
    <TableRow>
      <TableHead scope="col">Paciente</TableHead>
      <TableHead scope="col">Localização</TableHead>
      ...
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow>
      <TableCell>{alert.patientName}</TableCell>
      ...
    </TableRow>
  </TableBody>
</Table>
```

**Justificativa**: Sistemas de saúde devem ser acessíveis a profissionais com diferentes capacidades. Suporte a screen readers permite que enfermeiros com deficiência visual utilizem o sistema.

## 3.4.11 Responsividade e Mobile

Interface utiliza **design responsivo** baseado em Tailwind breakpoints:

- **Mobile** (< 768px): Visualização em coluna única, cards empilhados, tabela com scroll horizontal
- **Tablet** (768px - 1024px): Grid 2 colunas, sidebar colapsável
- **Desktop** (> 1024px): Grid 4 colunas, sidebar fixa

```tsx
// Exemplo de grid responsivo
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  <Card>...</Card>
  <Card>...</Card>
  <Card>...</Card>
  <Card>...</Card>
</div>
```

**Limitação mobile**: Dashboard é **otimizado para desktop/tablet**, mas **funcional em mobile**. Ações críticas (reconhecer/reposicionar) são touch-friendly, mas visualização de tabela complexa em tela pequena não é ideal.

**Justificativa**: Contexto de uso principal é estação de enfermagem com desktop/tablet. Suporte mobile é fallback para situações excepcionais (ex: enfermeiro em ronda com smartphone).

## 3.4.12 Performance e Otimização

### Técnicas Aplicadas:

1. **React.memo**: Componentes puros memoizados para evitar re-renders desnecessários
2. **useCallback**: Funções de callback memoizadas para estabilidade referencial
3. **Lazy Loading**: Code splitting via `React.lazy()` para páginas menos acessadas
4. **Debounce**: Input de busca tem debounce de 300ms para evitar requisições excessivas
5. **Virtual Scrolling**: Não implementado (população de alertas geralmente < 100 itens)

```tsx
// Exemplo de memoização
const FilterBar = React.memo(({ filters, onFilterChange, ... }) => {
  return (
    <div className="filter-bar">
      <Input
        placeholder="Buscar paciente..."
        value={filters.searchText || ''}
        onChange={debounce((e) => onFilterChange('searchText', e.target.value), 300)}
      />
    </div>
  );
});
```

### Bundle Size:

- **Produção**: ~350 KB (gzipped)
- **Vendor**: ~200 KB (React, Radix UI, Lucide)
- **App**: ~150 KB (código da aplicação)

**Tempo de carregamento inicial**: ~1.2s em 3G, ~300ms em WiFi

**Justificativa**: Bundle size é aceitável para aplicação hospitalar (geralmente em rede interna rápida). Priorização de funcionalidade sobre micro-otimização de tamanho.

## 3.4.13 Testes End-to-End

Sistema de testes E2E com **Cypress 15.5.0** cobre fluxos críticos:

```javascript
// cypress/e2e/dashboard.cy.js
describe('Dashboard', () => {
  beforeEach(() => {
    cy.login('enfermeiro', 'senha123'); // Helper customizado
    cy.visit('/dashboard');
  });

  it('exibe alertas ativos', () => {
    cy.contains('Alertas Ativos').should('be.visible');
    cy.get('[data-testid="alerts-table"]').should('exist');
  });

  it('reconhece alerta', () => {
    cy.get('[data-testid="alert-row"]').first().within(() => {
      cy.contains('Reconhecer').click();
    });
    cy.contains('Alerta reconhecido').should('be.visible');
  });

  it('completa alerta (reposicionamento)', () => {
    cy.get('[data-testid="alert-row"]').first().within(() => {
      cy.contains('Reposicionar').click();
    });
    cy.get('[data-testid="confirm-dialog"]').within(() => {
      cy.contains('Confirmar').click();
    });
    cy.contains('Paciente reposicionado com sucesso').should('be.visible');
  });
});
```

**Cobertura de testes**:
- Login/logout
- Dashboard: exibição, filtros, reconhecimento, reposicionamento
- Gestão de pacientes: CRUD completo
- Timeline: filtros e exibição

**Execução**: `npm run test:e2e` (CI/CD integrado)

## 3.4.14 Considerações sobre Segurança

### Medidas Implementadas:

1. **HTTPS Obrigatório**: Produção força HTTPS para criptografar comunicação
2. **JWT com Expiração**: Tokens expiram após 8 horas, exigindo re-autenticação
3. **CORS Restritivo**: Backend só aceita requisições de domínios whitelistados
4. **Sanitização de Inputs**: Todos os inputs passam por validação/escape no backend
5. **Content Security Policy**: Headers CSP previnem XSS
6. **Rate Limiting**: Backend limita taxa de requisições por IP (evita brute force)

### Limitações Conhecidas:

- **LocalStorage para Tokens**: Vulnerável a XSS (alternativa: httpOnly cookies, exige refatoração)
- **Sem Refresh Tokens**: Usuário é deslogado após expiração (melhoria futura: refresh transparente)
- **Sem 2FA**: Autenticação de fator único (aceitável para MVP, mas não ideal para produção)

## 3.4.15 Síntese

A interface web representa o ponto de contato principal entre o sistema de monitoramento e a equipe de enfermagem. Sua arquitetura prioriza **usabilidade em contexto clínico** (alertas visuais/sonoros, filtros flexíveis, ações rápidas), **confiabilidade** (tratamento de erros, fallback de polling, estados de loading claros) e **acessibilidade** (suporte a teclado, screen readers, contraste adequado).

A combinação de tecnologias modernas (React 18, TypeScript, WebSocket) com design centrado no usuário resulta em ferramenta eficaz para reduzir incidência de úlceras por pressão através de alertas oportunos e gestão eficiente de reposicionamento de pacientes acamados.

As decisões técnicas documentadas nesta seção refletem trade-offs conscientes entre complexidade, manutenibilidade e requisitos clínicos, estabelecendo base sólida para evolução futura do sistema conforme feedback de uso real em ambiente hospitalar.
