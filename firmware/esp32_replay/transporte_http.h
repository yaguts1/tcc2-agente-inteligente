// Transporte HTTP: um POST por evento em /api/eventos.
//
// A resposta chega no retorno do POST, então o desfecho é sempre síncrono —
// `transporteDesfecho()` nunca devolve PENDENTE aqui.

#ifndef TRANSPORTE_HTTP_H
#define TRANSPORTE_HTTP_H

#include "replay_comum.h"
#include <HTTPClient.h>

namespace replay {

HTTPClient   g_http;
WiFiClient   g_clienteTcp;
ResultadoEnvio g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;

// Autentica este dispositivo na ingestão. Precisa ser chamado depois de
// `g_http.begin()` e antes do GET/POST. O X-Device-Id que já era enviado é
// escolhido pelo próprio firmware: identifica, mas não prova nada.
// Sem DEVICE_TOKEN definido não envia nada — o backend só exige o header se
// UPP_DEVICE_TOKEN estiver configurado do lado dele.
inline void adicionarTokenDispositivo() {
#ifdef DEVICE_TOKEN
  if (strlen(DEVICE_TOKEN) > 0) g_http.addHeader("X-Device-Token", DEVICE_TOKEN);
#endif
}

inline void configurarPadraoDoTransporte() {
  if (g_config.endpoint.isEmpty()) g_config.endpoint = String("/api") + API_PREFIXO + "/eventos";
}

inline bool transporteIniciarImpl() {
  conectarWiFi();
  return WiFi.status() == WL_CONNECTED;
}

inline void transporteManterImpl() { /* HTTP não mantém conexão entre envios */ }

inline bool transporteObterPacienteImpl() {
  if (g_config.camaId.isEmpty()) { registrarLog("[ERRO] Cama ID nao configurado"); return false; }
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    if (WiFi.status() != WL_CONNECTED) { registrarLog("[ERRO] Sem Wi-Fi para consultar paciente"); return false; }
  }
  String url = montarUrl(String("/api") + API_PREFIXO + "/pacientes/cama/" + urlEncode(g_config.camaId));
  registrarLog("[PACIENTE] Consultando " + url);
  g_http.begin(g_clienteTcp, url);
  g_http.addHeader("Accept", "application/json");
  adicionarTokenDispositivo();
  int status = g_http.GET();
  if (status != 200) {
    // Conta como falha, igual a uma recusa no envio.
    //
    // Só o caminho de ENVIO incrementava, então um aparelho preso aqui — que é
    // onde ele fica com token errado, porque esta rota também exige o token —
    // reportava `falhas=0 enviados=0`: indistinguível de um que acabou de ligar
    // e nunca começou. É o estado que mais importa enxergar, porque é o da
    // configuração errada, e era o único invisível.
    g_status.totalFalhas++;
    registrarLog("[ERRO] Falha ao obter paciente da cama. HTTP=" + String(status));
    g_http.end();
    return false;
  }
  String corpo = g_http.getString();
  g_http.end();
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
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      registrarLog("[ERRO] Sem Wi-Fi");
      g_ultimoDesfecho = ResultadoEnvio::TRANSIENTE;
      return false;
    }
  }
  g_http.begin(g_clienteTcp, montarUrl(g_config.endpoint));
  g_http.addHeader("Content-Type", "application/json");
  g_http.addHeader("X-Seq", String(evento.seq));
  g_http.addHeader("X-Device-Id", g_config.deviceId);
  adicionarTokenDispositivo();
  int status = g_http.POST(evento.payload);
  g_http.end();

  g_ultimoDesfecho = classificarResposta(status);
  if (g_ultimoDesfecho == ResultadoEnvio::ACK) {
    g_status.totalEnviados++;
    g_status.ultimaRespostaMs = millis();
    registrarLog("[ACK] seq=" + String(evento.seq) + " status=" + String(status));
  } else {
    g_status.totalFalhas++;
    registrarLog("[FALHA] seq=" + String(evento.seq) + " status=" + String(status) +
                 (g_ultimoDesfecho == ResultadoEnvio::PERMANENTE ? " (recusado em definitivo)" : " (temporario)"));
  }
  return true;
}

inline ResultadoEnvio transporteDesfechoImpl() { return g_ultimoDesfecho; }

}  // namespace replay

#endif  // TRANSPORTE_HTTP_H
