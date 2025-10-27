# 🧪 GUIA DE TESTE - FASE 3.3: Relatórios/Export

**Data:** Outubro 27, 2025  
**Objetivo:** Validar funcionalidades de exportação em CSV e PDF  
**Tempo Estimado:** 30-45 minutos  

---

## ✅ Pre-requisitos

- [ ] Backend rodando: `uvicorn interface.api:router --reload`
- [ ] Frontend rodando: `npm run dev`
- [ ] Browser aberto em `http://localhost:3000`
- [ ] Logado no sistema
- [ ] Dados de teste: Pelo menos 5-10 alertas no banco

---

## 📋 Testes Manuais

### Teste 1: CSV Export - Sem Filtros

**Objetivo:** Exportar todos os alertas em CSV

**Passos:**
1. Ir para Dashboard
2. Scroll até "Exportar Dados" panel
3. Deixar todos os campos em branco
4. Selecionar "CSV"
5. Clicar "Baixar CSV"

**Validações:**
- [ ] Arquivo baixa com nome padrão (ex: `alertas_20251027.csv`)
- [ ] Arquivo abre corretamente em Excel/Notepad
- [ ] Contém cabeçalhos: `alert_id, alert_timestamp, alert_type, severity, status, patient_id, observacao`
- [ ] Todos os alertas estão presentes
- [ ] Sem erros no console

---

### Teste 2: CSV Export - Com Data Range

**Objetivo:** Exportar apenas alertas em uma data específica

**Passos:**
1. Dashboard > Exportar Dados
2. Data Inicial: `2025-10-20`
3. Data Final: `2025-10-27`
4. Formato: CSV
5. Clicar "Baixar CSV"

**Validações:**
- [ ] Arquivo contém apenas alertas nesse período
- [ ] Alertas fora do período NÃO aparecem
- [ ] Nome do arquivo reflete datas (ex: `alertas_2025-10-20_2025-10-27.csv`)
- [ ] Número de linhas reduzido (esperado)

---

### Teste 3: CSV Export - Status Filter

**Objetivo:** Exportar apenas alertas com status específico

**Passos:**
1. Dashboard > Exportar Dados
2. Status: `Pendente`
3. Formato: CSV
4. Clicar "Baixar CSV"

**Validações:**
- [ ] Todos os alertas têm `status = pending`
- [ ] Alertas reconhecidos/completos não aparecem
- [ ] Arquivo nome inclui status (opcional)

**Repetir para:**
- [ ] Status = `Reconhecido`
- [ ] Status = `Concluído`

---

### Teste 4: CSV Export - Patient Filter

**Objetivo:** Exportar alertas de um paciente específico

**Passos:**
1. Dashboard > Exportar Dados
2. ID do Paciente: `PAC-0001` (ou existente)
3. Formato: CSV
4. Clicar "Baixar CSV"

**Validações:**
- [ ] Todos os alertas têm `patient_id = PAC-0001`
- [ ] Alertas de outros pacientes não aparecem
- [ ] Nome do arquivo inclui patient ID

---

### Teste 5: CSV Export - Filtros Combinados

**Objetivo:** Usar múltiplos filtros simultaneamente

**Passos:**
1. Dashboard > Exportar Dados
2. Data Inicial: `2025-10-20`
3. Data Final: `2025-10-27`
4. Status: `Pendente`
5. ID do Paciente: `PAC-0001`
6. Formato: CSV
7. Clicar "Baixar CSV"

**Validações:**
- [ ] Apenas alertas que correspondem A TODOS os filtros aparecem
- [ ] Interseção correta dos filtros
- [ ] Número de linhas bem reduzido

---

### Teste 6: CSV Export - Large Dataset

**Objetivo:** Testar exportação com muitos dados

**Passos:**
1. Limpar filtros (deixar em branco)
2. Formato: CSV
3. Clicar "Baixar CSV"
4. Medir tempo de download

**Validações:**
- [ ] Exportação completa em < 5 segundos
- [ ] Arquivo é válido (abre em Excel)
- [ ] Sem timeout/erro

**Observação:** Se houver < 100 alertas, resultado será rápido mesmo. Ideal ter 1000+.

---

### Teste 7: PDF Export - Sem Filtros

**Objetivo:** Exportar todos os alertas em PDF

**Passos:**
1. Dashboard > Exportar Dados
2. Deixar todos os campos em branco
3. Selecionar "PDF"
4. Clicar "Baixar PDF"

**Validações:**
- [ ] Arquivo baixa com nome padrão (ex: `relatorio_2025-10-27.pdf`)
- [ ] Arquivo abre corretamente em leitor PDF
- [ ] Contém:
  - [ ] Título: "Relatório de Alertas - UPP"
  - [ ] Data/período
  - [ ] Tabela com dados
  - [ ] Footer com timestamp
  - [ ] Cabeçalho com colunas
- [ ] Sem erros no console

---

### Teste 8: PDF Export - Com Patient ID

**Objetivo:** Exportar PDF de um paciente específico

**Passos:**
1. Dashboard > Exportar Dados
2. ID do Paciente: `PAC-0001`
3. Formato: PDF
4. Clicar "Baixar PDF"

**Validações:**
- [ ] PDF contém apenas alertas de `PAC-0001`
- [ ] Título do PDF identifica o paciente
- [ ] Nome do arquivo inclui patient ID (ex: `relatorio_PAC-0001_2025-10-27.pdf`)

---

### Teste 9: PDF Export - Formatting

**Objetivo:** Validar aparência visual do PDF

**Passos:**
1. Exportar um PDF (qualquer filtro)
2. Abrir em leitor PDF (Adobe, Preview, etc)
3. Examinar visual

**Validações:**
- [ ] Cabeçalho visível e legível
- [ ] Tabela formatada com cores alternadas
- [ ] Bordas da tabela presentes
- [ ] Fonte legível (não muito pequena)
- [ ] Footer com data/hora
- [ ] Página inteira visível (não cortada)
- [ ] Sem caracteres estranhos/corrupted

---

### Teste 10: UI - Data Picker Interaction

**Objetivo:** Validar data picker funciona

**Passos:**
1. Dashboard > Exportar Dados
2. Clicar campo "Data Inicial"
3. Selecionar uma data do calendário
4. Clicar campo "Data Final"
5. Selecionar outra data

**Validações:**
- [ ] Datas aparecem nos campos
- [ ] Formato correto (YYYY-MM-DD)
- [ ] Sem erros ao mudar datas
- [ ] Validação: Se start > end, deve mostrar erro

---

### Teste 11: UI - Reset Button

**Objetivo:** Testar limpeza de filtros

**Passos:**
1. Preencher todos os campos:
   - Data Inicial: `2025-10-01`
   - Data Final: `2025-10-27`
   - Status: `Pendente`
   - ID do Paciente: `PAC-0001`
2. Clicar botão "🔄 Limpar"

**Validações:**
- [ ] Todos os campos voltam vazios
- [ ] Status volta para "Todos"
- [ ] Formato volta para "CSV"
- [ ] Sem dados em memória

---

### Teste 12: Error Handling - Invalid Date Range

**Objetivo:** Testar validação de datas inválidas

**Passos:**
1. Data Inicial: `2025-10-27`
2. Data Final: `2025-10-01` (anterior!)
3. Clicar "Baixar CSV"

**Validações:**
- [ ] Erro aparece: "A data inicial deve ser anterior à data final"
- [ ] Exportação NÃO acontece
- [ ] Mensagem de erro legível
- [ ] Erro desaparece ao mudar datas

---

### Teste 13: Error Handling - No Results

**Objetivo:** Testar exportação com filtros que não retornam dados

**Passos:**
1. ID do Paciente: `PAC-INVALID-999`
2. Formato: CSV
3. Clicar "Baixar CSV"

**Validações:**
- [ ] Arquivo é criado mesmo com 0 dados
- [ ] Arquivo contém apenas cabeçalhos
- [ ] Sem erro (falha silenciosa)
- [ ] Para PDF: Mostra "Nenhum alerta encontrado"

---

### Teste 14: Error Handling - No Auth

**Objetivo:** Testar que endpoints são protegidos

**Passos:**
1. Fazer logout
2. Na console do browser (F12), executar:
   ```javascript
   fetch('/api/alerts/export/csv')
     .then(r => r.json())
     .then(console.log);
   ```

**Validações:**
- [ ] Retorna erro 401 Unauthorized
- [ ] Mensagem: "Não autenticado"
- [ ] Sem acesso ao arquivo

---

### Teste 15: Network - File Download

**Objetivo:** Validar headers HTTP corretos

**Passos:**
1. Dashboard > Exportar Dados
2. Formato: CSV
3. Abrir DevTools (F12) > Network tab
4. Clicar "Baixar CSV"
5. Procurar requisição GET para `/api/alerts/export/csv`

**Validações - CSV:**
- [ ] Status: 200 OK
- [ ] Content-Type: `text/csv`
- [ ] Content-Disposition: `attachment; filename=alertas_*.csv`

**Repetir para PDF:**
- [ ] Status: 200 OK
- [ ] Content-Type: `application/pdf`
- [ ] Content-Disposition: `attachment; filename=relatorio_*.pdf`

---

## 🐛 Edge Cases

### Edge Case 1: Very Large Date Range

**Passos:**
1. Data Inicial: `2000-01-01`
2. Data Final: `2025-12-31`
3. Clicar "Baixar CSV"

**Esperado:** Funciona, retorna todos os alertas disponíveis

---

### Edge Case 2: Same Start and End Date

**Passos:**
1. Data Inicial: `2025-10-27`
2. Data Final: `2025-10-27`
3. Clicar "Baixar CSV"

**Esperado:** Funciona, retorna apenas alertas de 27/10

---

### Edge Case 3: Special Characters in Patient ID

**Passos:**
1. ID do Paciente: `PAC-0001-SPECIAL!@#`
2. Clicar "Baixar CSV"

**Esperado:** Sem crashes, filtra normalmente (ou 0 resultados)

---

### Edge Case 4: Concurrent Exports

**Passos:**
1. Clicar "Baixar CSV"
2. Imediatamente clicar "Baixar PDF" (antes de terminar)

**Esperado:** Ambos downloads iniciam, sem conflito

---

### Edge Case 5: Browser Refresh During Export

**Passos:**
1. Clicar "Baixar PDF"
2. Enquanto está gerando (se lento), pressionar F5

**Esperado:** Download continua normalmente (navegador faz o download background)

---

## ✅ Checklist de Qualidade

- [ ] Nenhum erro no console (DevTools)
- [ ] Nenhum warning no console
- [ ] Todos os 15 testes acima passam
- [ ] UI é responsiva (sem layout quebrado)
- [ ] Botões têm feedback visual (hover, click)
- [ ] Loading state funciona (spinner ou texto)
- [ ] Error messages são claras
- [ ] Arquivos têm nomes descritivos
- [ ] Exports são rápidos (< 5s)
- [ ] TypeScript sem errors

---

## 📊 Resultados

Após completar todos os testes, preencher:

| Teste | Status | Notas |
|-------|--------|-------|
| 1. CSV - Sem Filtros | ✅ | - |
| 2. CSV - Date Range | ✅ | - |
| 3. CSV - Status Filter | ✅ | - |
| 4. CSV - Patient Filter | ✅ | - |
| 5. CSV - Filtros Combinados | ✅ | - |
| 6. CSV - Large Dataset | ✅ | - |
| 7. PDF - Sem Filtros | ✅ | - |
| 8. PDF - Patient ID | ✅ | - |
| 9. PDF - Formatting | ✅ | - |
| 10. UI - Date Picker | ✅ | - |
| 11. UI - Reset | ✅ | - |
| 12. Error - Invalid Dates | ✅ | - |
| 13. Error - No Results | ✅ | - |
| 14. Error - No Auth | ✅ | - |
| 15. Network - Headers | ✅ | - |
| **TOTAL** | **15/15** | **✅ PASSANDO** |

---

## 🚀 Próximos Passos

Se todos os testes passarem:

1. ✅ Marcar FASE 3.3 como completa
2. ✅ Fazer merge para branch main
3. ✅ Começar FASE 3.4 ou seguinte
4. ✅ Fazer deploy em staging

Se testes falharem:

1. 🔴 Documentar error
2. 🔴 Investigar root cause
3. 🔴 Criar issue
4. 🔴 Refazer teste após fix

---

**Data de Conclusão:** ________  
**Testador:** ________  
**Assinatura:** ________
