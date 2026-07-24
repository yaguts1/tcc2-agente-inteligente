# ESP32 Firmware - Sistema de Monitoramento de Postura

## 📁 Estrutura

- **esp32_replay.ino** - Versão HTTP (POST para /api/eventos)
- **esp32_replay_websocket.ino** - ✅ **VERSÃO RECOMENDADA** (WebSocket /ws/eventos)
- **esp32_replay.h** - Header com estruturas e configurações
- **data/eventos.jsonl** - Dados de exemplo (históricos)
- **data/eventos_now.jsonl** - Dados de exemplo (tempo atual)

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

- `CMD_START` - Iniciar replay
- `CMD_STOP` - Parar replay

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
