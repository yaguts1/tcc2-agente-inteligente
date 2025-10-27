# 📅 DESIGN: Sistema de Agenda/Schedule - Supressão de Alertas

## 1. Visão Geral

Sistema para agendar períodos onde alertas de repouso **NÃO** são processados ou são processados com tolerância reduzida.

**Casos de Uso**:
- ⏰ Refeições (almoço, jantar, café)
- 🏥 Procedimentos (cirurgias, exames)
- 👨‍⚕️ Atendimento médico
- 🚶 Fisioterapia/reabilitação
- 😴 Sono previsto

---

## 2. Arquitetura do Banco de Dados

### Tabela: `agendas_paciente`

```sql
CREATE TABLE agendas_paciente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    tipo TEXT NOT NULL,  -- 'refeicao', 'cirurgia', 'procedimento', 'atendimento', 'outro'
    descricao TEXT,
    
    -- Recorrência semanal (segunda a domingo)
    -- Se NULL, é um agendamento único (data_inicio)
    dias_semana TEXT,  -- JSON: [0,1,2,3,4,5,6] ou null
    
    -- Horários
    hora_inicio TEXT,  -- HH:MM
    hora_fim TEXT,     -- HH:MM
    
    -- Para agendamentos únicos (não recorrentes)
    data_inicio TEXT,  -- YYYY-MM-DD (ISO)
    data_fim TEXT,     -- YYYY-MM-DD (ISO, se multi-dia)
    
    -- Configuração
    modo TEXT DEFAULT 'suprimir',  -- 'suprimir' | 'reduzir' | 'monitorar'
    reducao_janela_min INTEGER,  -- Se modo='reduzir', reduz janela em X minutos
    
    ativo BOOLEAN DEFAULT 1,
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (paciente_id) REFERENCES fichas_paciente(paciente_id)
);

-- Índices
CREATE INDEX idx_agendas_paciente_id ON agendas_paciente(paciente_id);
CREATE INDEX idx_agendas_ativo ON agendas_paciente(ativo);
```

---

## 3. API Endpoints

### 3.1 Criar Agenda

```
POST /api/pacientes/{paciente_id}/agenda
```

**Corpo (Recorrente - Semanal)**:
```json
{
  "tipo": "refeicao",
  "descricao": "Almoço",
  "dias_semana": [1, 2, 3, 4, 5],  // Seg-Sex
  "hora_inicio": "12:00",
  "hora_fim": "13:00",
  "modo": "suprimir"
}
```

**Corpo (Único - Data Específica)**:
```json
{
  "tipo": "cirurgia",
  "descricao": "Cirurgia de joelho",
  "data_inicio": "2025-10-28",
  "data_fim": "2025-10-29",
  "hora_inicio": "08:00",
  "hora_fim": "16:00",
  "modo": "suprimir"
}
```

**Resposta (201)**:
```json
{
  "id": 1,
  "paciente_id": "PAC-001",
  "tipo": "refeicao",
  "descricao": "Almoço",
  "dias_semana": [1, 2, 3, 4, 5],
  "hora_inicio": "12:00",
  "hora_fim": "13:00",
  "modo": "suprimir",
  "ativo": true,
  "created_at": "2025-10-27T16:00:00"
}
```

---

### 3.2 Listar Agendas

```
GET /api/pacientes/{paciente_id}/agenda
```

**Query Params**:
- `ativo` (bool): Apenas ativas (default: true)

**Resposta (200)**:
```json
[
  {
    "id": 1,
    "tipo": "refeicao",
    "descricao": "Almoço",
    "dias_semana": [1, 2, 3, 4, 5],
    "hora_inicio": "12:00",
    "hora_fim": "13:00",
    "modo": "suprimir",
    "ativo": true
  },
  {
    "id": 2,
    "tipo": "cirurgia",
    "descricao": "Cirurgia de joelho",
    "data_inicio": "2025-10-28",
    "data_fim": "2025-10-29",
    "hora_inicio": "08:00",
    "hora_fim": "16:00",
    "modo": "suprimir",
    "ativo": true
  }
]
```

---

### 3.3 Atualizar Agenda

```
PATCH /api/pacientes/{paciente_id}/agenda/{agenda_id}
```

**Corpo**: Campos a atualizar (cualquier subset dos campos acima)

```json
{
  "ativo": false,
  "descricao": "Almoço tardio"
}
```

---

### 3.4 Deletar Agenda

```
DELETE /api/pacientes/{paciente_id}/agenda/{agenda_id}
```

---

### 3.5 Verificar se está em Período Suprimido

```
GET /api/pacientes/{paciente_id}/agenda/ativo?timestamp={ISO_TIMESTAMP}
```

**Resposta (200)**:
```json
{
  "em_periodo_suprimido": true,
  "agendas_ativas": [
    {
      "id": 1,
      "tipo": "refeicao",
      "descricao": "Almoço",
      "hora_inicio": "12:00",
      "hora_fim": "13:00",
      "modo": "suprimir"
    }
  ],
  "modo_resultado": "suprimir"
}
```

---

## 4. Lógica de Processamento

### 4.1 Função: Verificar Período Suprimido

```python
def is_timestamp_in_suppressed_period(
    db_path: str,
    paciente_id: str,
    timestamp: datetime
) -> tuple[bool, str]:
    """
    Verifica se timestamp está dentro de período suprimido.
    
    Args:
        db_path: Caminho do banco
        paciente_id: ID do paciente
        timestamp: Timestamp para verificar
        
    Returns:
        (is_suppressed: bool, modo: str)
        
    Lógica:
    1. Buscar agendas ativas para paciente
    2. Para cada agenda:
        a. Se recorrente (dias_semana):
            - Verificar se dia_da_semana coincide
            - Verificar se hora coincide
        b. Se única (data_inicio/fim):
            - Verificar se data está no intervalo
            - Verificar se hora coincide
    3. Se múltiplas agendas:
        - Se alguma é 'suprimir' → retorna (True, 'suprimir')
        - Caso contrário → retorna (True, 'reduzir' ou 'monitorar')
    """
```

---

### 4.2 Integração com Engine de Alertas

**Antes**:
```python
# modulo_alerta/engine.py
alertas = processar_alertas(grade, perfil, paciente_id)
```

**Depois**:
```python
# modulo_alerta/engine.py
alertas = processar_alertas(grade, perfil, paciente_id)

# NOVO: Filtrar alertas suprimidos
alertas_filtrados = []
for alerta in alertas:
    timestamp_alerta = alerta['inicio']
    
    is_suppressed, mode = is_timestamp_in_suppressed_period(
        DB_PATH, paciente_id, timestamp_alerta
    )
    
    if is_suppressed:
        if mode == 'suprimir':
            continue  # Pula o alerta
        elif mode == 'reduzir':
            # Reduz janela_min em configurado
            alerta['janela_min'] = max(5, alerta['janela_min'] - reduction)
        elif mode == 'monitorar':
            # Marca como "monitorado" (não suprime, apenas marca)
            alerta['monitorado'] = True
    
    alertas_filtrados.append(alerta)

return alertas_filtrados
```

---

## 5. Frontend UI

### 5.1 Modal de Agenda (Nova Página)

**Localização**: `/pacientes/{id}/agenda`

**Componentes**:
1. **Tabs**:
   - Recorrentes (Semanal)
   - Únicos (Data Específica)

2. **Recorrentes**:
   - Dropdown: Tipo (Refeição, Cirurgia, etc)
   - Input: Descrição
   - Days Picker: Seg-Dom (checkboxes)
   - Time Picker: Hora Início
   - Time Picker: Hora Fim
   - Dropdown: Modo (Suprimir, Reduzir, Monitorar)
   - Button: "Adicionar"

3. **Lista de Agendas**:
   - Card por agenda
   - Mostrar: Tipo, Descrição, Dias/Data, Horas, Modo
   - Botões: Edit, Delete, Toggle Ativo

---

### 5.2 Exemplo Visual

```
┌─────────────────────────────────────────┐
│  📅 Agenda de Supressão de Alertas      │
├─────────────────────────────────────────┤
│ [Recorrentes] [Únicos]                  │
├─────────────────────────────────────────┤
│                                         │
│ ▢ Tipo: [Refeição ▼]                  │
│ ▢ Descrição: [Almoço]                  │
│ ▢ Dias: [✓Seg ✓Ter ✓Qua ✓Qui ✓Sex]   │
│ ▢ Hora: [12:00] até [13:00]           │
│ ▢ Modo: [Suprimir ▼]                  │
│                                         │
│ [+ Adicionar Agenda]                   │
├─────────────────────────────────────────┤
│ Agendas Ativas:                         │
│                                         │
│ 🍽️ Almoço (Seg-Sex 12:00-13:00)        │
│    Modo: Suprimir                       │
│    [Edit] [Delete] [Pausar]            │
│                                         │
│ 🏥 Cirurgia (28/10 08:00-16:00)        │
│    Modo: Suprimir                       │
│    [Edit] [Delete] [Pausar]            │
│                                         │
│ 👨‍⚕️ Atendimento (Terça 14:00-15:00)      │
│    Modo: Reduzir (10 min)              │
│    [Edit] [Delete] [Pausar]            │
│                                         │
└─────────────────────────────────────────┘
```

---

## 6. Tipos de Agenda Padrão

| Tipo | Descrição | Modo Padrão | Duração Típica |
|------|-----------|------------|-----------------|
| **refeicao** | Café, Almoço, Jantar | Suprimir | 1h |
| **cirurgia** | Procedimento cirúrgico | Suprimir | 2-4h |
| **procedimento** | Exame, fisioterapia | Reduzir | 30min-1h |
| **atendimento** | Consulta médica | Suprimir | 30min-1h |
| **outro** | Customizado | Monitorar | Conforme |

---

## 7. Validações

1. **Horários**: `hora_inicio < hora_fim`
2. **Dias Semana**: Array válido [0-6]
3. **Datas**: `data_inicio <= data_fim` (se multi-dia)
4. **Janela Redução**: Entre 5 e 60 minutos
5. **Modo**: 'suprimir' | 'reduzir' | 'monitorar'
6. **Tipo**: Um dos tipos predefinidos

---

## 8. Casos de Uso - Exemplos

### Exemplo 1: Refeição Recorrente
```json
{
  "tipo": "refeicao",
  "descricao": "Almoço",
  "dias_semana": [1, 2, 3, 4, 5],
  "hora_inicio": "12:00",
  "hora_fim": "13:00",
  "modo": "suprimir"
}
```

**Resultado**: Todo dia de semana às 12h, alertas são suprimidos.

---

### Exemplo 2: Cirurgia (Dia Específico)
```json
{
  "tipo": "cirurgia",
  "descricao": "Cirurgia de joelho",
  "data_inicio": "2025-10-28",
  "hora_inicio": "08:00",
  "hora_fim": "16:00",
  "modo": "suprimir"
}
```

**Resultado**: No dia 28/10 de 08:00-16:00, alertas são suprimidos.

---

### Exemplo 3: Procedimento com Redução
```json
{
  "tipo": "procedimento",
  "descricao": "Fisioterapia",
  "dias_semana": [1, 3, 5],
  "hora_inicio": "14:00",
  "hora_fim": "15:00",
  "modo": "reduzir",
  "reducao_janela_min": 10
}
```

**Resultado**: Seg/Qua/Sex às 14h, janela de alerta reduz em 10 minutos.

---

## 9. Implementação - Roadmap

### Fase 1: Backend (1-2 dias)
- [x] Schema de banco de dados
- [ ] Endpoints CRUD
- [ ] Função: `is_timestamp_in_suppressed_period()`
- [ ] Integração com engine de alertas
- [ ] Testes

### Fase 2: Frontend (1-2 dias)
- [ ] Componentes de UI
- [ ] Modal/Página de Agenda
- [ ] Integração com API
- [ ] Validações de formulário

### Fase 3: Testes e Deploy (1 dia)
- [ ] Testes end-to-end
- [ ] Validação em produção
- [ ] Documentação

---

## 10. Benefícios

✅ **Reduz Falsos Positivos**: Não gera alertas durante refeições
✅ **Flexível**: Suprime, reduz ou apenas monitora
✅ **Recorrente**: Configurar 1x, vale para sempre
✅ **Único**: Cirurgias e procedimentos específicos
✅ **Hospitalar**: Essencial para ambiente real

---

## 11. Considerações Futuras

- 🔄 Múltiplos horários por dia
- 📊 Analytics: Verificar suppressão
- 🔔 Notificações: Alertar sobre eventos suprimidos
- ⚠️ Override: Usuário pode forçar alerta
- 📱 Mobile: App para staff configurar agendas

---

*Design Document - Sistema de Agenda/Schedule*
*TCC2 - Sistema de Monitoramento Hospitalar*
*Data: 27/10/2025*
