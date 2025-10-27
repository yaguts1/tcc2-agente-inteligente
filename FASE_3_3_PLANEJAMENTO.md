# 📊 FASE 3.3: Relatórios/Export - Planejamento Detalhado

**Data:** Outubro 27, 2025  
**Status:** 🔵 Em Planejamento  
**Tempo Estimado:** 4 horas  
**Prioridade:** Alta  

---

## 🎯 Objetivo

Implementar funcionalidades de exportação de dados (CSV e PDF) com filtros avançados por data, status e paciente.

---

## 📋 Escopo

### ✅ Será Incluído
- [ ] CSV export de alertas com filtros
- [ ] PDF export de relatórios com formatação
- [ ] Filtros por data (start_date, end_date)
- [ ] Filtros por status (pending, acknowledged, completed)
- [ ] Filtros por paciente/patient_id
- [ ] UI component para seleção de filtros
- [ ] Botões de download em Dashboard
- [ ] Validação de datas/parâmetros
- [ ] Geração dinâmica de nomes de arquivo
- [ ] Testes manuais completos

### ⏭️ NÃO será incluído (FASE 4)
- [ ] Agendamento automático de relatórios
- [ ] Envio por email
- [ ] Armazenamento em servidor
- [ ] Relatórios personalizados por template

---

## 🏗️ Arquitetura

### Backend

**Endpoints a criar:**

```
GET /api/alerts/export/csv
  Query params: start_date, end_date, status, patient_id, limit
  Response: CSV file (Content-Type: text/csv)

GET /api/alerts/export/pdf
  Query params: start_date, end_date, status, patient_id
  Response: PDF file (Content-Type: application/pdf)

GET /api/stats/export
  Query params: start_date, end_date
  Response: JSON com resumo

POST /api/export/filtered
  Body: {start_date, end_date, status, patient_id, format: 'csv'|'pdf'}
  Response: File download
```

**Dependencies:**
```
reportlab >= 4.0.0  # PDF generation
pandas >= 2.0.0     # CSV handling (already installed)
python-dateutil     # Date parsing
```

**Classes/Functions:**
```python
class ExportFilters(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None  # 'pending', 'acknowledged', 'completed'
    patient_id: Optional[str] = None
    limit: int = 10000

class ExportService:
    def __init__(self, db_path: str)
    
    def export_to_csv(self, filters: ExportFilters) -> str
        # Returns CSV content as string
    
    def export_to_pdf(self, filters: ExportFilters) -> bytes
        # Returns PDF content as bytes
    
    def get_alerts_for_export(self, filters: ExportFilters) -> List[dict]
        # Query database with filters
    
    def _validate_dates(self, start: datetime, end: datetime) -> bool
        # Validate date range
```

### Frontend

**New Files:**
```
frontend/src/components/
  └── ExportPanel.tsx
      ├── DateRangePicker component
      ├── StatusFilter component
      ├── PatientFilter component
      ├── Format selector (CSV/PDF)
      └── Download buttons

frontend/src/lib/
  └── exportApi.ts
      ├── exportAlertsToCSV()
      ├── exportAlertsToPDF()
      └── getExportStats()
```

**Integration Points:**
```
DashboardPage.tsx
  ├── Add ExportPanel component
  ├── Import exportApi
  └── Add download handler

App.tsx (optional)
  └── Add /export route for dedicated page
```

---

## 📋 Checklist de Implementação

### Phase 1: Backend - CSV Export (1h)

- [ ] Instalar reportlab e dependências
- [ ] Criar `ExportFilters` Pydantic model
- [ ] Criar `ExportService` class com:
  - [ ] `export_to_csv()` method
  - [ ] `export_to_pdf()` method (stub)
  - [ ] `get_alerts_for_export()` com filtros
  - [ ] `_validate_dates()` helper
- [ ] Criar endpoint `GET /api/alerts/export/csv`
- [ ] Adicionar validações de query params
- [ ] Testar localmente com curl

### Phase 2: Backend - PDF Export (1h)

- [ ] Implementar `export_to_pdf()` com reportlab
- [ ] Formatação visual com:
  - [ ] Header (title, date range)
  - [ ] Table com dados
  - [ ] Footer com timestamp/total
- [ ] Criar endpoint `GET /api/alerts/export/pdf`
- [ ] Testar localmente com curl

### Phase 3: Frontend - UI Components (1h)

- [ ] Criar `ExportPanel.tsx` com:
  - [ ] Date range picker (start_date, end_date)
  - [ ] Status filter dropdown
  - [ ] Patient filter dropdown
  - [ ] Format selector (CSV/PDF radio buttons)
  - [ ] "Download" button
  - [ ] "Reset filters" button
- [ ] Criar `exportApi.ts` com fetch functions
- [ ] Add loading/success/error states
- [ ] Add input validation

### Phase 4: Frontend - Integration (30min)

- [ ] Integrar ExportPanel em DashboardPage.tsx
- [ ] Add export button in header
- [ ] Connect download handlers
- [ ] Test file downloads work

### Phase 5: Testing & Docs (1h)

- [ ] Manual tests (12 scenarios)
- [ ] Edge case testing
- [ ] Performance testing with large datasets
- [ ] Create GUIA_TESTE_FASE3_3.md
- [ ] Create FASE_3_3_RESUMO_EXECUTIVO.md

---

## 💾 Database Queries

### Query for filtered alerts

```python
# In ExportService.get_alerts_for_export()

query = """
SELECT 
  alert_id,
  alert_timestamp,
  alert_type,
  severity,
  status,
  patient_id,
  observacao,
  created_at,
  updated_at
FROM alertas
WHERE 1=1
  AND (:start_date IS NULL OR alert_timestamp >= :start_date)
  AND (:end_date IS NULL OR alert_timestamp <= :end_date)
  AND (:status IS NULL OR status = :status)
  AND (:patient_id IS NULL OR patient_id = :patient_id)
ORDER BY alert_timestamp DESC
LIMIT :limit
"""

params = {
  'start_date': filters.start_date,
  'end_date': filters.end_date,
  'status': filters.status,
  'patient_id': filters.patient_id,
  'limit': filters.limit,
}
```

---

## 🎨 UI Components Design

### ExportPanel Component

```typescript
// frontend/src/components/ExportPanel.tsx

interface ExportFilters {
  startDate: Date | null;
  endDate: Date | null;
  status: 'all' | 'pending' | 'acknowledged' | 'completed';
  patientId: string | null;
  format: 'csv' | 'pdf';
}

function ExportPanel() {
  const [filters, setFilters] = useState<ExportFilters>({
    startDate: null,
    endDate: null,
    status: 'all',
    patientId: null,
    format: 'csv',
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const handleExport = async () => {
    // Call API based on format
    // Trigger browser download
  };
  
  const handleReset = () => {
    // Reset all filters to defaults
  };
  
  return (
    <div className="export-panel">
      {/* Date Range Picker */}
      {/* Status Filter */}
      {/* Patient Filter */}
      {/* Format Selector */}
      {/* Buttons: Download, Reset */}
      {/* Error message */}
    </div>
  );
}
```

### Integração em DashboardPage

```typescript
// frontend/src/components/pages/DashboardPage.tsx

export function DashboardPage() {
  return (
    <div className="dashboard">
      <header>
        <h1>Dashboard</h1>
        <ExportPanel />  {/* Add aqui */}
      </header>
      
      <div className="content">
        <StatsCards />
        <TimelineChart />
      </div>
    </div>
  );
}
```

---

## 📝 API Request Examples

### CSV Export

```bash
curl -X GET "http://localhost:8000/api/alerts/export/csv?start_date=2025-10-01&end_date=2025-10-27&status=pending" \
  -H "Authorization: Bearer user@email.com:1761567586" \
  -o alerts.csv

# Response
Content-Type: text/csv
Content-Disposition: attachment; filename="alertas_2025-10-01_2025-10-27.csv"

alert_id,alert_timestamp,alert_type,severity,status,patient_id
1,2025-10-27T10:00:00,postura,high,pending,PAC-0001
2,2025-10-27T11:00:00,pressao,medium,acknowledged,PAC-0001
```

### PDF Export

```bash
curl -X GET "http://localhost:8000/api/alerts/export/pdf?start_date=2025-10-01&patient_id=PAC-0001" \
  -H "Authorization: Bearer user@email.com:1761567586" \
  -o relatario.pdf

# Response
Content-Type: application/pdf
Content-Disposition: attachment; filename="relatorio_PAC-0001_2025-10-01.pdf"
[PDF binary content]
```

---

## 🧪 Test Scenarios

### Test 1: CSV Export - All Data
```
Filters: none (all defaults)
Expected: Download CSV with all alerts
```

### Test 2: CSV Export - Date Range
```
Filters: start_date=2025-10-20, end_date=2025-10-27
Expected: Only alerts in that range
```

### Test 3: CSV Export - Status Filter
```
Filters: status=pending
Expected: Only pending alerts
```

### Test 4: CSV Export - Patient Filter
```
Filters: patient_id=PAC-0001
Expected: Only alerts for PAC-0001
```

### Test 5: CSV Export - Combined Filters
```
Filters: date range + status + patient
Expected: Intersection of all filters
```

### Test 6: CSV - Large Dataset
```
Export with 10000+ rows
Expected: Completes in < 5s, file downloads
```

### Test 7: PDF Export - Basic
```
Filters: none
Expected: PDF with formatted table
```

### Test 8: PDF Export - With Filters
```
Filters: patient_id + date range
Expected: PDF title reflects filters
```

### Test 9: PDF - Formatting
```
Expected: Header, title, date range, table, footer, page numbers
```

### Test 10: UI - Date Picker
```
Select start and end dates
Expected: Dates populate in form
```

### Test 11: UI - Reset Filters
```
Set filters, click "Reset"
Expected: All filters cleared
```

### Test 12: UI - Download Button
```
Set filters, click "Download CSV/PDF"
Expected: File downloads with correct name
```

---

## ⚠️ Edge Cases

### Edge Case 1: Invalid Date Range
```
start_date > end_date
Response: 400 Bad Request
```

### Edge Case 2: No Results
```
Filters match zero alerts
Response: Empty CSV or PDF with "No data" message
```

### Edge Case 3: Invalid Status
```
status=invalid_status
Response: 400 Bad Request with valid values
```

### Edge Case 4: Non-existent Patient
```
patient_id=INVALID
Response: Empty results (silently)
```

### Edge Case 5: Very Old Dates
```
start_date=1990-01-01
Response: Only actual data returned
```

### Edge Case 6: Large Date Range
```
start_date=1995-01-01, end_date=2025-12-31
Response: All data, paginated/limited
```

### Edge Case 7: Unauthorized User
```
No Authorization header
Response: 401 Unauthorized
```

### Edge Case 8: Permission Check
```
User requests export for different patient
Response: Should check permissions (implement later)
```

---

## 📦 Dependencies to Install

```bash
pip install reportlab>=4.0.0 python-dateutil
```

Add to `requirements.txt`:
```
reportlab==4.0.9
python-dateutil==2.8.2
```

---

## 🚀 Implementation Sequence

**Hour 1: Backend CSV**
1. Install dependencies ✓
2. Create ExportFilters model
3. Create ExportService class
4. Implement CSV export logic
5. Create GET /api/alerts/export/csv endpoint

**Hour 2: Backend PDF**
1. Implement PDF export logic with reportlab
2. Create GET /api/alerts/export/pdf endpoint
3. Test both endpoints with curl
4. Handle edge cases

**Hour 3: Frontend UI**
1. Create ExportPanel component
2. Create exportApi.ts
3. Integrate in DashboardPage
4. Test UI interactions

**Hour 4: Testing & Docs**
1. Run 12 test scenarios
2. Fix any issues
3. Create documentation
4. Commit to git

---

## 📊 Success Criteria

✅ **CSV Export**
- Endpoint returns valid CSV
- Headers correctly named
- Filters work (date, status, patient)
- Large datasets (10k+ rows) work

✅ **PDF Export**
- Endpoint returns valid PDF
- Formatted with header/footer
- Table readable
- Filters reflected in title/content

✅ **Frontend**
- Date picker works
- Filter dropdowns populated
- Download buttons work
- Files have correct names
- No console errors

✅ **Testing**
- All 12 tests pass
- Edge cases handled
- Performance acceptable (< 5s)
- No breaking changes to existing code

✅ **Documentation**
- GUIA_TESTE_FASE3_3.md with screenshots
- API documentation updated
- Code comments for complex logic

---

## 📈 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| CSV generation (1k rows) | < 1s | Should be instant |
| CSV generation (10k rows) | < 5s | Database query bottleneck |
| PDF generation (1k rows) | < 2s | reportlab is slower |
| PDF generation (10k rows) | < 10s | May need pagination |
| File download | < 100ms | Network dependent |

---

## 🎓 Technical Notes

### CSV Format
- Use pandas for clean CSV generation
- Include headers
- Proper escaping for special characters
- UTF-8 encoding

### PDF Format
- Use reportlab's Table for data
- Include company header/footer
- Page numbers
- Proper margins and fonts
- Landscape mode for wide tables

### Date Handling
- Accept ISO 8601 format (2025-10-27)
- Accept ISO 8601 datetime with time
- Use server timezone
- Validate start_date <= end_date

### File Naming Convention
```
alertas_2025-10-01_2025-10-27.csv
relatorio_PAC-0001_2025-10-27.pdf
export_full_2025-10-27.csv
```

---

## ✅ Definição de Pronto

Uma tarefa está "pronta" quando:

1. ✅ Código implementado e testado localmente
2. ✅ Sem console errors/warnings
3. ✅ Testes passam (manuais ou automáticos)
4. ✅ Documentação criada
5. ✅ Commit pushed para git
6. ✅ Build compila sem erros

---

## 📞 Next Steps

1. ⏳ Revisão deste planejamento
2. 🚀 Começar Phase 1 (Backend CSV)
3. 📝 Atualizar status em STATUS_GERAL.md
4. 🔄 Commit inicial: "feat: FASE 3.3 - Planejamento de Relatórios/Export"

---

**Pronto para começar?** 🚀
