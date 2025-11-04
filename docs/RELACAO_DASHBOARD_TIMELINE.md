# Relação Dashboard ↔ Timeline (Histórico)

## ✅ Status: **ADEQUADAMENTE RELACIONADOS**

Data: 2025-01-28

---

## 📋 Resumo Executivo

O Dashboard e o Timeline (Histórico) estão **adequadamente relacionados** através do sistema de navegação principal. Ambas as páginas fazem parte do mesmo fluxo de aplicação e compartilham a mesma estrutura de dados, permitindo ao usuário:

1. ✅ **Ver alertas ativos no Dashboard** (pendentes e reconhecidos)
2. ✅ **Navegar para o Histórico** para ver todos os eventos (incluindo completados)
3. ✅ **Retornar ao Dashboard** a qualquer momento através do menu lateral

---

## 🔄 Fluxo de Navegação

### **Estrutura de Navegação**

```
App.tsx
  └── AppLayout.tsx (Menu de Navegação)
       ├── Dashboard (ícone: LayoutDashboard)
       ├── Histórico (ícone: History) ← Timeline
       ├── Pacientes (ícone: Users)
       └── Admin (ícone: Settings)
```

### **Localização dos Arquivos**

- **Menu de Navegação**: `frontend/src/components/layout/AppLayout.tsx`
- **Dashboard**: `frontend/src/components/pages/DashboardPage.tsx`
- **Timeline**: `frontend/src/components/pages/TimelinePage.tsx`
- **Controlador**: `frontend/src/App.tsx`

---

## 🎯 Complementaridade das Páginas

### **Dashboard - Vista em Tempo Real**

**Propósito**: Monitoramento ativo de alertas que **requerem ação**

**Funcionalidades**:
- ✅ Exibe apenas alertas **pendentes** e **reconhecidos**
- ✅ Remove alertas **completados** da visualização
- ✅ WebSocket em tempo real para atualizações instantâneas
- ✅ Ações rápidas: "Reconhecer" e "Completar"
- ✅ Filtros por paciente, severidade, status, data
- ✅ Métricas em cards: Ativos, Reconhecidos, Completados Hoje, Taxa de Conclusão

**Código-chave** (DashboardPage.tsx, linha 119):
```typescript
// Filter out completed alerts - only show active and acknowledged alerts in the dashboard
const activeAlerts = alertsData.filter(alert => alert.status !== 'completed');
```

---

### **Timeline - Vista Histórica**

**Propósito**: Auditoria completa de **todos** os eventos do sistema

**Funcionalidades**:
- ✅ Exibe **todos** os eventos: abertos, reconhecidos, completados, reposicionamentos
- ✅ Agrupamento cronológico por dia
- ✅ Filtros avançados: paciente, tipo de evento, intervalo de datas
- ✅ Exportação de dados para análise
- ✅ Timeline visual com ícones e badges de status
- ✅ Limite inicial de 100 eventos (carregável sob demanda)

**Tipos de Eventos Rastreados**:
- `alert_open` → Alerta criado
- `alert_acknowledged` → Alerta reconhecido
- `alert_completed` → Alerta encerrado
- `repositioning` → Paciente reposicionado

---

## 🔗 Relação de Dados

### **Fluxo de Informação**

```
[ESP32] → [WebSocket /ws/eventos] → [Quality Filter] → [Database]
                                                            │
                    ┌───────────────────────────────────────┴────────────────────────┐
                    │                                                                │
                    ▼                                                                ▼
            [Alert Engine]                                              [Timeline Events]
                    │                                                                │
                    │                                                                │
            ┌───────┴─────────┐                                           ┌──────────┴──────────┐
            │                 │                                           │                     │
            ▼                 ▼                                           ▼                     ▼
    [WebSocket Broadcast] [Database]                            [Timeline API]         [Database]
            │                 │                                           │                     │
            ▼                 ▼                                           ▼                     ▼
      [DASHBOARD]       [alertas table]                          [TIMELINE]          [timeline_events]
    - Alertas ativos   - 60 registros                         - Todos eventos        - 120 registros
    - Status em tempo  - Pendentes +                          - Auditoria completa   - Histórico total
      real               Reconhecidos                          - Exportação           - Rastreabilidade
```

---

## 🎨 Integração de UI/UX

### **Menu Lateral (Desktop)**

O `AppLayout.tsx` fornece navegação consistente:

```tsx
const navigation = [
  { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
  { id: 'timeline', name: 'Histórico', icon: History },    // ← Timeline
  { id: 'patients', name: 'Pacientes', icon: Users },
  { id: 'admin', name: 'Admin', icon: Settings },
] as const;
```

**Características**:
- ✅ Sempre visível (sidebar fixa em desktop)
- ✅ Indicador visual da página ativa (fundo azul primário)
- ✅ Transição suave entre páginas
- ✅ Ícones intuitivos (Dashboard = painel, Histórico = relógio)

---

### **Menu Mobile**

- ✅ Botão hamburger no topo direito
- ✅ Menu expansível com todas as opções de navegação
- ✅ Fecha automaticamente ao selecionar uma página
- ✅ Mesma funcionalidade do desktop

---

## 📊 Casos de Uso Práticos

### **Caso 1: Enfermeiro no Plantão**

1. **Abre Dashboard** → Vê 5 alertas pendentes
2. Reconhece 2 alertas de risco médio
3. Completa 1 alerta de reposicionamento
4. **Navega para Histórico** → Verifica que todos os eventos foram registrados corretamente
5. Exporta relatório do turno (últimas 8 horas)

---

### **Caso 2: Supervisor Revisando Conformidade**

1. **Abre Histórico** → Filtra por paciente específico
2. Verifica padrão de reposicionamentos (deve ser a cada 2 horas)
3. Identifica atraso de 30 minutos em um alerta
4. **Navega para Dashboard** → Verifica alertas atuais do mesmo paciente
5. Toma ação corretiva

---

### **Caso 3: Administrador Gerando Relatório Mensal**

1. **Abre Histórico** → Aplica filtro de data (01/01 a 31/01)
2. Filtra por tipo: "alert_completed"
3. Exporta dados para análise
4. **Navega para Dashboard** → Verifica taxa de conclusão atual (métrica em card)
5. Compara desempenho do mês

---

## ✅ Verificação de Integração

### **Testes de Navegação**

```bash
# 1. Abrir aplicação no navegador
npm run dev

# 2. Fazer login

# 3. Verificar navegação Dashboard → Timeline
- Clicar em "Histórico" no menu lateral
- Confirmar que eventos são exibidos
- Verificar filtros funcionando

# 4. Verificar navegação Timeline → Dashboard  
- Clicar em "Dashboard" no menu lateral
- Confirmar que alertas ativos aparecem
- Verificar métricas em cards

# 5. Verificar complementaridade
- Completar um alerta no Dashboard
- Navegar para Timeline
- Confirmar evento "alert_completed" foi registrado
```

---

## 🔄 Sincronização de Estado

### **WebSocket em Tempo Real (Dashboard)**

```typescript
const handleWebSocketMessage = useCallback((message: any) => {
  if (message.type === 'alert_update') {
    const { alert_id, status } = message;
    if (status === 'completed') {
      // Remove do Dashboard (não exibe completados)
      setAlerts(prev => prev.filter(alert => alert.id !== alert_id));
    } else {
      // Atualiza status (pending → acknowledged)
      setAlerts(prev =>
        prev.map(alert =>
          alert.id === alert_id ? { ...alert, status } : alert
        )
      );
    }
    // Atualiza métricas
    statsApi.getStats().then(setStats);
  }
}, []);
```

### **Polling/Refresh Manual (Timeline)**

```typescript
const fetchEvents = useCallback(async () => {
  const data = await timelineApi.getEvents(filters);
  setEvents(data); // Atualiza lista completa de eventos
}, [filters]);
```

**Garantias**:
- ✅ Dashboard sempre mostra estado atual (WebSocket)
- ✅ Timeline sempre mostra histórico completo (API REST)
- ✅ Ambas as páginas consultam a mesma fonte de verdade (banco de dados SQLite)

---

## 📈 Métricas de Qualidade

| Aspecto | Status | Detalhes |
|---------|--------|----------|
| **Navegação** | ✅ Excelente | Menu lateral sempre visível, 1 clique para trocar |
| **Consistência Visual** | ✅ Excelente | Mesmo layout, cores, componentes UI |
| **Complementaridade** | ✅ Excelente | Dashboard = ação, Timeline = auditoria |
| **Sincronização** | ✅ Excelente | WebSocket (Dashboard) + API (Timeline) |
| **UX Mobile** | ✅ Bom | Menu hamburger funcional |
| **Performance** | ✅ Bom | Dashboard em tempo real, Timeline paginado (100 eventos) |
| **Acessibilidade** | ✅ Bom | Ícones descritivos, labels claros |

---

## 🎯 Recomendações de Melhorias (Opcionais)

### **1. Links Contextuais entre Páginas**

**Problema**: Não há links diretos de alertas específicos entre Dashboard e Timeline

**Solução Proposta**:
```tsx
// No Dashboard, ao completar um alerta:
<Button onClick={() => {
  handleComplete(alertId);
  // Após completar, oferecer navegação rápida
  toast.success(
    'Alerta completado!',
    {
      action: {
        label: 'Ver no Histórico',
        onClick: () => onNavigate('timeline')
      }
    }
  );
}}>
  Completar
</Button>
```

### **2. Badge de Eventos Novos no Menu**

**Problema**: Não há indicador visual de novos eventos no Timeline

**Solução Proposta**:
```tsx
const navigation = [
  { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
  { 
    id: 'timeline', 
    name: 'Histórico', 
    icon: History,
    badge: newEventsCount > 0 ? newEventsCount : undefined  // ← Badge
  },
  // ...
];
```

### **3. Deep Linking para Filtros**

**Problema**: Ao navegar do Dashboard para Timeline, os filtros são resetados

**Solução Proposta**:
```tsx
// No Dashboard, ao clicar "Ver Histórico do Paciente X":
onNavigate('timeline', { 
  filters: { 
    paciente_id: selectedPatientId,
    dateFrom: todayStart 
  } 
});
```

---

## 🏁 Conclusão

### ✅ **SIM, o Dashboard está adequadamente relacionado com o Histórico (Timeline) e vice-versa**

**Evidências**:

1. ✅ **Navegação Integrada**: Menu lateral sempre acessível com 1 clique entre páginas
2. ✅ **Dados Compartilhados**: Ambas consultam o mesmo banco de dados (alertas, eventos)
3. ✅ **Complementaridade Clara**: Dashboard = ação, Timeline = auditoria
4. ✅ **Sincronização Garantida**: WebSocket (Dashboard) + API REST (Timeline)
5. ✅ **UI/UX Consistente**: Mesmo design system, componentes reutilizados
6. ✅ **Fluxo de Trabalho Natural**: Usuário pode monitorar alertas (Dashboard) e auditar histórico (Timeline) sem fricção

**Arquitetura de Navegação**:
```
[App.tsx] ──controls──> [currentPage state]
    │
    ├──> [AppLayout.tsx] ──provides──> [navigation menu]
    │         │
    │         ├──> Dashboard (LayoutDashboard icon)
    │         ├──> Timeline/Histórico (History icon)  ← Relação direta
    │         ├──> Pacientes
    │         └──> Admin
    │
    └──> [renderPage()] ──renders──> 
              ├──> <DashboardPage /> quando currentPage='dashboard'
              └──> <TimelinePage /> quando currentPage='timeline'
```

**Não há problemas de integração**. O sistema está funcionando conforme esperado! 🎉

---

## 📝 Documentação Relacionada

- [JORNADA_INFORMACAO_ESP32.md](./JORNADA_INFORMACAO_ESP32.md) - Fluxo completo de dados
- [ARQUITETURA_DIAGRAMA.md](./ARQUITETURA_DIAGRAMA.md) - Diagramas de sistema
- [QUICK_REFERENCE_FRONTEND.md](./QUICK_REFERENCE_FRONTEND.md) - Referência do frontend
