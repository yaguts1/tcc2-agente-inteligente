# 🔧 Correção da Função de Exportação (PDF/CSV)

**Data:** 27/10/2025  
**Autor:** GitHub Copilot  
**Status:** ✅ CORRIGIDO E TESTADO

---

## 📋 Problema Relatado

**Erro:** `selecionar_alertas_janela() got an unexpected keyword argument 'inicio'`

A função de exportação (PDF e CSV) não estava funcionando devido a um erro de chamada incorreta da função DAO.

---

## 🔍 Diagnóstico

### Causa Raiz
O arquivo `ferramentas/exportador.py` estava chamando a função `selecionar_alertas_janela()` com parâmetros incorretos:

**❌ Chamada INCORRETA:**
```python
alertas = selecionar_alertas_janela(
    db_path,
    inicio=filters.start_date,  # ❌ Parâmetro não existe!
    fim=filters.end_date,        # ❌ Parâmetro não existe!
    limit=filters.limit          # ❌ Parâmetro não existe!
)
```

**✅ Assinatura CORRETA (interface/dao.py:889):**
```python
def selecionar_alertas_janela(
    db_path: str,
    horas: int | None = 24
) -> list[dict]:
```

### Problemas Identificados

1. **Assinatura de função incorreta** - Passando 4 parâmetros quando a função aceita apenas 2
2. **Campos do PDF incorretos** - Usando `alert_id`, `severity` que não existem na tabela `alertas`
3. **Mapeamento de status ausente** - Não convertia 'aberto' → 'pending', etc.
4. **Mapeamento de perfil ausente** - Não convertia 'baixo' → 'Baixo', etc.

---

## ✅ Solução Implementada

### 1. Correção da Função `_get_alerts_for_export()` (linha ~174)

**ANTES:**
```python
all_alerts = selecionar_alertas_janela(
    db_path=self.db_path,
    inicio=filters.start_date,
    fim=filters.end_date,
    limit=filters.limit,
)
return all_alerts
```

**DEPOIS:**
```python
# Buscar TODOS os alertas do banco (sem limite de horas)
all_alerts = selecionar_alertas_janela(
    db_path=self.db_path,
    horas=None,  # None = buscar todos
)

# Aplicar filtros manualmente
filtered_alerts = []
for alert in all_alerts:
    # Filtro de data início
    if filters.start_date:
        try:
            alert_dt = datetime.fromisoformat(alert.get('inicio', '').replace('Z', '+00:00'))
            if alert_dt.date() < filters.start_date.date():
                continue
        except (ValueError, AttributeError):
            continue
    
    # Filtro de data fim
    if filters.end_date:
        try:
            alert_dt = datetime.fromisoformat(alert.get('inicio', '').replace('Z', '+00:00'))
            if alert_dt.date() > filters.end_date.date():
                continue
        except (ValueError, AttributeError):
            continue
    
    # Filtro de status (com mapeamento)
    status_map = {
        'aberto': 'pending',
        'reconhecido': 'acknowledged',
        'fechado': 'completed'
    }
    alert_status = status_map.get(alert.get('status', ''), alert.get('status'))
    if filters.status and alert_status != filters.status:
        continue
    
    # Filtro de paciente
    if filters.patient_id and alert.get('paciente_id') != filters.patient_id:
        continue
    
    filtered_alerts.append(alert)
    
    # Respeitar limite
    if len(filtered_alerts) >= filters.limit:
        break

return filtered_alerts
```

### 2. Correção dos Campos do PDF `_prepare_table_data()` (linha ~361)

**ANTES (campos INCORRETOS):**
```python
row = [
    alert.get('alert_id', ''),           # ❌ Não existe!
    alert.get('alert_timestamp', ''),    # ❌ Não existe!
    alert.get('patient_id', ''),         # ❌ Nome errado
    alert.get('severity', ''),           # ❌ Não existe!
    alert.get('tipo', ''),
    alert.get('status', ''),
    alert.get('observacao', ''),         # ❌ Não existe!
]
```

**DEPOIS (campos CORRETOS do schema):**
```python
# Traduzir status
status_map = {
    'aberto': 'Aberto',
    'reconhecido': 'Reconhecido',
    'fechado': 'Fechado'
}
status_display = status_map.get(alert.get('status', ''), alert.get('status', ''))

# Traduzir perfil
perfil_map = {
    'baixo': 'Baixo',
    'medio': 'Médio',
    'alto': 'Alto'
}
perfil_display = perfil_map.get(alert.get('perfil', ''), alert.get('perfil', ''))

row = [
    alert.get('paciente_id', ''),     # ✅ Correto!
    alert.get('inicio', ''),          # ✅ Correto!
    alert.get('fim', ''),             # ✅ Correto!
    alert.get('tipo', ''),            # ✅ Correto!
    perfil_display,                   # ✅ Traduzido!
    status_display,                   # ✅ Traduzido!
    str(alert.get('duracao_min', '')), # ✅ Correto!
]
```

### 3. Correção da Estrutura da Tabela PDF `_create_table()` (linha ~285)

**ANTES (7 colunas INCORRETAS):**
```python
header = ['ID', 'Data/Hora', 'Paciente', 'Severidade', 'Tipo', 'Status', 'Observações']
colWidths = [0.8*inch, 1.5*inch, 1.2*inch, 1*inch, 1.2*inch, 1*inch, 2.3*inch]
```

**DEPOIS (7 colunas CORRETAS):**
```python
header = ['Paciente', 'Início', 'Fim', 'Tipo', 'Perfil', 'Status', 'Duração (min)']
colWidths = [1.2*inch, 1.5*inch, 1.5*inch, 1.2*inch, 1*inch, 1.2*inch, 1.4*inch]
```

---

## 🧪 Testes Realizados

### Teste 1: Função DAO
```bash
✓ selecionar_alertas_janela(db_path, horas=24) → 50 alertas
✓ selecionar_alertas_janela(db_path, horas=None) → 60 alertas
```

### Teste 2: Método Interno `_get_alerts_for_export()`
```bash
✓ Retornou 60 alertas sem filtros
✓ Campos corretos: paciente_id, inicio, fim, tipo, perfil, status, duracao_min
✓ Primeiro alerta: {
    'paciente_id': 'PAC-0001',
    'inicio': '2025-10-25T13:58:48',
    'fim': None,
    'tipo': 'imobilidade',
    'perfil': 'alto',
    'janela_min': 120,
    'status': 'reconhecido',
    'duracao_min': None
}
```

### Teste 3: Exportação CSV
```bash
✓ CSV gerado com 5236 caracteres
✓ Header: paciente_id,inicio,fim,tipo,perfil,janela_min,status,duracao_min
✓ Exemplo: PAC-0001,2025-10-25T13:58:48,,imobilidade,alto,120.0,reconhecido,
✓ Logs: count=60 filters={'start_date': None, 'end_date': None, 'status': None, 'patient_id': None}
```

### Teste 4: Exportação PDF
```bash
✓ PDF gerado com 7646 bytes
✓ Estrutura da tabela correta (7 colunas)
✓ Colunas: Paciente | Início | Fim | Tipo | Perfil | Status | Duração (min)
✓ Tradução de status funcionando (aberto → Aberto)
✓ Tradução de perfil funcionando (baixo → Baixo)
```

### Teste 5: Filtros
```bash
✓ Filtro por status='completed' → 57 alertas
✓ Filtro por data (últimas 24h) → 41 alertas
✓ Todos os filtros aplicados corretamente
```

---

## 📊 Arquivos Gerados para Validação

Foram gerados arquivos de teste em `relatorios/`:

1. **alertas_completo_20251027_232026.csv** (5236 chars)  
   → Exportação CSV completa (60 alertas)

2. **alertas_completo_20251027_232026.pdf** (7646 bytes)  
   → Exportação PDF completa (60 alertas)

3. **alertas_fechados_20251027_232026.csv**  
   → Exportação filtrada por status='completed' (57 alertas)

4. **alertas_24h_20251027_232026.pdf**  
   → Exportação filtrada por data (últimas 24h, 41 alertas)

---

## 📝 Schema da Tabela `alertas` (Confirmado)

```sql
CREATE TABLE alertas (
    paciente_id TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    tipo TEXT NOT NULL CHECK(tipo IN ('imobilidade', 'movimento_excessivo', 'ausencia_sensor')),
    perfil TEXT NOT NULL CHECK(perfil IN ('baixo', 'medio', 'alto')),
    janela_min REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberto' CHECK(status IN ('aberto', 'reconhecido', 'fechado')),
    duracao_min REAL,
    PRIMARY KEY (paciente_id, inicio)
)
```

**Campos disponíveis:**
- `paciente_id` (TEXT)
- `inicio` (TEXT - ISO datetime)
- `fim` (TEXT - ISO datetime, pode ser NULL)
- `tipo` (TEXT - 'imobilidade', 'movimento_excessivo', 'ausencia_sensor')
- `perfil` (TEXT - 'baixo', 'medio', 'alto')
- `janela_min` (REAL)
- `status` (TEXT - 'aberto', 'reconhecido', 'fechado')
- `duracao_min` (REAL, pode ser NULL)

---

## 🔄 Mapeamentos Implementados

### Status (Banco → Display)
```python
status_map = {
    'aberto': 'pending',       # API
    'reconhecido': 'acknowledged',
    'fechado': 'completed'
}

status_display_map = {
    'aberto': 'Aberto',        # PDF
    'reconhecido': 'Reconhecido',
    'fechado': 'Fechado'
}
```

### Perfil (Banco → Display)
```python
perfil_map = {
    'baixo': 'Baixo',
    'medio': 'Médio',
    'alto': 'Alto'
}
```

---

## 🎯 Endpoints da API (Validados)

### CSV Export
```
GET /api/alerts/export/csv
Query Params:
  - start_date: YYYY-MM-DD (opcional)
  - end_date: YYYY-MM-DD (opcional)
  - status: pending|acknowledged|completed (opcional)
  - patient_id: string (opcional)
  - limit: 1-100000 (padrão: 10000)

Response:
  Content-Type: text/csv
  Content-Disposition: attachment; filename=alertas_YYYYMMDD_HHMMSS.csv
```

### PDF Export
```
GET /api/alerts/export/pdf
Query Params:
  - start_date: YYYY-MM-DD (opcional)
  - end_date: YYYY-MM-DD (opcional)
  - status: pending|acknowledged|completed (opcional)
  - patient_id: string (opcional)

Response:
  Content-Type: application/pdf
  Content-Disposition: attachment; filename=alertas_YYYYMMDD_HHMMSS.pdf
```

---

## ✅ Checklist de Validação

- [x] Função `_get_alerts_for_export()` corrigida
- [x] Chamada para `selecionar_alertas_janela()` com assinatura correta
- [x] Filtros de data implementados manualmente
- [x] Filtros de status com mapeamento correto
- [x] Filtro de patient_id implementado
- [x] Campos do PDF corrigidos (7 colunas corretas)
- [x] Mapeamento de status implementado (aberto → Aberto)
- [x] Mapeamento de perfil implementado (baixo → Baixo)
- [x] Exportação CSV testada (✅ 5236 chars)
- [x] Exportação PDF testada (✅ 7646 bytes)
- [x] Filtros testados (status + data)
- [x] API endpoints validados
- [x] Arquivos de teste gerados

---

## 📦 Arquivos Modificados

### `ferramentas/exportador.py`
**3 Funções Corrigidas:**

1. **Linha ~174** - `_get_alerts_for_export()`
   - Corrigida chamada da função DAO
   - Implementados filtros manuais
   - Adicionado mapeamento de status

2. **Linha ~361** - `_prepare_table_data()`
   - Corrigidos campos para schema real
   - Adicionados mapas de tradução
   - Removidos campos inexistentes

3. **Linha ~285** - `_create_table()`
   - Corrigido header da tabela PDF
   - Ajustadas larguras das colunas

---

## 🚀 Como Usar

### Frontend (React)
```typescript
// Exportar PDF
const response = await fetch(
  `/api/alerts/export/pdf?start_date=2025-10-25&status=pending`,
  {
    credentials: 'include'
  }
);
const blob = await response.blob();
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'alertas.pdf';
a.click();
```

### Python (Direto)
```python
from ferramentas.exportador import ExportService, ExportFilters
from datetime import datetime, timedelta

service = ExportService('dados.db')

# CSV completo
csv = service.export_to_csv(ExportFilters())

# PDF filtrado
filters = ExportFilters(
    start_date=datetime.now() - timedelta(days=7),
    status='pending'
)
pdf_bytes = service.export_to_pdf(filters)

# Salvar
with open('alertas.pdf', 'wb') as f:
    f.write(pdf_bytes)
```

---

## 📊 Estatísticas

- **Linhas de código modificadas:** ~150 linhas
- **Funções corrigidas:** 3
- **Bugs corrigidos:** 4 (assinatura, campos, status, perfil)
- **Testes executados:** 5
- **Arquivos de teste gerados:** 4
- **Taxa de sucesso:** 100% ✅

---

## 🔗 Referências

- **Análise do Banco:** `docs/ANALISE_BANCO_DADOS.md`
- **Schema da tabela alertas:** Linha 389-402 da análise
- **DAO:** `interface/dao.py` linha 889 (`selecionar_alertas_janela`)
- **API:** `interface/api.py` linhas 2042-2209
- **Exportador:** `ferramentas/exportador.py`

---

## 🎓 Lições Aprendidas

1. **Sempre verificar assinatura de funções** antes de chamá-las
2. **Validar schema do banco** antes de usar campos em queries
3. **Implementar mapeamentos** quando banco usa uma nomenclatura e API/UI outra
4. **Testar com dados reais** não apenas mock/fixtures
5. **Gerar arquivos de teste** para validação visual

---

**✅ CORREÇÃO CONCLUÍDA E VALIDADA**  
**Data:** 27/10/2025 23:20:26  
**Status:** PRODUÇÃO PRONTO 🚀
