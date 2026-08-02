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
//
// Para a BANCADA DE E2E, use 8010: a 8000 costuma estar ocupada pelo container
// `upp_app`, e tanto `tests/test_e2e_esp32.py` quanto o Playwright sobem um
// backend próprio, com banco descartável, na porta que estiver aqui. Rodar
// contra o container faria a suíte semear paciente de teste no banco de verdade.
#define SERVER_IP   "192.168.0.10"
#define SERVER_PORT 8000

// Prefixo da API. Duas opções, e as duas atendidas pelo servidor:
//
//   ""      -> /api/eventos           (caminho histórico, o padrão)
//   "/v1"   -> /api/v1/eventos        (versão FIXADA)
//
// Fixar a versão importa MAIS para o firmware que para qualquer outro
// consumidor: atualizá-lo exige reflash físico de cada aparelho preso a um
// leito. Um servidor que mude de contrato quebraria a frota inteira de uma vez,
// e a correção passaria por visitar leito a leito.
//
// Com "/v1", este aparelho continua falando a v1 mesmo depois de o servidor
// passar a servir uma v2 — e a migração vira uma decisão, não um acidente de
// deploy.
//
// `GET /api/versoes` lista o que o servidor atende.
#define API_PREFIXO ""

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
