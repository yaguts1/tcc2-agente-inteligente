// Transporte WebSocket: conexão persistente em /api/ws/eventos.
//
// A diferença essencial em relação ao HTTP é que o ACK é ASSÍNCRONO:
// `sendTXT()` retorna assim que entrega o quadro ao socket, e a resposta do
// servidor chega depois, por callback. Por isso `transporteDesfecho()` devolve
// PENDENTE enquanto ninguém confirmou.
//
// A versão anterior deste transporte tratava "mandei" como "chegou": contava
// `totalEnviados`, escrevia "[ACK]" no log e avançava o checkpoint no envio.
// Se o servidor recusasse a amostra — ou se a conexão caísse entre o send e o
// ACK —, o evento era dado por entregue e o replay seguia adiante. Perda
// silenciosa, do lado do dispositivo, exatamente o que o ACK existe para
// evitar.

#ifndef TRANSPORTE_WS_H
#define TRANSPORTE_WS_H

#include "replay_comum.h"
#include <HTTPClient.h>
#include <WebSocketsClient.h>

namespace replay {

WebSocketsClient g_ws;
WiFiClient       g_clienteTcp;
bool             g_wsConectado = false;
ResultadoEnvio   g_ultimoDesfecho = ResultadoEnvio::PENDENTE;
unsigned long    g_enviadoEmMs = 0;

// Sem resposta neste prazo, o envio conta como TRANSIENTE e entra no backoff.
//
// Sem timeout, uma conexão que morre calada (cabo caindo, servidor travado sem
// fechar o socket) deixaria a máquina de estados esperando um ACK que nunca
// vem — o replay pararia sem log e sem retomada.
static const unsigned long TIMEOUT_ACK_MS = 15000;

inline void configurarPadraoDoTransporte() {
  if (g_config.endpoint.isEmpty()) g_config.endpoint = "/api/ws/eventos";
}

inline void aoEventoWebSocket(WStype_t tipo, uint8_t *payload, size_t length) {
  switch (tipo) {
    case WStype_CONNECTED: {
      registrarLog("[WS] Conectado ao servidor");
      // O token vai no CORPO da mensagem de auth, e não como header: a lib de
      // WebSocket do ESP32 não permite definir headers no handshake. O backend
      // aceita os dois caminhos (ver interface/routers/ingestao.py).
      String tokenCampo = "";
#ifdef DEVICE_TOKEN
      if (strlen(DEVICE_TOKEN) > 0) tokenCampo = ",\"token\":\"" + String(DEVICE_TOKEN) + "\"";
#endif
      g_ws.sendTXT("{\"device_id\":\"" + g_config.deviceId +
                   "\",\"cama_id\":\"" + g_config.camaId + "\"" + tokenCampo + "}");
      break;
    }

    case WStype_TEXT: {
      String msg((const char *)payload, length);
      StaticJsonDocument<256> doc;
      if (deserializeJson(doc, msg)) { registrarLog("[WS] Resposta ilegivel: " + msg); break; }
      String status = doc["status"] | "";

      if (status == "connected") {
        // Só aqui a conexão está de fato utilizável: antes disso o servidor
        // ainda não validou o token, e um envio seria descartado.
        g_wsConectado = true;
        registrarLog("[WS] Autenticado");
      } else if (status == "ok") {
        g_ultimoDesfecho = ResultadoEnvio::ACK;
        g_status.totalEnviados++;
        g_status.ultimaRespostaMs = millis();
        registrarLog("[ACK] seq=" + String((uint32_t)(doc["seq"] | 0)));
      } else if (status == "error") {
        // O backend devolve código estável (ver `websocket_eventos`).
        // `invalid_device_token` é configuração errada: insistir permite que o
        // dispositivo se recupere sozinho quando alguém corrigir, e desistir
        // seria descartar amostra clínica por engano de operação.
        const char *codigo = doc["error"] | "";
        // Regra em `logica_pura.h`, testada em firmware/test.
        g_ultimoDesfecho = (pura::classificarErroWebSocket(codigo) == pura::Desfecho::PERMANENTE)
                               ? ResultadoEnvio::PERMANENTE
                               : ResultadoEnvio::TRANSIENTE;
        g_status.totalFalhas++;
        registrarLog("[FALHA] ws error=" + String(codigo));
      }
      break;
    }

    case WStype_DISCONNECTED:
      registrarLog("[WS] Desconectado");
      g_wsConectado = false;
      // Uma queda entre o envio e o ACK não pode ser lida como entrega: o
      // evento volta para a fila de reenvio.
      if (g_ultimoDesfecho == ResultadoEnvio::PENDENTE) {
        g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;
      }
      break;

    case WStype_ERROR:
      registrarLog("[WS] Erro no socket");
      g_wsConectado = false;
      if (g_ultimoDesfecho == ResultadoEnvio::PENDENTE) {
        g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;
      }
      break;

    default:
      break;
  }
}

inline bool transporteIniciarImpl() {
  conectarWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;
  if (g_wsConectado) return true;

  static bool iniciado = false;
  if (!iniciado) {
    registrarLog("[WS] Conectando a " + g_config.hostServidor + ":" +
                 String(g_config.portaServidor) + g_config.endpoint);
    g_ws.begin(g_config.hostServidor.c_str(), g_config.portaServidor, g_config.endpoint.c_str());
    g_ws.onEvent(aoEventoWebSocket);
    g_ws.setReconnectInterval(5000);
    iniciado = true;
  }
  // Ainda não autenticado: o chamador tenta de novo no próximo ciclo. Não há
  // `delay()` aqui — travar o loop atrasaria o `g_ws.loop()`, que é justamente
  // quem faz o handshake progredir.
  return false;
}

inline void transporteManterImpl() { g_ws.loop(); }

// A resolução do paciente continua por HTTP: é uma consulta pontual, e abrir um
// segundo canal só para isso não se paga.
inline bool transporteObterPacienteImpl() {
  if (g_config.camaId.isEmpty()) { registrarLog("[ERRO] Cama ID nao configurado"); return false; }
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    if (WiFi.status() != WL_CONNECTED) { registrarLog("[ERRO] Sem Wi-Fi para consultar paciente"); return false; }
  }
  HTTPClient http;
  String url = montarUrl("/api/pacientes/cama/" + urlEncode(g_config.camaId));
  registrarLog("[PACIENTE] Consultando " + url);
  http.begin(g_clienteTcp, url);
  http.addHeader("Accept", "application/json");
#ifdef DEVICE_TOKEN
  if (strlen(DEVICE_TOKEN) > 0) http.addHeader("X-Device-Token", DEVICE_TOKEN);
#endif
  int status = http.GET();
  if (status != 200) {
    registrarLog("[ERRO] Falha ao obter paciente da cama. HTTP=" + String(status));
    http.end();
    return false;
  }
  String corpo = http.getString();
  http.end();
  DynamicJsonDocument doc(2048);
  if (deserializeJson(doc, corpo)) { registrarLog("[ERRO] Resposta paciente invalida"); return false; }
  const char *pac = doc["paciente_id"] | "";
  if (strlen(pac) == 0) { registrarLog("[ERRO] Resposta nao contem paciente_id"); return false; }
  g_config.pacienteId = String(pac);
  g_config.perfilPaciente = String(doc["perfil"] | "");
  String p = g_config.perfilPaciente; if (p.isEmpty()) p = "-";
  registrarLog("[PACIENTE] Vinculado a " + g_config.pacienteId + " (perfil=" + p + ")");
  return true;
}

inline bool transporteEnviarImpl(const EventoReplay &evento) {
  if (!g_wsConectado) { g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE; return false; }
  // O `seq` acompanha o payload para o ACK poder ser correlacionado — o
  // servidor o devolve na resposta.
  StaticJsonDocument<1664> doc;
  if (deserializeJson(doc, evento.payload)) {
    // Não deveria acontecer: `lerProximoEvento` já validou. Se acontecer, é
    // conteúdo que ninguém vai aceitar.
    g_ultimoDesfecho = ResultadoEnvio::PERMANENTE;
    return true;
  }
  doc["seq"] = evento.seq;
  String comSeq; serializeJson(doc, comSeq);

  g_ultimoDesfecho = ResultadoEnvio::PENDENTE;
  g_enviadoEmMs = millis();
  if (!g_ws.sendTXT(comSeq)) {
    g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;
    return false;
  }
  return true;
}

inline ResultadoEnvio transporteDesfechoImpl() {
  if (g_ultimoDesfecho == ResultadoEnvio::PENDENTE &&
      millis() - g_enviadoEmMs > TIMEOUT_ACK_MS) {
    registrarLog("[WS] Sem ACK dentro do prazo; tratando como temporario");
    g_status.totalFalhas++;
    g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;
  }
  return g_ultimoDesfecho;
}

}  // namespace replay

#endif  // TRANSPORTE_WS_H
