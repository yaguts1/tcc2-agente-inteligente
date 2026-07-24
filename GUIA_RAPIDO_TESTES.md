# 🚀 Guia Rápido: Testando a Jornada ESP32 → Servidor

## ⚡ Setup Rápido (5 minutos)

### 1. Preparar Ambiente
```bash
# Ativar ambiente virtual
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
.\venv\Scripts\Activate.ps1

# Verificar sistema
python scripts_demo/verificar_sistema.py
```

### 2. Iniciar Servidor
```bash
# Terminal 1
uvicorn interface.web:app --reload
```

Aguarde até ver:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 3. Testar Jornada Completa
```bash
# Terminal 2
python scripts_demo/testar_jornada_completa.py
```

**Resultado esperado:**
```
✅ CONEXAO
✅ AUTENTICACAO
✅ ENVIO
✅ PERSISTENCIA
✅ BROADCAST
🎉 SUCESSO! Jornada completa funcionando corretamente
```

---

## 🔧 Testes Individuais

### Teste 1: Verificação do Sistema
```bash
python scripts_demo/verificar_sistema.py
```
**O que testa:**
- ✅ Banco de dados
- ✅ Módulos Python
- ✅ Frontend
- ✅ Dependências

### Teste 2: WebSocket Simples
```bash
python scripts_demo/test_simple_ws.py
```
**O que testa:**
- ✅ Conexão WebSocket
- ✅ Envio de evento
- ✅ Recebimento de ACK

### Teste 3: API REST
```bash
python scripts_demo/test_rest_api.py
```
**O que testa:**
- ✅ POST /api/frontend/eventos
- ✅ Processamento batch
- ✅ Geração de alertas

### Teste 4: Jornada Completa
```bash
python scripts_demo/testar_jornada_completa.py
```
**O que testa:**
- ✅ Toda a jornada E2E
- ✅ 5 passos de integração
- ✅ Persistência e alertas

---

## 📊 Monitoramento

### Ver Métricas
```bash
# Acessar no navegador
http://localhost:8000/metrics
```

### Ver Logs
```bash
# Os logs aparecem no terminal do servidor
# Busque por:
- ws_evento_salvo
- ws_alertas_gerados
- broadcast_start
```

### Ver Banco de Dados
```bash
python -c "
import sqlite3
conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Eventos
cursor.execute('SELECT COUNT(*) FROM eventos')
print(f'Eventos: {cursor.fetchone()[0]}')

# Alertas
cursor.execute('SELECT COUNT(*) FROM alertas')
print(f'Alertas: {cursor.fetchone()[0]}')

# Timeline
cursor.execute('SELECT COUNT(*) FROM timeline_events')
print(f'Timeline: {cursor.fetchone()[0]}')
"
```

---

## 🐛 Troubleshooting

### ❌ Erro: "Connection refused"
**Solução:**
```bash
# Certifique-se que o servidor está rodando
uvicorn interface.web:app --reload
```

### ❌ Erro: "Module not found"
**Solução:**
```bash
# Ativar ambiente virtual
.\venv\Scripts\Activate.ps1
```

### ❌ Erro: "Database locked"
**Solução:**
```bash
# Fechar outros processos que usam o banco
# Ou reiniciar servidor
```

### ❌ Nenhum alerta gerado
**Explicação:**
- Normal! Alertas são gerados apenas quando:
  - Paciente fica muito tempo imóvel
  - Baseado no perfil de risco
- Para forçar alerta: envie 25+ eventos na mesma postura

---

## 📱 Simular ESP32

### Opção 1: Script Python
```bash
python -c "
import asyncio
import websockets
import json
from datetime import datetime

async def simular_esp32():
    uri = 'ws://localhost:8000/api/ws/eventos'
    
    async with websockets.connect(uri) as ws:
        # Autenticação
        await ws.send(json.dumps({
            'device_id': 'DEV-TESTE',
            'cama_id': 'C-01'
        }))
        print(f'Auth: {await ws.recv()}')
        
        # Enviar 30 eventos (2.5 horas em supino)
        for i in range(30):
            evento = {
                'seq': i+1,
                'device_id': 'DEV-TESTE',
                'paciente_id': 'PAC-0001',
                'ts_utc': datetime.now().isoformat(),
                'tipo': 'postura',
                'valor': 1,  # supino
                'confianca': 0.95
            }
            await ws.send(json.dumps(evento))
            resp = await ws.recv()
            print(f'{i+1}/30: {resp}')

asyncio.run(simular_esp32())
"
```

### Opção 2: Usar scripts_demo/test_simple_ws.py
```bash
python scripts_demo/test_simple_ws.py
```

---

## 🌐 Frontend

### Iniciar Frontend
```bash
cd frontend
npm run dev
```

### Acessar
```
http://localhost:5173
```

### Páginas
- `/` - Dashboard
- `/alerts` - Lista de alertas
- `/patients` - Pacientes
- `/timeline` - Timeline de eventos

---

## 📖 Documentação Adicional

- `JORNADA_INFORMACAO_ESP32.md` - Documentação técnica completa
- `ARQUITETURA_DIAGRAMA.md` - Diagramas visuais
- `VERIFICACAO_JORNADA_COMPLETA.md` - Relatório de verificação
- `RELATORIO_VERIFICACAO.md` - Status do sistema

---

## 💡 Dicas

### Limpar banco de dados
```bash
python -c "
import sqlite3
conn = sqlite3.connect('dados.db')
conn.execute('DELETE FROM eventos WHERE device_id LIKE \"%TESTE%\"')
conn.execute('DELETE FROM alertas WHERE paciente_id LIKE \"%TEST%\"')
conn.commit()
print('✅ Dados de teste removidos')
"
```

### Ver últimos eventos
```bash
python -c "
import sqlite3
import pandas as pd
conn = sqlite3.connect('dados.db')
df = pd.read_sql('SELECT * FROM eventos ORDER BY id DESC LIMIT 10', conn)
print(df)
"
```

### Ver alertas ativos
```bash
python -c "
import sqlite3
import pandas as pd
conn = sqlite3.connect('dados.db')
df = pd.read_sql(\"SELECT * FROM alertas WHERE status='pending' ORDER BY inicio DESC\", conn)
print(df)
"
```

---

## ✅ Checklist de Testes

Antes de considerar o sistema pronto:

- [ ] `scripts_demo/verificar_sistema.py` passou
- [ ] `scripts_demo/testar_jornada_completa.py` passou
- [ ] Frontend carrega sem erros
- [ ] WebSocket conecta e mantém conexão
- [ ] Eventos são persistidos no banco
- [ ] Alertas são gerados corretamente
- [ ] Frontend recebe alertas em tempo real
- [ ] Logs estão sendo gerados
- [ ] Métricas estão disponíveis em /metrics

---

**🎉 Se todos os itens acima estiverem ✅, o sistema está pronto!**

