# Estratégia de Testes Completa do Sistema

## 📋 Visão Geral

Este documento descreve a **melhor estratégia** para testar todas as funcionalidades do sistema de alertas de reposicionamento.

## 🎯 Pirâmide de Testes

```
              E2E (UI)
            ↗  10%  ↖
       Integration
      ↗    20%     ↖
  Unit Tests
 ↗   70%        ↖
```

### 1. **Unit Tests (70%)** - Backend Python
Testes unitários rápidos e isolados

### 2. **Integration Tests (20%)** - API + DB
Testes de integração entre componentes

### 3. **E2E Tests (10%)** - Cypress
Testes end-to-end do fluxo completo do usuário

---

## 🔧 Ferramentas de Teste

### Backend (Python)
- **pytest** - Framework de testes
- **TestClient** (FastAPI) - Testes de API
- **fixtures** - Dados de teste

### Frontend (React)
- **Cypress** - E2E e Component Testing
- **Vitest** - Unit tests (já configurado)

---

## 📊 Cobertura de Funcionalidades

### ✅ Funcionalidades Principais

1. **Autenticação**
   - Login/Logout
   - Registro de usuário
   - Sessão expirando

2. **Dashboard**
   - Listagem de alertas
   - Filtros (severidade, status, paciente, data, busca)
   - Estatísticas (ativos, reconhecidos, completados)
   - WebSocket real-time
   - Polling fallback
   - Ações: Reconhecer, Completar alertas

3. **Timeline/Histórico**
   - Visualização de eventos por paciente
   - Filtro por tipo de evento
   - Gráfico de postura ao longo do tempo
   - Detalhes de eventos

4. **Pacientes**
   - Listagem de pacientes
   - Cadastro/Edição/Exclusão
   - Informações: Nome, Leito, Perfil de Risco
   - Simulação de dados
   - Agendas de reposicionamento
   - Exportação de dados

5. **Admin**
   - Visualização de eventos órfãos
   - Estatísticas por leito
   - Reconciliação em lote por leito
   - Indicação de paciente atual

6. **Processamento de Dados**
   - Ingestão de eventos ESP32
   - Detecção de postura
   - Geração de alertas
   - Processamento retroativo (reconciliação)
   - Timeline de eventos

---

## 🧪 Estratégia de Testes por Camada

### 1️⃣ Backend Unit Tests (70%)

**Já existentes (manter e expandir):**

#### a) Testes de Domínio/Lógica
```python
# tests/test_decisor.py - Motor de alertas
# tests/test_engine.py - Engine de processamento
# tests/test_configuracao.py - Perfis de risco
```

**O que testar:**
- ✅ Detecção de postura correta
- ✅ Geração de alertas (alto, médio, baixo risco)
- ✅ Histerese e cooldown
- ✅ Fechamento de alertas por movimento

#### b) Testes de DAO/Persistência
```python
# tests/test_dao_select_alerts.py - Queries de alertas
# tests/test_agenda_integracao.py - Agendas
```

**O que testar:**
- ✅ Inserção/Leitura de alertas
- ✅ Filtros e janelas de tempo
- ✅ Queries de pacientes por leito
- ✅ Device events órfãos

#### c) Testes de API Endpoints
```python
# tests/test_api.py - Endpoints gerais
# tests/test_api_ingestao.py - Ingestão de eventos
# tests/test_auth.py - Autenticação
```

**O que testar:**
- ✅ POST /eventos - ingestão
- ✅ GET /frontend/alerts - listagem
- ✅ POST /alerts/{id}/acknowledge - reconhecer
- ✅ POST /alerts/{id}/complete - completar
- ✅ GET /device_events/stats - estatísticas órfãos
- ✅ POST /device_events/reconcile_bed/{cama_id} - reconciliação

**CRIAR NOVOS:**
```python
# tests/test_reconciliacao_completa.py
def test_reconciliacao_cria_alertas_retroativos():
    """Testa que reconciliação processa alertas de eventos órfãos"""
    # 1. Inserir eventos órfãos com cama_id
    # 2. Cadastrar paciente no leito
    # 3. Chamar reconcileBed
    # 4. Verificar alertas criados
    # 5. Verificar timeline atualizada
    pass

def test_reconciliacao_leito_sem_paciente():
    """Testa que reconciliação falha se não há paciente no leito"""
    pass

def test_stats_agrupa_por_leito():
    """Testa que /device_events/stats agrupa corretamente"""
    pass
```

---

### 2️⃣ Integration Tests (20%)

**Já existentes:**
```python
# tests/test_websocket.py - WebSocket connection
# tests/test_export_endpoints.py - Exportação
# tests/test_lifespan_reconciler.py - Reconciliação automática
```

**CRIAR NOVOS:**

```python
# tests/test_fluxo_completo_paciente.py
def test_fluxo_completo_cadastro_ate_alerta():
    """
    Fluxo completo:
    1. Cadastrar paciente
    2. Enviar eventos de postura
    3. Verificar geração de alertas
    4. Reconhecer alerta
    5. Completar alerta
    6. Verificar timeline
    """
    pass

# tests/test_websocket_tempo_real.py
def test_websocket_notifica_dashboard_novo_alerta():
    """Testa que WebSocket envia notificação quando alerta é criado"""
    pass

def test_websocket_atualiza_status_alerta():
    """Testa que WebSocket notifica quando status muda"""
    pass

# tests/test_filtros_dashboard.py
def test_filtro_por_severidade():
    """GET /frontend/alerts?riskLevel=high"""
    pass

def test_filtro_por_status():
    """GET /frontend/alerts?status_filter=pending"""
    pass

def test_filtro_por_leito():
    """GET /frontend/alerts?room=101A"""
    pass
```

---

### 3️⃣ E2E Tests - Cypress (10%)

**Estrutura:**
```
frontend/cypress/e2e/
├── 01-auth.cy.ts                 ← Autenticação
├── 02-dashboard.cy.ts            ← Dashboard e alertas
├── 03-timeline.cy.ts             ← Histórico
├── 04-pacientes.cy.ts            ← Gestão de pacientes
├── 05-admin-reconciliacao.cy.ts ← Reconciliação
└── 06-fluxo-completo.cy.ts      ← Jornada completa
```

#### **01-auth.cy.ts**
```typescript
describe('Autenticação', () => {
  it('Deve fazer login com credenciais válidas', () => {
    cy.visit('/');
    cy.get('input[name="username"]').type('admin');
    cy.get('input[name="password"]').type('senha');
    cy.get('button[type="submit"]').click();
    cy.url().should('include', '/dashboard');
  });

  it('Deve mostrar erro com credenciais inválidas', () => {
    cy.visit('/');
    cy.get('input[name="username"]').type('invalido');
    cy.get('input[name="password"]').type('errado');
    cy.get('button[type="submit"]').click();
    cy.contains('Usuário ou senha incorretos').should('be.visible');
  });

  it('Deve fazer logout corretamente', () => {
    cy.login(); // Custom command
    cy.get('[aria-label="Logout"]').click();
    cy.url().should('eq', Cypress.config().baseUrl + '/');
  });

  it('Deve redirecionar para login se não autenticado', () => {
    cy.visit('/dashboard');
    cy.url().should('eq', Cypress.config().baseUrl + '/');
  });
});
```

#### **02-dashboard.cy.ts**
```typescript
describe('Dashboard de Alertas', () => {
  beforeEach(() => {
    cy.login();
    cy.visit('/dashboard');
  });

  it('Deve mostrar estatísticas de alertas', () => {
    cy.contains('Alertas Ativos').should('be.visible');
    cy.contains('Reconhecidos').should('be.visible');
    cy.contains('Completados Hoje').should('be.visible');
  });

  it('Deve listar alertas na tabela', () => {
    cy.get('table').should('be.visible');
    cy.get('tbody tr').should('have.length.greaterThan', 0);
  });

  it('Deve filtrar alertas por severidade', () => {
    cy.get('[data-testid="filter-severity"]').click();
    cy.contains('Alto Risco').click();
    
    // Verificar que só mostra alertas de alto risco
    cy.get('tbody tr').each(($row) => {
      cy.wrap($row).find('[data-severity="high"]').should('exist');
    });
  });

  it('Deve reconhecer um alerta', () => {
    cy.get('tbody tr').first().find('[data-action="acknowledge"]').click();
    cy.contains('Alerta reconhecido').should('be.visible');
    
    // Verificar mudança de status
    cy.get('tbody tr').first().find('[data-status="acknowledged"]').should('exist');
  });

  it('Deve completar um alerta', () => {
    cy.get('tbody tr').first().find('[data-action="complete"]').click();
    cy.contains('Paciente reposicionado com sucesso').should('be.visible');
    
    // Alerta deve desaparecer da lista
    // (ou aparecer como completado dependendo do filtro)
  });

  it('Deve buscar por nome de paciente', () => {
    cy.get('[data-testid="search-input"]').type('João Silva');
    cy.get('tbody tr').should('contain', 'João Silva');
  });

  it('Deve receber atualizações via WebSocket', () => {
    // Simular evento WebSocket
    cy.window().then((win) => {
      win.postMessage({
        type: 'alert_update',
        alert_id: 'test_123',
        status: 'acknowledged'
      }, '*');
    });
    
    // Verificar atualização na UI
    cy.get(`[data-alert-id="test_123"]`).should('have.attr', 'data-status', 'acknowledged');
  });
});
```

#### **03-timeline.cy.ts**
```typescript
describe('Timeline de Eventos', () => {
  beforeEach(() => {
    cy.login();
    cy.visit('/timeline');
  });

  it('Deve selecionar um paciente e mostrar timeline', () => {
    cy.get('[data-testid="patient-select"]').click();
    cy.contains('João Silva').click();
    
    cy.get('[data-testid="timeline-events"]').should('be.visible');
    cy.get('[data-testid="timeline-event"]').should('have.length.greaterThan', 0);
  });

  it('Deve filtrar eventos por tipo', () => {
    cy.selectPatient('João Silva');
    
    cy.get('[data-testid="filter-event-type"]').click();
    cy.contains('Alertas').click();
    
    cy.get('[data-testid="timeline-event"]').each(($event) => {
      cy.wrap($event).should('contain', 'alert');
    });
  });

  it('Deve mostrar detalhes do evento ao clicar', () => {
    cy.selectPatient('João Silva');
    cy.get('[data-testid="timeline-event"]').first().click();
    
    cy.get('[data-testid="event-details"]').should('be.visible');
    cy.contains('Timestamp').should('be.visible');
    cy.contains('Tipo').should('be.visible');
  });

  it('Deve mostrar gráfico de postura', () => {
    cy.selectPatient('João Silva');
    cy.get('[data-testid="posture-chart"]').should('be.visible');
  });
});
```

#### **04-pacientes.cy.ts**
```typescript
describe('Gestão de Pacientes', () => {
  beforeEach(() => {
    cy.login();
    cy.visit('/patients');
  });

  it('Deve listar pacientes cadastrados', () => {
    cy.get('[data-testid="patient-card"]').should('have.length.greaterThan', 0);
  });

  it('Deve cadastrar novo paciente', () => {
    cy.get('[data-testid="add-patient"]').click();
    
    cy.get('input[name="nome"]').type('Maria Santos');
    cy.get('input[name="cama_id"]').type('102B');
    cy.get('select[name="perfil"]').select('alto');
    
    cy.get('button[type="submit"]').click();
    
    cy.contains('Paciente cadastrado com sucesso').should('be.visible');
    cy.contains('Maria Santos').should('be.visible');
  });

  it('Deve editar paciente existente', () => {
    cy.get('[data-testid="patient-card"]').first().find('[data-action="edit"]').click();
    
    cy.get('input[name="nome"]').clear().type('João Silva Atualizado');
    cy.get('button[type="submit"]').click();
    
    cy.contains('Paciente atualizado com sucesso').should('be.visible');
    cy.contains('João Silva Atualizado').should('be.visible');
  });

  it('Deve executar simulação de dados', () => {
    cy.get('[data-testid="patient-card"]').first().click();
    
    cy.get('[data-testid="simulate-button"]').click();
    cy.get('input[name="horas"]').type('2');
    cy.get('button[type="submit"]').click();
    
    cy.contains('Simulação concluída', { timeout: 10000 }).should('be.visible');
    cy.contains('eventos').should('be.visible');
    cy.contains('alertas').should('be.visible');
  });

  it('Deve criar agenda de reposicionamento', () => {
    cy.get('[data-testid="patient-card"]').first().click();
    cy.get('[data-testid="add-agenda"]').click();
    
    cy.get('input[name="inicio"]').type('08:00');
    cy.get('input[name="fim"]').type('18:00');
    cy.get('select[name="acao"]').select('reduzir');
    
    cy.get('button[type="submit"]').click();
    
    cy.contains('Agenda criada com sucesso').should('be.visible');
  });
});
```

#### **05-admin-reconciliacao.cy.ts**
```typescript
describe('Admin - Reconciliação de Eventos Órfãos', () => {
  beforeEach(() => {
    cy.login();
    
    // Setup: Criar eventos órfãos de teste
    cy.request('POST', '/api/test/create-orphan-events', {
      cama_id: '101A',
      count: 10
    });
    
    cy.visit('/admin');
  });

  it('Deve mostrar estatísticas de eventos órfãos', () => {
    cy.contains('Admin - Eventos Órfãos').should('be.visible');
    cy.contains('Eventos Órfãos Detectados').should('be.visible');
  });

  it('Deve mostrar cards por leito com órfãos', () => {
    cy.get('[data-testid="bed-card"]').should('have.length.greaterThan', 0);
    
    cy.get('[data-testid="bed-card"]').first().within(() => {
      cy.contains('Leito').should('be.visible');
      cy.contains('eventos órfãos').should('be.visible');
      cy.contains('Paciente Atual').should('be.visible');
    });
  });

  it('Deve reconciliar eventos de um leito', () => {
    cy.get('[data-testid="bed-card"]').first().within(() => {
      cy.get('[data-action="reconcile"]').click();
    });
    
    // Confirmar ação
    cy.contains('Reconciliar').click();
    
    cy.contains('eventos reconciliados com sucesso').should('be.visible');
    
    // Card deve desaparecer
    cy.get('[data-testid="bed-card"]').should('have.length', 0);
    cy.contains('Nenhum evento órfão').should('be.visible');
  });

  it('Deve atualizar estatísticas ao clicar em refresh', () => {
    cy.get('[data-testid="refresh-button"]').click();
    cy.contains('Carregando').should('be.visible');
    cy.get('[data-testid="bed-card"]').should('be.visible');
  });

  it('Deve mostrar help card explicando reconciliação', () => {
    cy.contains('Como Funciona a Reconciliação').should('be.visible');
    cy.contains('Eventos Órfãos são dados de ESP32s').should('be.visible');
  });
});
```

#### **06-fluxo-completo.cy.ts**
```typescript
describe('Fluxo Completo do Sistema', () => {
  it('Jornada completa: Cadastro → Eventos → Alertas → Resolução', () => {
    // 1. Login
    cy.login();
    
    // 2. Cadastrar paciente
    cy.visit('/patients');
    cy.get('[data-testid="add-patient"]').click();
    cy.get('input[name="nome"]').type('Paciente Teste E2E');
    cy.get('input[name="cama_id"]').type('TEST-101');
    cy.get('select[name="perfil"]').select('alto');
    cy.get('button[type="submit"]').click();
    
    cy.contains('Paciente cadastrado com sucesso').should('be.visible');
    
    // 3. Simular dados (gerar eventos)
    cy.get('[data-testid="patient-card"]').contains('Paciente Teste E2E').click();
    cy.get('[data-testid="simulate-button"]').click();
    cy.get('input[name="horas"]').type('1');
    cy.get('button[type="submit"]').click();
    
    cy.contains('Simulação concluída', { timeout: 15000 }).should('be.visible');
    
    // 4. Verificar alertas no Dashboard
    cy.visit('/dashboard');
    cy.contains('Paciente Teste E2E').should('be.visible');
    
    // 5. Verificar estatísticas atualizadas
    cy.contains('Alertas Ativos').parent().should('contain', '1');
    
    // 6. Reconhecer alerta
    cy.get('tbody tr').contains('Paciente Teste E2E')
      .parent('tr')
      .find('[data-action="acknowledge"]')
      .click();
    
    cy.contains('Alerta reconhecido').should('be.visible');
    
    // 7. Verificar timeline
    cy.visit('/timeline');
    cy.get('[data-testid="patient-select"]').click();
    cy.contains('Paciente Teste E2E').click();
    
    cy.get('[data-testid="timeline-event"]').should('have.length.greaterThan', 0);
    cy.contains('alert_ack').should('be.visible');
    
    // 8. Completar alerta
    cy.visit('/dashboard');
    cy.get('tbody tr').contains('Paciente Teste E2E')
      .parent('tr')
      .find('[data-action="complete"]')
      .click();
    
    cy.contains('Paciente reposicionado com sucesso').should('be.visible');
    
    // 9. Verificar que alerta sumiu da lista ativa
    cy.get('tbody tr').should('not.contain', 'Paciente Teste E2E');
    
    // 10. Cleanup - Deletar paciente
    cy.visit('/patients');
    cy.get('[data-testid="patient-card"]').contains('Paciente Teste E2E')
      .parent()
      .find('[data-action="delete"]')
      .click();
    cy.contains('Confirmar').click();
    cy.contains('Paciente excluído').should('be.visible');
  });
});
```

---

## 🛠️ Comandos Custom do Cypress

Criar em `frontend/cypress/support/commands.ts`:

```typescript
// cypress/support/commands.ts
declare global {
  namespace Cypress {
    interface Chainable {
      login(username?: string, password?: string): Chainable<void>;
      selectPatient(patientName: string): Chainable<void>;
      createPatient(data: { nome: string; cama_id: string; perfil: string }): Chainable<void>;
    }
  }
}

Cypress.Commands.add('login', (username = 'admin', password = 'senha') => {
  cy.session([username, password], () => {
    cy.visit('/');
    cy.get('input[name="username"]').type(username);
    cy.get('input[name="password"]').type(password);
    cy.get('button[type="submit"]').click();
    cy.url().should('include', '/dashboard');
  });
});

Cypress.Commands.add('selectPatient', (patientName: string) => {
  cy.get('[data-testid="patient-select"]').click();
  cy.contains(patientName).click();
});

Cypress.Commands.add('createPatient', (data) => {
  cy.visit('/patients');
  cy.get('[data-testid="add-patient"]').click();
  cy.get('input[name="nome"]').type(data.nome);
  cy.get('input[name="cama_id"]').type(data.cama_id);
  cy.get('select[name="perfil"]').select(data.perfil);
  cy.get('button[type="submit"]').click();
  cy.contains('Paciente cadastrado com sucesso').should('be.visible');
});

export {};
```

---

## 📝 Checklist de Implementação

### Backend (Python)

- [x] test_decisor.py - Motor de alertas
- [x] test_engine.py - Processamento
- [x] test_api.py - Endpoints básicos
- [x] test_auth.py - Autenticação
- [ ] **test_reconciliacao_completa.py** - Reconciliação (CRIAR)
- [ ] **test_filtros_dashboard.py** - Filtros de alertas (CRIAR)
- [ ] **test_websocket_tempo_real.py** - Notificações WS (CRIAR)
- [ ] **test_fluxo_completo_paciente.py** - Integração completa (CRIAR)

### Frontend (Cypress E2E)

- [x] Cypress configurado
- [ ] **01-auth.cy.ts** - Login/Logout (CRIAR)
- [ ] **02-dashboard.cy.ts** - Dashboard completo (CRIAR)
- [ ] **03-timeline.cy.ts** - Histórico (CRIAR)
- [ ] **04-pacientes.cy.ts** - Gestão pacientes (CRIAR)
- [ ] **05-admin-reconciliacao.cy.ts** - Admin (CRIAR)
- [ ] **06-fluxo-completo.cy.ts** - E2E completo (CRIAR)

---

## 🚀 Como Executar

### Backend Tests

```bash
# Todos os testes
pytest

# Com cobertura
pytest --cov=interface --cov=nucleo --cov=modulo_alerta --cov-report=html

# Teste específico
pytest tests/test_reconciliacao_completa.py -v

# Com logs
pytest tests/test_api.py -v -s
```

### Frontend E2E Tests

```bash
cd frontend

# Modo interativo (recomendado para desenvolvimento)
npm run test:e2e:open

# Modo headless (CI/CD)
npm run test:e2e

# Teste específico
npx cypress run --spec "cypress/e2e/02-dashboard.cy.ts"
```

---

## 📊 Métricas de Qualidade

### Cobertura Esperada
- **Backend**: > 80% de cobertura de código
- **Frontend**: > 70% dos fluxos principais cobertos

### Performance
- Testes unitários: < 5 segundos total
- Testes de integração: < 30 segundos total
- E2E completo: < 5 minutos

---

## 🎯 Prioridades de Implementação

### Alta Prioridade (Crítico)
1. ✅ test_auth.cy.ts - Login essencial
2. ✅ test_reconciliacao_completa.py - Nova feature
3. ✅ test_dashboard.cy.ts - Funcionalidade principal
4. ✅ test_fluxo_completo.cy.ts - Validação E2E

### Média Prioridade
5. ✅ test_timeline.cy.ts
6. ✅ test_pacientes.cy.ts
7. ✅ test_filtros_dashboard.py

### Baixa Prioridade (Nice to have)
8. ✅ test_websocket_tempo_real.py
9. ✅ Testes de performance
10. ✅ Testes de acessibilidade (a11y)

---

## 💡 Dicas e Boas Práticas

### ✅ DO's

1. **Isolar testes** - Cada teste deve ser independente
2. **Usar fixtures** - Reutilizar dados de teste
3. **Limpar estado** - Sempre resetar DB entre testes
4. **Nomes descritivos** - `test_reconciliacao_cria_alertas_quando_paciente_existe`
5. **Assertions claras** - Mensagens de erro úteis
6. **Data-testid** - Usar atributos específicos no HTML

### ❌ DON'Ts

1. **Não testar implementação** - Teste comportamento
2. **Não usar sleeps** - Usar `cy.wait()` com aliases
3. **Não duplicar testes** - DRY principle
4. **Não testar bibliotecas** - Confie nas deps
5. **Não ignorar falhas** - Todos os testes devem passar

---

## 🔄 CI/CD Integration

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2

  frontend-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Cypress run
        uses: cypress-io/github-action@v5
        with:
          working-directory: frontend
          start: npm run dev
          wait-on: 'http://localhost:5173'
```

---

## 📚 Recursos Adicionais

- [Pytest Docs](https://docs.pytest.org/)
- [Cypress Best Practices](https://docs.cypress.io/guides/references/best-practices)
- [Testing Trophy](https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

---

## ✅ Conclusão

A melhor estratégia para testar TODAS as funcionalidades é:

1. **70% Unit Tests** - Rápidos, isolados, alta cobertura
2. **20% Integration** - Validam integração entre componentes
3. **10% E2E** - Simulam usuário real, validam fluxo completo

Comece pelos testes de alta prioridade e expanda gradualmente. Com esta estratégia você terá:

- ✅ Confiança no código
- ✅ Detecção rápida de bugs
- ✅ Documentação viva
- ✅ Refatoração segura
- ✅ Deploy com confiança
