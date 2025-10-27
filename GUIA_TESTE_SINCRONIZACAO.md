# Guia de Teste Manual - Sincronização Frontend/Backend

## Teste 1: Verificar Carregamento Inicial de Pacientes

### Passos:
1. Abra a página **http://localhost:5173** (ou a URL do seu frontend)
2. Navegue para a aba **Pacientes**
3. Abra o **DevTools** (F12)
4. Vá para a aba **Console**
5. Procure pelos logs iniciais:

```
[PatientsPage] fetchPatients() called
[PatientsPage] API returned patients: [...]
```

### Resultado Esperado:
- ✅ Devem aparecer 3 pacientes na grid (se teste anterior foi executado)
- ✅ Se lista vazia, deve aparecer mensagem "Nenhum paciente cadastrado"
- ✅ Logs devem mostrar dados sendo carregados

---

## Teste 2: Criar Novo Paciente e Verificar Se Aparece

### Passos:
1. Na página **Pacientes**, clique em "+ Novo Paciente"
2. Preencha o formulário:
   - **Nome**: "Teste E2E XYZ"
   - **Quarto**: "777"
   - **Leito**: "Teste 777"
   - **Risco**: "Alto Risco"
   - **Intervalo**: "2"
3. Clique em **"Criar Paciente"**
4. **Monitore o Console** durante a criação:

```
[PatientForm] Creating new patient with data: {...}
[PatientForm] Patient created successfully: {id: "PAC-XXXX", ...}
```

5. Deve aparecer a tela de **SimulationPanel**
6. Clique em **"Voltar à Lista"**
7. Monitore o Console:

```
[PatientForm] "Voltar à Lista" clicked, calling onSuccess()
[PatientsPage] PatientForm.onSuccess() called
[PatientsPage] Calling fetchPatients() after form success
[PatientsPage] fetchPatients() called
[PatientsPage] API returned patients: [...]
[PatientsPage] fetchPatients() completed, hiding form
[PatientForm] onSuccess() completed
```

### Resultado Esperado:
- ✅ Novo paciente com nome "Teste E2E XYZ" aparece na lista
- ✅ Todos os logs aparecem na sequência correta
- ✅ Não há erros no console

---

## Teste 3: Editar Paciente Existente

### Passos:
1. Na lista de pacientes, clique em **"Editar"** de qualquer paciente
2. Altere o **Nome** adicionando " - EDITADO" no final
3. Clique em **"Atualizar Paciente"**
4. Monitore o Console:

```
[PatientForm] Updating patient: PAC-XXXX
[PatientForm] Patient updated successfully
[PatientForm] "Voltar à Lista" clicked
[PatientsPage] PatientForm.onSuccess() called
[PatientsPage] fetchPatients() called
[PatientsPage] API returned patients: [...]
```

### Resultado Esperado:
- ✅ Paciente volta para lista com nome atualizado
- ✅ Alterações aparecem imediatamente
- ✅ Sem erros

---

## Teste 4: Deletar Paciente

### Passos:
1. Na lista, encontre um paciente e clique no ícone **Lixeira**
2. Confirme a deleção no diálogo
3. Monitore o Console:

```
[PatientsPage] Patient removed with success
[PatientsPage] Calling handleDelete
```

### Resultado Esperado:
- ✅ Paciente desaparece da lista
- ✅ Total de pacientes diminui
- ✅ Sem erros

---

## Teste 5: Erro de Quarto/Leito Duplicado

### Passos:
1. Clique em "+ Novo Paciente"
2. Preencha com dados de um paciente existente (mesma cama/leito)
3. Clique em "Criar Paciente"

### Resultado Esperado:
- ✅ Mensagem de erro: "Cama XXX já está atribuída ao paciente PAC-XXXX"
- ✅ Usuário fica no formulário (não vai para SimulationPanel)
- ✅ Pode corrigir os dados e tentar novamente

---

## Comandos de Verificação

### Verificar se API está respondendo:
```bash
curl http://localhost:8000/api/pacientes
```

### Contar total de pacientes:
```bash
curl -s http://localhost:8000/api/pacientes | jq 'length'
```

### Verificar se frontend está em desenvolvimento:
```bash
cd frontend
npm run dev
# Deve abrir http://localhost:5173
```

---

## Checklist de Sucesso

- [ ] Pacientes carregam ao abrir a página
- [ ] Novo paciente aparece na lista após criação
- [ ] Edição de paciente funciona
- [ ] Deleção de paciente funciona
- [ ] Erros são mostrados corretamente
- [ ] Logs aparecem no console (verificar sequência correta)
- [ ] Sem erros JavaScript no console
- [ ] Sem erros HTTP (status 4xx/5xx)

---

## Troubleshooting

### Problema: Lista vazia mesmo com pacientes no backend
- ✅ Verificar console para erros
- ✅ Verificar se logs "[PatientsPage] API returned" aparecem
- ✅ Limpar cache do navegador (Ctrl+Shift+Del)
- ✅ Recarregar página (F5)

### Problema: Paciente criado mas não aparece na lista
- ✅ Verificar logs de onSuccess - devem mostrar "fetchPatients() completed"
- ✅ Pode ser delay de rede - aguardar alguns segundos
- ✅ Verificar no backend se realmente foi criado: `curl http://localhost:8000/api/pacientes`

### Problema: Simulação não funciona
- ✅ Verificar se backend está respondendo em `/api/pacientes/{id}/simular`
- ✅ Verificar logs no servidor Python

---

**Data**: 2024-12-19
**Status**: Sistema sincronizado e funcional ✅
