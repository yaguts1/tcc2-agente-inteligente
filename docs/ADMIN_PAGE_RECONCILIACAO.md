# AdminPage - Reconciliação de Eventos Órfãos

## Visão Geral

A página Admin foi completamente reimplementada para trabalhar com a arquitetura correta onde **cada leito possui um ESP32 fixo**. A reconciliação agora é feita por leito (cama_id), não por dispositivos móveis.

## Arquitetura

### Conceito de Eventos Órfãos

**Eventos Órfãos** são dados de sinais vitais recebidos de ESP32s em leitos sem paciente cadastrado.

Acontece quando:
- ESP32 já está enviando dados antes do cadastro do paciente
- Há atraso no cadastro após a internação
- ESP32 está em teste ou manutenção
- Paciente foi transferido mas novo paciente ainda não cadastrado

### Fluxo de Reconciliação

```
1. ESP32 envia payload com cama_id
2. Backend busca paciente atual do leito
3. Se não há paciente → evento fica órfão
4. Ao cadastrar paciente no leito
5. Admin pode reconciliar eventos órfãos
6. Eventos são processados retroativamente
   - Criação de timeline
   - Análise de alertas
   - Associação ao paciente
```

## Interface da AdminPage

### Layout

A página exibe um **dashboard de leitos** com:

1. **Header**
   - Título "Admin - Eventos Órfãos"
   - Botão "Atualizar" para refresh
   - Descrição breve

2. **Alert de Resumo**
   - Aparece se há eventos órfãos
   - Mostra total de eventos e número de leitos afetados

3. **Grid de Cards por Leito**
   - Layout responsivo (1 col mobile, 2 tablet, 3 desktop)
   - Um card por leito com eventos órfãos
   - Cada card mostra:
     - Ícone de leito + ID do leito
     - Badge com contagem de eventos órfãos
     - Paciente atual (nome) ou "Leito vazio"
     - Período dos eventos (primeira e última data)
     - Botão "Reconciliar" (se há paciente) ou alert pedindo cadastro

4. **Card de Ajuda**
   - Explica o que são eventos órfãos
   - Lista quando acontecem
   - Descreve o que a reconciliação faz

### Estados da UI

#### Loading State
```tsx
- Skeleton de 6 cards
- Header com texto "Carregando estatísticas..."
```

#### Empty State
```tsx
- Card com mensagem "Nenhum evento órfão"
- Ícone de check
- "Todos os eventos estão associados a pacientes"
```

#### Error State
```tsx
- ErrorBanner com mensagem de erro
- Botões "Tentar Novamente" e "Dispensar"
```

#### Reconciling State
```tsx
- Botão do leito específico mostra spinner
- Texto "Reconciliando..."
- Botão desabilitado
```

## Backend - Endpoints

### GET /device_events/stats

Retorna estatísticas de eventos órfãos agrupados por leito.

**Response:**
```json
{
  "total_orphans": 15,
  "beds": [
    {
      "cama_id": "101A",
      "count": 8,
      "first_event": "2024-01-20T08:30:00",
      "last_event": "2024-01-20T12:45:00",
      "current_patient": {
        "id": "123",
        "name": "João Silva"
      }
    },
    {
      "cama_id": "102B",
      "count": 7,
      "first_event": "2024-01-20T09:00:00",
      "last_event": "2024-01-20T11:30:00",
      "current_patient": null
    }
  ]
}
```

**Lógica:**
1. Busca todos eventos órfãos (processed_at IS NULL)
2. Extrai cama_id do payload
3. Agrupa por cama_id
4. Para cada leito:
   - Conta eventos
   - Pega primeira e última data
   - Busca paciente atual via `obter_ficha_por_cama()`

### POST /device_events/reconcile_bed/{cama_id}

Reconcilia TODOS os eventos órfãos de um leito específico.

**Parameters:**
- `cama_id`: ID do leito (path param)

**Response:**
```json
{
  "message": "15 eventos reconciliados com sucesso",
  "processed_count": 15,
  "failed_count": 0
}
```

**Lógica:**
1. Busca eventos órfãos do leito
2. Busca paciente atual do leito
3. Para cada evento:
   - Marca como processado
   - Processa retroativamente (timeline + alertas)
4. Retorna contagem de sucessos/falhas

## Frontend - Implementação

### Componente AdminPage.tsx

**Estado:**
```tsx
const [bedStats, setBedStats] = useState<BedStats[]>([]);
const [isLoading, setIsLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [reconcilingBed, setReconcilingBed] = useState<string | null>(null);
```

**Funções Principais:**

#### fetchStats()
```tsx
- Chama deviceEventsApi.getStats()
- Atualiza bedStats com resposta
- Calcula totalOrphans
- Trata erros
```

#### handleReconcileBed(camaId, patientName)
```tsx
- Mostra confirmação com nome do paciente
- Chama deviceEventsApi.reconcileBed(camaId)
- Mostra toast de sucesso
- Recarrega estatísticas
- Trata erros
```

#### formatDateTime(isoString)
```tsx
- Formata data/hora para pt-BR
- Formato: DD/MM/YYYY HH:MM
```

### API Client (lib/api.ts)

**Tipos:**
```typescript
interface BedStats {
  cama_id: string;
  count: number;
  first_event: string;
  last_event: string;
  current_patient: {
    id: string;
    name: string;
  } | null;
}

interface DeviceEventsStats {
  total_orphans: number;
  beds: BedStats[];
}

interface ReconcileResponse {
  message: string;
  processed_count: number;
  failed_count?: number;
}
```

**Métodos:**
```typescript
deviceEventsApi.getStats(): Promise<DeviceEventsStats>
deviceEventsApi.reconcileBed(camaId: string): Promise<ReconcileResponse>
```

## Fluxo de Uso

### Cenário: Cadastro Atrasado

1. **Situação Inicial:**
   - ESP32 do leito 101A enviando dados desde 08:00
   - Paciente João só cadastrado às 10:00
   - 120 eventos órfãos acumulados (08:00 - 10:00)

2. **Admin Acessa Página:**
   - Vê card do leito 101A
   - Badge mostra "120 eventos órfãos"
   - Paciente atual: João Silva
   - Período: 20/01/2024 08:00 - 20/01/2024 10:00

3. **Admin Clica "Reconciliar":**
   - Confirmação: "Reconciliar 120 eventos para João Silva?"
   - Confirma

4. **Sistema Processa:**
   - 120 eventos associados ao João
   - Timeline retroativa criada (08:00 - 10:00)
   - Alertas analisados no período
   - Toast: "120 eventos reconciliados com sucesso"

5. **Card do Leito Desaparece:**
   - Não há mais eventos órfãos
   - Dados agora visíveis no Dashboard/Timeline

## Testes

### Teste Manual

1. **Preparação:**
   ```python
   # Inserir eventos órfãos
   python insert_retroactive_events.py
   ```

2. **Verificar Stats:**
   ```bash
   curl http://localhost:8000/device_events/stats
   ```

3. **Acessar Admin:**
   - Navegar para /admin
   - Verificar cards de leitos

4. **Reconciliar:**
   - Clicar "Reconciliar" em um leito
   - Confirmar
   - Verificar toast de sucesso

5. **Validar:**
   - Card deve desaparecer
   - Acessar Timeline do paciente
   - Verificar eventos retroativos aparecem

### Teste Automatizado

```bash
python testar_reconciliacao_cama_id.py
```

Valida:
- Extração de cama_id do payload
- Lookup de paciente por leito
- Processamento retroativo
- Criação de timeline
- Análise de alertas

## Diferenças da Versão Anterior

### ❌ Versão Antiga (Incorreta)
- Baseada em device_assignments
- Conceito de dispositivos móveis
- Tabela device_assignments
- Reconciliação individual por evento
- Interface de lista de eventos

### ✅ Versão Nova (Correta)
- Baseada em cama_id do payload
- ESP32 fixo por leito
- Sem tabela de associações
- Reconciliação em lote por leito
- Interface de dashboard por leito

## Vantagens da Nova Arquitetura

1. **Simplicidade:** Sem gerenciamento de associações
2. **Performance:** Reconciliação em lote
3. **UX Melhor:** Dashboard visual por leito
4. **Alinhamento:** Reflete realidade física (ESP32 fixo)
5. **Manutenção:** Menos código, menos bugs

## Referências

- `docs/ARQUITETURA_ESP32_LEITO_PACIENTE.md` - Arquitetura geral
- `docs/JORNADA_INFORMACAO_ESP32.md` - Fluxo de dados ESP32
- `interface/api.py` - Endpoints de reconciliação
- `frontend/src/components/pages/AdminPage.tsx` - UI da página
- `testar_reconciliacao_cama_id.py` - Testes de reconciliação
