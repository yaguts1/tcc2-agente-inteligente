# Contexto do Sistema - Agente Inteligente de Prevenção de UPP

Este documento consolida todas as informações técnicas, arquiteturais e de negócio relevantes para o desenvolvimento e manutenção do sistema.

---

## 1. Visão Geral

O sistema é uma solução IoT completa para monitoramento e prevenção de úlceras por pressão (UPP) em pacientes hospitalares. Ele utiliza sensores de pressão (ESP32) para detectar a postura do paciente em tempo real, processa esses dados no backend para identificar imobilidade prolongada e gera alertas para a equipe de enfermagem via interface web.

### Stack Tecnológico
- **Hardware**: ESP32 com sensores de pressão (comunicação via WebSocket).
- **Backend**: Python 3.11+, FastAPI, SQLite, WebSocket, Pandas, Structlog.
- **Frontend**: React 18.3, TypeScript, Vite, Radix UI, TailwindCSS.
- **Infraestrutura**: Docker, Docker Compose.

---

## 2. Arquitetura do Sistema

A arquitetura é baseada em eventos e microsserviços lógicos dentro de um monólito modular.

### Componentes Principais
1.  **ESP32 (Sensor)**: Captura dados de pressão e envia eventos JSON via WebSocket (`/ws/eventos`).
2.  **Backend (FastAPI)**:
    *   **WebSocket Server**: Gerencia conexões com dispositivos e frontend.
    *   **Quality Filter**: Filtra ruídos e valida dados de entrada.
    *   **Alert Engine**: Processa eventos, aplica regras de negócio e gera alertas.
    *   **REST API**: Fornece endpoints para gestão de pacientes, dispositivos e dados históricos.
3.  **Banco de Dados (SQLite)**: Persistência de eventos, alertas, pacientes e configurações.
4.  **Frontend (React)**: Dashboard em tempo real, gestão de pacientes e visualização de timeline.

### Fluxo de Dados (Resumo)
1.  **Captura**: ESP32 lê sensores e envia payload JSON (`{"tipo": "postura", "valor": 1, ...}`).
2.  **Ingestão**: Backend recebe via WebSocket, autentica o dispositivo e valida o payload.
3.  **Filtragem**: Módulo de qualidade remove ruídos (jitter) e duplicatas.
4.  **Persistência**: Evento válido é salvo na tabela `eventos`.
5.  **Processamento**: Engine de Alertas avalia o histórico recente do paciente.
6.  **Decisão**: Se o tempo na mesma postura exceder o limite do perfil de risco, um alerta é gerado/atualizado.
7.  **Notificação**: Alerta é salvo e enviado via WebSocket (`/ws/alerts`) para o frontend.

---

## 3. Regras de Negócio e Motor de Decisão

O "cérebro" do sistema é o Motor de Decisão (`nucleo/decisor.py` e `modulo_alerta/engine.py`).

### Perfis de Risco
Os limites de tempo para mudança de postura dependem do perfil do paciente:
*   **Baixo Risco**: Janela de 240 minutos (4 horas).
*   **Médio Risco**: Janela de 120 minutos (2 horas).
*   **Alto Risco**: Janela de 60 minutos (1 hora).

### Lógica de Alerta
*   **Acumulador**: O sistema soma o tempo contínuo em uma mesma postura.
*   **Histerese**: Pequenas movimentações (ruído) não resetam o contador.
*   **Supressão**: Alertas podem ser suprimidos automaticamente por agendas configuradas (ex: horário de refeição, cirurgia).
*   **Estados do Alerta**:
    *   `NOVO`: Detectado, aguardando ação.
    *   `RECONHECIDO`: Enfermeiro visualizou (ACK).
    *   `RESOLVIDO`: Paciente foi reposicionado.

---

## 4. Sistema de Agenda (Supressão de Alertas)

Permite configurar períodos onde o monitoramento é pausado ou flexibilizado para evitar falsos positivos durante rotinas hospitalares.

*   **Tipos**: Refeição, Cirurgia, Procedimento, Fisioterapia.
*   **Modos**:
    *   `suprimir`: Não gera alertas.
    *   `reduzir`: Reduz o tempo limite (torna mais sensível) ou aumenta tolerância (menos sensível) - *configurável*.
    *   `monitorar`: Apenas registra, sem alertar.
*   **Recorrência**: Suporta agendamentos únicos (data específica) ou semanais (dias da semana).

---

## 5. Infraestrutura e Deployment

### Estrutura de Pastas
*   `frontend/`: Código fonte React (build gera estáticos em `dist/`).
*   `interface/`: Código fonte Backend FastAPI.
*   `dados.db`: Banco de dados SQLite (arquivo único).
*   `docker-compose.yml`: Orquestração única (dev e produção), com volume nomeado para persistir `dados.db`.

### Comandos Essenciais
*   **Build e Run (Docker)**: `docker compose up --build`
*   **Backend Dev**: `uvicorn interface.web:app --reload`
*   **Frontend Dev**: `cd frontend && npm run dev`
*   **Testes**: `pytest`

### Variáveis de Ambiente (.env)
*   `APP_PREFIX`: Prefixo da URL (ex: `/TCC`) para deploy em subdiretórios.
*   `UPP_DB_PATH`: Caminho do banco de dados.
*   `VITE_API_URL`: URL da API para o frontend (build time).

---

## 6. Pontos de Atenção para Manutenção

*   **WebSocket**: A conexão é stateful. O `ws_manager_optimized.py` gerencia a lista de clientes conectados.
*   **Banco de Dados**: SQLite é robusto para a escala atual, mas em alta concorrência de escrita pode gargalar. O código usa `WAL mode` para mitigar.
*   **Frontend Build**: O frontend é uma SPA. Em produção, o backend serve o `index.html` para qualquer rota não-API (fallback) para suportar o roteamento do React Router.

---

*Documento gerado automaticamente em 22/11/2025, consolidando a documentação do projeto.*
