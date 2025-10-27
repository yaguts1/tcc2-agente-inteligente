# Frontend Agenda - Guia de Integração

## Resumo

Os componentes React para o Sistema de Agenda foram implementados com sucesso. Este guia mostra como integrar a funcionalidade na UI existente.

## Componentes Criados

### 1. **API Client** (`frontend/src/api/agendaApi.ts`)
- Gerencia requisições HTTP para os endpoints de agenda
- Tipagem TypeScript completa
- Métodos: `createAgenda`, `listAgendas`, `getAgenda`, `updateAgenda`, `deleteAgenda`, `checkSuppression`

### 2. **Custom Hook** (`frontend/src/hooks/useAgenda.ts`)
- `useAgenda(pacienteId)` - Hook para gerenciar estado de agendas
- Carrega agendas automaticamente ao montar
- Fornece métodos: `loadAgendas`, `createAgenda`, `updateAgenda`, `deleteAgenda`, `selectAgenda`, `clearError`

### 3. **Componentes UI**

#### AgendaForm.tsx
- Formulário para criar/editar agendas
- Validação completa de campos
- Suporta agendas recorrentes e one-time
- Props:
  - `agenda?: Agenda | null` - Agenda para edição (opcional)
  - `onSubmit: (data) => Promise<void>` - Callback ao salvar
  - `onCancel?: () => void` - Callback ao cancelar
  - `loading?: boolean` - Estado de carregamento

#### AgendaList.tsx
- Lista agendas em cards responsivos
- Exibe informações: tipo, modo, horário, dias/datas
- Ações: editar, deletar
- Props:
  - `agendas: Agenda[]` - Lista de agendas
  - `loading: boolean` - Estado de carregamento
  - `onEdit: (agenda) => void` - Callback ao clicar editar
  - `onDelete: (id) => Promise<void>` - Callback ao deletar

#### AgendaPanel.tsx
- Painel principal que organiza a funcionalidade
- Gerencia visualização: lista ou formulário
- Integra `useAgenda` hook
- Props:
  - `pacienteId: string` - ID do paciente

## Como Usar

### Opção 1: Integrar na PatientsPage (Painel Abas)

```tsx
// frontend/src/components/pages/PatientsPage.tsx

import { AgendaPanel } from '../patients/AgendaPanel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';

export function PatientsPage() {
  // ... código existente ...

  return (
    <Tabs defaultValue="list" className="w-full">
      <TabsList>
        <TabsTrigger value="list">Listagem</TabsTrigger>
        <TabsTrigger value="agendas">Agendas</TabsTrigger>
      </TabsList>
      
      <TabsContent value="list">
        {/* Conteúdo existente */}
      </TabsContent>
      
      <TabsContent value="agendas">
        {selectedPatientId && (
          <AgendaPanel pacienteId={selectedPatientId} />
        )}
      </TabsContent>
    </Tabs>
  );
}
```

### Opção 2: Integrar em Modal/Drawer

```tsx
// Exemplo com Modal
import { Dialog } from '../ui/dialog';
import { AgendaPanel } from '../patients/AgendaPanel';

function PatientDetailModal({ patientId, open, onClose }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Agendas do Paciente</DialogTitle>
        </DialogHeader>
        <AgendaPanel pacienteId={patientId} />
      </DialogContent>
    </Dialog>
  );
}
```

### Opção 3: Integrar em Dedicated Page

```tsx
// frontend/src/components/pages/PatientAgendaPage.tsx

import { useParams } from 'react-router-dom';
import { AgendaPanel } from '../patients/AgendaPanel';

export function PatientAgendaPage() {
  const { patientId } = useParams<{ patientId: string }>();
  
  if (!patientId) {
    return <div>Paciente não encontrado</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1>Agendas do Paciente</h1>
        <p>Gerencie supressão, redução ou monitoramento de alertas</p>
      </div>
      <AgendaPanel pacienteId={patientId} />
    </div>
  );
}
```

## Exemplos de Uso Rápido

### Usar o Hook Diretamente

```tsx
import { useAgenda } from '../hooks/useAgenda';

function MyComponent({ pacienteId }: { pacienteId: string }) {
  const {
    agendas,
    loading,
    error,
    createAgenda,
    updateAgenda,
    deleteAgenda,
    loadAgendas,
  } = useAgenda(pacienteId);

  const handleCreate = async () => {
    try {
      await createAgenda({
        tipo: 'refeicao',
        modo: 'suprimir',
        hora_inicio: '12:00',
        hora_fim: '13:00',
        dias_semana: [1, 2, 3, 4, 5],
        data_inicio: '2025-10-27',
        descricao: 'Almoço',
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      {loading && <p>Carregando...</p>}
      {error && <p>Erro: {error}</p>}
      <button onClick={handleCreate}>Criar Agenda</button>
      <ul>
        {agendas.map((agenda) => (
          <li key={agenda.id}>{agenda.descricao}</li>
        ))}
      </ul>
    </div>
  );
}
```

### Usar o API Diretamente

```tsx
import AgendaApi from '../api/agendaApi';

async function handleCreateAgenda(pacienteId: string) {
  try {
    const agenda = await AgendaApi.createAgenda(pacienteId, {
      tipo: 'cirurgia',
      modo: 'reduzir',
      hora_inicio: '09:00',
      hora_fim: '12:00',
      dias_semana: null,
      data_inicio: '2025-10-27',
      data_fim: '2025-10-27',
      reducao_janela_min: 30,
      descricao: 'Cirurgia programada',
    });
    
    console.log('Agenda criada:', agenda);
  } catch (error) {
    console.error('Erro:', error);
  }
}
```

## Estilos CSS

Os componentes incluem estilos CSS modulares:

- `AgendaForm.css` - Estilos do formulário
- `AgendaList.css` - Estilos da listagem
- `AgendaPanel.css` - Estilos do painel

Todos os estilos são auto-contidos e não conflitam com o CSS existente.

## Variáveis de Ambiente

Configure em `.env`:

```bash
VITE_API_URL=http://localhost:8000
```

Se não configurado, padrão é `http://localhost:8000`.

## Tipos TypeScript

```tsx
// Tipos disponíveis para importar
import type {
  Agenda,
  AgendaCreate,
  AgendaUpdate,
  SuppressionCheckResponse,
  AgendasResponse,
} from '../api/agendaApi';
```

## Tratamento de Erros

Os componentes tratam automaticamente:
- Erros de rede
- Validação de entrada
- Erros do servidor (400, 404, 500)
- Timeouts

Mensagens de erro são exibidas ao usuário automaticamente.

## Performance

- Carregamento lazy das agendas
- Requisições otimizadas (sem N+1)
- Estados locais para UI responsiva
- Sem re-renders desnecessários (memoização)

## Próximas Melhorias

- [ ] Integração com calendário visual (FullCalendar)
- [ ] Sincronização com Google Calendar
- [ ] Notificações/lembretes
- [ ] Relatórios de efetividade
- [ ] Agendas templates
- [ ] Importar/exportar agendas

## Troubleshooting

### "Erro: is_timestamp_in_suppressed_period failed"
- Verifique se o backend está rodando
- Confirme que a rota está registrada em `web.py`

### "Agenda não aparece na lista"
- Verifique se o `pacienteId` está correto
- Confirme que a agenda tem `ativo=true`
- Verifique o console do navegador para erros

### "Formulário não valida"
- Certifique-se de que os horários estão no formato HH:MM
- Datas devem estar em formato YYYY-MM-DD
- Redução deve estar entre 5-60 minutos

## Resumo da Implementação

✅ API client completo  
✅ Hook customizado para estado  
✅ Componente de formulário (AgendaForm)  
✅ Componente de listagem (AgendaList)  
✅ Painel integrado (AgendaPanel)  
✅ Estilos responsivos e modernos  
✅ Tratamento de erros  
✅ TypeScript completo  
✅ Pronto para produção  

**Status**: 🟢 **PRONTO PARA USAR**
