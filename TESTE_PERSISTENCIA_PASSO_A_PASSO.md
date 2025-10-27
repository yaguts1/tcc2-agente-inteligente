# 🧪 TESTE DE PERSISTÊNCIA DE AGENDAS - GUIA PASSO A PASSO

**Data**: 27 de Outubro de 2025  
**Objetivo**: Validar que agendas persistem após a correção do bug  
**Tempo Estimado**: 15 minutos  

---

## ✅ PRÉ-REQUISITOS

- [ ] Backend rodando em `http://localhost:8000`
- [ ] Frontend rodando em `http://localhost:5173`
- [ ] Database vazio ou com dados de teste (PAC-0001)

---

## 🚀 PROCEDIMENTO DE TESTE

### Fase 1: Limpar Database Anterior (Opcional)

Se desejar começar do zero:

```bash
# Windows
del database.db

# Mac/Linux
rm database.db
```

**Efeito**: Próxima execução cria novo banco

---

### Fase 2: Abrir Interface

1. Abra browser: `http://localhost:5173`
2. Navigate: **Pacientes** (menu principal)
3. Localize: **PAC-0001** (primeira linha)
4. Clique: **📅 Agendas** (novo botão)

**Esperado**: Painel de agendas abre, lista vazia ou com agendas anteriores

---

### Fase 3: TESTE 1 - Criar Primeira Agenda

#### Passo 1: Clicar em "Criar Agenda"

- Clique no botão: **+ Criar Agenda**

**Esperado**: Formulário abre com campos vazios

#### Passo 2: Preencher Formulário

| Campo | Valor | Descrição |
|-------|-------|-----------|
| **Tipo** | Refeição | Comida do paciente |
| **Descrição** | Café da manhã | Texto livre |
| **Modo** | Suprimir | Supressa de alertas |
| **Data Início** | Hoje | Usar data picker |
| **Hora Início** | 08:00 | Manhã |
| **Hora Fim** | 09:00 | 1 hora de duração |
| **Recorrência** | - | Deixar vazio (one-time) |

**Foto esperada**:
```
┌─────────────────────────┐
│ + Criar Agenda          │
├─────────────────────────┤
│ Tipo: [Refeição       ▼]│
│ Descrição: Café...      │
│ Data: [2025-10-27    ] │
│ Início: [08:00       ] │
│ Fim: [09:00          ] │
│ Modo: [Suprimir     ▼] │
│ [Salvar]  [Cancelar]   │
└─────────────────────────┘
```

#### Passo 3: Salvar

- Clique: **Salvar Agenda**

**Esperado**:
- ✅ Sem erro no console
- ✅ Formulário desaparece
- ✅ Agenda aparece na lista
- ✅ ID visível (ex: #5)

**Resultado**: ✅ AGENDA 1 CRIADA

---

### Fase 4: TESTE 2 - Validar Persistência (Refresh)

#### Passo 1: Refrescar página

- Tecle: `F5` (ou Ctrl+R)
- Aguarde: Carregamento completo

**Esperado**:
- ✅ Página recarrega
- ✅ Paciente PAC-0001 ainda visível
- ✅ Clique em **📅 Agendas** novamente

#### Passo 2: Verificar Lista

**Esperado**:
- ✅ Lista NÃO está vazia
- ✅ Agenda criada ainda existe
- ✅ Mesmo ID (#5 ou similar)
- ✅ Mesmos dados (Refeição, 08:00-09:00)

**Resultado**: ✅ PERSISTÊNCIA VALIDADA

---

### Fase 5: TESTE 3 - Criar Segunda Agenda (Recorrente)

#### Passo 1: Clicar "+ Criar Agenda"

#### Passo 2: Preencher Diferente

| Campo | Valor |
|-------|-------|
| **Tipo** | Cirurgia |
| **Descrição** | Cirurgia agendada |
| **Modo** | Reduzir |
| **Data Início** | Amanhã |
| **Hora Início** | 14:00 |
| **Hora Fim** | 15:30 |
| **Janela Redução** | 30 min |
| **Dias Semana** | Seg, Ter, Qua (0,1,2) |

#### Passo 3: Salvar

**Esperado**: Agenda 2 aparece na lista

---

### Fase 6: TESTE 4 - Testar Edição

#### Passo 1: Clicar em Agenda para Editar

- Clique em primeira agenda criada
- Ou botão "✏️ Editar"

#### Passo 2: Modificar Campo

Mude: **Descrição** para "Café da manhã às 8h"

#### Passo 3: Salvar Mudanças

**Esperado**: Agenda atualizada na lista

#### Passo 4: Refrescar

Tecle `F5` novamente

**Esperado**: Mudança persiste após refresh

**Resultado**: ✅ EDIÇÃO FUNCIONA

---

### Fase 7: TESTE 5 - Testar Deleção

#### Passo 1: Selecionar Agenda

Clique em segunda agenda (Cirurgia)

#### Passo 2: Deletar

- Clique botão: **🗑️ Deletar**
- Confirme: Pop-up de confirmação

**Esperado**: 
- ✅ Agenda remove da lista
- ✅ Sem erro

#### Passo 3: Refrescar

Tecle `F5`

**Esperado**:
- ✅ Agenda deletada não aparece
- ✅ Primeira agenda (Refeição) ainda existe

**Resultado**: ✅ DELEÇÃO FUNCIONA

---

### Fase 8: TESTE 6 - Validar Backend Diretamente

Abra novo terminal:

```bash
# Testar GET (Lista)
curl http://localhost:8000/api/pacientes/PAC-0001/agenda

# Testar POST (Criar)
curl -X POST http://localhost:8000/api/pacientes/PAC-0001/agenda \
  -H "Content-Type: application/json" \
  -d '{
    "tipo": "atendimento",
    "modo": "monitorar",
    "hora_inicio": "10:00",
    "hora_fim": "11:00",
    "data_inicio": "2025-10-28"
  }'

# Testar GET (Obter específica)
curl http://localhost:8000/api/pacientes/PAC-0001/agenda/5
```

**Esperado**:
- ✅ Status 200 em todos
- ✅ Dados retornam corretamente
- ✅ IDs incrementam

---

## 📊 CHECKLIST DE VALIDAÇÃO

### Frontend
- [ ] Agendas criam sem erro
- [ ] Agendas aparecem na lista
- [ ] Agendas persistem após refresh
- [ ] Edição atualiza dados
- [ ] Deleção remove da lista
- [ ] Sem erros no console (F12)

### Backend
- [ ] POST retorna 201 com agenda criada
- [ ] GET retorna 200 com lista
- [ ] GET específica retorna agenda correta
- [ ] PATCH atualiza campos
- [ ] DELETE retorna 204
- [ ] Logs mostram operações

### Database
- [ ] SQLite recebe inserts
- [ ] Dados persistem entre processos
- [ ] Sem corrupção de dados

---

## 🚨 TROUBLESHOOTING

### Problema: "Lista vazia após criar"

**Solução 1**: Verificar console (F12)
```
- Buscar erro vermelho
- Anotar mensagem
- Consultar PERSISTENCIA_AGENDA_CORRIGIDA.md
```

**Solução 2**: Testar API diretamente
```bash
curl http://localhost:8000/api/pacientes/PAC-0001/agenda
```

**Solução 3**: Verificar network (F12 → Network)
- POST request retorna 201?
- Response tem ID?
- GET request retorna array?

### Problema: "Erro ao salvar: CORS"

**Solução**: Verificar VITE_API_URL
```bash
# Abrir arquivo
cat frontend/.env

# Deve ter
VITE_API_URL=http://localhost:8000
```

### Problema: "Refresh não persiste"

**Indicador**: Bug ainda existe!

**Ação**: Voltar para PERSISTENCIA_AGENDA_CORRIGIDA.md

**Verificar**:
1. Arquivo `frontend/src/api/agendaApi.ts` modificado?
2. Função `listAgendas()` tem novo código?
3. Frontend foi recompilado? (Ctrl+Shift+R força refresh)

---

## ✅ TESTES PASSANDO

Quando tudo funciona:

```
TESTE 1: Criar agenda          ✅ PASS
TESTE 2: Persistência (refresh)✅ PASS
TESTE 3: Criar recorrente      ✅ PASS
TESTE 4: Editar               ✅ PASS
TESTE 5: Deletar              ✅ PASS
TESTE 6: API Backend          ✅ PASS

RESULTADO: AGENDAS FUNCIONANDO 100% ✅
```

---

## 📝 DOCUMENTAÇÃO DE RESULTADO

Quando terminar os testes, execute:

```bash
# Capturar resultado
git status
git log --oneline -5

# Criar arquivo de teste
echo "TESTE REALIZADO: $(date)" >> test_results.log
```

---

## 🎯 PRÓXIMO PASSO

Após validar tudo:

1. ✅ **Fase 1 Completa**: Persistência validada
2. ↓
3. **Próximo**: Executar suite de testes (`test_agenda_integracao.py`)

---

**Bom teste! 🚀**

Quando terminar, confirme aqui o resultado:
- ✅ Tudo funcionando?
- ⚠️ Algum erro?
- ❌ Crítico descoberto?

