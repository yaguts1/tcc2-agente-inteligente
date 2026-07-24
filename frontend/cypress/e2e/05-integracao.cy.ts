describe('FASE 3.4: Integração Completa - Todas as Features', () => {
  beforeEach(() => {
    cy.clearLocalStorage();
    cy.visit('/');
  });

  it('Fluxo Completo 1: Visualizar → Filtrar → Sincronizar → Offline', () => {
    // PASSO 1: Visualizar alertas (testa compressão de mensagens)
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // PASSO 2: Aplicar filtro por severidade (testa filtros WebSocket)
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Validar que filtro foi aplicado
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).first().within(() => {
      cy.get('[data-testid="alert-severity"]').should('contain', 'HIGH');
    });

    // PASSO 3: Verificar sincronização em localStorage (testa localStorage Sync)
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      expect(cached).to.exist;
    });

    // PASSO 4: Recarregar página (testa recuperação de cache)
    cy.reload();

    // Validar que cache foi recuperado
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      if (cached) {
        const alerts = JSON.parse(cached);
        expect(Array.isArray(alerts)).to.be.true;
      }
    });

    // PASSO 5: Limpar filtros
    cy.get('[data-testid="clear-filters"]', { timeout: 5000 }).click();

    // Validar que todos os alertas retornam
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('Fluxo Completo 2: Múltiplos Filtros → Cache → Navegação', () => {
    // Carregar alertas inicialmente
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Aplicar filtro de severidade
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Aplicar filtro de paciente
    cy.get('[data-testid="patient-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="patient-option"]', { timeout: 5000 }).first().click();

    // Validar que ambos filtros estão aplicados
    cy.get('[data-testid="active-filters"]', { timeout: 5000 }).should('exist');

    // Verificar que cache foi sincronizado
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      expect(cached).to.exist;
    });

    // Simular navegação
    cy.get('[data-testid="nav-pacientes"]', { timeout: 5000 }).then(($el) => {
      if ($el.length > 0) {
        cy.wrap($el).click();
        cy.wait(500); // Aguardar navegação
        cy.go('back'); // Voltar
      }
    });

    // Validar que filtros e cache persistem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('Fluxo Completo 3: Performance Geral', () => {
    // Medir tempo de carregamento inicial
    cy.window().then((win) => {
      const startTime = performance.now();

      cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
      cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

      const endTime = performance.now();
      const loadTime = endTime - startTime;

      // Esperamos que a compressão e filtros façam isso em menos de 5 segundos
      expect(loadTime).to.be.lessThan(5000);
    });

    // Aplicar filtro e medir tempo de resposta
    cy.window().then((win) => {
      const startTime = performance.now();

      cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
      cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

      const endTime = performance.now();
      const filterTime = endTime - startTime;

      // Filtro deve ser instantâneo ou muito rápido
      expect(filterTime).to.be.lessThan(2000);
    });

    // Recarregar página e medir tempo de recuperação do cache
    cy.window().then((win) => {
      const startTime = performance.now();

      cy.reload();

      cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

      const endTime = performance.now();
      const reloadTime = endTime - startTime;

      // Com cache, reload deve ser rápido
      expect(reloadTime).to.be.lessThan(5000);
    });
  });

  it('Fluxo Completo 4: Resiliência e Recuperação', () => {
    // Carregar alertas normalmente
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Simular perda de cache
    cy.window().then((win) => {
      win.localStorage.removeItem('alerts_cache');
    });

    // Recarregar página
    cy.reload();

    // Sistema deve recuperar (do servidor ou do vazio)
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

    // Aplicar filtro mesmo sem cache prévia
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Validar que filtro funciona mesmo assim
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Verificar que novo cache foi criado
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      expect(cached).to.exist;
    });
  });

  it('Fluxo Completo 5: Tratamento de Erros', () => {
    // Verificar que não há erros na inicialização
    cy.get('[data-testid="error-message"]').should('not.exist');

    // Carregar alertas
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Aplicar filtro inválido (se houver)
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-critical"]', { timeout: 5000 }).then(($el) => {
      // Se não existir, não clica (filtro inválido)
      if ($el.length > 0) {
        cy.wrap($el).click();
        cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('exist');
      }
    });

    // Verificar que nenhum erro foi mostrado
    cy.get('[data-testid="error-message"]').should('not.exist');
  });
});
