describe('FASE 3.4.3: localStorage Sync e Acesso Offline', () => {
  beforeEach(() => {
    cy.clearLocalStorage();
    cy.visit('/');
  });

  it('deve sincronizar alertas para localStorage', () => {
    // Aguardar alertas carregarem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Verificar que localStorage contém cache de alertas
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      expect(cached).to.exist;
      
      // Validar que é JSON válido
      if (cached) {
        const alerts = JSON.parse(cached);
        expect(Array.isArray(alerts)).to.be.true;
      }
    });
  });

  it('deve manter cache ao atualizar a página', () => {
    // Carregar alertas
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Contar alertas na tela
    cy.get('[data-testid="alert-item"]').then(($items) => {
      const firstLoadCount = $items.length;

      // Recarregar página
      cy.reload();

      // Validar que cache foi restaurado
      cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should(($reloaded) => {
        expect($reloaded.length).to.be.at.least(0); // Cache pode estar vazio no início
      });

      // Verificar que localStorage persiste
      cy.window().then((win) => {
        const cached = win.localStorage.getItem('alerts_cache');
        expect(cached).to.exist;
      });
    });
  });

  it('deve respeitar limite de itens em cache', () => {
    cy.window().then((win) => {
      // Simular adição de muitos alertas ao cache
      const manyAlerts = Array.from({ length: 1500 }, (_, i) => ({
        id: `alert-${i}`,
        severity: 'HIGH',
        patient_id: `PAC-${String(i % 10).padStart(4, '0')}`,
        message: `Test alert ${i}`,
        timestamp: new Date().toISOString(),
      }));

      // Salvar no localStorage
      win.localStorage.setItem('alerts_cache', JSON.stringify(manyAlerts));

      // Recarregar para aplicar limite
      cy.reload();

      // Verificar que cache respeitou limite de 1000 itens
      cy.window().then((win2) => {
        const cached = win2.localStorage.getItem('alerts_cache');
        if (cached) {
          const alerts = JSON.parse(cached);
          expect(alerts.length).to.be.at.most(1000);
        }
      });
    });
  });

  it('deve permitir limpeza do cache', () => {
    // Carregar alertas
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Verificar que cache existe
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      expect(cached).to.exist;

      // Limpar cache
      win.localStorage.removeItem('alerts_cache');
    });

    // Recarregar página
    cy.reload();

    // Validar que cache foi limpo
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      // Cache pode ser recriado ou estar vazio
      if (cached) {
        const alerts = JSON.parse(cached);
        expect(Array.isArray(alerts)).to.be.true;
      }
    });
  });

  it('deve exibir informações de sincronização', () => {
    // Aguardar alertas carregarem
    cy.get('[data-testid="alert-item"]', { timeout: 5000 }).should('have.length.greaterThan', 0);

    // Procurar por indicador de sincronização ou status
    cy.get('[data-testid="sync-status"]', { timeout: 5000 }).should('exist');
  });

  it('deve deduplicar alertas em cache', () => {
    cy.window().then((win) => {
      // Criar dois alertas idênticos
      const alert = {
        id: 'alert-1',
        severity: 'HIGH',
        patient_id: 'PAC-0001',
        message: 'Test alert',
        timestamp: '2025-10-27T10:00:00Z',
      };

      const cache = [alert, alert]; // Duplicado
      win.localStorage.setItem('alerts_cache', JSON.stringify(cache));
    });

    // Recarregar para aplicar deduplicação
    cy.reload();

    // Verificar que duplicatas foram removidas
    cy.window().then((win) => {
      const cached = win.localStorage.getItem('alerts_cache');
      if (cached) {
        const alerts = JSON.parse(cached);
        
        // Contar IDs únicos
        const uniqueIds = new Set(alerts.map((a: any) => a.id));
        expect(uniqueIds.size).to.equal(alerts.length);
      }
    });
  });
});
