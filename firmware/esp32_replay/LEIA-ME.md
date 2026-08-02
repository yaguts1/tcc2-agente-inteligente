# ESP32 Firmware - Sistema de Monitoramento de Postura

## 📁 Estrutura

- **esp32_replay.ino** - O sketch (setup/loop + máquina de estados)
- **esp32_replay.h** - Tipos e a interface de transporte
- **replay_comum.h** - Lógica compartilhada: arquivo, checkpoint, backoff, Wi-Fi
- **transporte_http.h** - Envio por HTTP (POST em `/api/eventos`)
- **transporte_ws.h** - Envio por WebSocket (`/api/ws/eventos`)
- **data/eventos.jsonl** - Dados de exemplo (históricos)
- **data/eventos_now.jsonl** - Dados de exemplo (tempo atual)

### Escolher o transporte

Em `config.h`:

```cpp
#define USAR_WEBSOCKET   // comente para usar HTTP
```

> **Antes eram dois sketches** — `esp32_replay.ino` e
> `esp32_replay_websocket.ino` — lado a lado, com ~90% de código repetido.
> Isso **não compilava**: o Arduino concatena todos os `.ino` da pasta num
> único arquivo, e os dois definiam `setup()`, `loop()` e mais onze funções.
> Quem abrisse o sketch recebia uma parede de erros de redefinição.
>
> Pior que o build: as duas cópias derivaram. A variante WebSocket, que este
> LEIA-ME recomendava, tinha ficado para trás em cinco correções já feitas na
> HTTP — entre elas gravar no checkpoint a posição **lida** em vez da
> **entregue** (perda silenciosa de amostra depois de um reboot) e nunca voltar
> ao estado `ENVIANDO` depois de uma falha, o que queimava todas as tentativas
> em poucas dezenas de milissegundos e encerrava o replay na primeira
> oscilação de rede.

## Compilar e testar (sem placa)

O firmware era a única parte do sistema sem verificação no fluxo: não havia
toolchain, então mudanças chegavam ao repositório sem nunca terem passado por um
compilador. Foi assim que o sketch chegou a um estado em que **não compilava**
sem que nada acusasse.

```bash
pip install platformio

pio run  -d firmware                 # compila as duas variantes (HTTP e WebSocket)
pio run  -d firmware -e websocket    # só uma
pio test -d firmware -e nativo       # testes da lógica, na máquina, sem ESP32
```

`pio test -e nativo` precisa de um **gcc do host**. No Windows, sem MinGW, roda
por container:

```bash
docker run --rm -v "$PWD:/repo" -w /repo python:3.11-slim sh -c   "apt-get update -qq && apt-get install -y -qq build-essential &&    pip install -q platformio && pio test -d firmware -e nativo"
```

A CI roda os dois a cada push (job `firmware`). O `config.h` é criado a partir
do exemplo quando não existe — serve para compilar, nunca para gravar num
dispositivo real.

### O que os testes cobrem

Só a lógica que não depende de hardware, que é onde estão as decisões:
classificação da resposta do servidor (quando desistir de um evento), backoff
(quanto esperar) e leitura de timestamp ISO com fuso. Rede, SPIFFS e a máquina
de estados continuam exigindo um dispositivo — o compilador cobre a sintaxe
deles, não o comportamento.

## 🚀 Como Usar

### 1. Configuração Inicial

As credenciais de WiFi e o endereço do servidor NÃO ficam no código versionado.
Crie seu `config.h` local a partir do exemplo (é git-ignored — não será commitado):

```bash
cd firmware/esp32_replay
cp config.example.h config.h
```

Edite `config.h` com os valores da sua rede:

```cpp
#define WIFI_SSID   "SUA_REDE_WIFI"
#define WIFI_SENHA  "SUA_SENHA_WIFI"
#define SERVER_IP   "192.168.0.10"   // IP do backend na sua LAN (sem http:// e sem porta)
#define SERVER_PORT 8000
```

Os sketches `.ino` incluem `config.h` automaticamente. Demais parâmetros
(deviceId, camaId, endpoint, etc.) continuam editáveis no bloco `ReplayConfig`
dentro do `.ino`.

> ⚠️ **Segurança**: nunca coloque senha WiFi real direto no `.ino` — ela vai
> parar no histórico do git. Uma senha exposta assim no passado deste repo já
> foi removida do código, mas continua no histórico e deve ser trocada na vida
> real.

### 2. Preparar Dados

#### Opção A: Usar dados históricos (para testes)
Use o arquivo `data/eventos.jsonl` (já existente)

#### Opção B: Gerar dados com timestamp atual
Execute o script Python para gerar eventos com timestamp atual:

```bash
python scripts/gerar_eventos_esp32.py --output firmware/esp32_replay/data/eventos_now.jsonl --horas 2
```

### 3. Upload do Firmware

1. Instale as bibliotecas necessárias via Arduino IDE:
   - **ArduinoJson** (versão 6.x)
   - **WebSockets** by Markus Sattler

2. Upload do sistema de arquivos (SPIFFS):
   - Ferramentas → ESP32 Sketch Data Upload
   - Isso carrega o arquivo `data/eventos.jsonl` para o ESP32

3. Upload do código:
   - Compile e faça upload do `esp32_replay_websocket.ino`

### 4. Monitoramento

Abra o Serial Monitor (115200 baud) para ver os logs:

```
[WIFI] Connected IP=192.168.0.100
[WS] Conectando a ws://SERVER_IP:8000/ws/eventos...
[WS] ✅ Conectado ao servidor WebSocket
[WS] Conexão estabelecida com sucesso
[ESTADO] -> 1
[ACK] seq=1 via WebSocket
[ACK] seq=2 via WebSocket
...
```

## 📊 Formato dos Dados

### Formato Atual (CORRETO) ✅

```json
{
  "seq": 1,
  "device_id": "DEV-001",
  "paciente_id": "PAC-0001",
  "cama_id": "C-01",
  "ts_utc": "2025-10-27T14:30:00Z",
  "tipo": "postura",
  "valor": 1,
  "confianca": 0.95
}
```

### Mapeamento de Posturas

- `0` = Decúbito lateral direito
- `1` = Supino (de costas)
- `2` = Decúbito lateral esquerdo
- `3` = Prono (de bruços)

## 🔧 Comandos Seriais

Enquanto o ESP32 está rodando, você pode enviar comandos via Serial:

- `CMD_START` - Iniciar replay (retoma do checkpoint, se houver)
- `CMD_STOP` - Parar replay
- `CMD_RESET` - Apagar o checkpoint; o próximo `CMD_START` recomeça do início
- `CMD_STATUS` - Imprimir a contabilidade do aparelho numa linha

```
[STATUS] estado=4 ativo=0 seq=24 enviados=24 falhas=0 descartados=0 offset=4017
```

Os totais **sobrevivem ao fim do replay** — é depois de terminar que alguém
pergunta como foi. Só um `CMD_START` novo os zera. (Antes, `resetarReplay()`
apagava estado e contabilidade juntos, e o estado FINALIZADO o chama: o aparelho
esquecia o que tinha feito no instante em que terminava de fazer.)

### Duas linhas de log que valem como contrato

- `[CKPT] offset=N` — sai **depois** do `close()` do arquivo de checkpoint, e é
  o único sinal de que o ponto de retomada está no disco. `[ACK] seq=N` não
  serve para isso: sobre WebSocket quem a imprime é o callback do socket, e a
  gravação acontece uma volta de loop depois.
- `[INFO] Replay finalizado` — o fim de verdade. `[INFO] Fim do arquivo` sai
  quando a última linha foi lida, com o replay ainda ativo; um `CMD_START`
  enviado nessa janela é recusado com "Replay ja em execucao".

### Por que `CMD_RESET` existe

`CMD_START` **retoma de onde parou** — é o comportamento correto depois de um
reboot ou de uma queda de rede, e é o que impede a perda de amostra. Mas quando
o replay chega ao fim do arquivo, o checkpoint gravado aponta para o EOF: um
segundo `CMD_START` reabria, dava `seek` para o fim e não enviava nada. Sem
erro, sem log, sem evento — parecia o dispositivo travado.

Zerar é uma decisão de quem opera, não um efeito colateral de dar START (senão
todo reboot recomeçaria o arquivo e duplicaria o que já foi entregue). Por isso
é um comando à parte. É também o que torna o E2E de hardware repetível — ver
`tests/test_e2e_esp32.py`.

## ⚙️ Configurações Avançadas

### Delay entre pacotes

```cpp
.delayEntrePacotesMs  = 500,  // 500ms entre eventos
.respeitarTimestamp   = false, // true = usa delta real dos timestamps
```

### Retry e Backoff

```cpp
.tentativasMax        = 5,     // Máximo de tentativas
.backoffBaseMs        = 500,   // Backoff inicial
.backoffMaxMs         = 60000, // Backoff máximo (1 min)
.backoffWithJitter    = true,  // Adicionar jitter
```

## 🐛 Troubleshooting

### ESP32 não conecta ao WiFi
- Verifique SSID e senha
- Confirme que está na mesma rede do servidor

### WebSocket não conecta
- Confirme que o backend está rodando: `uvicorn interface.web:app --reload`
- Verifique o IP e porta do servidor
- Teste o endpoint manualmente: `ws://IP:8000/ws/eventos`

### Eventos não aparecem no dashboard
- Verifique se o `paciente_id` existe no sistema
- Confirme que a `cama_id` está associada ao paciente
- Verifique os timestamps dos eventos (devem estar dentro de ±24h do momento atual)

### Arquivo não encontrado
- Certifique-se de fazer o upload do SPIFFS (Ferramentas → ESP32 Sketch Data Upload)
- Verifique o nome do arquivo em `.arquivoEventos`

## 📝 Notas Importantes

1. **Versão WebSocket é mais eficiente** - Use `esp32_replay_websocket.ino`
2. **Checkpoint automático** - O ESP32 salva a posição do arquivo, pode retomar de onde parou
3. **Timestamps** - Use dados com timestamps próximos ao atual para ver alertas no dashboard
4. **Paciente automático** - O firmware consulta `/api/pacientes/cama/{cama_id}` para resolver o paciente
