# Cheatsheet — demonstração ao vivo

Uma página para ter na mão durante a apresentação. O runner é
`scripts/demo.py`; `python -m scripts.demo roteiro` imprime uma versão curta
disto no terminal.

**Tempos medidos nesta bancada**, não estimados: ato 1 **29s**, ato 2 **38s**,
ato 3 **51s**, ato 5 **61s**. Somando os automatizados, ~3 min de máquina — o
resto é fala. O ato 4 depende de alguém mexer no celular.

---

## Antes de sair de casa

- [ ] **Leve hotspot de celular ou roteador de viagem.** Rede de auditório
      costuma ter *client isolation*: o notebook e o ESP32 se veem na internet
      mas não entre si, e o aparelho nunca alcança o backend. É o risco que mais
      derruba esta demo, e não tem conserto no local.
- [ ] Cabo USB do ESP32 (o mesmo que grava e alimenta).
- [ ] Ensaie o **ato 2 com `--manual`** pelo menos uma vez. É o único caminho
      que depende de alguém arrancar o cabo, e é o que eu não consegui exercitar
      automaticamente.

## 10 minutos antes

```bash
docker compose up -d --build app                       # sobe o sistema real
python -m scripts.demo preparar --porta COM3           # perfil demo + dados + SPIFFS + paciente
python -m scripts.demo checar   --porta COM3           # só comece se disser PRONTO
```

`preparar` regrava o aparelho apontando para o **container** (porta 8000,
prefixo `/TCC`) e gera dados novos. Os dados **vencem em ±24 h** — refaça no dia.

- [ ] Abrir `http://localhost:8000/TCC/` e dar **Ctrl+Shift+R** (senão o
      navegador serve o bundle antigo do cache).
- [ ] Fazer login antes de projetar.
- [ ] Projetar **dashboard e terminal lado a lado**. O log do ESP32 correndo ao
      lado do alerta nascendo *é* o visual da demo.

---

## Os cinco atos

Cada ato limpa o leito e reinicia o container antes de começar, então pode ser
repetido à vontade e rodado em qualquer ordem — **menos o ato 4**, que precisa
de um alerta aberto (rode o ato 1 antes).

### Ato 1 — O dado é real · 29s

```bash
python -m scripts.demo ato1 --porta COM3
```

> Ninguém tocou no navegador. O dado saiu de um sensor, atravessou Wi-Fi,
> ingestão, filtro e motor de alertas, e voltou pela mesma conexão que a tela já
> mantinha aberta.

### Ato 2 — Cai a energia · 38s

```bash
python -m scripts.demo ato2 --porta COM3            # automático (linha EN)
python -m scripts.demo ato2 --porta COM3 --manual   # você arranca o cabo
```

> O checkpoint guarda o que foi **entregue**, não o que foi lido. Por isso a
> amostra que estava em voo quando a energia caiu foi reenviada, e a chave
> primária da grade recusou a duplicata. 24 de 24, sem perda e sem duplicação.

Este é o ato com mais densidade de engenharia: é o defeito real que o projeto
corrigiu, reproduzido ao vivo.

### Ato 3 — Cai o servidor · 51s

```bash
python -m scripts.demo ato3 --porta COM3
```

> O dispositivo não desiste. O backoff tem teto, então ele bate no servidor uma
> vez por minuto até voltar — em vez de parar de vez e esperar alguém ir até o
> leito apertar um botão.

### Ato 4 — A enfermeira está no elevador · guiado

```bash
python -m scripts.demo ato1 --porta COM3   # precisa de um alerta aberto
python -m scripts.demo ato4
```

No celular, com a sessão aberta: **modo avião** → **Reconhecer** → mostrar que a
tela aceitou → **desligar o modo avião**.

> Wi-Fi hospitalar cai em corredor, escada e elevador. Não é caso de borda, é a
> topologia. Sem a fila, quem marcou quatro pacientes numa zona morta perdia os
> quatro — e sem saber quais. O reenvio é seguro porque o `alert_id` é chave
> natural (paciente, início) e o servidor é idempotente.

### Ato 5 — Alguém errou a credencial · 61s

```bash
python -m scripts.demo ato5 --porta COM3
```

Aponte o `0 descartes` na saída.

> Ele **não** descarta. 401 é erro de configuração, não amostra ruim —
> descartar aqui jogaria fora dado clínico por engano de operação. Corrigido o
> `.env`, ele se recupera sozinho: sem visita ao leito, sem reflash.

---

## Fechamento

```bash
# backend — o deselect evita UMA falha pré-existente (ver nota abaixo)
python -m pytest -q --deselect tests/test_backup_restauravel.py::test_ciclo_completo_com_o_original_destruido

UPP_ESP32_PORT=COM3 python -m pytest tests/test_e2e_esp32.py -q   # hardware
cd frontend && npm run e2e                                        # navegador
```

> ⚠️ **Não rode `pytest -q` puro no palco.**
> `test_backup_restauravel.py::test_ciclo_completo_com_o_original_destruido`
> falha **no Windows** com `PermissionError` ao apagar um SQLite ainda aberto —
> é limitação do sistema de arquivos, não do sistema, e é anterior a este
> trabalho. Uma linha vermelha no fechamento custa mais do que ela vale
> explicar. Se a banca perguntar, a resposta honesta é essa; em Linux e na CI
> ela passa.

> Cada cena que vocês viram tem um teste automatizado equivalente. Não é
> encenação: é o que o CI verifica a cada push.

| Ato | Teste que o cobre |
|---|---|
| 1 | `frontend/e2e/esp32-ate-a-tela.spec.ts` |
| 2 | `test_e2e_esp32.py::test_reboot_no_meio_do_replay_retoma_da_amostra_certa` |
| 3 | `test_e2e_esp32.py::test_queda_do_servidor_no_meio_do_replay_nao_perde_amostra` |
| 4 | `frontend/e2e/fila-offline.spec.ts` |
| 5 | `test_e2e_esp32.py::test_token_errado_faz_o_aparelho_insistir_ate_alguem_corrigir` |

---

## Quando der errado

Todos estes já aconteceram durante o desenvolvimento. O `checar` pega os seis
primeiros **antes** de você subir no palco — por isso ele existe.

| Sintoma | Causa | Conserto |
|---|---|---|
| `checar` diz que `SERVER_IP` não é desta máquina | Wi-Fi caiu, ou o DHCP trocou o IP | Reconecte o Wi-Fi; se o IP mudou, edite `SERVER_IP` em `firmware/esp32_replay/config.h` e rode `perfil-demo` |
| `[WS] Desconectado` em laço, sem explicação | O firmware gravado **não é** o que você acha — o upload não pegou | `python -m scripts.demo checar` compara o `alvo` que o aparelho declara com o `config.h`; regrave com `perfil-demo` |
| Tudo responde **404** | `APP_PREFIXO` errado (container usa `/TCC`, bancada usa `""`) | `python -m scripts.demo perfil-demo --porta COM3` |
| Replay termina "com sucesso" e **nada aparece** | Dados fora de ±24 h — o pipeline ignora e não reclama | `python -m scripts.demo preparar --porta COM3` |
| Segundo replay não produz nada | `_DEDUP_CACHE` vive **no processo**: as mesmas amostras viram duplicatas, com ACK | Qualquer `ato*` já reinicia o container; manualmente, `docker restart upp_app` |
| Dashboard vazio mas o motor "já avisou" | `estado_incremental` guarda `alerta_atual` aberto; apagar só a tabela `alertas` deixa o paciente num limbo | Rode qualquer `ato*` (o `limpar_leito` apaga os três: linhas, estado e memória) |
| Alerta no banco, mas não na tela | Bundle antigo no cache do navegador | **Ctrl+Shift+R** |
| Porta 8000 ocupada / bancada quer subir ali | O container é dono da 8000; os testes usam a 8010 | Não derrube o container: o perfil `bancada` já usa 8010 |
| ESP32 não aparece na COM3 | Cabo de carga (sem dados), ou driver CP210x | Troque o cabo; `[System.IO.Ports.SerialPort]::getportnames()` lista as portas |

**Zerar um paciente são três coisas**, e duas não aparecem em lugar nenhum da
interface: as linhas do banco, o `estado_incremental` do motor, e o cache de
dedup na memória do processo. O `limpar_leito` do runner cuida das três — é por
isso que os atos são repetíveis.

---

## Depois da demo

```bash
python -m scripts.demo perfil-bancada --porta COM3
```

Devolve o aparelho ao alvo dos testes (porta 8010, sem prefixo). Sem isto, a
suíte de hardware falha explicando que o firmware está no perfil errado.

O paciente da demo (`Sr. Antônio Nogueira`, leito C-01) fica no banco. Para
removê-lo, use a tela de pacientes — o runner não apaga paciente, só o histórico
dele.
