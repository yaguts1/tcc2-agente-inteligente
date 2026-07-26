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
- O leitor de upload JSONL (`/api/grade` e `/admin/import_alerts`) decodificava
  cada bloco de 64 KiB isoladamente: um caractere acentuado partido na fronteira
  do bloco derrubava o upload inteiro com 500, de forma intermitente porque
  depende de onde o acento cai. Em português isso atinge qualquer arquivo acima
  de 64 KiB.
- Uma linha inválida no meio de um lote em `/api/grade` abortava o upload
  **depois** de gravar as linhas anteriores, e a resposta era só um erro sem
  contagem alguma — o cliente não tinha como saber que metade do arquivo havia
  entrado. Agora a linha ruim é contada e reportada (`rejeitadas`,
  `linhas_rejeitadas`) e o restante do lote segue; 400 só quando **nenhuma**
  linha pôde ser lida, que é o caso em que nada ficou gravado.
- O `flush` ao fim de um upload em lote esvaziava o buffer de reordenação de
  **todos** os dispositivos, inclusive os que estavam transmitindo ao vivo:
  amostras eram liberadas antes da janela de jitter fechar e perdiam o buffer
  que serviria para reordená-las. Agora o flush é restrito aos dispositivos do
  próprio upload.
- `/api/grade` recusava `text/plain; charset=utf-8` (o que `curl -F` envia) e
  `application/x-ndjson` (o media type registrado para JSONL): o `Content-Type`
  era comparado com os parâmetros do header colados.
- O filtro de datas da Timeline devolvia o dia **anterior** ao pedido em
  qualquer fuso a oeste de Greenwich: `new Date('2026-07-26')` é meia-noite
  **UTC**, e o `setHours(0,0,0,0)` seguinte zerava o dia 25 no horário de
  Brasília. Filtrar "26/07 a 26/07" trazia o histórico do dia 25 e nenhum
  evento do dia 26.
- O botão "Carregar mais eventos" da Timeline comparava com 100 fixo em vez do
  limite em vigor: depois de um clique (limite 200), uma lista de 150 eventos —
  já o histórico completo — continuava exibindo o botão, e clicar não mudava
  nada.

- O botão "Excluir" da tela de Pacientes chamava `DELETE /api/pacientes/{id}`,
  rota que nunca existiu: respondia **405**, o usuário via "Erro ao remover
  paciente" e o paciente continuava na lista. `PatientRepository.delete` e
  `dao.remover_paciente` já estavam escritos e sem nenhum chamador. A cascata
  também estava incompleta — deixava `alertas` para trás, e o alerta órfão
  voltava ao dashboard rotulado com o ID cru do paciente, sem quarto.
- A ação em lote de alertas fazia `Promise.all` com uma requisição por alerta,
  ignorando `/frontend/alerts/batch/*`. Como `Promise.all` rejeita no primeiro
  erro e o 409 `transicao_invalida` é esperado, bastava um alerta já
  reconhecido por outra pessoa para o enfermeiro ver "erro" — enquanto os
  demais já tinham sido gravados, sem nada na tela dizendo quais.
- `GET /frontend/alerts` cortava em `limit` sem dizer: o dashboard filtra em
  memória sobre o que recebeu, então um paciente atrasado podia ficar fora da
  tela sem sinal algum. Agora o total vai no cabeçalho `X-Total-Count` e a tela
  avisa quando está exibindo parte.

### Adicionado — visibilidade

- O aviso de monitoramento interrompido no dashboard passa a listar **quais**
  pacientes estão sem dados, com leito e minutos em silêncio, separando "nunca
  recebeu leitura" (erro de instalação ou de vínculo device↔leito) de "o sensor
  parou". A informação já existia em `/api/monitoramento` e nenhuma tela a
  consumia — o aviso dizia "3 pacientes sem monitoramento, verifique o sensor"
  sem dizer qual leito conferir.

- `contar()` da trilha de auditoria recebia `**filtros` e **ignorava todos**,
  contando a tabela inteira enquanto a docstring prometia o total dos que casam
  com os filtros. Nada em produção a chamava, então o defeito nunca apareceu —
  e apareceria agora, ao paginar a consulta filtrada, como um total maior que o
  real.
- `GET /auditoria` cortava em `limit` sem dizer. Numa trilha usada para
  responder "quem acessou os dados deste titular?" (LGPD Art. 18), resposta
  cortada em silêncio é resposta incompleta a uma pergunta legal. Agora traz
  `X-Total-Count`.

### Adicionado — réplica externa de backup

- Réplica dos backups para **fora da VM**, por `scripts/replicar_backups.sh`
  (rsync, executado pelo cron do host). Backup no mesmo disco do banco cobre
  erro de operação e corrupção, mas perda de disco ou da VM levaria os dois
  juntos — e a tela diria "Backup em dia" até o fim.
  - O transporte fica **fora da aplicação** de propósito: rodá-lo no processo
    web exigiria chave SSH dentro do container e prenderia o sistema a um
    transporte só. Migrar para nuvem é trocar uma linha do script (`rsync` por
    `rclone copy`, `aws s3 sync`); o recibo e a tela não mudam.
  - O script deixa um **recibo** que a aplicação lê e reporta em
    `/admin/backup/status` e na tela. Sem isso, uma replicação que parasse de
    rodar seria indistinguível de uma que funciona — exatamente a falha que
    backup existe para evitar. Erro também gera recibo.
  - Sem `BACKUP_REPLICACAO_INTERVALO_HORAS`, a tela informa que não há réplica
    configurada **sem alarme**: alarmar pelo que a instituição não configurou
    treina a equipe a ignorar o vermelho.

- O backup herdava `journal_mode=WAL` do banco vivo, e a **própria verificação**
  criava um `-shm` (32 KB) e um `-wal` ao lado de cada arquivo — encontrado
  inspecionando o container em execução, que tinha 10 backups e 20 sidecars.
  Consequências: `cleanup_old_backups` apaga só `backup_*.db` e deixaria os
  sidecars órfãos no disco para sempre; a réplica externa os copiaria junto; e
  um `-wal` ao lado do `.db` no destino seria replicado pelo SQLite ao
  restaurar. Agora o backup é fechado em `journal_mode=DELETE` — um arquivo
  autocontido — e a limpeza remove sidecars remanescentes junto com o arquivo.
- Recibo de replicação com data no **futuro** (relógio do host adiantado) seria
  tratado como recente para sempre: a replicação poderia morrer e a tela
  seguiria dizendo que a cópia externa estava de pé.

### Corrigido — configuração que não chegava ao container

- **Onze variáveis documentadas no `.env.example` e lidas pelo código nunca
  eram repassadas ao container.** O `docker-compose.yml` lista as variáveis uma
  a uma (não há `env_file:`), então quem preenchesse `BACKUP_INTERVAL_HOURS=6`
  seguiria com 24, quem ajustasse `MONITORAMENTO_LIMITE_MIN` não mudaria nada,
  e a retenção da auditoria jamais rodaria — tudo em silêncio, porque o default
  existe e funciona. O mesmo defeito já havia sido encontrado para
  `UPP_DEVICE_TOKEN` e `UPP_AUDIT_KEY`; corrigiram essas duas e as outras
  ficaram. `tests/test_configuracao_chega_ao_container.py` impede a próxima.
- `UPP_ADMIN_USER` e `PROCESSADOR_ESTRATEGIA` têm default real no código, então
  são repassadas com o default no compose (`${VAR:-admin}`) e não vazias:
  variável definida como `""` substitui o default por string vazia, o que seria
  trocar um defeito por outro.

### Adicionado — operação

- Rate limit nos endpoints comuns (alertas, timeline, stats, pacientes,
  exportação). `_check_api_rate_limit` existia e **nenhum endpoint o declarava
  como dependência**: só login (5/min), lote (10/min) e ingestão (token bucket)
  tinham teto. Configurável por `API_RATE_LIMIT_POR_MINUTO`, padrão folgado
  (240/min por IP). `/healthz`, `/api/health` e `/metrics` ficam de fora — um
  429 ali faria o monitoramento derrubar o serviço que ele vigia.
- Limpeza periódica de tokens revogados já expirados, que só faziam a tabela
  crescer. A rotina existia pronta e sem nenhum chamador fora dos testes.
- `POST /api/auditoria/expurgar` (admin): a interface que faltava para o
  expurgo da trilha. `expurgar_anteriores_a` existia com a docstring pedindo
  "uma operação explícita, e não um expurgo automático com prazo arbitrário" —
  mas não havia endpoint, comando nem agendamento, ou seja, explícito e
  inalcançável. Sem `confirmar=true` devolve só a prévia de quantas linhas
  sairiam.
- Retenção contínua da trilha por `AUDITORIA_RETENCAO_DIAS`. **Vazio por
  padrão**: sem política declarada nada é expurgado, e valor inválido ou não
  positivo também não expurga — diante de configuração que não se entende, o
  lado seguro do erro é preservar.

- Os endpoints de backup devolviam o **caminho absoluto** dos arquivos no
  servidor (`path`), que o cliente não usa para nada — todas as operações são
  por `filename`. Entregar a estrutura de diretórios ao navegador é o mesmo
  vazamento que `erro_interno` existe para evitar no resto da API.

- **A política de senha não valia no cadastro.** `/usuarios/eu/senha` e
  `/usuarios/{u}/senha` exigiam 8 caracteres, `/auth/register` não exigia nada
  e o formulário do frontend pedia 6 — três respostas diferentes para a mesma
  pergunta. Dava para criar a conta com `"a"` e só então ser impedido de trocar
  para `"a"`; como o primeiro usuário da instalação vira **admin**, era a conta
  administrativa que nascia sem exigência alguma. Agora os três caminhos saem
  de uma fonte só (`exigir_senha_forte` / `SENHA_MIN_LEN`).
- O invariante "a instalação nunca fica sem admin ativo" era conferido no
  router, numa consulta separada do `UPDATE`. Duas requisições simultâneas
  rebaixando administradores diferentes viam, cada uma, o outro ainda como
  admin — e as duas passavam. A checagem passou para dentro da transação que a
  aplica (`BEGIN IMMEDIATE`, em `UserRepository`).
- `BACKUP_INTERVAL_HOURS` era lido em dois lugares com tratamentos diferentes:
  o agendador caía no padrão diante de um valor ilegível e o endpoint de status
  respondia 500. Pior que a robustez, divergindo eles fariam o veredito "estou
  coberto?" julgar a idade do último backup contra um intervalo que não é o que
  o agendador usa.

- O painel de eventos órfãos exibia um total que os próprios botões dele não
  conseguiam zerar. `total_orphans` era `len(events)` — a contagem da amostra
  já limitada a 10.000 — e incluía eventos sem `cama_id` no payload, que não
  aparecem em leito nenhum. O operador reconciliava todos os leitos, o número
  não zerava e nada explicava por quê. Agora o total vem de um `COUNT(*)`, os
  órfãos sem leito são reportados à parte e a tela avisa quando o agrupamento
  foi calculado sobre amostra parcial.
- `except Exception: pass` na resolução do paciente do leito fazia a tela
  exibir "Leito vazio" e instruir a "cadastrar um paciente neste leito" quando
  o paciente existia e a consulta é que havia falhado — conselho errado por
  falha silenciosa.

### Adicionado — telas de administração

- A página de Admin era exclusivamente reconciliação de eventos órfãos,
  enquanto **dez rotas de gestão de usuários e de backup existiam sem nenhuma
  tela**. Agora tem três abas:
  - **Usuários**: listar, promover/rebaixar, desativar/reativar e redefinir
    senha. A tela reflete as regras do backend em vez de reimplementá-las —
    desativar em vez de excluir (excluir levaria junto a autoria registrada na
    linha do tempo), e o aviso de que toda ação sensível encerra as sessões do
    alvo.
  - **Backup**: veredito de cobertura no topo (`saudavel` combina "recente" com
    "proporcional ao banco vivo"), lista de arquivos, verificação de que cada
    um realmente restaura, criação sob demanda e limpeza. Um arquivo sem selo é
    exibido como "não verificado", nunca como íntegro.
  - **Eventos órfãos**: o painel que já existia, extraído para componente.
- Troca da própria senha, disponível a qualquer usuário no menu lateral.
  `POST /usuarios/eu/senha` existia sem tela: trocar a própria senha só era
  possível por `curl` ou pedindo a um administrador que a redefinisse — o que
  expõe a senha a um terceiro. Como a troca encerra todas as sessões, o diálogo
  avisa antes e desconecta depois, em vez de deixar o usuário recebendo 401 sem
  entender.
- O item "Admin" do menu passa a aparecer apenas para o papel `admin`
  (afordância; a autorização continua no backend, pelo JWT).

### Decisões registradas

- Os filtros por conexão do WebSocket (`?severity=`, `?patient_id=`,
  `?alert_types=`) continuam **sem uso pelo frontend, de propósito**: o React
  abre uma única conexão compartilhada entre o dashboard e a tela de Histórico,
  e filtrar ali silenciaria os outros consumidores. A capacidade fica para uma
  eventual tela por leito, que deve abrir uma segunda conexão. Documentado no
  endpoint e no `useWebSocket`, com testes cobrindo a conexão sem filtro (a que
  a aplicação usa) e a integridade dos campos que o filtro testa.

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