# 🐛 Problema: Simulação não está gerando alertas visíveis

## Diagnóstico

Analisando o banco de dados, descobri que:

```
Paciente: P1
  Grade: 1891 eventos ✅
  Alertas: 0 ❌  <-- PROBLEMA!
```

**Causa raiz**: A simulação para P1 foi executada **ANTES** do servidor ser reiniciado com o código corrigido. Os dados foram salvos na `grade`, mas o processamento de alertas não foi executado porque o código bugado não passava o `paciente_id` corretamente.

## Evidência do Funcionamento Correto

Nos logs do servidor, vemos que para **PAC-7778** funcionou perfeitamente:

```json
{"paciente_id": "PAC-7778", "num_eventos": 289, "event": "simulacao_grade_salva"}
{"paciente_id": "PAC-7778", "num_alertas": 6, "event": "simulacao_alertas_processados"} ✅
{"paciente_id": "PAC-7778", "num_alertas": 6, "event": "simulacao_alertas_salvos"} ✅
```

E no banco de dados:

```
Paciente: PAC-7778
  Grade: 868 eventos ✅
  Alertas: 42 ✅ <- FUNCIONOU!
```

## Solução

### 1. Limpar dados antigos do P1 (opcional)

```sql
DELETE FROM grade WHERE paciente_id = 'P1';
```

### 2. Executar nova simulação

**Via Frontend:**
1. Ir para página Pacientes
2. Selecionar paciente P1
3. Clicar em "Gerar Dados Simulados"
4. Configurar:
   - Duração: 4 horas
   - Perfil: alto
   - Seed: qualquer número
5. Clicar em "Gerar"

**Via API (PowerShell):**

```powershell
# 1. Garantir que servidor está rodando
# Abrir terminal separado e executar:
.\venv\Scripts\python.exe -m uvicorn interface.web:app --reload

# 2. Em outro terminal, chamar API:
$body = @{ 
    duracao_horas = 4
    perfil = "alto"
    seed = 123 
} | ConvertTo-Json

Invoke-WebRequest `
    -Uri "http://127.0.0.1:8000/api/pacientes/P1/simular" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"
```

### 3. Verificar resultados

**Dashboard:**
- Deve mostrar cards com contadores de alertas
- Filtrar por paciente P1
- Ver alertas das últimas 24h

**Timeline:**
- Selecionar paciente P1
- Ver eventos de postura ao longo do tempo

**Banco de dados:**

```python
import sqlite3
conn = sqlite3.connect("dados.db")
cursor = conn.cursor()

# Ver alertas gerados
cursor.execute("""
    SELECT COUNT(*), MIN(inicio), MAX(inicio)
    FROM alertas 
    WHERE paciente_id = 'P1'
""")
print(cursor.fetchone())
```

## Alertas Visíveis nas Últimas 24h

Para aparecer no Dashboard, os alertas precisam estar nas últimas 24 horas. A simulação AGORA gera dados de:

```python
inicio = agora - timedelta(hours=duracao_horas)  # 4 horas atrás
fim = agora                                       # AGORA
```

Exemplo para 4 horas:
- **Início**: 2025-10-29 01:18:00 (4h atrás)
- **Fim**: 2025-10-29 05:18:00 (agora)
- **Dashboard mostra**: Últimas 24h ✅ (inclui estes dados)

## Verificação Final

Após rodar nova simulação para P1, verificar:

```python
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("dados.db")
cursor = conn.cursor()

# Alertas nas últimas 24h
limite = (datetime.now() - timedelta(hours=24)).isoformat()
cursor.execute("""
    SELECT COUNT(*) 
    FROM alertas 
    WHERE paciente_id = 'P1' AND inicio >= ?
""", (limite,))

count = cursor.fetchone()[0]
print(f"Alertas de P1 nas últimas 24h: {count}")

if count > 0:
    print("✅ Sucesso! Alertas devem aparecer no Dashboard")
else:
    print("❌ Problema persiste")
```

## Próximos Passos

1. **Executar nova simulação** para P1 via frontend
2. **Atualizar Dashboard** (F5 se necessário)
3. **Verificar Timeline** para ver eventos históricos
4. **Testar WebSocket** em tempo real (simular novos eventos)

---

**Nota**: O código está correto agora. O problema foi timing - a simulação antiga rodou com código bugado. Uma nova execução deve funcionar perfeitamente! 🚀
