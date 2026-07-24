// ESP32 NDJSON replayer sketch
#include "esp32_replay.h"
#include "config.h"  // credenciais WiFi/servidor (git-ignored; ver config.example.h)

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <ctype.h>

// If using SD storage, #include <SD.h> and set g_config.usarSd = true

namespace {

// Default configuration (edit before flashing)
ReplayConfig g_config{
    .arquivoEventos       = "/eventos.jsonl",
    .hostServidor         = "http://" SERVER_IP,
    .portaServidor        = SERVER_PORT,
    .endpoint             = "/api/eventos",
    .delayEntrePacotesMs  = 500,
    .respeitarTimestamp   = false,
    .tentativasMax        = 5,
    .backoffBaseMs        = 500,
    .backoffMaxMs         = 60000,
    .backoffWithJitter    = true,
    .usarSd               = false,
    .ssid                 = WIFI_SSID,
    .senha                = WIFI_SENHA,
    .deviceId             = "DEV-001",
    .pacienteId           = "",
    .camaId               = "C-01",
    .perfilPaciente       = "",
    .enviarComoArquivo    = false,
};

ReplayStatus g_status{};
File         g_arquivoEventos;
HTTPClient   g_http;
WiFiClient   g_client;

ReplayCommand g_comandoPendente = ReplayCommand::CMD_NONE;
EventoReplay  g_eventoAtual{};
bool          g_eventoDisponivel = false;
bool          g_pacienteSincronizado = false;
uint8_t       g_tentativaAtual   = 0;

unsigned long g_proximoEnvioMs = 0;
String        g_ultimaTsIso;

void registrarLog(const String &mensagem) { Serial.println(mensagem); }

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("[WIFI] Connecting to %s...\n", g_config.ssid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.begin(g_config.ssid.c_str(), g_config.senha.c_str());
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print('.');
    if (millis() - t0 > 20000) { Serial.println("\n[WIFI] Timeout"); break; }
  }
  if (WiFi.status() == WL_CONNECTED) Serial.printf("\n[WIFI] Connected IP=%s\n", WiFi.localIP().toString().c_str());
}

bool inicializarArmazenamento() {
  if (g_config.usarSd) {
    // TODO: enable SD.begin and proper pins
    return false;
  }
  return SPIFFS.begin(true);
}

bool abrirArquivoEventos() {
  if (!inicializarArmazenamento()) { registrarLog("[ERRO] Falha ao iniciar armazenamento"); return false; }
  if (g_config.usarSd) {
    // g_arquivoEventos = SD.open(g_config.arquivoEventos, "r");
  } else {
    g_arquivoEventos = SPIFFS.open(g_config.arquivoEventos, "r");
  }
  if (!g_arquivoEventos) { registrarLog("[ERRO] Nao foi possivel abrir " + g_config.arquivoEventos); return false; }
  const char *ckpt = "/eventos.offset";
  if (SPIFFS.exists(ckpt)) {
    File f = SPIFFS.open(ckpt, "r");
    if (f) {
      String s = f.readString(); f.close(); s.trim();
      if (s.length() > 0) {
        unsigned long pos = (unsigned long)s.toInt();
        if (pos > 0 && g_arquivoEventos.seek(pos, SeekSet)) registrarLog("[INFO] Retomando offset " + String(pos));
      }
    }
  }
  return true;
}

bool parseIsoToEpochSeconds(const String& iso, unsigned long &out_s) {
  if (iso.length() < 19) return false;
  int year = iso.substring(0,4).toInt();
  int month = iso.substring(5,7).toInt();
  int day = iso.substring(8,10).toInt();
  int hour = iso.substring(11,13).toInt();
  int minute = iso.substring(14,16).toInt();
  int second = iso.substring(17,19).toInt();
  if (year <= 1970 || month < 1 || month > 12 || day < 1 || day > 31) return false;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) return false;
  auto days_from_civil = [](int y, unsigned m, unsigned d)->long {
    y -= m <= 2; const long era = (y >= 0 ? y : y - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(y - era * 400);
    const unsigned doy = (153u * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const unsigned doe = yoe * 365 + yoe/4 - yoe/100 + doy;
    return era * 146097L + static_cast<long>(doe) - 719468L;
  };
  long days = days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
  unsigned long epoch = (unsigned long)days * 86400UL + (unsigned long)hour*3600UL + (unsigned long)minute*60UL + (unsigned long)second;
  if (iso.length() > 19) {
    String tail = iso.substring(19); tail.trim();
    if (tail.length()>0) {
      if (tail.charAt(0)=='Z' || tail.charAt(0)=='z') {}
      else if (tail.charAt(0)=='+' || tail.charAt(0)=='-') {
        if (tail.length() >= 6) {
          int sign = (tail.charAt(0)=='+')?1:-1;
          int off_h = tail.substring(1,3).toInt();
          int off_m = tail.substring(4,6).toInt();
          if (off_h>=0 && off_h<=23 && off_m>=0 && off_m<=59) {
            long offs = (long)off_h*3600L + (long)off_m*60L;
            if (sign>0) epoch -= (unsigned long)offs; else epoch += (unsigned long)offs;
          }
        }
      }
    }
  }
  out_s = epoch; return true;
}

bool lerProximoEvento(EventoReplay &evento) {
  while (true) {
    if (!g_arquivoEventos.available()) return false;
    String linha = g_arquivoEventos.readStringUntil('\n'); linha.trim();
    if (linha.isEmpty()) continue;
    StaticJsonDocument<1536> doc;
    DeserializationError err = deserializeJson(doc, linha);
    if (err) { registrarLog("[WARN] JSON invalido; pulando linha"); continue; }
    doc["device_id"] = g_config.deviceId; doc["paciente_id"] = g_config.pacienteId; doc["cama_id"] = g_config.camaId;
    String out; serializeJson(doc, out);
    evento.payload = out; evento.seq = ++g_status.seqAtual;
    if (g_config.respeitarTimestamp) {
      String tsIso = doc["ts_utc"] | "";
      if (tsIso.length()>=19) {
        unsigned long sAtual=0, sUlt=0;
        if (parseIsoToEpochSeconds(tsIso, sAtual)) {
          if (g_ultimaTsIso.length()>=19 && parseIsoToEpochSeconds(g_ultimaTsIso, sUlt)) {
            long delta = (long)sAtual - (long)sUlt; if (delta<0) delta=0;
            g_proximoEnvioMs = millis() + (unsigned long)delta * 1000UL;
          } else g_proximoEnvioMs = millis();
          g_ultimaTsIso = tsIso;
        } else g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
      } else g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
    }
    return true;
  }
}

String montarUrl(const String &rotaBruta) { String base = g_config.hostServidor; if (base.endsWith("/")) base.remove(base.length()-1); String rota = rotaBruta; if (!rota.startsWith("/")) rota = "/" + rota; return base + ":" + String(g_config.portaServidor) + rota; }
String montarUrlEventos() { return montarUrl(g_config.endpoint); }

String urlEncode(const String &valor) {
  static const char HEX_CHARS[] = "0123456789ABCDEF";
  String saida; saida.reserve(valor.length());
  for (size_t i=0;i<valor.length();++i) {
    const unsigned char c = static_cast<unsigned char>(valor.charAt(i));
    if (isalnum(c) || c=='-'||c=='_'||c=='.'||c=='~') { saida += (char)c; }
    else if (c==' ') saida += "%20";
    else { saida += '%'; saida += HEX_CHARS[(c>>4)&0x0F]; saida += HEX_CHARS[c&0x0F]; }
  }
  return saida;
}

bool atualizarPacienteDaCama() {
  if (g_config.camaId.isEmpty()) { registrarLog("[ERRO] Cama ID nao configurado"); return false; }
  if (WiFi.status()!=WL_CONNECTED) { conectarWiFi(); if (WiFi.status()!=WL_CONNECTED) { registrarLog("[ERRO] Sem Wi-Fi para consultar paciente"); return false; } }
  String rota = "/api/pacientes/cama/" + urlEncode(g_config.camaId); String url = montarUrl(rota); registrarLog("[PACIENTE] Consultando " + url);
  g_http.begin(g_client, url); g_http.addHeader("Accept","application/json"); int status = g_http.GET(); if (status != 200) { registrarLog("[ERRO] Falha ao obter paciente da cama. HTTP=" + String(status)); g_http.end(); return false; }
  String corpo = g_http.getString(); g_http.end(); DynamicJsonDocument doc(2048); DeserializationError err = deserializeJson(doc, corpo); if (err) { registrarLog("[ERRO] Resposta paciente invalida: " + String(err.c_str())); return false; }
  const char *pac = doc["paciente_id"] | ""; const char *perfil = doc["perfil"] | ""; if (strlen(pac)==0) { registrarLog("[ERRO] Resposta nao contem paciente_id"); return false; }
  g_config.pacienteId = String(pac); g_config.perfilPaciente = String(perfil); String p = g_config.perfilPaciente; if (p.isEmpty()) p = "-"; registrarLog("[PACIENTE] Vinculado a " + g_config.pacienteId + " (perfil=" + p + ")"); return true;
}

bool garantirPacienteConfigurado() { if (g_pacienteSincronizado) return true; if (atualizarPacienteDaCama()) { g_pacienteSincronizado = true; return true; } return false; }

bool enviarEvento(const EventoReplay &evento) {
  if (WiFi.status()!=WL_CONNECTED) { conectarWiFi(); if (WiFi.status()!=WL_CONNECTED) { registrarLog("[ERRO] Sem Wi-Fi"); return false; } }
  String url = montarUrlEventos(); g_http.begin(g_client, url); g_http.addHeader("Content-Type","application/json"); g_http.addHeader("X-Seq", String(evento.seq)); g_http.addHeader("X-Device-Id", g_config.deviceId);
  int status = g_http.POST(evento.payload); g_http.end(); if (status>=200 && status<300) { g_status.totalEnviados++; g_status.ultimaRespostaMs = millis(); registrarLog("[ACK] seq=" + String(evento.seq) + " status=" + String(status)); return true; }
  g_status.totalFalhas++; registrarLog("[FALHA] seq=" + String(evento.seq) + " status=" + String(status)); return false;
}

void salvarCheckpoint() { if (!g_arquivoEventos) return; const char *ckpt = "/eventos.offset"; unsigned long pos = (unsigned long)g_arquivoEventos.position(); File f = SPIFFS.open(ckpt, "w"); if (f) { f.print(String(pos)); f.close(); } }

uint32_t calcularBackoff(uint8_t tentativa) { unsigned long res = g_config.backoffBaseMs * (1UL << tentativa); if (g_config.backoffMaxMs>0 && res > g_config.backoffMaxMs) res = g_config.backoffMaxMs; if (g_config.backoffWithJitter) { uint32_t jitter = (uint32_t)(res/4); uint32_t add = (uint32_t)(esp_random() % (jitter+1)); res += add; } return (uint32_t)res; }

void atualizarEstado(ReplayState novo) { g_status.estadoAtual = novo; registrarLog("[ESTADO] -> " + String(static_cast<int>(novo))); }

void resetarReplay() { if (g_arquivoEventos) g_arquivoEventos.close(); g_status = ReplayStatus{}; g_eventoAtual = EventoReplay{}; g_eventoDisponivel = false; g_pacienteSincronizado = false; g_tentativaAtual = 0; g_proximoEnvioMs = 0; g_ultimaTsIso = ""; }

} // namespace

// Public API
void configurarReplay(const ReplayConfig &cfg) { g_config = cfg; }
void iniciarReplay() { if (g_status.replayAtivo) { registrarLog("[INFO] Replay ja em execucao"); return; } registrarLog("[INFO] Iniciando replay"); resetarReplay(); g_status.replayAtivo = true; atualizarEstado(ReplayState::OCIOSO); }
void interromperReplay() { registrarLog("[INFO] Parando replay"); g_status.replayAtivo = false; atualizarEstado(ReplayState::FINALIZADO); resetarReplay(); }

void tratarComandoSerial() { while (Serial.available()) { String linha = Serial.readStringUntil('\n'); linha.trim(); if (linha.equalsIgnoreCase("CMD_START")) g_comandoPendente = ReplayCommand::CMD_START; else if (linha.equalsIgnoreCase("CMD_STOP")) g_comandoPendente = ReplayCommand::CMD_STOP; else if (!linha.isEmpty()) registrarLog("[WARN] Comando desconhecido: " + linha); } }
void tratarComandoOta(const String &comando) { if (comando.equalsIgnoreCase("CMD_START")) g_comandoPendente = ReplayCommand::CMD_START; else if (comando.equalsIgnoreCase("CMD_STOP")) g_comandoPendente = ReplayCommand::CMD_STOP; else registrarLog("[WARN] OTA comando desconhecido: " + comando); }

void processarReplay() {
  tratarComandoSerial();
  if (g_comandoPendente == ReplayCommand::CMD_START) { iniciarReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  else if (g_comandoPendente == ReplayCommand::CMD_STOP) { interromperReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  if (!g_status.replayAtivo) return;
  switch (g_status.estadoAtual) {
    case ReplayState::OCIOSO: {
      conectarWiFi(); if (!garantirPacienteConfigurado()) { registrarLog("[ERRO] Tentando sincronizar paciente..."); return; }
      if (!abrirArquivoEventos()) { registrarLog("[ERRO] Abortando"); interromperReplay(); break; }
      atualizarEstado(ReplayState::ENVIANDO); break;
    }
    case ReplayState::ENVIANDO: {
      if (!g_eventoDisponivel) { if (!lerProximoEvento(g_eventoAtual)) { registrarLog("[INFO] Fim do arquivo"); atualizarEstado(ReplayState::FINALIZADO); break; } g_eventoDisponivel = true; g_tentativaAtual = 0; }
      if (g_config.respeitarTimestamp) { /* g_proximoEnvioMs set in lerProximoEvento */ }
      else { if (g_proximoEnvioMs==0) g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs; }
      if ((long)g_proximoEnvioMs - (long)millis() > 0) return;
      g_proximoEnvioMs = 0;
      if (g_config.enviarComoArquivo) {
        registrarLog("[INFO] Enviando arquivo como multipart para /api/grade");
        String boundary = "----ESP32Boundary" + String((uint32_t)esp_random()); String crlf = "\r\n";
        String head = "--" + boundary + crlf; head += "Content-Disposition: form-data; name=\"arquivo\"; filename=\"eventos.jsonl\"" + crlf; head += "Content-Type: application/jsonl" + crlf + crlf;
        String tail = crlf + "--" + boundary + "--" + crlf;
        g_arquivoEventos.seek(0, SeekSet); String content=""; while (g_arquivoEventos.available()) { String part = g_arquivoEventos.readStringUntil('\n'); content += part + "\n"; }
        String body = head + content + tail; String url = montarUrl("/api/grade"); g_http.begin(g_client, url); g_http.addHeader("Content-Type","multipart/form-data; boundary=" + boundary); g_http.addHeader("X-Device-Id", g_config.deviceId);
        int status = g_http.POST(body); g_http.end(); if (status>=200 && status<300) { registrarLog("[ACK] upload status=" + String(status)); atualizarEstado(ReplayState::FINALIZADO); return; } else { registrarLog("[FALHA] upload status=" + String(status)); }
      }
      atualizarEstado(ReplayState::ESPERANDO_ACK);
      if (enviarEvento(g_eventoAtual)) { g_eventoDisponivel = false; g_tentativaAtual = 0; salvarCheckpoint(); atualizarEstado(ReplayState::ENVIANDO); }
      else { atualizarEstado(ReplayState::REENVIAR); }
      break;
    }
    case ReplayState::ESPERANDO_ACK: { if (g_eventoDisponivel) atualizarEstado(ReplayState::REENVIAR); else atualizarEstado(ReplayState::ENVIANDO); break; }
    case ReplayState::REENVIAR: { if (g_tentativaAtual >= g_config.tentativasMax) { registrarLog("[ERRO] Limite retries atingido"); atualizarEstado(ReplayState::FINALIZADO); break; } const uint32_t aguardar = calcularBackoff(g_tentativaAtual); registrarLog("[INFO] Reenviando em " + String(aguardar) + " ms"); g_proximoEnvioMs = millis() + aguardar; g_tentativaAtual++; return; break; }
    case ReplayState::FINALIZADO: { salvarCheckpoint(); registrarLog("[INFO] Replay finalizado"); g_status.replayAtivo = false; resetarReplay(); break; }
  }
}

void setup() { Serial.begin(115200); registrarLog("[SETUP] ESP32 Replay ready"); uint32_t seed = ESP.getEfuseMac(); randomSeed((unsigned long)(seed ^ millis())); conectarWiFi(); }
void loop() { processarReplay(); delay(10); }
