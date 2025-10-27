# 🎯 Proposta: Integração de Dados Simulados no Dashboard

## 📋 Situação Atual

O site tem:
- ✅ Criação manual de pacientes (`/pacientes/form`)
- ✅ Geração em massa de pacientes (`/pacientes/generar`)
- ❌ **Dados reais/simulados não estão sendo carregados para exibição no dashboard**
- ✅ Simulador existe (funções em `dados_simulados/gerador.py`)

---

## 🎨 Arquitetura Proposta

Seguindo o padrão HTMX + servidor Jinja2 existente:

```
┌─────────────────────────────────────────┐
│ Dashboard (index.html)                  │
│  - Lista de pacientes                   │
│  - Timeline de eventos                  │
│  - Alertas                              │
└────────────┬────────────────────────────┘
             │ HTMX GET/POST
             ▼
┌─────────────────────────────────────────┐
│ Web.py (FastAPI)                        │
│                                         │
│ [NOVO] @app.post("/pacientes/simular")  │
│  ├─ Recebe: paciente_id, duracao, seed  │
│  ├─ Chama: gerar_sessao_simulada()      │
│  ├─ Salva em: DB (grade + eventos)      │
│  └─ Retorna: feedback HTML              │
│                                         │
│ [EXISTENTE] @app.get("/partials/...")   │
│  ├─ Timeline (já busca do DB)           │
│  ├─ Alertas (já busca do DB)            │
│  └─ Eventos (já busca do DB)            │
└────────────┬────────────────────────────┘
             │ DAO (dao.py)
             ▼
┌─────────────────────────────────────────┐
│ SQLite Database                         │
│  - pacientes                            │
│  - grade (posturas simuladas)           │
│  - eventos                              │
│  - alertas                              │
└─────────────────────────────────────────┘
```

---

## ✨ Implementação Proposta

### 1️⃣ Novo Endpoint em `web.py` (Padrão HTMX)

```python
@app.post("/pacientes/{paciente_id}/simular", response_class=HTMLResponse)
async def paciente_simular(
    request: Request,
    paciente_id: str,
    form: Dict = Depends(get_form_data)
) -> HTMLResponse:
    """
    Gera dados simulados para um paciente específico.
    
    Form data:
    - duracao_horas: int (1-72)
    - seed: int (optional)
    - perfil: str (baixo/medio/alto)
    
    Retorna:
    - HTML de feedback + trigger HTMX para recarregar dashboard
    """
    try:
        # 1. Validar paciente existe
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if not ficha:
            return _render_erro("Paciente não encontrado")
        
        # 2. Extrair parâmetros
        duracao = min(max(int(form.get("duracao_horas", 24)), 1), 72)
        seed = int(form.get("seed", 42))
        perfil = form.get("perfil", ficha.get("perfil", "medio"))
        
        # 3. Gerar dados simulados
        df_grade, contextos = gerar_sessao_simulada(
            duracao_horas=duracao,
            seed=seed,
            passo_min=5,
            perfil=PerfilPaciente(perfil=perfil)
        )
        df_grade.insert(0, "paciente_id", paciente_id)
        
        # 4. Salvar no DB (via DAO)
        inserir_grade(DB_PATH, df_grade)
        
        # 5. Processar alertas
        _, alertas = processar_alertas(df_grade[["timestamp", "postura"]], perfil, paciente_id)
        if alertas:
            inserir_alertas(DB_PATH, alertas)
        
        # 6. Retornar com trigger HTMX
        contexto = {"request": request, "success": True, "duracao": duracao}
        response = templates.TemplateResponse("pacientes/partials/simulacao_feedback.html", contexto)
        _set_hx_trigger(response, "simulacao-concluida", {
            "paciente_id": paciente_id,
            "eventos": len(df_grade),
            "alertas": len(alertas)
        })
        return response
        
    except Exception as e:
        logger.exception("simulacao_erro", paciente_id=paciente_id, error=str(e))
        return _render_erro(f"Erro ao simular: {str(e)}")
```

### 2️⃣ Template HTML para Painel de Simulação

**Arquivo**: `interface/templates/pacientes/partials/simulacao_panel.html`

```html
<fieldset>
  <legend>🎬 Gerar Dados Simulados</legend>
  
  <form hx-post="/pacientes/{paciente_id}/simular"
        hx-target="#simulacao-resultado"
        hx-swap="outerHTML swap:1s">
    
    <div class="form-group">
      <label for="sim_duracao">Duração (horas):</label>
      <input type="number" id="sim_duracao" name="duracao_horas" 
             value="24" min="1" max="72" required />
    </div>
    
    <div class="form-group">
      <label for="sim_seed">Seed (opcional):</label>
      <input type="number" id="sim_seed" name="seed" value="42" />
      <small>Use para resultados reproduzíveis</small>
    </div>
    
    <div class="form-group">
      <label for="sim_perfil">Perfil de Risco:</label>
      <select id="sim_perfil" name="perfil">
        <option value="baixo">Baixo</option>
        <option value="medio" selected>Médio</option>
        <option value="alto">Alto</option>
      </select>
    </div>
    
    <button type="submit" class="btn-primary">▶️ Simular</button>
  </form>
  
  <div id="simulacao-resultado"></div>
</fieldset>
```

### 3️⃣ Template de Feedback

**Arquivo**: `interface/templates/pacientes/partials/simulacao_feedback.html`

```html
{% if success %}
<div class="alert alert-success">
  ✅ Simulação concluída!<br>
  {{ duracao }} horas geradas com sucesso.
  <br>
  <small>Os dados aparecerão na timeline em segundos...</small>
</div>
{% else %}
<div class="alert alert-error">
  ❌ Erro na simulação
</div>
{% endif %}
```

### 4️⃣ Integração no Formulário do Paciente

Modificar `interface/templates/pacientes/partials/form.html`:

```html
<!-- Adicionar após "Rotinas pessoais" -->
{% if paciente_id %}
  <div id="simulacao-panel"
       hx-get="/pacientes/simulacao-panel?paciente_id={{ paciente_id }}"
       hx-trigger="load">
    <!-- Painel carregado dinamicamente -->
  </div>
{% endif %}
```

---

## 🔄 Fluxo do Usuário

1. **Criar/Selecionar Paciente**
   ```
   Novo paciente → Preencher dados → Salvar
   ```

2. **Gerar Dados Simulados**
   ```
   Abrir painel "Gerar Dados Simulados"
   → Configurar duração, seed, perfil
   → Clicar "Simular"
   → Dados salvos no DB
   ```

3. **Visualizar Timeline**
   ```
   Dashboard recarrega automaticamente via HTMX
   → Timeline mostra eventos gerados
   → Alertas processados aparecem
   ```

---

## 📊 Vantagens dessa Abordagem

✅ **Mantém padrão existente** (HTMX + Jinja2 + FastAPI)  
✅ **Zero alterações no frontend** (tudo server-side rendering)  
✅ **Reutiliza funções já testadas** (gerador, alertas)  
✅ **Dados persistem no DB** (pode ser reutilizado depois)  
✅ **Sem breaking changes** (compatível 100%)  
✅ **Integração WebSocket já pronta** (para real-time depois)  

---

## 🛠️ Alterações Necessárias

### Arquivo: `interface/web.py`

1. ✅ Adicionar import:
   ```python
   from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente
   from modulo_alerta.engine import processar_alertas
   ```

2. ✅ Adicionar função helper:
   ```python
   async def get_form_data(request: Request) -> Dict:
       return await request.form()
   ```

3. ✅ Adicionar 2 endpoints:
   - `GET /pacientes/simulacao-panel` - Carrega painel
   - `POST /pacientes/{paciente_id}/simular` - Processa simulação

### Templates novos:

1. `simulacao_panel.html` (~30 linhas)
2. `simulacao_feedback.html` (~10 linhas)

### Modificações existentes:

1. `form.html` - Adicionar `<div id="simulacao-panel">` (~5 linhas)

---

## 📈 Próximos Passos Opcionais

### Fase 2: Validação Automática
```python
# Após gerar dados
resultado = validar_sessao_gerada(df_grade, verbose=False)
if not resultado["valido"]:
    logger.warning(f"Dados com problemas: {resultado['avisos']}")
    # Avisar usuário
```

### Fase 3: Controles Avançados
- **Carregar dados de arquivo**: `POST /pacientes/{id}/upload-grade`
- **Exportar dados**: `GET /pacientes/{id}/export-grade`
- **Batch simulação**: `POST /pacientes/batch-simular`
- **Schedule automático**: Background task para rodar simulações

### Fase 4: Real-time WebSocket
- Conectar ESP32 real ao `/ws/eventos`
- Dashboard recebe dados ao vivo

---

## 🎯 Recomendação Final

**Implementar AGORA:**
1. Endpoint `/pacientes/{id}/simular`
2. Templates de painel + feedback
3. Integração no form existente

**~2-3 horas de trabalho** | **100% backward compatible**

Depois você terá:
- ✅ Dashboard com dados reais/simulados
- ✅ Base para WebSocket depois
- ✅ Validação de dados integrada
- ✅ Pronto para produção

**Quer que eu implemente?** 🚀
