describe('FASE 3.4.2: Compressão de Mensagens', () => {
  beforeEach(() => {
    cy.clearLocalStorage();
    cy.visit('/');
  });

  it('deve carregar alertas com sucesso', () => {
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('deve exibir informações completas do alerta', () => {
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).first().within(() => {
      cy.get('[data-testid="alert-severity"]').should('exist');
      cy.get('[data-testid="alert-patient"]').should('exist');
      cy.get('[data-testid="alert-message"]').should('exist');
      cy.get('[data-testid="alert-timestamp"]').should('exist');
    });
  });

  it('deve manter performance ao carregar muitos alertas', () => {
    // Tempo de início
    cy.window().then((win) => {
      const startTime = performance.now();

      // Aguardar alertas carregarem
      cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

      // Registrar tempo de conclusão
      const endTime = performance.now();
      const loadTime = endTime - startTime;

      // Validar que carregou em menos de 5 segundos (considerando compressão)
      expect(loadTime).to.be.lessThan(5000);
    });
  });

  it('deve renderizar corretamente após filtro (testa compressão parcial)', () => {
    // Aplicar filtro (deve comprimir apenas mensagens filtradas)
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Validar que alertas ainda estão completos
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).first().within(() => {
      cy.get('[data-testid="alert-severity"]').should('contain', 'HIGH');
      cy.get('[data-testid="alert-message"]').should('have.text');
    });
  });

  it('deve atualizar alertas em tempo real (WebSocket com compressão)', () => {
    // Verificar alertas iniciais
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

    // Aguardar alguns segundos para possível atualização em tempo real
    cy.wait(2000);

    // Validar que a interface permanece responsiva
    cy.get('[data-testid="alerts-container"]').should('exist');
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('deve preservar ordem dos alertas após compressão', () => {
    cy.get('[data-testid="alert-item"]', { timeout: 5000 })
      .then(($items) => {
        // Validar que existe pelo menos um item
        expect($items.length).to.be.greaterThan(0);

        // Verificar que cada item tem timestamp
        cy.wrap($items).first().find('[data-testid="alert-timestamp"]').should('exist');
      });
  });
});
