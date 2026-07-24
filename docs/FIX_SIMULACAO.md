# PROBLEMA: Simulação Não Gera Alertas Visíveis

## 🔍 Diagnóstico

### Problemas Identificados:

A simulação de dados tinha 2 problemas principais:

1. ✅ **CORRIGIDO**: Função `inserir_grade` recebia DataFrame SEM paciente_id
   - Linha 2117 em api.py: `inserir_grade(DB_PATH, df_grade)`  
   - Deveria ser: `inserir_grade(DB_PATH, df_grade, paciente_id=paciente_id)`

2. ✅ **CORRIGIDO**: Simulação gerava dados do FUTURO
   - Dashboard mostra apenas últimas 24 horas (passado até agora)
   - Dados futuros NÃO aparecem
   - **Solução**: Gerar dados do PASSADO até AGORA
   - `inicio = agora - timedelta(hours=duracao_horas)` ✅

## ✅ Correções Aplicadas

### 1. Corrigir chamada de `inserir_grade` (api.py linha 2117)

```python
# ANTES (❌)
inserir_grade(DB_PATH, df_grade)

# DEPOIS (✅)
inserir_grade(DB_PATH, df_grade, paciente_id=paciente_id)
```

### 2. Corrigir período da simulação (gerador.py linha 194)

```python
# ANTES (❌) - Gerava dados no FUTURO
if inicio is None:
    inicio = agora  # Começava AGORA, ia para futuro
fim = inicio + timedelta(hours=duracao_horas)

# DEPOIS (✅) - Gera dados do PASSADO até AGORA
if inicio is None:
    inicio = agora - timedelta(hours=duracao_horas)  # X horas atrás
fim = inicio + timedelta(hours=duracao_horas)  # Até AGORA
```

**Resultado:**
- Simulação de 4h: Início 4h atrás → Fim agora
- Dashboard mostra alertas (últimas 24h) ✅
- Timeline mostra eventos ✅

## 🧪 Script de Teste

Criado `scripts_demo/testar_simulacao.py` para validar end-to-end:

```bash
python scripts_demo/testar_simulacao.py P1 2 alto
```

Testa:
1. Verificação de paciente
2. Geração de dados
3. Salvamento de grades
4. Processamento de alertas
5. Salvamento de alertas
6. Verificação no banco

## 🔧 Próximos Passos

### Para o Usuário:

1. **Reiniciar servidor backend** (para aplicar correção)
   ```bash
   # Parar servidor (Ctrl+C)
   uvicorn interface.web:app --reload
   ```

2. **Criar novo paciente** (ou usar existente com ficha completa)
   - Ir em "Pacientes" → "Adicionar Paciente"
   - Preencher: Nome, Leito, Perfil de Risco

3. **Executar simulação**
   - Selecionar paciente
   - Clicar "Gerar Dados Simulados"
   - Configurar: 2-4 horas (suficiente para gerar alertas)
   - Perfil: "Alto" (gera mais alertas)

4. **Verificar resultados**
   - **Dashboard**: Ver alertas gerados (últimas 24h)
   - **Timeline**: Ver eventos de postura

### Se ainda não funcionar:

Executar teste manual:
```bash
.\venv\Scripts\python.exe scripts_demo/testar_simulacao.py <PACIENTE_ID> 4 alto
```

Exemplo:
```bash
.\venv\Scripts\python.exe scripts_demo/testar_simulacao.py PAC-0001 4 alto
```

## 📊 Verificação Manual do Banco

```python
import sqlite3

conn = sqlite3.connect("dados.db")
cursor = conn.cursor()

# Ver pacientes
cursor.execute("SELECT * FROM pacientes")
print("Pacientes:", cursor.fetchall())

# Ver grades de um paciente
cursor.execute("SELECT COUNT(*) FROM grade WHERE paciente_id = 'P1'")
print("Eventos grade:", cursor.fetchone())

# Ver alertas de um paciente
cursor.execute("SELECT COUNT(*) FROM alertas WHERE paciente_id = 'P1'")
print("Alertas:", cursor.fetchone())

# Ver período dos alertas
cursor.execute("""
    SELECT MIN(inicio), MAX(inicio) 
    FROM alertas 
    WHERE paciente_id = 'P1'
""")
print("Período alertas:", cursor.fetchone())

conn.close()
```

## 🎯 Checklist de Validação

- [x] Correção aplicada em `api.py` linha 2117
- [x] Script de teste criado (`scripts_demo/testar_simulacao.py`)
- [ ] Servidor reiniciado
- [ ] Simulação testada no frontend
- [ ] Alertas aparecem no Dashboard
- [ ] Eventos aparecem na Timeline
- [ ] Verificação manual do banco OK

## 💡 Dicas

- **Perfil "Alto"** gera mais alertas (maior imobilidade)
- **4-8 horas** é bom período para testes
- **Seed fixo** (ex: 42) gera mesmos resultados
- **Verificar logs** do backend para ver erros detalhados

## ⚠️ Problemas Conhecidos

1. **Timeline não existe**: Precisa criar tabela ou verificar schema
2. **Alertas antigos**: Dashboard só mostra últimas 24h
3. **Cache**: Pode precisar refresh manual no Dashboard
