# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue em parte o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)  
e este projeto adota [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [Não publicado]

> **Lacuna no registro:** entre `v0.1.0` (ago/2025) e esta entrada o changelog
> ficou parado enquanto o projeto seguiu evoluindo (frontend React, ingestão via
> ESP32, WebSocket, deploy em Docker, agendas de supressão e outros). Essas
> mudanças estão no histórico do git, não aqui — reconstruí-las a posteriori
> seria inventar registro. A partir daqui o arquivo volta a ser mantido.

### Corrigido — corretude

- `utc_now_iso()` gravava hora **local** apesar do nome. Com
  `TZ=America/Sao_Paulo`, atribuições de dispositivo nasciam 3 h no passado e
  leituras de sensor eram creditadas a um paciente que ainda não estava no
  leito.
- O caminho de ingestão engolia falhas com `except Exception: pass` e respondia
  sucesso mesmo assim, então o ESP32 dava a amostra por entregue e a
  descartava. Agora `/eventos` responde 503, `/grade` reporta `perdidos` com
  `code="partial"` e o WebSocket só confirma (`ACK`) o que foi realmente
  gravado.
- `GET /pacientes/{id}/agenda/check` era inalcançável (respondia 422, porque
  `"check"` casava com a rota `/{agenda_id:int}` declarada antes).
- `DELETE` de agenda inexistente respondia 500: o `raise HTTPException(404)`
  estava dentro do `try` capturado pelo `except Exception` genérico.
- O WebSocket de alertas nunca entregava nada a clientes conectados com filtro
  — o payload publicado não continha `patient_id`, `severity` nem `alert_type`,
  que são exatamente os campos que o filtro testa.
- `broadcast()` iterava o dicionário de conexões com `await` dentro do laço;
  uma conexão ou desconexão concorrente abortava o envio para todos os demais.
- A aba de Histórico ficava sempre vazia após simular: eventos de timeline só
  eram gravados para alertas `aberto`, e a simulação em lote gera apenas
  alertas já fechados.

### Corrigido — segurança

- `UPP_ADMIN_PASS` autenticava **qualquer** nome de usuário: o ramo só roda
  quando o usuário não existe no banco e comparava apenas a senha, então o
  atacante escolhia a identidade do JWT. Agora exige o usuário admin
  configurado, compara com `secrets.compare_digest` e fica indisponível em
  produção.
- Apenas 7 de 41 rotas exigiam credencial. Passaram a exigir sessão o CRUD de
  pacientes, `/frontend/alerts`, `/stats`, `/timeline`, `/health`, as agendas e
  os endpoints de backup (onde `cleanup?keep_days=0` anônimo apagava todos os
  backups).
- O cadastro de usuários era aberto, o que anularia a autenticação acima.
  A primeira conta segue livre (bootstrap); depois exige sessão ou
  `X-Register-Token`.
- Cookie de sessão sem `SameSite` combinado com `allow_credentials=True`
  expunha todo endpoint que muda estado a CSRF. Agora `SameSite=Lax` e `Secure`
  conforme o protocolo da requisição. O cookie `session_user`, forjável, deixou
  de ser emitido.
- CORS liberava `localhost:3000/5173` incondicionalmente, inclusive em
  produção, e o middleware era instalado dentro de `try/except: pass` — uma
  falha subia o app **sem política de CORS**.
- O frontend fabricava um token (`usuario:timestamp`) e o enviava como
  `Bearer`; não era um JWT e só não quebrava porque o backend recorre ao
  cookie.

### Adicionado

- `UPP_DEVICE_TOKEN`: autenticação dos ESP32 na ingestão (`/eventos`,
  `/grade`, `/ws/eventos` e `/pacientes/cama/*`). O firmware só enviava
  `X-Device-Id`, escolhido por ele mesmo — identificava, mas não autenticava
  nada. Sem a variável definida a verificação fica desligada, para não derrubar
  bancadas montadas, e o app avisa no startup.

### Removido

- ~5.100 linhas de documentação que eram registros de sessões de depuração,
  várias contradizendo umas às outras (ver `docs/README.md`).
- ~3.100 linhas de código sem qualquer importador, no backend e no frontend,
  incluindo uma terceira implementação de rate limiter e 449 linhas de teste
  que cobriam um hook que nada usava.
- 15 scripts de `scripts_demo/` sem referência, o log de depuração
  `websocket_test_logs.txt` e artefatos gerados (CSV/PDF) que estavam
  versionados.

---

## [v0.1.0] - 2025-08-22

### Adicionado
- **Simulador de posturas (eventos)**  
  - Geração de posturas com transições válidas, dwell time, falhas e refeições.  
  - Saída em grade (`timestamp`, `postura`) para inspeção em série temporal.  
  - Exportação opcional de eventos brutos com a flag `--eventos`.  

- **Testes automatizados**  
  - Teste básico de geração de sessão.  
  - Teste de reprodutibilidade (seed fixa).  
  - Teste de contagem de linhas.  

- **Integração Contínua (CI)**  
  - Configuração de GitHub Actions para rodar `pytest` em cada PR e push.  

---

[v0.1.0]: https://github.com/yaguts1/tcc2-agente-inteligente/releases/tag/v0.1.0 