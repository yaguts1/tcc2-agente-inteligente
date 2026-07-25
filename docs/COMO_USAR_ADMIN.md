# 🛠️ Como Usar a Página de Administração

**Página de Admin** - Gerenciar eventos de dispositivos e reconciliação

---

## 📋 Visão Geral

A página de Administração permite gerenciar **eventos órfãos** - dados recebidos de dispositivos ESP32 que chegaram **antes** de serem associados a um paciente.

---

## 🎯 Quando Usar?

### **Cenário Típico:**

```
09:00 - ESP32 (device_001) começa a enviar dados de pressão
        ❌ Ainda não há device_assignment
        → Dados vão para tabela device_events (PENDENTES)

09:15 - Enfermeiro associa device_001 ao Paciente João
        ✅ device_assignment criado

09:20 - Admin clica em "Reconciliar"
        ✅ Eventos das 09:00-09:15 são processados retroativamente
        ✅ Dados agora estão associados ao Paciente João
```

---

## 🔧 Funcionalidades

### **1. Botão "Atualizar" 🔄**

**O que faz:**
- Recarrega a lista de eventos do banco de dados
- Mostra eventos recém-chegados ou recém-processados

**Quando usar:**
- Após criar um device_assignment
- Para verificar se novos eventos chegaram
- Após reconciliação, para ver mudanças de status

---

### **2. Botão "Reconciliar" ✅**

**O que faz:**
1. Busca todos eventos com status `PENDENTE`
2. Para cada evento:
   - Verifica se existe `device_assignment` para aquele dispositivo no momento do evento
   - Se SIM → Processa evento e marca como `PROCESSADO`
   - Se NÃO → Mantém `PENDENTE` para tentar depois

**Quando usar:**
- Após criar device_assignments
- Quando há eventos pendentes que já deveriam ter pacientes associados
- Periodicamente para limpar eventos órfãos

---

## 📊 Entendendo a Tabela

| Coluna | Descrição |
|--------|-----------|
| **ID** | Identificador único do evento |
| **Dispositivo** | ID do ESP32 que enviou os dados |
| **Timestamp** | Data/hora em que o evento foi capturado |
| **Dados (Payload)** | Conteúdo JSON do evento (clique "Ver completo" para expandir) |
| **Criado em** | Quando o servidor recebeu o evento |
| **Status** | 🟡 Pendente / 🟢 Processado |
| **Processado em** | Quando foi reconciliado (se aplicável) |

---

## 🔄 Fluxo Completo de Reconciliação

### **Passo 1: Eventos Órfãos Chegam**

```json
// ESP32 envia dados às 10:00
{
  "device_id": "ESP32_QUARTO_201",
  "postura": "decubito_dorsal",
  "confianca": 0.85,
  "amostra_ms": 1761710000000,
  "ts_utc": "2025-10-29T10:00:00Z",
  "pressao_pico": 420.5
}
```

**Problema**: Não há paciente associado → Evento fica **PENDENTE**

---

### **Passo 2: Criar Device Assignment**

**Opção A - Via Interface (Página de Pacientes):**
1. Acesse "Pacientes"
2. Selecione o paciente
3. Clique em "Associar Dispositivo"
4. Escolha o ESP32 e defina período

**Opção B - Via API:**
```bash
POST /api/device_assignments
{
  "device_id": "ESP32_QUARTO_201",
  "paciente_id": "PAC-001",
  "start_ts": "2025-10-29T09:00:00Z"
}
```

---

### **Passo 3: Reconciliar**

1. Vá para **Admin** no menu lateral
2. Clique no botão **"Reconciliar"**
3. Sistema processa eventos órfãos automaticamente
4. Eventos são marcados como **PROCESSADO**

---

### **Passo 4: Verificar Resultado**

**Antes da Reconciliação:**
```
ID | Device              | Status    | Processado em
#7 | ESP32_QUARTO_201    | Pendente  | -
```

**Depois da Reconciliação:**
```
ID | Device              | Status      | Processado em
#7 | ESP32_QUARTO_201    | Processado  | 29/10/2025, 10:20
```

**No Dashboard:**
- Evento agora aparece para o Paciente João
- Alertas foram gerados (se aplicável)
- Histórico está completo

---

## 🎨 Cards de Métricas

### **Eventos Pendentes 🟡**
- Eventos aguardando reconciliação
- Dispositivo ainda não associado a paciente

### **Eventos Processados 🟢**
- Eventos já reconciliados com sucesso
- Dados integrados ao sistema

### **Total de Eventos ⚙️**
- Soma de pendentes + processados
- Inclui eventos de todos os dispositivos

---

## ⚠️ Troubleshooting

### **Problema: Evento não reconcilia**

**Sintomas:**
- Cliquei em "Reconciliar"
- Evento continua PENDENTE

**Soluções:**

1. **Verificar device_assignment existe:**
   ```sql
   SELECT * FROM device_assignments 
   WHERE device_id = 'ESP32_QUARTO_201' 
   AND end_ms IS NULL;
   ```

2. **Verificar período do assignment:**
   - `start_ms` deve ser ANTES do timestamp do evento
   - `end_ms` deve ser NULL ou DEPOIS do timestamp do evento

3. **Verificar payload do evento:**
   - Clique em "Ver completo"
   - Campos obrigatórios: `postura`, `confianca`, `amostra_ms`, `ts_utc`
   - Se faltar campos → evento será pulado

---

### **Problema: Muitos eventos pendentes**

**Causas Comuns:**

1. **ESP32 configurado mas não associado:**
   - Solução: Criar device_assignment

2. **Assignment expirou (`end_ms` definido):**
   - Solução: Criar novo assignment ou remover `end_ms`

3. **Payload inválido:**
   - Solução: Corrigir configuração do ESP32

---

## 📈 Boas Práticas

### ✅ **DO (Faça):**

- Crie device_assignments ANTES de ligar o ESP32
- Reconcilie periodicamente (ex: 1x por turno)
- Monitore eventos pendentes (não deixe acumular)
- Use "Atualizar" para verificar resultado da reconciliação

### ❌ **DON'T (Não faça):**

- Não deixe ESP32s enviando dados sem assignment por muito tempo
- Não crie assignments com períodos muito curtos (causa fragmentação)
- Não reconcilie durante alta carga do sistema
- Não ignore eventos pendentes por dias

---

## 🔧 Manutenção

### **Limpeza de Eventos Processados (Opcional)**

Eventos processados podem ser arquivados após X dias:

```sql
-- Ver eventos processados há mais de 30 dias
SELECT * FROM device_events 
WHERE processed_at < datetime('now', '-30 days');

-- Deletar (cuidado!)
DELETE FROM device_events 
WHERE processed_at < datetime('now', '-30 days');
```

⚠️ **Atenção**: Apenas delete se tiver backup!

---

## 📞 Ajuda Adicional

- **Documentação Completa**: [JORNADA_INFORMACAO_ESP32.md](../JORNADA_INFORMACAO_ESP32.md)
- **Testes**: Execute `python scripts_demo/testar_admin_adequado.py` para validar reconciliação
- **Logs**: Verifique terminal do servidor para detalhes de erros

---

## 🎯 Checklist Rápido

Antes de reconciliar, verifique:

- [ ] Device_assignment existe
- [ ] Assignment cobre o período dos eventos
- [ ] Payload dos eventos está correto
- [ ] Paciente existe no sistema
- [ ] Cama do assignment está correta

Se todos ✅ → Reconciliação deve funcionar!
