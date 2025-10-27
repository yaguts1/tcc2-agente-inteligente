# 🔍 ANÁLISE CRÍTICA: Contaminação de Dados + Sistema de Reposição

**Data**: 27 de Outubro de 2025  
**Severity**: 🔴 **CRÍTICA - Afeta confiabilidade do sistema**

---

## PROBLEMA #1: Dados Contaminados no Database

### Sintoma
- Dashboard mostra "PAC-0001" com dados de testes
- Dashboard mostra eventos de 26/10 quando simulação foi executada em 27/10
- Histórico não é limpo entre testes

### Root Cause

**Arquivo**: `dados_simulados/gerador.py` linhas 205-206

```python
agora = datetime.now().replace(second=0, microsecond=0)
if inicio is None:
    inicio = agora - timedelta(hours=duracao_horas)  # ⚠️ PROBLEMA!
```

**Problema**: Quando você simula 24 horas **hoje**, o sistema gera eventos para:
- **26/10 13:30** até **27/10 13:30** (metade do passado!)

Não para **27/10 13:30** até **28/10 13:30** (futuro).

### Impacto

1. **Dashboard mostra histórico como presente**: 
   - Eventos de 26/10 aparecem no Dashboard como se fossem de hoje
   - User vê "Alertas de ontem" misturados com "alertas de hoje"

2. **Data contamination**:
   - Dados de teste antigos não são limpos
   - PAC-0001, PAC-7770, etc permanecem no BD
   - Simulações subsequentes se misturam

3. **Métricas incorretas**:
   - Alertas "Completados Hoje" pode incluir alertas de ontem
   - Taxa de conclusão imprecisa

### Solução Proposta

**Opção A (Curto prazo)**: Gerar para **FUTURO**
```python
# ANTES (⚠️ Gera para passado):
if inicio is None:
    inicio = agora - timedelta(hours=duracao_horas)

# DEPOIS (✅ Gera para futuro):
if inicio is None:
    inicio = agora  # Começa AGORA
fim = inicio + timedelta(hours=duracao_horas)  # Vai para FUTURO
```

**Opção B (Melhor prática)**: Deixar user escolher
```typescript
// Frontend: SimulationPanel.tsx
<Select value={timeMode}>
  <SelectItem value="future">Futuro (novo: agora → +24h)</SelectItem>
  <SelectItem value="past">Histórico (antigo: -24h → agora)</SelectItem>
  <SelectItem value="custom">Customizado (escolher data)</SelectItem>
</Select>
```

---

## PROBLEMA #2: Contrato Backend/Frontend - Reposição Incorreta

### Análise do Dashboard

Você vê na aba "Alertas":
```
Paciente                    Quarto/Leito    Risco        Último Repo.    Próximo Repo.    Status      Ações
Alexandre Lasthaus          201B / Leito 37  Risco Médio  17:48           15:55            Reposicionar ✓
Alexandre Lasthaus          201B / Leito 37  Risco Médio  16:56           18:25            Reposicionar ✓
PAC-0001                    /                Risco Médio  17:48           19:49            Pendente     Reconhecer
```

### Problemas Identificados

#### 1. Timestamps Passados e Futuros Misturados
- "Último Repo: 17:48" + "Próximo Repo: 15:55"
- **15:55 é ANTES de 17:48!** ❌
- Significa que "Próximo Repouso" já passou

#### 2. Coluna "Próximo Repouso" (Próximo Repouso.)
- Se gerei eventos há 2 horas, "Próximo" deveria ser FUTURO
- Aparecem tempos como "15:55" que está **no passado**
- **Root cause**: Eventos foram gerados para 26/10, e agora é 27/10

#### 3. Cálculo de "Próximo Repouso" Incorreto
- **Onde é calculado**: `interface/api.py` linhas ~800-850?
- **Como é calculado**: Deve ser `max(timestamp) + repositioningInterval`
- **Problema**: Pode estar usando timestamps passados

### Contrato Backend/Frontend Esperado

```typescript
// Frontend espera:
interface AlertaReposicionamento {
  paciente_id: string;
  nome: string;
  quarto_leito: string;
  risco: 'alto' | 'medio' | 'baixo';
  ultimo_repouso: ISO8601;        // ← DEVE SER PASSADO
  proximo_repouso: ISO8601;       // ← DEVE SER FUTURO
  intervalo_minutos: number;
  status: 'aberto' | 'reconhecido' | 'fechado';
}
```

**Validação necessária**:
```
se proximo_repouso < agora:
  ❌ ALERTA EXPIRADO (repouso deveria ter sido feito)
se proximo_repouso > agora + 24h:
  ⚠️ INTERVALO MUITO LONGO (suspeito)
se proximo_repouso < ultimo_repouso:
  ❌ ERRO LÓGICO (futuro antes do passado!)
```

---

## PROBLEMA #3: Dashboard Metrics Incorretas

### Métricas Atuais (screenshot)
```
Alertas Ativos:        4
Reconhecidos:          0
Completados Hoje:      4
Taxa de Conclusão:     50%
```

### Análise

**Código atual** (`interface/api.py` linhas 260-310):

```python
# Busca última SEMANA
all_alerts = selecionar_alertas_janela(DB_PATH, horas=168)

# Conta status
active_alerts = len([a for a in all_alerts if a.get("status") == "aberto"])
acked_alerts = len([a for a in all_alerts if a.get("status") == "reconhecido"])

# Conta só HOJE
agora = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
completed_today = len([
    a for a in all_alerts 
    if a.get("status") == "fechado" and a.get("fim") >= agora
])
```

### Problemas

1. **Janela inconsistente**:
   - activeAlerts e acked: de SEMANA (7 dias)
   - completedToday: apenas HOJE (1 dia)

2. **Métrica "Taxa de Conclusão" enganosa**:
   ```
   Taxa = completedToday / (activeAlerts + acked_alerts + completedToday)
   Taxa = 4 / (4 + 0 + 4) = 50%
   ```
   
   **Problema**: activeAlerts vem de SEMANA, completedToday vem de HOJE
   - Compara maçã com laranja
   - Se 100 alertas antigos ainda abertos, taxa fica 1%
   - Métrica não é útil

### Solução Proposta

```python
# Usar janela CONSISTENTE de 24h
agora = datetime.now()
inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)

alerts_hoje = selecionar_alertas_janela(DB_PATH, horas=24)

activeAlerts = len([a for a in alerts_hoje if a.get("status") == "aberto"])
acked_alerts = len([a for a in alerts_hoje if a.get("status") == "reconhecido"])
completed_today = len([a for a in alerts_hoje if a.get("status") == "fechado"])

# Taxa REAL de conclusão de hoje
total_alertas_hoje = activeAlerts + acked_alerts + completed_today
completion_rate = (
    (completed_today / total_alertas_hoje * 100)
    if total_alertas_hoje > 0 else 0
)

# Nova métrica: Alertas vencidos (proximo_repouso < agora)
vencidos = len([
    a for a in alerts_hoje
    if a.get("status") in ["aberto", "reconhecido"]
    and datetime.fromisoformat(a.get("proximo_repouso")) < agora
])
```

---

## PROBLEMA #4: Falta Sistema de Agenda/Schedule

### Situação Atual
- ❌ Não há forma de agendar "almoço" (14:00-15:00)
- ❌ Não há forma de bloquear "cirurgia" (10:00-12:00)
- ❌ Alertas são SEMPRE processados, mesmo durante refeições
- ❌ Sistema não é robusto para ambientes hospitalares reais

### Casos de Uso Reais

```
Paciente: Alexandre Lasthaus
Intervalo de repouso: 2h

14:00 - 15:00: ALMOÇO       [Reposicionamentos não são alertados]
15:00 - 17:00: FISIOTERAPIA  [Paciente em exercício, sem alertas]
19:00 - 20:00: JANTAR       [Reposicionamentos não são alertados]
20:00 - 06:00: NOTURNO      [Reposicionamentos normais, alertas reducidos]

Evento: 14:30 - Paciente não reposiciona
Situação Atual:  ❌ ALERTA CRÍTICO
Situação Ideal:  ✅ SEM ALERTA (está em almoço programado)
```

### Arquitetura Proposta: Sistema de Agenda

```
Pacientes Page
  ├─ Card "Alexandre Lasthaus"
  │   ├─ Dados básicos (Quarto, Leito, Risco, Intervalo)
  │   ├─ Botão "Editar"
  │   └─ 🆕 Botão "Agenda"
  │
  └─ Modal "Agenda do Paciente"
      ├─ Eventos Semanais:
      │   ├─ Segunda a Sexta
      │   │   ├─ 06:00-06:30: Café da manhã [SUPRIMIR ALERTA]
      │   │   ├─ 12:00-13:00: Almoço [SUPRIMIR ALERTA]
      │   │   ├─ 18:00-19:00: Jantar [SUPRIMIR ALERTA]
      │   │   └─ 20:00-08:00: Período Noturno [REDUZIR FREQUÊNCIA]
      │   │
      │   ├─ Terça (recorrente)
      │   │   ├─ 10:00-11:00: Fisioterapia [SUPRIMIR ALERTA]
      │   │   └─ 15:00-15:30: Curativos [REDUZIR FREQUÊNCIA]
      │   │
      │   └─ Quinta (recorrente)
      │       └─ 09:00-12:00: Cirurgia [SUPRIMIR ALERTA]
      │
      ├─ Eventos Personalizados:
      │   ├─ 27/10 14:00-16:00: Procedimento especial [SUPRIMIR ALERTA]
      │   └─ 28/10 08:00-10:00: Tomografia [SUPRIMIR ALERTA]
      │
      └─ Botões: [Salvar] [Cancelar]

Tipos de Supressão:
  • SUPRIMIR: Não processar alertas (almoço)
  • REDUZIR: Aumentar intervalo em 50% (noturno)
  • MONITORAR: Apenas notificar (sem auto-reposicionar)
```

### Schema do Banco de Dados

```sql
-- Nova tabela
CREATE TABLE agendas_paciente (
  id UUID PRIMARY KEY,
  paciente_id VARCHAR UNIQUE,
  
  -- Eventos recorrentes
  seg_ate_sex_manha: JSON,   -- [{inicio: "06:00", fim: "06:30", tipo: "suprimir"}]
  seg_ate_sex_almoco: JSON,
  seg_ate_sex_noite: JSON,
  
  -- Eventos semanais
  terca_fisioterapia: JSON,
  quinta_cirurgia: JSON,
  
  -- Eventos personalizados (data específica)
  eventos_customizados: JSON, -- [{data: "2025-10-27", inicio: "14:00", fim: "16:00", tipo: "suprimir"}]
  
  criado_em: TIMESTAMP,
  atualizado_em: TIMESTAMP,
  criado_por: VARCHAR
);
```

### API Proposta

```
POST   /api/pacientes/{id}/agenda
GET    /api/pacientes/{id}/agenda
PATCH  /api/pacientes/{id}/agenda
DELETE /api/pacientes/{id}/agenda/{event_id}

GET    /api/pacientes/{id}/proximo-alerta
  Retorna: próximo alerta considerando a agenda
  {
    proximo_repouso: ISO8601,
    suprimido_por: string | null,  // "almoço", "cirurgia", etc
    tipo_supressao: "suprimir" | "reduzir" | "monitorar"
  }
```

### Lógica de Processamento de Alertas

```python
# Antes (simples):
if tempo_sem_repouso > intervalo:
    gerar_alerta()

# Depois (robusto):
def processar_repouso(paciente_id, timestamp):
    # 1. Verificar se está em período agendado
    agenda = obter_agenda(paciente_id)
    periodo = agenda.encontrar_periodo(timestamp)
    
    if periodo:
        match periodo.tipo_supressao:
            case "suprimir":
                # Não gera alerta
                registrar_evento("suppressed", periodo.nome)
                return None
            case "reduzir":
                # Aumenta intervalo
                intervalo *= 1.5
            case "monitorar":
                # Apenas log, sem alerta
                registrar_evento("monitored", periodo.nome)
    
    # 2. Calcular próximo repouso
    tempo_sem_repouso = timestamp - ultimo_repouso
    if tempo_sem_repouso > intervalo:
        alerta = gerar_alerta()
        registrar_evento("alert_generated", alerta)
        return alerta
    
    return None
```

---

## RESUMO: Arquitetura de Reposição Robusta

### Atual (❌ Frágil)
```
Frontend                Backend
─────────────────────────────────
ListarAlerts() ────────→ Busca BD
                        Calcula próxima
                        Retorna lista
                   ←──── Exibe
```

**Problemas**:
- Timestamps misturados (passado/futuro)
- Sem contexto hospitalar
- Métricas inconsistentes
- Dados antigos não limpos

### Proposto (✅ Robusto)
```
Frontend                         Backend
───────────────────────────────────────────────
GerenciarPaciente ────→ Criar/editar
                       Gerenciar agenda
                       (refeições, cirurgias)
                   
ListarAlerts() ────────→ Busca eventos
                        Filtra por agenda
                        Calcula com supressão
                        Retorna com timestamps corretos
                   ←──── Exibe com contexto

Dashboard ─────────────→ Calcula métricas consistentes
(24h)                  (janela uniforme)
                   ←──── Taxa real de conclusão
```

**Benefícios**:
- ✅ Timestamps consistentes
- ✅ Contexto hospitalar integrado
- ✅ Métricas precisas
- ✅ Data clean & segregation
- ✅ Pronto para produção

---

## Recomendações Imediatas

### 1️⃣ Crítico (Hoje)
- [ ] Limpar dados antigos do BD (PAC-0001, testes antigos)
- [ ] **Corrigir gerador**: Simular para FUTURO (opção A proposta)
- [ ] Testar com dados de 27/10 apenas

### 2️⃣ Importante (Esta semana)
- [ ] Corrigir Dashboard metrics (usar janela consistente de 24h)
- [ ] Validar cálculos de "Próximo Repouso"
- [ ] Revisar contrato Backend/Frontend

### 3️⃣ Futuro (Sprints próximos)
- [ ] Implementar sistema de Agenda
- [ ] Adicionar supressão de alertas
- [ ] Criar interface de gerenciamento de agenda

---

**Status**: 🔴 **ANÁLISE COMPLETA - AÇÃO NECESSÁRIA**
