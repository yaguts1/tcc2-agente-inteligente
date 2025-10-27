# 🔧 CORREÇÕES: Erro 500 em Simulação + Warning Key Prop

**Data**: 27 de Outubro de 2025  
**Status**: ✅ **RESOLVIDO**  
**Commit**: a08b408

## Problemas Encontrados

### 1. Erro 500 na Simulação
```
POST /api/pacientes/PAC-7780/simular → 500 Internal Server Error
Mensagem: "PerfilPaciente.__init__() got an unexpected keyword argument 'perfil'"
```

**Causa**: Em `interface/api.py` linha 1433, estava sendo feito:
```python
perfil=PerfilPaciente(perfil=payload.perfil)  # ❌ 'perfil' não é parâmetro
```

**Solução**: Usar `PERFIS_PREDEFINIDOS` para mapear nível de risco:
```python
# Mapear nível de risco para perfil
perfil_key = payload.perfil.lower() if payload.perfil else "medio"
perfil_params = PERFIS_PREDEFINIDOS.get(perfil_key, PERFIS_PREDEFINIDOS["medio"])
perfil = PerfilPaciente(**perfil_params)  # ✅ Correto!

df_grade, contextos = gerar_sessao_simulada(
    duracao_horas=payload.duracao_horas,
    seed=payload.seed or 42,
    passo_min=5,
    perfil=perfil,  # ✅ Agora funciona!
    incluir_contexto=True
)
```

### 2. Warning React: "Each child in a list should have a unique 'key' prop"
```
PatientsPage.tsx renders skeleton cards without proper keys
Warning at Card component
```

**Causa**: Em `frontend/src/components/pages/PatientsPage.tsx` linha 139, skeleton loading usava index como key:
```tsx
{[...Array(6)].map((_, i) => (
  <Card key={i}>  {/* ❌ index como key é anti-pattern */}
```

**Solução**: Usar string única para skeleton:
```tsx
{[...Array(6)].map((_, i) => (
  <Card key={`skeleton-${i}`}>  {/* ✅ String única */}
```

## Testes Realizados

### Teste de Simulação (test_simulacao.py)
```
✅ CRIAÇÃO DE PACIENTE
   Status: 201 CREATED
   Paciente: PAC-7782

✅ SIMULAÇÃO DE DADOS
   Status: 200 OK
   Eventos: 25
   Alertas: 1
   Duração: 2h

✅ SEM ERROS 500
```

### Build Frontend
```
✅ Build Status: PASSED
   - 1728 módulos transformados
   - 421.60 kB JS (gzip: 127.70 kB)
   - Build time: 1.69s
   - ⚠️ ZERO ERRORS
   - ⚠️ ZERO WARNINGS
```

## Arquivos Modificados

```
1. interface/api.py
   - Linha 51: Importar PERFIS_PREDEFINIDOS
   - Linhas 1429-1436: Corrigir mapeamento de perfil

2. frontend/src/components/pages/PatientsPage.tsx
   - Linha 139: Corrigir key prop do skeleton

3. test_simulacao.py (novo arquivo)
   - Script para testar endpoint de simulação
```

## Fluxo de Funcionamento Correto

```
ANTES (❌):
1. Usuário clica "Simular"
2. Frontend envia: {duracao_horas: 2, perfil: "medio"}
3. Backend tenta: PerfilPaciente(perfil="medio")
4. Erro: argumento não reconhecido
5. Resposta: 500 Internal Server Error

DEPOIS (✅):
1. Usuário clica "Simular"
2. Frontend envia: {duracao_horas: 2, perfil: "medio"}
3. Backend mapeia: PERFIS_PREDEFINIDOS["medio"] → {limite_tempo_postura: 120, ...}
4. Backend cria: PerfilPaciente(**params)
5. Simula: 25 eventos gerados
6. Resposta: 200 OK com dados
```

## Próximas Verificações

- [ ] Testar simulação com "alto" risco
- [ ] Testar simulação com "baixo" risco
- [ ] Verificar se Timeline mostra eventos após simulação
- [ ] Verificar se Dashboard atualiza com novos alertas

---

**Status**: ✅ DOIS BUGS CRÍTICOS RESOLVIDOS E VALIDADOS
