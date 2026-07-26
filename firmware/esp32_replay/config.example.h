#pragma once
// Configuração de rede/servidor do firmware ESP32 (replayer).
//
// SETUP (obrigatório antes de compilar/flashar):
//   1. Copie este arquivo para `config.h` na MESMA pasta:
//        cp config.example.h config.h
//   2. Edite `config.h` com os valores da sua rede.
//
// `config.h` é git-ignored — NUNCA comite credenciais reais no repositório.
// (O sketch inclui "config.h", não este arquivo de exemplo.)

// -----------------------------------------------------------------------
// Transporte
// -----------------------------------------------------------------------
// Descomente para enviar por WebSocket (conexão persistente, /api/ws/eventos).
// Comentado, o firmware usa HTTP (um POST por evento, /api/eventos).
//
// Antes isto era a escolha de QUAL ARQUIVO .ino manter na pasta — os dois
// existiam lado a lado e, como o Arduino concatena todos os .ino do sketch,
// nenhum dos dois compilava sem apagar o outro.
//
// #define USAR_WEBSOCKET

#define WIFI_SSID   "SUA_REDE_WIFI"
#define WIFI_SENHA  "SUA_SENHA_WIFI"

// IP ou host do backend na sua LAN — sem esquema http:// e sem a porta.
#define SERVER_IP   "192.168.0.10"
#define SERVER_PORT 8000

// Token compartilhado que autentica este dispositivo na ingestão.
// Precisa ser IGUAL ao UPP_DEVICE_TOKEN definido no .env do backend.
//
// O X-Device-Id que o firmware já enviava é escolhido pelo próprio
// dispositivo — identifica, mas não autentica nada. Sem este token, qualquer
// um que alcance a rede consegue injetar leituras em nome de um paciente.
//
// Deixe vazio ("") apenas se o backend também estiver sem UPP_DEVICE_TOKEN
// (bancada isolada); nesse caso a verificação fica desligada dos dois lados.
#define DEVICE_TOKEN ""
