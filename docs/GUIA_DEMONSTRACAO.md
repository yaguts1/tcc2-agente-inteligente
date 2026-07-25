# 🎯 Guia de Demonstração do Sistema

## Objetivo
Este documento apresenta roteiros práticos para demonstrar todas as capacidades do sistema de monitoramento de posturas e prevenção de lesões por pressão.

---

## 📋 Índice

1. [Preparação do Ambiente](#1-preparação-do-ambiente)
2. [Demonstração Básica (10 minutos)](#2-demonstração-básica-10-minutos)
3. [Demonstração Completa (30 minutos)](#3-demonstração-completa-30-minutos)
4. [Demonstração Técnica Avançada (45+ minutos)](#4-demonstração-técnica-avançada-45-minutos)
5. [Cenários de Uso Específicos](#5-cenários-de-uso-específicos)
6. [Demonstração para Diferentes Públicos](#6-demonstração-para-diferentes-públicos)

---

## 1. Preparação do Ambiente

### 1.1. Iniciar Serviços

```powershell
# Terminal 1 - Backend
cd C:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
.\venv\Scripts\python.exe -m uvicorn interface.web:app --reload

# Terminal 2 - Frontend
cd frontend
npm run dev
```

**Verificar:**
- ✅ Backend: http://127.0.0.1:8000
- ✅ Frontend: http://localhost:5173
- ✅ API Docs: http://127.0.0.1:8000/docs

### 1.2. Preparar Dados de Demonstração

**Opção A: Usar dados existentes**
```powershell
# Verificar pacientes no banco
.\venv\Scripts\python.exe scripts_demo/ver_pacientes.py
```

**Opção B: Gerar dados novos**
```powershell
# Limpar dados antigos e gerar simulação fresca
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-001 24 alto
```

### 1.3. Checklist Pré-Demonstração

- [ ] Backend rodando sem erros
- [ ] Frontend acessível no navegador
- [ ] Pelo menos 2 pacientes com dados (últimas 24h)
- [ ] WebSocket conectado (verificar console do navegador)
- [ ] Terminal com logs visível (para demonstrações técnicas)

---

## 2. Demonstração Básica (10 minutos)

**Público-alvo:** Gestores, stakeholders não-técnicos

### 2.1. Dashboard Principal (3 min)

1. **Abrir Dashboard**
   - Acesse http://localhost:5173
   - Mostre visão geral com cards de estatísticas

2. **Explicar Cards**
   - "Alertas Ativos": Situações críticas que exigem ação imediata
   - "Pacientes Monitorados": Total em acompanhamento
   - "Risco Alto": Pacientes prioritários
   - "Taxa de Resolução": Eficiência da equipe

3. **Filtros e Pesquisa**
   - Demonstre filtro por paciente
   - Mostre pesquisa em tempo real
   - Explique filtros por tipo de alerta

### 2.2. Lista de Alertas (3 min)

1. **Explorar Alertas**
   - Mostre lista com priorização por severidade
   - Explique cores (vermelho=crítico, amarelo=atenção)
   - Demonstre badges de status

2. **Interação com Alerta**
   - Clique em um alerta → expande detalhes
   - Mostre botões de ação (Reconhecer/Fechar)
   - Explique workflow: Ativo → Reconhecido → Fechado

### 2.3. Timeline (2 min)

1. **Visualização Temporal**
   - Navegue para Timeline
   - Selecione um paciente
   - Mostre histórico de eventos de postura
   - Explique padrões visuais (cores por postura)

2. **Análise Rápida**
   - Identifique períodos longos em mesma postura
   - Mostre como isso gera alertas

### 2.4. Gestão de Pacientes (2 min)

1. **Lista de Pacientes**
   - Mostre cadastro ativo
   - Explique campos (nome, leito, perfil de risco)
   - Demonstre edição rápida

**Mensagem-chave:** "Sistema intuitivo que centraliza informações críticas e facilita tomada de decisão."

---

## 3. Demonstração Completa (30 minutos)

**Público-alvo:** Equipe clínica, usuários finais

### 3.1. Fluxo Completo de Monitoramento (10 min)

#### Passo 1: Cadastro de Paciente
```
1. Ir para Pacientes
2. Clicar em "Novo Paciente"
3. Preencher:
   - Nome: "Maria Silva"
   - Leito: "C-05"
   - Perfil: "Alto Risco"
   - Observações: "Mobilidade reduzida, diabética"
4. Salvar
```

#### Passo 2: Gerar Dados Simulados
```
1. Selecionar paciente "Maria Silva"
2. Clicar em "Gerar Dados Simulados"
3. Configurar:
   - Duração: 4 horas
   - Perfil: alto
   - Seed: 456
4. Aguardar confirmação
```

#### Passo 3: Verificar Dashboard
```
1. Voltar ao Dashboard (F5 se necessário)
2. Filtrar por "Maria Silva"
3. Mostrar alertas gerados
4. Explicar critérios de detecção
```

### 3.2. Workflow de Resposta a Alertas (8 min)

#### Cenário: Alerta de Imobilidade Prolongada

1. **Detecção**
   - Alerta aparece no Dashboard (vermelho)
   - Notificação visual + badge de contador

2. **Reconhecimento**
   - Enfermeiro clica no alerta
   - Vê detalhes: paciente, postura, duração
   - Clica em "Reconhecer"
   - Status muda para "Reconhecido" (amarelo)

3. **Ação**
   - Equipe vai até leito C-05
   - Reposiciona paciente
   - Registra observação (se implementado)

4. **Fechamento**
   - Volta ao Dashboard
   - Clica em "Fechar Alerta"
   - Alerta sai da lista ativa

5. **Auditoria**
   - Mostre Timeline
   - Evento de reposicionamento visível
   - Histórico completo preservado

### 3.3. Análise de Padrões (6 min)

1. **Timeline Detalhada**
   - Selecione paciente com histórico de 24h
   - Identifique padrões:
     - Predominância de supino noturno
     - Reposicionamentos durante dia
     - Períodos críticos (>2h mesma postura)

2. **Comparação de Perfis**
   - Mostre paciente alto risco vs baixo risco
   - Compare frequência de alertas
   - Explique limites diferentes por perfil

### 3.4. Gestão Administrativa (6 min)

1. **Admin Page (Reconciliação)**
   - Acesse Admin → Device Events
   - Mostre cards por leito
   - Explique eventos órfãos (sem paciente atribuído)
   - Demonstre reconciliação em lote

2. **Configurações de Perfil**
   - Edite paciente
   - Mude perfil de risco
   - Explique impacto nos limiares de alerta

3. **Relatórios** (se implementado)
   - Exporte dados
   - Mostre formatos disponíveis (CSV, JSONL)

**Mensagem-chave:** "Fluxo completo desde detecção até resolução, com rastreabilidade total."

---

## 4. Demonstração Técnica Avançada (45+ minutos)

**Público-alvo:** Desenvolvedores, arquitetos, avaliadores técnicos

### 4.1. Arquitetura do Sistema (10 min)

#### Backend (FastAPI + SQLite)

```powershell
# Mostrar estrutura do projeto
tree /F /A interface
tree /F /A modulo_alerta
tree /F /A dados_simulados
```

**Explicar:**
- API REST + WebSocket
- Camadas: API → DAO → Banco
- Motor de decisão (modulo_alerta/engine.py)
- Filtros de qualidade (quality/filtro.py)

#### Frontend (React + TypeScript + Vite)

```powershell
cd frontend
tree /F /A src\components
```

**Demonstrar:**
- Componentes reutilizáveis (shadcn/ui)
- State management (React hooks)
- WebSocket client (tempo real)
- Build otimizado (Vite)

### 4.2. Fluxo de Dados Completo (10 min)

#### 1. Ingestão de Eventos

**Mostrar código:**
```python
# interface/api.py - receber_evento()
# - Validação com Pydantic
# - Rate limiting
# - Filtro de qualidade
# - Reconciliação de device_id → paciente_id
```

**Demonstrar no terminal:**
```powershell
# Enviar evento via curl
$body = @{
    device_id = "ESP32-001"
    cama_id = "C-05"
    postura = "supino"
    confianca = 0.95
    amostra_ms = 100
    ts_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/eventos" -Method POST -Body $body -ContentType "application/json"
```

#### 2. Processamento de Alertas

**Mostrar código:**
```python
# modulo_alerta/engine.py - processar_alertas()
# - Detecção de imobilidade
# - Cálculo de severidade
# - Histerese e cooldown
```

**Executar teste:**
```powershell
.\venv\Scripts\python.exe -c "
from modulo_alerta.engine import processar_alertas
import pandas as pd
from datetime import datetime, timedelta

# Criar dados de teste
now = datetime.now()
eventos = [
    {'timestamp': (now - timedelta(minutes=i*5)), 'postura': 'supino'}
    for i in range(30)  # 150 minutos em supino
]
df = pd.DataFrame(eventos)

_, alertas = processar_alertas(df, 'alto', 'TEST-001')
print(f'Alertas gerados: {len(alertas)}')
for a in alertas:
    print(f'  - {a}')
"
```

#### 3. WebSocket Broadcasting

**Mostrar logs em tempo real:**
```
Terminal 1: Backend logs
Terminal 2: Browser DevTools → Network → WS
Terminal 3: Enviar evento via API
```

**Verificar:**
- Evento chega ao backend
- Alerta é processado
- WebSocket envia broadcast
- Frontend atualiza instantaneamente

### 4.3. Simulador de Dados (8 min)

#### Arquitetura do Simulador

```python
# dados_simulados/gerador.py
```

**Demonstrar:**
1. **Perfis de Risco**
   ```python
   PERFIS_PREDEFINIDOS = {
       "alto": {"limite_tempo_postura": 90, "prob_falha_reposicao": 0.85},
       "medio": {"limite_tempo_postura": 120, "prob_falha_reposicao": 0.7},
       "baixo": {"limite_tempo_postura": 150, "prob_falha_reposicao": 0.4},
   }
   ```

2. **Distribuições Normais Truncadas**
   ```python
   TEMPOS_POSTURA = {
       "supino": (90, 30),        # μ=90min, σ=30min
       "lateral_direito": (120, 40),
       # ...
   }
   ```

3. **Contextos Hospitalares**
   ```python
   # Refeições, procedimentos, visitas
   # dados_simulados/contextos.py
   ```

#### Executar Simulação Completa

```powershell
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-002 24 alto
```

**Mostrar saída:**
- Geração de 289 eventos
- Processamento de alertas
- Inserção no banco
- Validação de dados

### 4.4. Testes Automatizados (7 min)

#### Unit Tests (Backend)

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v --cov=interface --cov=modulo_alerta
```

**Explicar cobertura:**
- API endpoints
- Motor de alertas
- DAO (camada de dados)
- Filtros de qualidade

#### Integration Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/integration/ -v
```

**Demonstrar:**
- Fluxo end-to-end
- Integração WebSocket
- Reconciliação de eventos órfãos

#### E2E Tests (Frontend - Cypress)

```powershell
cd frontend
npm run test:e2e
```

**Mostrar testes:**
- Login flow
- Dashboard navigation
- Alert interaction
- Patient CRUD

### 4.5. Performance e Escalabilidade (5 min)

#### Métricas de Performance

```powershell
# Estresse de ingestão
.\venv\Scripts\python.exe -c "
import requests
import time
from concurrent.futures import ThreadPoolExecutor

def enviar_evento(i):
    body = {
        'device_id': f'ESP32-{i:03d}',
        'cama_id': f'C-{i:02d}',
        'postura': 'supino',
        'confianca': 0.95,
        'amostra_ms': 100,
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    }
    r = requests.post('http://127.0.0.1:8000/api/eventos', json=body)
    return r.status_code

# Enviar 100 eventos em paralelo
with ThreadPoolExecutor(max_workers=10) as executor:
    resultados = list(executor.map(enviar_evento, range(100)))

print(f'Sucesso: {resultados.count(200)}/100')
"
```

#### Rate Limiting

```python
# interface/rate_limiter.py
# - Token bucket algorithm
# - Limites por IP/device
# - Backpressure handling
```

#### Compressão WebSocket

```python
# interface/message_compressor.py
# - Compressão de payloads grandes
# - Redução de bandwidth
```

### 4.6. Segurança e Auditoria (5 min)

#### Autenticação

```powershell
# Login via API
$body = @{ username = "admin"; password = "admin" } | ConvertTo-Json
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/auth/login" -Method POST -Body $body -ContentType "application/json"
$token = ($response.Content | ConvertFrom-Json).token
```

#### Logs Estruturados

```python
# logging_setup.py
# - Formato JSON
# - Contexto enriquecido
# - Rastreamento de eventos
```

**Mostrar logs:**
```
{"event": "evento_recebido", "device_id": "ESP32-001", "paciente_id": "PAC-001", ...}
{"event": "alerta_gerado", "tipo": "imobilidade", "severidade": 3, ...}
```

---

## 5. Cenários de Uso Específicos

### 5.1. Cenário Clínico: Turno Noturno

**Contexto:** Equipe reduzida monitora 10 pacientes durante madrugada

**Demonstração:**
1. Dashboard mostra 10 pacientes ativos
2. Alerta de imobilidade em Leito C-03 (2h30 em supino)
3. Enfermeiro reconhece alerta
4. Timeline mostra que paciente estava dormindo
5. Decisão: reposicionar agora ou aguardar despertar natural?
6. Ação registrada + alerta fechado

**Valor:** Priorização inteligente + rastreabilidade de decisões

### 5.2. Cenário Técnico: Integração com ESP32

**Setup:**
1. ESP32 com firmware `esp32_replay.ino`
2. Arquivo `eventos.jsonl` no SPIFFS
3. Configuração de Wi-Fi e endpoint

**Demonstração:**
```cpp
// Configuração no firmware
ReplayConfig g_config{
    .hostServidor = "http://192.168.0.67",
    .portaServidor = 8000,
    .endpoint = "/api/eventos",
    .camaId = "C-01",
    // ...
};
```

**Fluxo:**
1. ESP32 conecta Wi-Fi
2. Consulta `/api/pacientes/cama/C-01` → obtém paciente_id
3. Lê eventos de SPIFFS
4. Envia POST para `/api/eventos`
5. Backend processa e gera alertas
6. Frontend atualiza em tempo real

**Valor:** Integração real com hardware IoT

### 5.3. Cenário Administrativo: Reconciliação de Dados

**Problema:** ESP32 enviou eventos antes do paciente ser cadastrado

**Demonstração:**
1. Verificar Admin → Device Events
2. Card do Leito C-05 mostra "12 eventos órfãos"
3. Cadastrar paciente no Leito C-05
4. Clicar em "Reconciliar Eventos"
5. Sistema processa eventos retroativamente
6. Dashboard atualiza com alertas históricos

**Valor:** Flexibilidade operacional + zero perda de dados

### 5.4. Cenário de Pesquisa: Exportação de Dados

**Objetivo:** Analisar padrões para estudo clínico

**Demonstração:**
```powershell
# Exportar alertas completos
.\venv\Scripts\python.exe -m ferramentas.exportador_jsonl --tipo alertas --output relatorios/estudo_2025.jsonl

# Exportar grade temporal
.\venv\Scripts\python.exe -m ferramentas.exportador_jsonl --tipo grade --paciente PAC-001 --output dados_pac001.jsonl
```

**Análise externa:**
```python
import pandas as pd

# Carregar dados
df = pd.read_json('relatorios/estudo_2025.jsonl', lines=True)

# Estatísticas
print(f"Total de alertas: {len(df)}")
print(f"Por tipo:\n{df['tipo'].value_counts()}")
print(f"Tempo médio de resposta: {df['tempo_resposta'].mean():.1f} min")
```

**Valor:** Interoperabilidade + suporte a pesquisa

---

## 6. Demonstração para Diferentes Públicos

### 6.1. Para Gestores/Administradores Hospitalares

**Foco:** ROI, eficiência operacional, compliance

**Roteiro (15 min):**
1. **Dashboard Executivo** (5 min)
   - Métricas agregadas (taxa de resposta, cobertura)
   - Tendências (redução de lesões por pressão)
   - Benchmarks (comparação com literatura)

2. **Relatórios** (5 min)
   - Exportação de dados para auditoria
   - Conformidade com protocolos (NPUAP/EPUAP)
   - Rastreabilidade de ações

3. **Escalabilidade** (5 min)
   - Custo por leito monitorado
   - Expansão para novas unidades
   - Integração com HIS/EMR

**Mensagem:** "Sistema que reduz custos, melhora outcomes e simplifica compliance."

### 6.2. Para Equipe de Enfermagem

**Foco:** Usabilidade, workflow, suporte à decisão

**Roteiro (20 min):**
1. **Interface Intuitiva** (5 min)
   - Login rápido
   - Dashboard limpo e organizado
   - Ações com 1-2 cliques

2. **Alertas Inteligentes** (8 min)
   - Priorização automática
   - Contexto clínico (perfil do paciente)
   - Redução de alarmes falsos

3. **Timeline de Paciente** (7 min)
   - Histórico completo
   - Identificação de padrões
   - Suporte a handoff entre turnos

**Mensagem:** "Ferramenta que facilita o trabalho diário e melhora qualidade do cuidado."

### 6.3. Para Equipe Médica

**Foco:** Evidência clínica, precisão, insights

**Roteiro (25 min):**
1. **Critérios de Alerta** (8 min)
   - Base em guidelines internacionais
   - Personalização por perfil de risco
   - Ajuste de sensibilidade

2. **Análise de Padrões** (10 min)
   - Correlação postura x lesões
   - Identificação de pacientes de risco
   - Tendências temporais

3. **Integração com Decisão Clínica** (7 min)
   - Dados como suporte (não substituição)
   - Contexto amplo (comorbidades, mobilidade)
   - Documentação de intervenções

**Mensagem:** "Dados objetivos para decisões clínicas mais informadas."

### 6.4. Para Desenvolvedores/TI

**Foco:** Arquitetura, APIs, extensibilidade

**Roteiro (40 min):**
1. **Stack Tecnológico** (10 min)
   - Backend: Python 3.11, FastAPI, SQLite
   - Frontend: React 18, TypeScript, Vite
   - IoT: ESP32, Wi-Fi, HTTP/WebSocket

2. **APIs REST e WebSocket** (12 min)
   - OpenAPI/Swagger docs
   - Autenticação JWT
   - Rate limiting

3. **Arquitetura de Dados** (10 min)
   - Schema do banco (SQLite)
   - Migrations e versionamento
   - Backup e recovery

4. **Deployment** (8 min)
   - Docker/docker-compose
   - CI/CD (potencial)
   - Monitoramento (logs, métricas)

**Mensagem:** "Sistema bem arquitetado, documentado e pronto para produção."

### 6.5. Para Avaliadores Acadêmicos/Banca

**Foco:** Contribuição científica, metodologia, resultados

**Roteiro (60 min):**
1. **Problema e Motivação** (8 min)
   - Prevalência de LPP
   - Limitações de soluções existentes
   - Gap identificado

2. **Proposta e Arquitetura** (12 min)
   - Abordagem híbrida (IoT + backend inteligente)
   - Motor de decisão com histerese
   - Simulador para validação

3. **Implementação** (15 min)
   - Demonstração técnica completa
   - Código-fonte (estrutura, qualidade)
   - Testes automatizados

4. **Validação e Resultados** (15 min)
   - Simulações com perfis de risco
   - Métricas (precisão, recall, latência)
   - Casos de uso clínico

5. **Discussão e Trabalhos Futuros** (10 min)
   - Limitações atuais
   - ML para predição preditiva
   - Integração com sensores avançados
   - Estudos clínicos prospectivos

**Mensagem:** "Pesquisa rigorosa com implementação funcional e potencial de impacto real."

---

## 7. Checklist de Preparação por Tipo de Demo

### Demo Básica (10 min)
- [ ] Backend e frontend rodando
- [ ] 2+ pacientes com alertas ativos
- [ ] Browser aberto em Dashboard
- [ ] Apresentação de slides (opcional)

### Demo Completa (30 min)
- [ ] Todos os itens da demo básica
- [ ] Dados de simulação frescos (< 24h)
- [ ] Timeline populada
- [ ] Admin page com eventos órfãos (para reconciliação)
- [ ] Roteiro impresso

### Demo Técnica (45+ min)
- [ ] Todos os itens da demo completa
- [ ] IDE aberto (VSCode) com código relevante
- [ ] Terminal com logs visíveis
- [ ] Postman/curl para testes de API
- [ ] Browser DevTools aberto (Network, Console)
- [ ] Documentação técnica à mão

### Demo para Banca (60 min)
- [ ] Todos os itens da demo técnica
- [ ] Slides com arquitetura, diagramas, resultados
- [ ] Código-fonte navegável (GitHub/local)
- [ ] Artigos/guidelines de referência
- [ ] Dados de validação (métricas, gráficos)
- [ ] Backup de ambiente (caso de falhas)

---

## 8. Troubleshooting Durante Demonstração

### Problema: Frontend não conecta ao backend
**Sintoma:** Dashboard vazio, erros no console
**Solução:**
```powershell
# Verificar backend
curl http://127.0.0.1:8000/api/stats

# Verificar CORS
# interface/api.py → origins = ["*"] ou ["http://localhost:5173"]
```

### Problema: WebSocket desconectado
**Sintoma:** Alertas não atualizam em tempo real
**Solução:**
```javascript
// Browser console
WebSocket.OPEN === 1 // deve retornar true
```

### Problema: Simulação não gera alertas
**Sintoma:** Dashboard vazio após simulação
**Solução:**
```powershell
# Verificar banco
.\venv\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('dados.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM alertas WHERE paciente_id = \"DEMO-001\"')
print(f'Alertas no banco: {cursor.fetchone()[0]}')
"

# Re-gerar com perfil alto (mais alertas)
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-001 4 alto
```

### Problema: Performance lenta
**Sintoma:** Dashboard demora a carregar
**Solução:**
```powershell
# Limpar dados antigos
.\venv\Scripts\python.exe -c "
import sqlite3
from datetime import datetime, timedelta
conn = sqlite3.connect('dados.db')
cursor = conn.cursor()
limite = (datetime.now() - timedelta(days=7)).isoformat()
cursor.execute('DELETE FROM alertas WHERE inicio < ?', (limite,))
cursor.execute('DELETE FROM grade WHERE ts < ?', (limite,))
conn.commit()
print(f'Dados antigos removidos')
"
```

---

## 9. Scripts Úteis para Demo

### Script 1: Reset Completo
```powershell
# reset_demo.ps1
Write-Host "Limpando dados de demonstração..." -ForegroundColor Yellow

# Limpar banco
.\venv\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('dados.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM alertas')
cursor.execute('DELETE FROM grade')
cursor.execute('DELETE FROM device_events')
cursor.execute('DELETE FROM pacientes WHERE id LIKE \"DEMO-%\"')
conn.commit()
print('Banco limpo')
"

# Gerar dados novos
Write-Host "Gerando dados de demonstração..." -ForegroundColor Green
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-001 24 alto
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-002 24 medio
.\venv\Scripts\python.exe scripts_demo/testar_simulacao_com_verificacao.py DEMO-003 24 baixo

Write-Host "Ambiente pronto para demonstração!" -ForegroundColor Cyan
```

### Script 2: Verificação de Saúde
```powershell
# health_check.ps1
Write-Host "=== Health Check ===" -ForegroundColor Cyan

# Backend
$backend = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -ErrorAction SilentlyContinue
if ($backend) {
    Write-Host "✓ Backend: OK" -ForegroundColor Green
} else {
    Write-Host "✗ Backend: FALHOU" -ForegroundColor Red
}

# Frontend
$frontend = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -ErrorAction SilentlyContinue
if ($frontend) {
    Write-Host "✓ Frontend: OK" -ForegroundColor Green
} else {
    Write-Host "✗ Frontend: FALHOU" -ForegroundColor Red
}

# Dados
$dados = .\venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('dados.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM alertas'); print(cursor.fetchone()[0])"
Write-Host "✓ Alertas no banco: $dados" -ForegroundColor Green
```

---

## 10. Recursos Adicionais

### Documentação Técnica
- `JORNADA_INFORMACAO_ESP32.md` - Fluxo de dados completo
- `docs/ARQUITETURA_ESP32_LEITO_PACIENTE.md` - Arquitetura do sistema
- `tests/` - Suíte automatizada (roda no CI); `scripts_demo/README.md` cobre as
  verificações manuais

### Apresentações
- Slides (preparar em PowerPoint/Google Slides)
- Diagramas (draw.io, Excalidraw)
- Vídeo demo (gravar com OBS Studio)

### Dados de Apoio
- Benchmarks de performance
- Estatísticas de uso
- Estudos de caso (fictícios ou reais)

---

**Última atualização:** 04/11/2025  
**Versão:** 1.0  
**Autor:** Sistema de Documentação Automatizada
