/// <reference types="cypress" />

// Custom commands for E2E tests
// Note: Commands are registered dynamically and don't need type definitions

// Login as admin user
Cypress.Commands.add('loginAsAdmin', () => {
  cy.visit('/auth/login');
  cy.get('input[type="email"]').type('admin@example.com');
  cy.get('input[type="password"]').type('admin123');
  cy.get('button[type="submit"]').click();
});

// Login as specific user
Cypress.Commands.add('loginAsUser', (email: string, password: string) => {
  cy.visit('/auth/login');
  cy.get('input[type="email"]').type(email);
  cy.get('input[type="password"]').type(password);
  cy.get('button[type="submit"]').click();
});

// Clear browser localStorage
Cypress.Commands.add('clearLocalStorage', () => {
  cy.window().then((win) => {
    win.localStorage.clear();
  });
});

// Prevent uncaught exceptions from failing tests
Cypress.on('uncaught:exception', (err) => {
  if (err.message.includes('ResizeObserver loop limit exceeded')) {
    return false;
  }
  return true;
});
