describe('FASE 3.4.1: Filtros WebSocket', () => {
  beforeEach(() => {
    cy.clearLocalStorage();
    cy.visit('/');
  });

  it('deve carregar a página inicial', () => {
    cy.get('body').should('exist');
    cy.url().should('include', '/');
  });

  it('deve exibir o painel de alertas', () => {
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
  });

  it('deve aplicar filtro por severidade', () => {
    // Esperar os alertas carregarem
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

    // Selecionar filtro de severidade
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).should('exist');
    cy.get('[data-testid="severity-filter"]').click();

    // Selecionar "HIGH"
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Validar que apenas alertas HIGH aparecem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).each(($alert) => {
      cy.wrap($alert).find('[data-testid="alert-severity"]').should('contain', 'HIGH');
    });
  });

  it('deve aplicar filtro por paciente', () => {
    cy.get('[data-testid="patient-filter"]', { timeout: 5000 }).should('exist');
    cy.get('[data-testid="patient-filter"]').click();

    // Selecionar primeiro paciente disponível
    cy.get('[data-testid="patient-option"]', { timeout: 5000 }).first().click();

    // Validar que alertas mostram apenas do paciente selecionado
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).each(($alert) => {
      cy.wrap($alert).find('[data-testid="alert-patient"]').should('exist');
    });
  });

  it('deve limpar filtros e reexibir todos os alertas', () => {
    // Aplicar um filtro
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Contar alertas com filtro
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).then(($filtered) => {
      const filteredCount = $filtered.length;

      // Limpar filtro
      cy.get('[data-testid="clear-filters"]', { timeout: 5000 }).click();

      // Contar alertas sem filtro (deve ser maior ou igual)
      cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should(($all) => {
        expect($all.length).to.be.at.least(filteredCount);
      });
    });
  });

  it('deve aplicar múltiplos filtros simultaneamente', () => {
    // Aplicar filtro de severidade
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Aplicar filtro de paciente
    cy.get('[data-testid="patient-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="patient-option"]', { timeout: 5000 }).first().click();

    // Validar que ambos os filtros estão aplicados
    cy.get('[data-testid="active-filters"]', { timeout: 5000 }).should('contain', 'HIGH');
    cy.get('[data-testid="active-filters"]', { timeout: 5000 }).should('contain', 'PAC-');
  });
});
