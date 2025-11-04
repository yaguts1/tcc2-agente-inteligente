# ⚡ QUICK REFERENCE - Frontend do Projeto

**Data:** 27/10/2025  
**Leia isto PRIMEIRO antes de trabalhar no projeto**

---

## 🎯 O QUE VOCÊ PRECISA SABER

### Frontend Atual: React/TypeScript ✅

```bash
# Localização
cd frontend/

# Rodar em desenvolvimento
npm run dev

# URL
http://localhost:5173
```

**Stack:**
- ✅ React 18.3 + TypeScript
- ✅ Vite (build rápido)
- ✅ Radix UI + TailwindCSS
- ✅ Cypress (testes E2E)

---

### ⚠️ Frontend LEGADO: Jinja2/HTMX (NÃO USAR)

```bash
# Localização (NÃO EDITAR)
interface/templates/
```

**Por que não usar:**
- ❌ Tecnologia antiga
- ❌ Sem TypeScript
- ❌ Difícil manutenção
- ❌ Performance inferior
- ❌ Sem testes

---

## 📁 Estrutura do Projeto

```
tcc2-agente-inteligente/
│
├── frontend/                    ← ✅ FRONTEND MODERNO (USAR)
│   ├── src/
│   │   ├── components/
│   │   │   ├── pages/
│   │   │   │   ├── DashboardPage.tsx
│   │   │   │   ├── TimelinePage.tsx
│   │   │   │   ├── PatientsPage.tsx
│   │   │   │   └── AdminPage.tsx
│   │   │   └── ui/              (50+ componentes)
│   │   ├── hooks/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── interface/                   ← Backend + API
│   ├── api.py                   (REST API - MANTER)
│   ├── web.py                   (Server-side routes)
│   ├── dao.py                   (Database access)
│   └── templates/               ← ❌ LEGADO (NÃO USAR)
│
├── firmware/                    ← ESP32 (WebSocket client)
│   └── esp32_replay/
│       └── esp32_replay_websocket.ino
│
└── docs/
    ├── FLUXO_INFORMACAO_ESP32_FRONTEND.md
    └── FRONTEND_MODERNO_VS_LEGADO.md
```

---

## 🚀 Como Rodar o Projeto

### 1. Backend (FastAPI)

```bash
# Terminal 1
uvicorn interface.web:app --reload
```

**URL:** http://localhost:8000  
**API Docs:** http://localhost:8000/docs

### 2. Frontend (React)

```bash
# Terminal 2
cd frontend
npm run dev
```

**URL:** http://localhost:5173

---

## 🔄 Fluxo de Dados (Simplificado)

```
ESP32 Sensor
    ↓ WebSocket
Backend FastAPI (/ws/eventos)
    ↓ Process & Store
SQLite Database (eventos, alertas, timeline_events)
    ↓ REST API (JSON)
Frontend React (fetch)
    ↓ Render
UI (Dashboard, Timeline, Pacientes)
```

---

## 📚 Documentação Importante

| Documento | Descrição |
|-----------|-----------|
| **FLUXO_INFORMACAO_ESP32_FRONTEND.md** | Fluxo completo ESP32 → Frontend (atualizado para React) |
| **FRONTEND_MODERNO_VS_LEGADO.md** | Comparação detalhada, plano de migração |
| **README.md** | Instruções gerais do projeto |

---

## ✅ Checklist de Desenvolvimento

**Ao trabalhar no FRONTEND:**
- [ ] Editar apenas arquivos em `frontend/src/`
- [ ] Usar TypeScript (arquivos `.tsx` e `.ts`)
- [ ] Seguir padrão de componentes existentes
- [ ] Testar com `npm run dev`
- [ ] Rodar testes E2E: `npm run test:e2e`

**Ao trabalhar no BACKEND:**
- [ ] Editar `interface/api.py` (rotas REST)
- [ ] Manter compatibilidade JSON
- [ ] Testar endpoints em http://localhost:8000/docs
- [ ] **NÃO** editar `interface/templates/` (legado)

**Ao trabalhar no FIRMWARE:**
- [ ] Editar `firmware/esp32_replay/esp32_replay_websocket.ino`
- [ ] Conectar a `/ws/eventos`
- [ ] Enviar JSON com `device_id`, `paciente_id`, `ts_utc`, `postura`

---

## 🎨 Componentes UI Disponíveis

O frontend moderno tem **50+ componentes** prontos:

```tsx
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableHeader, TableBody, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Dialog } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
// ... e muito mais
```

**Localização:** `frontend/src/components/ui/`

---

## 🔑 Endpoints Principais da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/alerts/recent?hours=24` | GET | Alertas recentes |
| `/api/timeline?patient_id=PAC-0001` | GET | Histórico de eventos |
| `/api/frontend/patients` | GET | Lista de pacientes |
| `/api/devices` | GET | Dispositivos conectados |
| `/api/alerts/export/csv` | GET | Exportar CSV |
| `/api/frontend/alerts/{id}/acknowledge` | POST | Reconhecer alerta |
| `/ws/eventos` | WebSocket | ESP32 → Servidor |

---

## 🧪 Testes

```bash
# Testes E2E (Cypress)
cd frontend
npm run test:e2e
```

**Testes cobrem:**
- Login/Logout
- Dashboard (visualização de alertas)
- Timeline (histórico)
- Pacientes (CRUD)
- Admin (devices)

---

## 🚨 REGRAS DE OURO

1. ✅ **USE APENAS** o frontend em `frontend/` (React/TypeScript)
2. ❌ **NÃO EDITE** arquivos em `interface/templates/` (legado)
3. 🔄 **MANTENHA** a API REST em `interface/api.py`
4. 📝 **DOCUMENTE** mudanças significativas
5. 🧪 **TESTE** antes de commitar

---

## 💡 Dicas Rápidas

**Adicionar nova página:**
```tsx
// 1. Criar componente
frontend/src/components/pages/MinhaPage.tsx

// 2. Adicionar no App.tsx
import { MinhaPage } from './components/pages/MinhaPage';

// 3. Adicionar rota
case 'minha':
    return <MinhaPage />;
```

**Criar novo componente UI:**
```tsx
// frontend/src/components/MeuComponente.tsx
export function MeuComponente() {
    return <div>...</div>;
}
```

**Fazer requisição à API:**
```tsx
const response = await fetch('/api/meu-endpoint');
const data = await response.json();
```

---

**Última atualização:** 27/10/2025  
**Versão:** 2.0 (Frontend Moderno)  
**Status:** ✅ Pronto para desenvolvimento
