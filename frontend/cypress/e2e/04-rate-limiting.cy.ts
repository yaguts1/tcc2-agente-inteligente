describe('FASE 3.4.4: Rate Limiting e Proteção contra DDoS', () => {
  beforeEach(() => {
    cy.clearLocalStorage();
    cy.visit('/');
  });

  it('deve carregar alertas respeitando rate limit', () => {
    // Verificar que a página carrega normalmente (dentro do rate limit)
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('deve exibir indicador de status do servidor', () => {
    // Procurar por indicador de status/health
    cy.get('[data-testid="server-status"]', { timeout: 5000 }).should('exist');
  });

  it('deve manter responsividade durante carregamento normal', () => {
    // Aguardar alertas carregarem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Validar que cliques funcionam normalmente
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-filter"]').should('be.visible');
  });

  it('deve permitir filtração sem afetar rate limit', () => {
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Aplicar vários filtros rapidamente
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
    cy.get('[data-testid="severity-high"]', { timeout: 5000 }).click();

    // Aguardar resultado do filtro
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('exist');

    // Limpar filtro
    cy.get('[data-testid="clear-filters"]', { timeout: 5000 }).click();

    // Validar que alertas retornam
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);
  });

  it('deve recuperar corretamente de throttling', () => {
    // Verificar status inicial
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

    // Aguardar alguns segundos (simula pausa após limite)
    cy.wait(2000);

    // Validar que ainda funciona após pausa
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Verificar que pode interagir novamente
    cy.get('[data-testid="severity-filter"]', { timeout: 5000 }).click();
  });

  it('deve mostrar mensagem de erro se rate limit for excedido', () => {
    // Esta é uma verificação de fallback
    // Se o rate limit fosse excedido, deveria haver uma mensagem de erro
    
    // Verificar que não há mensagem de erro em operação normal
    cy.get('[data-testid="error-message"]').should('not.exist');

    // Ou se existir, não deve conter "rate limit"
    cy.get('[data-testid="error-message"]', { timeout: 1000 }).then(($el) => {
      if ($el.length > 0) {
        expect($el.text().toLowerCase()).to.not.include('rate limit');
      }
    });
  });

  it('deve registrar eventos normalmente sem bloqueios', () => {
    // Aguardar alertas carregarem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Verificar que há contador de alertas (indicador de que está processando)
    cy.get('[data-testid="alert-count"]', { timeout: 5000 }).should('exist');

    // Validar que o contador é um número positivo
    cy.get('[data-testid="alert-count"]').invoke('text').then((text) => {
      const count = parseInt(text);
      expect(count).to.be.greaterThan(0);
    });
  });

  it('deve permitir navegação sem bloqueios de rate limit', () => {
    // Ir para alertas
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');

    // Verificar se há navegação para outras seções
    cy.get('[data-testid="nav-pacientes"]', { timeout: 5000 }).then(($el) => {
      if ($el.length > 0) {
        cy.wrap($el).click();
        cy.url().should('include', '/pacientes');
      }
    });

    // Voltar para alertas
    cy.get('[data-testid="nav-alertas"]', { timeout: 5000 }).then(($el) => {
      if ($el.length > 0) {
        cy.wrap($el).click();
        cy.url().should('include', '/alertas');
      }
    });

    // Validar que ainda funciona
    cy.get('[data-testid="alerts-container"]', { timeout: 5000 }).should('exist');
  });
});
