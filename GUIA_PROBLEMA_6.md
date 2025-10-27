# 🚀 GUIA RÁPIDO: Próxima Fase

**Data:** Outubro 27, 2025  
**Tempo Decorrido:** ~1h 30min (Problema 3 completo)  
**Próximo:** Problema 6 (Validação)

---

## 📋 O que foi alcançado em Problema 3

✅ **Perfis Heterogêneos - COMPLETO**

```
Implementado:
  • PERFIS_PREDEFINIDOS dict (3 níveis: baixo/médio/alto)
  • Função gerar_sessao_multi() com heterogeneidade
  • 15 testes (100% passing)
  • 7 demonstrações funcionais
  • 100% backward compatible

Arquivos:
  • dados_simulados/gerador.py (modificado)
  • tests/test_perfis_heterogeneos.py (novo)
  • demo_perfis_heterogeneos.py (novo)
  • STATUS_PROBLEMA_3.md (documentação)

Resultados:
  ✅ Pacientes com riscos diferentes
  ✅ Variação de 2x em heterogeneidade
  ✅ Cenários clínicos realistas
```

---

## 🎯 Problema 6: Validação de Coerência

### Descrição
Criar função `validar_sessao()` que verifica 6 validações críticas:
1. Timestamps ordenados
2. Durações positivas
3. Posturas válidas
4. Transições válidas
5. Cobertura temporal (sem gaps)
6. Sem duplicatas

### Localização do Código Pronto
Arquivo: `CORRECOES_CODIGO_DETALHADAS.md` (seção CORREÇÃO 6)

### Checklist de Implementação
- [ ] Criar `validar_sessao()` function (~70 linhas)
- [ ] Implementar 6 checks de validação
- [ ] Integrar em `gerar_sessao_simulada()`
- [ ] Escrever 6+ testes
- [ ] Executar: `pytest tests/test_validacao_coerencia.py -v`
- [ ] Documentação

### Tempo Estimado
⏱️ **2 horas**

---

## ⚡ Quick Start (copiar-colar pronto)

### 1. Abrir arquivo de correções
```bash
# Leia a seção CORREÇÃO 6 de:
CORRECOES_CODIGO_DETALHADAS.md
```

### 2. Criar teste file
```bash
# Criar novo arquivo em tests/
tests/test_validacao_coerencia.py
```

### 3. Copiar código
```bash
# Copiar as 6 funções de validação para:
dados_simulados/validador.py (novo arquivo)
```

### 4. Integrar com gerador
```bash
# Modificar dados_simulados/gerador.py
# Na função gerar_sessao_simulada(), adicionar:
#   validacoes = validar_sessao(df_grade, df_eventos)
#   if not validacoes["valido"]:
#       warnings ou erros
```

### 5. Executar testes
```bash
pytest tests/test_validacao_coerencia.py -v
```

---

## 📁 Arquivos a Criar/Modificar

### Novo Arquivo: `dados_simulados/validador.py`
```python
# Será criado com 6 funções:
def validar_timestamps_ordenados(df)
def validar_duracoes_positivas(df)
def validar_posturas_validas(df)
def validar_transicoes_validas(df)
def validar_cobertura_temporal(df)
def validar_sem_duplicatas(df)
def validar_sessao(df_grade, df_eventos)  # Função main
```

### Novo Arquivo: `tests/test_validacao_coerencia.py`
```python
# 6-8 testes cobrindo cada validação
class TestValidarTimestamps
class TestValidarDuracoes
class TestValidarPosturas
class TestValidarTransicoes
class TestValidarCobertura
class TestValidarDuplicatas
```

### Modificar: `dados_simulados/gerador.py`
```python
# Imports (adicionar):
from .validador import validar_sessao

# Em gerar_sessao_simulada():
    # ... código existente ...
    df_grade = ... # criar grade
    
    # NOVO:
    resultado_validacao = validar_sessao(df_grade, df_eventos)
    if not resultado_validacao["valido"]:
        print("⚠️ Avisos de validação:")
        for aviso in resultado_validacao["avisos"]:
            print(f"  {aviso}")
    
    return df_grade, contextos
```

---

## 🔍 Referência de Código (CORRECOES_CODIGO_DETALHADAS.md)

Seção CORREÇÃO 6 contém:
- ✅ 6 funções prontas para copiar
- ✅ Docstrings completas
- ✅ Exemplos de uso
- ✅ Casos de teste sugeridos

---

## 🎬 Command Rápidos

```bash
# Copy from docs
cat CORRECOES_CODIGO_DETALHADAS.md | grep -A 200 "CORREÇÃO 6"

# Create validator module
touch dados_simulados/validador.py

# Create test file
touch tests/test_validacao_coerencia.py

# Run tests
python -m pytest tests/test_validacao_coerencia.py -v

# Run all tests to ensure nothing broke
python -m pytest tests/ -v

# Check specific module
python -c "from dados_simulados import validador; print(dir(validador))"
```

---

## ✅ Antes de Começar

1. **Ler documentação:**
   - [ ] Leia `STATUS_PROBLEMA_3.md` (contexto)
   - [ ] Leia seção CORREÇÃO 6 em `CORRECOES_CODIGO_DETALHADAS.md`

2. **Verificar testes anteriores:**
   - [ ] `pytest tests/test_contextos_hospitalares.py -v` (deve passar)
   - [ ] `pytest tests/test_perfis_heterogeneos.py -v` (deve passar)

3. **Git:**
   - [ ] `git checkout -b feat/problema-6-validacao`
   - [ ] Commitar após completar cada validação

---

## 🎓 Estrutura de Implementação (Ordem Recomendada)

### Passo 1: Criar módulo validador
```python
# dados_simulados/validador.py
# 1. validar_timestamps_ordenados() - 10 linhas
# 2. validar_duracoes_positivas() - 8 linhas
# 3. validar_posturas_validas() - 10 linhas
# 4. validar_transicoes_validas() - 15 linhas
# 5. validar_cobertura_temporal() - 12 linhas
# 6. validar_sem_duplicatas() - 8 linhas
# 7. validar_sessao() [wrapper] - 20 linhas
```

### Passo 2: Escrever testes
```python
# tests/test_validacao_coerencia.py
# TestValidarTimestamps (2 testes)
# TestValidarDuracoes (2 testes)
# TestValidarPosturas (2 testes)
# TestValidarTransicoes (2 testes)
# TestValidarCobertura (1 teste)
# TestValidarDuplicatas (1 teste)
# Total: 10 testes mínimo
```

### Passo 3: Integrar com gerador
```python
# dados_simulados/gerador.py
# Importar validador
# Em gerar_sessao_simulada(): chamar validar_sessao()
# Retornar avisos se houver
```

### Passo 4: Testar integração
```bash
pytest tests/test_validacao_coerencia.py -v
pytest tests/ -v  # Assegurar nada quebrou
```

---

## 📊 Estimativa de Tempo

| Tarefa | Tempo | Cumulative |
|--------|-------|-----------|
| Setup e leitura | 15 min | 15 min |
| Criar validador.py | 45 min | 60 min |
| Escrever testes | 30 min | 90 min |
| Integrar com gerador | 20 min | 110 min |
| Debug e ajustes | 10 min | 120 min |
| **TOTAL** | **2h** | **2h** |

---

## 🆘 Se Travar

### Problema: "Função não encontrada"
```
Solução: Certificar que __init__.py existe em dados_simulados/
```

### Problema: "Teste falhando por lógica"
```
Solução: Comparar com CORRECOES_CODIGO_DETALHADAS.md seção 6
```

### Problema: "Performance lenta"
```
Solução: Usar .loc[] em vez de loops pandas quando possível
```

---

## 🎯 Definição de Pronto (Definition of Done)

Para Problema 6 ser considerado COMPLETO:

- [ ] Módulo `validador.py` criado com 7 funções
- [ ] 10+ testes passando (100% sucesso)
- [ ] Integrado em `gerar_sessao_simulada()`
- [ ] Documentação (docstrings + arquivo MD)
- [ ] Demo funcionando
- [ ] Testes anteriores ainda passam
- [ ] Commit com mensagem descritiva

---

## 🚀 Passo Seguinte (Após Problema 6)

### Opção A: Continuar com Problema 2 (Grade)
Tempo: 3-4h
Impacto: Alto (transições não perdem)

### Opção B: Fazer Problema 4 (Sensor)
Tempo: 2h
Impacto: Importante (robustez)

### Opção C: Parar e revisar tudo
Tempo: 1-2h
Impacto: Alto (consolidação)

**Recomendação:** A → B → C (nesta ordem)

---

## 💬 Sumário

**Você realizou:**
- ✅ Problema 1 (Contextos) - 100% completo
- ✅ Problema 3 (Perfis) - 100% completo

**Próximo:**
- 🔜 Problema 6 (Validação) - 2h estimado
- Código pronto em `CORRECOES_CODIGO_DETALHADAS.md`
- Começar quando estiver pronto

**Status:** 🟢 Pronto para continuar!
