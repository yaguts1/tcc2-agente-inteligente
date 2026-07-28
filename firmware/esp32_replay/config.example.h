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

// Token que autentica ESTE dispositivo na ingestão.
//
// O X-Device-Id que o firmware envia é escolhido pelo próprio dispositivo —
// identifica, mas não autentica nada. Sem este token, qualquer um que alcance
// a rede injeta leituras em nome de um paciente.
//
// PREFIRA UM TOKEN POR APARELHO. Emita com:
//
//     POST /api/devices/{device_id}/token      (exige sessão de admin)
//
// O valor aparece UMA vez na resposta — o servidor guarda só o hash e não
// consegue mostrá-lo de novo. Perdeu, emita outro.
//
// Por que não usar o mesmo token em todos: estes aparelhos ficam presos ao
// leito, acessíveis, num prédio com circulação de público. Com um segredo
// único, um aparelho arrancado da parede entrega a credencial da frota
// inteira — e revogar exigiria reflashear todos, ou seja, na prática nunca se
// revogaria. Com token por aparelho, revogar é uma chamada:
//
//     DELETE /api/devices/{device_id}/token
//
// COMPATIBILIDADE: um aparelho que ainda não tem token próprio continua sendo
// aceito pelo UPP_DEVICE_TOKEN global do backend, para a frota poder migrar um
// de cada vez sem deixar a ala sem monitoramento. Depois que o aparelho recebe
// o dele, o global deixa de valer PARA ELE.
//
// Deixe vazio ("") apenas numa bancada isolada, com o backend também sem
// UPP_DEVICE_TOKEN; nesse caso a verificação fica desligada dos dois lados.
#define DEVICE_TOKEN ""
