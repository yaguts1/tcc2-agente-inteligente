# Sistema de Prevenção de Úlceras por Pressão (UPP)

**Sistema inteligente para monitoramento e prevenção de úlceras por pressão em pacientes hospitalares**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue.svg)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/yaguts1/tcc2-agente-inteligente.git
cd tcc2-agente-inteligente

# 2. Setup backend
python -m venv venv
venv\Scripts\activate  # Windows (use source venv/bin/activate no Linux/Mac)
pip install -r requirements.txt
python -c "from interface.dao import criar_esquema; criar_esquema('dados.db')"

# 3. Setup frontend
cd frontend && npm install && cd ..

# 4. Executar (escolha uma opção)

# Opção A - Script automático (Windows)
.\START_DEV.ps1

# Opção B - Manual
# Terminal 1 (Backend): uvicorn interface.web:app --reload
# Terminal 2 (Frontend): cd frontend && npm run dev

# 5. Acessar
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

### 🎯 Demonstração Rápida

```powershell
# Iniciar todos os serviços de uma vez
.\iniciar_tudo.ps1

# Preparar dados de demonstração
.\preparar_demo.ps1

# Verificar saúde do sistema
.\verificar_sistema.ps1
```

📖 **Guia completo de demonstração:** [`docs/GUIA_DEMONSTRACAO.md`](docs/GUIA_DEMONSTRACAO.md)

---

## 📋 Índice

- [Visão Geral](#-visão-geral)
- [Demonstração](#-demonstração)
- [Arquitetura](#️-arquitetura)
- [Funcionalidades](#-funcionalidades)
- [Tecnologias](#️-tecnologias)
- [Instalação Detalhada](#-instalação-detalhada)
- [Como Executar](#-como-executar)
- [Documentação](#-documentação)
- [API Reference](#-api-reference)
- [Testes](#-testes)
- [Deployment](#-deployment)
- [Estrutura do Projeto](#-estrutura-do-projeto)

---

## � Demonstração

### Opção 1: Setup Automático (Recomendado)

```powershell
# 1. Iniciar todos os serviços
.\iniciar_tudo.ps1

# 2. Preparar dados de demonstração
.\preparar_demo.ps1

# 3. Acessar o sistema
# → Frontend: http://localhost:5173
# → API Docs: http://127.0.0.1:8000/docs
```

### Opção 2: Demonstração Manual

1. **Iniciar Serviços**
   ```powershell
   # Terminal 1 - Backend
   .\venv\Scripts\python.exe -m uvicorn interface.web:app --reload
   
   # Terminal 2 - Frontend
   cd frontend
   npm run dev
   ```

2. **Gerar Dados de Teste**
   ```powershell
   # Paciente alto risco (24h de dados)
   .\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-ALTO 24 alto
   ```

3. **Explorar Funcionalidades**
   - **Dashboard**: Visualize alertas ativos e estatísticas
   - **Timeline**: Veja histórico de eventos de postura
   - **Pacientes**: Gerencie cadastro e perfis de risco
   - **Admin**: Reconcilie eventos órfãos de dispositivos

### 📊 Cenários de Demonstração

| Cenário | Descrição | Script |
|---------|-----------|--------|
| **Clínico Básico** | Dashboard + Alertas + Timeline | `preparar_demo.ps1` |
| **Técnico** | APIs + WebSocket + Reconciliação | Ver [`docs/GUIA_DEMONSTRACAO.md`](docs/GUIA_DEMONSTRACAO.md) |
| **Performance** | Carga de eventos em massa | Ver seção 4.5 do guia |
| **Integração IoT** | ESP32 real enviando dados | Ver [`docs/JORNADA_INFORMACAO_ESP32.md`](docs/JORNADA_INFORMACAO_ESP32.md) |

### 🔍 Verificação de Saúde

```powershell
# Verificar se tudo está funcionando
.\verificar_sistema.ps1

# Saída esperada:
# ✓ Backend: OK
# ✓ Frontend: OK
# ✓ Banco de Dados: OK
# ✓ Python Environment: OK
# ✓ Node.js: OK
# ✓ WebSocket: OK
```

📖 **Guia Completo:** [`docs/GUIA_DEMONSTRACAO.md`](docs/GUIA_DEMONSTRACAO.md)

---

## �🎯 Visão Geral

Sistema IoT completo para prevenção de úlceras por pressão em pacientes hospitalizados, integrando:

- **🔌 Hardware**: ESP32 com sensores de postura
- **⚡ Backend**: FastAPI com processamento em tempo real
- **💻 Frontend**: React SPA moderna e responsiva
- **🚨 Alertas**: Sistema inteligente baseado em perfil de risco

### Problema

Úlceras por pressão (UPP) afetam milhões de pacientes hospitalizados anualmente, causando:
- Dor e sofrimento
- Aumento do tempo de internação
- Custos elevados para o sistema de saúde
- Risco de infecções graves

### Solução

Monitoramento contínuo e automático da postura do paciente com:
- Detecção de imobilidade prolongada
- Alertas inteligentes para equipe médica
- Histórico completo de eventos
- Dashboard em tempo real

---

## 🏗️ Arquitetura

```
┌─────────────┐
│   ESP32     │  WebSocket (/ws/eventos)
│  (Sensor)   │─────────────────┐
└─────────────┘                 │
                                ▼
                    ┌───────────────────────┐
                    │   Backend (FastAPI)   │
                    │                       │
                    │  • WebSocket Server   │
                    │  • REST API           │◄─────┐
                    │  • Engine de Alertas  │      │
                    │  • Processamento      │      │
                    └───────────────────────┘      │
                                │                  │
                                ▼                  │
                    ┌───────────────────────┐      │
                    │   SQLite Database     │      │
                    │  • eventos            │      │
                    │  • alertas            │      │
                    │  • timeline_events    │      │
                    │  • pacientes          │      │
                    │  • devices            │      │
                    └───────────────────────┘      │
                                                   │
┌──────────────────────────────────────────────────┘
│  HTTP/JSON (REST API)
│
▼
┌───────────────────────┐
│  Frontend (React)     │
│  • Dashboard          │
│  • Timeline           │
│  • Pacientes          │
│  • Configuração       │
└───────────────────────┘
```

### Fluxo de Dados

1. **ESP32** → Captura postura e envia via WebSocket
2. **Backend** → Processa evento, detecta imobilidade
3. **Engine** → Avalia regras e gera alertas
4. **Database** → Persiste eventos e alertas
5. **Frontend** → Exibe alertas e timeline em tempo real
6. **Equipe Médica** → Recebe notificação e toma ação

---

## ✨ Funcionalidades

### 🔍 Monitoramento em Tempo Real
- Recepção contínua de dados do ESP32
- Processamento incremental de eventos
- Detecção automática de mudanças de postura
- Timeline visual de todos os eventos

### 🚨 Sistema de Alertas Inteligente
- **3 Perfis de Risco** (janela padrão, configurável por variável de ambiente):
  - Baixo: 120 min sem mudança
  - Médio: 90 min sem mudança
  - Alto: 60 min sem mudança
- Cooldown configurável (10 min padrão)
- Estados: NOVO, RECONHECIDO, RESOLVIDO
- Notificações prioritárias

### 👤 Gestão de Pacientes
- Cadastro completo (nome, leito, perfil de risco)
- Vinculação com dispositivos ESP32
- Upload de documentos (PDF, imagens)
- Rotinas de cuidado personalizadas

### 📅 Agendamento de Supressão
- Suprimir alertas durante procedimentos
- Redução de sensibilidade temporária
- Suporte a rotinas recorrentes
- Evita alarmes desnecessários

### 📊 Relatórios e Exportação
- Exportação em CSV e PDF
- Filtros por paciente, data e status
- Gráficos de eventos por dia
- Auditoria completa

### 🔐 Segurança e Autenticação
- Sistema de login
- Sessões seguras
- Controle de acesso
- Logs estruturados

---

## 🛠️ Tecnologias

### Backend
| Tecnologia | Versão | Uso |
|-----------|--------|-----|
| **Python** | 3.11+ | Linguagem principal |
| **FastAPI** | Latest | Framework web assíncrono |
| **SQLite** | 3 | Banco de dados |
| **WebSockets** | - | Comunicação em tempo real |
| **Prometheus** | - | Métricas e monitoramento |
| **structlog** | - | Logging estruturado |
| **pandas** | - | Processamento de dados |
| **pytest** | - | Testes automatizados |

### Frontend
| Tecnologia | Versão | Uso |
|-----------|--------|-----|
| **React** | 18.3 | Biblioteca UI |
| **TypeScript** | 5.x | Type safety |
| **Vite** | 6.3.5 | Build tool ultra-rápido |
| **Radix UI** | - | Componentes acessíveis |
| **TailwindCSS** | - | Utility-first CSS |
| **vitest** | - | Testes unitários |
| **Cypress** | - | Testes E2E |

### Hardware
| Tecnologia | Uso |
|-----------|-----|
| **ESP32** | Microcontrolador IoT |
| **Arduino** | Framework de desenvolvimento |
| **WebSocket Client** | Comunicação com servidor |

---

## 📦 Instalação Detalhada

### Pré-requisitos

- **Python 3.11+** ([Download](https://www.python.org/downloads/))
- **Node.js 18+** ([Download](https://nodejs.org/))
- **Git** ([Download](https://git-scm.com/))

### 1. Clonar Repositório

```bash
git clone https://github.com/yaguts1/tcc2-agente-inteligente.git
cd tcc2-agente-inteligente
```

### 2. Configurar Backend

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# Windows PowerShell
venv\Scripts\activate
# Windows CMD
venv\Scripts\activate.bat
# Linux/Mac
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Criar banco de dados
python -c "from interface.dao import criar_esquema; criar_esquema('dados.db')"
```

### 3. Configurar Frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Variáveis de Ambiente (Opcional)

Criar arquivo `.env` na raiz:

```env
# Backend
UPP_DB_PATH=dados.db
REDIS_URL=redis://localhost:6379/0

# Frontend (build time)
VITE_API_URL=http://localhost:8000

# Production
CORS_ORIGINS=https://seu-dominio.com
```

---

## 🏃 Como Executar

### Desenvolvimento Local

#### Opção 1: Script Automático (Windows)

```powershell
.\START_DEV.ps1
```

Este script inicia automaticamente backend e frontend.

#### Opção 2: Manual

**Terminal 1 - Backend:**
```bash
# Ativar venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Executar FastAPI
uvicorn interface.web:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### Acessar Aplicação

| Serviço | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **Backend API** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API Docs (ReDoc)** | http://localhost:8000/redoc |
| **Métricas (Prometheus)** | http://localhost:8000/metrics |

### Credenciais

No primeiro acesso, criar conta através da interface de registro.

---

## 📚 Documentação

### Documentos Técnicos

| Documento | Descrição |
|-----------|-----------|
| [QUICK_REFERENCE_FRONTEND.md](docs/QUICK_REFERENCE_FRONTEND.md) | Referência rápida para desenvolvimento frontend |
| [FLUXO_INFORMACAO_ESP32_FRONTEND.md](docs/FLUXO_INFORMACAO_ESP32_FRONTEND.md) | Fluxo completo ESP32 → Frontend |
| [FRONTEND_MODERNO_VS_LEGADO.md](docs/FRONTEND_MODERNO_VS_LEGADO.md) | Comparação arquitetural |
| [GUIA_BUILD_DEPLOYMENT.md](GUIA_BUILD_DEPLOYMENT.md) | Build e deployment |
| [CHECKLIST_DEPLOY_PRODUCAO.md](CHECKLIST_DEPLOY_PRODUCAO.md) | Checklist de produção |

---

## 🔌 API Reference

### Principais Endpoints

#### Autenticação
```http
POST /api/auth/login
POST /api/auth/register
POST /api/auth/logout
```

#### Alertas
```http
GET  /api/alerts/recent?hours=24
POST /api/frontend/alerts/{id}/acknowledge
POST /api/frontend/alerts/{id}/complete
GET  /api/alerts/export/csv?start_date=2025-01-01&end_date=2025-01-31
GET  /api/alerts/export/pdf?patient_id=PAC-0001
```

#### Timeline
```http
GET /api/timeline?patient_id=PAC-0001&limit=100
```

#### Pacientes
```http
GET    /api/frontend/patients
POST   /api/frontend/patients
PUT    /api/frontend/patients/{id}
DELETE /api/frontend/patients/{id}
```

#### Devices
```http
GET  /api/devices
POST /api/devices/register
PUT  /api/devices/{device_id}/link?patient_id=PAC-0001
```

#### WebSocket
```websocket
WS /ws/eventos   # ESP32 → Backend
WS /ws/alerts    # Backend → Frontend
```

### Exemplo de Uso

```python
import requests

# Listar alertas recentes
response = requests.get('http://localhost:8000/api/alerts/recent?hours=24')
alerts = response.json()

# Reconhecer alerta
requests.post('http://localhost:8000/api/frontend/alerts/1/acknowledge')
```

---

## 🧪 Testes

### Backend (Python)

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=interface --cov=nucleo --cov=modulo_alerta

# Testes específicos
pytest tests/test_api.py
pytest tests/test_decisor.py -v

# Teste de integração
pytest tests/test_main_batch.py
```

### Frontend (React)

```bash
cd frontend

# Testes E2E com Cypress
npm run test:e2e

# Modo interativo
npm run test:e2e:open
```

### Testes Manuais

```bash
# Simular eventos ESP32
python dados_simulados/gerador.py

# Testar exportação
python scripts_demo/test_export_files.py
```

---

## 🚢 Deployment

### Docker (Recomendado)

```bash
cp .env.example .env   # ajuste JWT_SECRET_KEY e demais variáveis
docker compose up --build
```

Isso builda o frontend, sobe a API em `http://localhost:8000` (docs em `/docs`, app em `/TCC/`) e também um proxy Caddy em `http://localhost` / `https://localhost` (HTTPS local autoassinado), com o banco SQLite, uploads e backups persistidos no volume nomeado `app_data`. Todas as variáveis de ambiente estão documentadas em `.env.example`.

Para subir em produção numa VM na nuvem com HTTPS automático (Let's Encrypt) via domínio real, siga [`GUIA_BUILD_DEPLOYMENT.md`](GUIA_BUILD_DEPLOYMENT.md).

### Manual

#### Build Frontend
```bash
cd frontend
npm run build
cd ..
```

O build gera arquivos em `frontend/build/` que devem ser servidos pelo backend.

#### Executar Backend (Produção)
```bash
# Com Gunicorn (recomendado)
gunicorn interface.web:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000

# Ou Uvicorn direto
uvicorn interface.web:app --host 0.0.0.0 --port 8000
```

#### Configuração Nginx (Opcional)

```nginx
server {
    listen 80;
    server_name seu-dominio.com;
    
    # Frontend (arquivos estáticos)
    location / {
        root /path/to/frontend/build;
        try_files $uri $uri/ /index.html;
    }
    
    # API Backend
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 📁 Estrutura do Projeto

```
tcc2-agente-inteligente/
│
├── frontend/                    # Frontend React/TypeScript
│   ├── src/
│   │   ├── components/          # Componentes React
│   │   │   ├── pages/           # Dashboard, Pacientes, Timeline
│   │   │   └── ui/              # Componentes Radix UI
│   │   ├── hooks/               # Custom hooks
│   │   ├── App.tsx              # Componente raiz
│   │   └── main.tsx             # Entry point
│   ├── public/                  # Arquivos estáticos
│   ├── package.json
│   └── vite.config.ts
│
├── interface/                   # Backend FastAPI
│   ├── api.py                   # REST API endpoints
│   ├── web.py                   # FastAPI app + WebSocket
│   ├── dao.py                   # Database access layer
│   ├── dao_agenda.py            # Agenda DAO
│   ├── endpoints_agenda.py      # Agenda endpoints
│   └── ws_manager_optimized.py  # WebSocket manager
│
├── nucleo/                      # Lógica de negócio
│   └── decisor.py               # Motor de decisão de alertas
│
├── modulo_alerta/               # Sistema de alertas
│   └── engine.py                # Engine de processamento
│
├── servicos/                    # Serviços auxiliares
│   ├── processamento_incremental.py
│   ├── metricas.py
│   └── backup.py
│
├── quality/                     # Filtros de qualidade
│   └── filtro.py
│
├── ferramentas/                 # Ferramentas
│   └── exportador_jsonl.py
│
├── firmware/                    # Firmware ESP32
│   └── esp32_replay/
│       └── esp32_replay_websocket.ino
│
├── dados_simulados/             # Dados para testes
│   └── gerador.py
│
├── tests/                       # Testes automatizados
│   ├── test_api.py
│   ├── test_decisor.py
│   └── ...
│
├── docs/                        # Documentação
│   ├── FLUXO_INFORMACAO_ESP32_FRONTEND.md
│   ├── QUICK_REFERENCE_FRONTEND.md
│   └── ...
│
├── requirements.txt             # Dependências Python
├── pytest.ini                   # Config pytest
├── docker-compose.yml           # Docker Compose
├── Dockerfile                   # Docker build
└── README.md                    # Este arquivo
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

### Convenções

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Lint Python**: `ruff` (config em `pyproject.toml`; roda no CI como job advisory)
- **Type-check TypeScript**: `tsc --noEmit` (`npm run typecheck`, roda no CI)
- **Testes**: Sempre adicionar testes para novas funcionalidades

---

## 📄 Licença

Este projeto está licenciado sob a MIT License - veja [LICENSE](LICENSE) para detalhes.

---

## 👥 Autores

- **Thiago Nogueira Marcondes** - [yaguts1](https://github.com/yaguts1)

---

## 📞 Suporte

- **Issues**: [GitHub Issues](https://github.com/yaguts1/tcc2-agente-inteligente/issues)
- **Documentação**: Pasta `docs/`
- **API Docs**: http://localhost:8000/docs

---

## 🎓 Contexto Acadêmico

Trabalho de Conclusão de Curso (TCC) - Engenharia de Computação

**Objetivo**: Desenvolver sistema IoT completo para prevenção de UPP usando:
- Internet das Coisas (ESP32)
- Processamento em tempo real (FastAPI)
- Interface moderna (React)
- Machine Learning (detecção de padrões)

---

**Versão**: 2.0.0  
**Última atualização**: 27/10/2025  
**Status**: ✅ Em desenvolvimento ativo
