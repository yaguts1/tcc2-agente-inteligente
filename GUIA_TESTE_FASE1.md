# 🧪 GUIA DE TESTE - FASE 1

**Data:** 27 de outubro de 2025  
**O que testar:** Painel de simulação React integrado com backend  
**Tempo estimado:** 10 minutos  

---

## ✅ Pré-requisitos

### **1. Backend rodando**
```bash
cd c:\Users\thiag.AIGOOO\Documents\TCC\tcc2-agente-inteligente
uvicorn interface.api:router --reload
```

**Esperado:**
```
Uvicorn running on http://127.0.0.1:8000
Application startup complete
```

### **2. Frontend rodando**
```bash
cd frontend
npm run dev
```

**Esperado:**
```
VITE v6.3.5  ready in 234 ms
➜  Local:   http://localhost:3000/
```

### **3. Browser aberto**
```
http://localhost:3000/pacientes
```

---

## 🧪 TESTE 1: Criar Paciente com Simulação

### **Passo 1.1: Abrir formulário**
- [ ] Clique "Novo Paciente"

**Esperado:**
```
Form vazio com campos:
- Nome Completo
- Quarto
- Leito
- Nível de Risco (dropdown)
- Intervalo de Reposicionamento
```

### **Passo 1.2: Preencher dados**
```
Nome: João Silva
Quarto: 101A
Leito: Leito 1
Nível: Médio
Intervalo: 2 horas
```

**Ação:**
- [ ] Clique "Criar Paciente"

**Esperado:**
```
✅ Toast: "Paciente criado com sucesso"
Painel de simulação aparece com:
- Campo "Duração (horas)"
- Campo "Seed (opcional)"
- Dropdown "Perfil de Risco"
- Botão "▶️ Simular"
```

---

## 🧪 TESTE 2: Simular Dados

### **Passo 2.1: Preencher simulação**
```
Duração: 24
Seed: 42
Perfil: Médio
```

**Ação:**
- [ ] Clique "▶️ Simular"

**Esperado:**
```
Spinner: "Gerando dados (24h)..."
(Aguardar 2-5 segundos)
```

### **Passo 2.2: Verificar sucesso**

**Esperado:**
```
✅ Card de sucesso (fundo verde):
  "✅ Simulação concluída com sucesso!"
  
Métricas:
  Duração: 24h
  Eventos gerados: 288
  Alertas processados: 12
  Status: Concluído
  
Mensagem:
  "Verifique a Timeline para visualizar os eventos gerados."
```

**Ação:**
- [ ] Clique "Gerar Novos Dados"

**Esperado:**
```
Form volta ao estado vazio pronto para nova simulação
```

---

## 🧪 TESTE 3: Verificar Timeline

### **Passo 3.1: Navegação**
- [ ] Clique no menu esquerdo "Timeline"

**Esperado:**
```
Página carrega com título "Histórico de Eventos"
Agrupação por data
```

### **Passo 3.2: Buscar eventos gerados**
- [ ] Procure por eventos da data de hoje

**Esperado:**
```
Timeline mostra:
- 288 eventos de postura (aprox)
- Tipos: postura (Deitado, Sentado, Em pé)
- Timestamps em 5min de intervalo
- Cards com cores e ícones
```

**Exemplo:**
```
2025-10-27 00:00  →  Deitado (60 min)
2025-10-27 01:00  →  Sentado (45 min)
2025-10-27 02:00  →  Em pé (30 min)
...
```

---

## 🧪 TESTE 4: Verificar Alertas

### **Passo 4.1: Navegação**
- [ ] Clique no menu esquerdo "Dashboard"

**Esperado:**
```
Página Dashboard carrega
Stats cards mostram números
```

### **Passo 4.2: Buscar alertas**
- [ ] Procure na tabela de alertas ativos

**Esperado:**
```
Tabela mostra:
- ~12 alertas novos
- Status: Pendente/Reconhecido
- Próximo reposicionamento: dentro de 2h
- Cores visuais (verde normal, vermelho atrasado)
```

---

## 🧪 TESTE 5: Editar Paciente Existente

### **Passo 5.1: Voltar e editar**
- [ ] Clique "Voltar à Lista"
- [ ] Clique "Editar" no paciente criado

**Esperado:**
```
Form carrega com dados preenchidos
Painel de simulação reaparece abaixo
```

### **Passo 5.2: Simular novamente com seed diferente**
```
Duração: 48
Seed: 123
Perfil: Alto
```

**Ação:**
- [ ] Clique "▶️ Simular"

**Esperado:**
```
✅ Nova simulação concluída
576 eventos (48h × 1 evento a cada 5min)
Mais alertas gerados (perfil Alto)
```

---

## 🧪 TESTE 6: Tratamento de Erros

### **Passo 6.1: Tentar duração inválida**
```
Duração: 100 (inválido!)
Seed: 42
Perfil: Médio
```

**Ação:**
- [ ] Clique "▶️ Simular"

**Esperado:**
```
❌ Erro em vermelho:
"Duração deve estar entre 1 e 72 horas"
Form fica visível para correção
```

### **Passo 6.2: Tentar perfil inválido**
(Se conseguir enviar via console)

**Esperado:**
```
❌ Erro 400 Bad Request
"Perfil inválido"
```

### **Passo 6.3: Paciente não existe**
(Manualmente testar via curl)

**Comando:**
```bash
curl -X POST http://localhost:8000/api/pacientes/PAC-INVALID/simular \
  -H "Content-Type: application/json" \
  -d '{"duracao_horas":24,"seed":42,"perfil":"medio"}'
```

**Esperado:**
```
404 Not Found
{
  "detail": {
    "code": "paciente_nao_encontrado",
    "message": "Paciente PAC-INVALID nao encontrado."
  }
}
```

---

## 📊 Matriz de Testes

| Teste | Descrição | Status |
|-------|-----------|--------|
| **1.1** | Abrir formulário novo paciente | ⬜ |
| **1.2** | Preencher e criar paciente | ⬜ |
| **2.1** | Preencher simulação | ⬜ |
| **2.2** | Verificar sucesso e métricas | ⬜ |
| **3.1** | Acessar timeline | ⬜ |
| **3.2** | Ver eventos gerados | ⬜ |
| **4.1** | Acessar dashboard | ⬜ |
| **4.2** | Ver alertas gerados | ⬜ |
| **5.1** | Editar paciente | ⬜ |
| **5.2** | Simular novamente | ⬜ |
| **6.1** | Erro duração inválida | ⬜ |
| **6.2** | Erro perfil inválido | ⬜ |
| **6.3** | Erro paciente não existe | ⬜ |

---

## 🐛 Troubleshooting

### **Problema: Painel não aparece**
```
✓ Verificar se paciente foi salvo (check toast)
✓ Recarregar página (F5)
✓ Verificar console do browser (F12)
```

### **Problema: Simulação não funciona**
```
✓ Verificar backend rodando (http://localhost:8000/docs)
✓ Verificar logs do backend
✓ Tentar com seed 42 (valor padrão)
✓ Tentar com duração 24 (valor padrão)
```

### **Problema: Dados não aparecem na Timeline**
```
✓ Recarregar página Timeline (F5)
✓ Verificar data (deve ser hoje)
✓ Verificar database: SELECT COUNT(*) FROM grade;
```

### **Problema: Alertas não aparecem no Dashboard**
```
✓ Recarregar página Dashboard (F5)
✓ Verificar database: SELECT COUNT(*) FROM alertas;
✓ Verificar se alertas foram processados (check logs)
```

---

## 📋 Checklist Final

- [ ] Backend compila e roda
- [ ] Frontend compila e roda
- [ ] Painel aparece após criar paciente
- [ ] Simulação completa com sucesso
- [ ] Timeline mostra 288 eventos
- [ ] Dashboard mostra ~12 alertas
- [ ] Edição reutiliza painel
- [ ] Erros são tratados corretamente
- [ ] Database é atualizado corretamente
- [ ] Sem erros no console

---

## ✅ Resultado Esperado

Se todos os testes passarem:

```
🎉 FASE 1 FUNCIONAL E PRONTA PARA USO! 🎉

✅ Painel de simulação criado
✅ Dados sendo gerados corretamente
✅ Timeline atualiza com eventos
✅ Alertas aparecem no dashboard
✅ Sem bugs ou erros
✅ Pronto para produção
```

---

## 📞 Se encontrar erros

1. Capture screenshot
2. Copie mensagem de erro
3. Verifique logs do backend
4. Verifique console do browser (F12)
5. Reporte com contexto

---

**Tempo estimado:** 10-15 minutos  
**Dificuldade:** Fácil  
**Requisitos:** Apenas o browser e terminal  

**Bom teste! 🚀**

