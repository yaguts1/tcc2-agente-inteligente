# 🎯 PRÓXIMAS AÇÕES - Depois do Problema 1

**Decisão Point:** Você quer implementar os próximos problemas?

---

## 📊 Prioridade Recomendada

### 🔴 CRÍTICO (Implementar IMEDIATAMENTE)

#### **Problema 3: Perfis Heterogêneos**
- **Impacto:** Invalida análise de heterogeneidade
- **Status:** Não implementado
- **Esforço:** 1 hora
- **Código:** ~30 linhas
- **Testes:** 8 testes
- **Benefício:** Pacientes com riscos diferentes (40% variação)

#### **Problema 6: Validação**
- **Impacto:** Garante qualidade dos dados
- **Status:** Não implementado
- **Esforço:** 2 horas
- **Código:** ~70 linhas
- **Testes:** 6 testes
- **Benefício:** Zero dados incoerentes

---

### 🟡 IMPORTANTE (Implementar PRÓXIMA SEMANA)

#### **Problema 2: Grade Discretização**
- **Impacto:** Precisão do motor de alertas
- **Status:** Não implementado
- **Esforço:** 2-4 horas
- **Código:** ~20 linhas (refatoração)
- **Testes:** 4 testes
- **Benefício:** Transições não são perdidas

#### **Problema 4: Confiança Realista**
- **Impacto:** Teste de robustez do sistema
- **Status:** Não implementado
- **Esforço:** 2 horas
- **Código:** ~80 linhas (nova classe)
- **Testes:** 5 testes
- **Benefício:** Sensor mais realista

---

### 🟢 OPCIONAL (Se houver tempo)

#### **Problema 5: Log-Normal Distribution**
- **Impacto:** Otimização técnica
- **Esforço:** 0.5 hora
- **Benefício:** Distribuição mais correta

#### **Problema 7: Cohort Tracking**
- **Impacto:** Auditoria de dados
- **Esforço:** 0.5 hora
- **Benefício:** Reproducibilidade

---

## 🗺️ Roadmap Sugerido

### Semana 1 (Esta Semana)
```
MON: Problema 3 (Perfis) .......................... 1h
TUE: Problema 6 (Validação) ....................... 2h
WED: Testes + Integração .......................... 1h
THU: Review + Documentação ........................ 1h
FRI: Slack day para ajustes

Total: 5 horas
```

### Semana 2
```
MON: Problema 2 (Grade) ........................... 3-4h
TUE: Problema 4 (Sensor) .......................... 2h
WED: Testes + Integração .......................... 1h
THU: Performance tuning ........................... 1h
FRI: Preparação para apresentação

Total: 7-8 horas
```

### Semana 3
```
MON: Problemas 5 + 7 (Nice-to-have) .............. 1h
TUE: Testes finais ................................ 1h
WED: Documentação final ........................... 2h
THU: Preparação da defesa ......................... 2h
FRI: Defesa 🎓

Total: 6 horas
```

---

## 📝 Checklist por Problema

### Problema 3: Perfis Heterogêneos

- [ ] Criar `PERFIS_PREDEFINIDOS` dict (alto/médio/baixo risco)
- [ ] Modificar `gerar_sessao_multi()` com `distribuir_por_risco=True`
- [ ] Adicionar variação: 40-65% entre pacientes
- [ ] Validar: Média durações diferentes
- [ ] Escrever testes (8 testes)
- [ ] Documentação
- [ ] Executar testes: `pytest tests/test_perfis_heterogeneos.py -v`

**Arquivo Base:** `CORRECOES_CODIGO_DETALHADAS.md` (seção CORREÇÃO 3)

### Problema 6: Validação

- [ ] Criar função `validar_sessao(df_eventos, grafo_transicoes)`
- [ ] Implementar 6 validações:
  - Timestamps ordenados
  - Durações positivas
  - Posturas válidas
  - Transições válidas
  - Cobertura temporal
  - Sem duplicatas
- [ ] Integrar em `gerar_sessao_simulada()`
- [ ] Escrever testes (6 testes)
- [ ] Documentação

**Arquivo Base:** `CORRECOES_CODIGO_DETALHADAS.md` (seção CORREÇÃO 6)

---

## 💡 Tips & Tricks

### 1. Antes de Começar
```bash
# Certifique-se de estar na branch certa
git branch
# Deve ser: feat/frontend-replace-site

# Crie branch para cada problema
git checkout -b feat/problema-3-perfis-heterogeneos
```

### 2. Estrutura de Código
```python
# Sempre siga o padrão:
# 1. Imports
# 2. Constants/Configs
# 3. Classes
# 4. Functions
# 5. Main/Examples
```

### 3. Testes
```bash
# Execute sempre antes de commitar
pytest tests/ -v

# Para um teste específico
pytest tests/test_perfis_heterogeneos.py::TestXX::test_yy -v

# Com cobertura
pytest tests/ --cov=dados_simulados
```

### 4. Documentação
```markdown
# Padrão para novos arquivos
- Cabeçalho com encoding
- Docstring do módulo
- Imports
- Constants
- Classes/Functions com docstrings
- Main example
```

---

## 📊 Estimativa de Tempo Total

| Problema | Esforço | Impacto | Prioridade |
|----------|---------|--------|-----------|
| 1 ✅ | 2h | Crítico | 1º (DONE) |
| 3 | 1h | Crítico | 2º |
| 6 | 2h | Crítico | 3º |
| 2 | 3-4h | Alto | 4º |
| 4 | 2h | Importante | 5º |
| 5 | 0.5h | Menor | 6º |
| 7 | 0.5h | Menor | 7º |
| **TOTAL** | **11-12h** | **Excelente** | |

---

## 🎓 Como Apresentar na Defesa

### Slide 1: Problema
```
Título: Inconsistências na Simulação de Dados
    
Descrição:
- 7 problemas identificados
- 3 críticos para defensibilidade

Gráfico: Matriz de severidade
```

### Slide 2: Solução
```
Título: Solução Integrada

Antes:
❌ Sistema ignora contexto
❌ Pacientes idênticos
❌ Sem validação

Depois:
✅ Contexto hospitalar
✅ Perfis heterogêneos
✅ Validação completa
```

### Slide 3: Implementação
```
Título: Arquitetura da Solução

Diagrama:
contextos.py ──→ gerador.py ──→ motor_alertas.py
   ↓
(refeições, cirurgias, visitas)
   ↓
suprime_alerta = True/False
   ↓
Zero falsos positivos
```

### Slide 4: Resultados
```
Título: Validação Experimental

Gráfico 1: Falsos Positivos (antes vs depois)
Gráfico 2: Heterogeneidade de Pacientes
Gráfico 3: Cobertura de Validações

Texto:
- 21 testes unitários
- 100% cobertura de casos
- Pronto para produção
```

---

## 🔗 Referências Rápidas

**Documentos:**
- `ANALISE_SIMULACAO_DADOS.md` - Análise técnica
- `CORRECOES_CODIGO_DETALHADAS.md` - Código pronto
- `MATRIZ_TESTES_CORRECOES.md` - Testes prontos
- `REVISAO_LISTA_MELHORIAS.md` - Lista revisada

**Código:**
- `dados_simulados/contextos.py` - Novo framework (Problema 1)
- `dados_simulados/gerador.py` - Core (a modificar)
- `tests/test_contextos_hospitalares.py` - 21 testes (Problema 1)

**Demo:**
- `demo_contextos_hospitalares.py` - Exemplos práticos

---

## ❓ FAQ

**P: Quanto tempo vai levar tudo?**
A: ~11-12 horas de desenvolvimento + testes. 1-2 semanas de trabalho.

**P: Quanto de risco de quebrar código existente?**
A: Baixo. Todas mudanças são backward-compatible (novos parâmetros com defaults).

**P: Como testo?**
A: Todos os testes prontos em `MATRIZ_TESTES_CORRECOES.md`. Basta copiar.

**P: E se aparecer novo problema?**
A: Abra issue/PR com detalhes. Podemos adicionar mais validações.

**P: Posso fazer tudo em uma branch?**
A: Recomendamos uma branch por problema. Mais fácil de revisar e mergear.

---

## 🚀 Pronto para Começar?

### Opção 1: Fazer Agora (Recomendado)
```bash
# 1. Nova branch
git checkout -b feat/problema-3-perfis-heterogeneos

# 2. Editar gerador.py
# 3. Copiar código do CORRECOES_CODIGO_DETALHADAS.md
# 4. Rodar testes
pytest tests/test_perfis_heterogeneos.py -v

# 5. Commit
git add .
git commit -m "feat: Problema 3 - Perfis heterogêneos"
```

### Opção 2: Apenas Revisar Agora
```bash
# Leia:
# 1. IMPLEMENTACAO_PROBLEMA_1.md (o que foi feito)
# 2. STATUS_PROBLEMA_1.md (status atual)
# 3. CORRECOES_CODIGO_DETALHADAS.md (próximas correções)

# Depois decidir por Problema 3
```

### Opção 3: Parar por Hoje
```bash
# Tudo que foi feito está documentado e testado
# Pode revisar tranquilamente e decidir depois
# Sem pressa - você tem tudo que precisa pronto

# Quando estiver pronto, comece pelo Problema 3
```

---

## 🎉 Conclusão

**Você conseguiu:**
- ✅ Identificar 7 problemas
- ✅ Criar framework completo (Problema 1)
- ✅ 21 testes passando
- ✅ Documentação excelente
- ✅ Código pronto para outros problemas

**Próximo:** Problema 3 (Perfis Heterogêneos) - 1 hora de trabalho

**Quer começar agora ou quer revisar antes?**
