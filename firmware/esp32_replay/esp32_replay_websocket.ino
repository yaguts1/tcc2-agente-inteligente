// ESP32 NDJSON replayer sketch com WebSocket (versão melhorada)
#include "esp32_replay.h"

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <ctype.h>

namespace {

// Default configuration (edit before flashing)
ReplayConfig g_config{
    .arquivoEventos       = "/eventos.jsonl",
    .hostServidor         = "192.168.0.67",
    .portaServidor        = 8000,
    .endpoint             = "/ws/eventos",  // ← WebSocket agora!
    .delayEntrePacotesMs  = 500,
    .respeitarTimestamp   = false,
    .tentativasMax        = 5,
    .backoffBaseMs        = 500,
    .backoffMaxMs         = 60000,
    .backoffWithJitter    = true,
    .usarSd               = false,
    .ssid                 = "ZECA PAGODINHO",
    .senha                = "32235496",
    .deviceId             = "DEV-001",
    .pacienteId           = "",
    .camaId               = "C-01",
    .perfilPaciente       = "",
    .enviarComoArquivo    = false,
};

ReplayStatus g_status{};
File         g_arquivoEventos;
WebSocketsClient webSocket;  // ← WebSocket em vez de HTTPClient
WiFiClient   g_client;

ReplayCommand g_comandoPendente = ReplayCommand::CMD_NONE;
EventoReplay  g_eventoAtual{};
bool          g_eventoDisponivel = false;
bool          g_pacienteSincronizado = false;
bool          g_websocketConectado = false;  // ← Novo
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
    doc["device_id"] = g_config.deviceId; 
    doc["paciente_id"] = g_config.pacienteId; 
    doc["cama_id"] = g_config.camaId;
    doc["seq"] = ++g_status.seqAtual;  // ← Adicionar seq
    String out; serializeJson(doc, out);
    evento.payload = out; 
    evento.seq = g_status.seqAtual;
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

// ← NOVO: Callback para WebSocket
void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch(type) {
    case WStype_CONNECTED:
      {
        Serial.println("[WS] ✅ Conectado ao servidor WebSocket");
        g_websocketConectado = true;
        
        // Enviar autenticação
        String auth = "{\"device_id\":\"" + g_config.deviceId + 
                     "\",\"cama_id\":\"" + g_config.camaId + "\"}";
        webSocket.sendTXT(auth);
        atualizarEstado(ReplayState::ENVIANDO);
      }
      break;
      
    case WStype_TEXT:
      {
        // Receber ACK ou resposta do servidor
        String msg((const char*)payload, length);
        Serial.printf("[WS] Recebido: %s\n", msg.c_str());
        
        // Parsear resposta
        StaticJsonDocument<256> doc;
        if (deserializeJson(doc, msg) == DeserializationError::Ok) {
          String status = doc["status"] | "";
          if (status == "ok") {
            // ACK recebido, próximo evento
            g_eventoDisponivel = false;
            g_tentativaAtual = 0;
          } else if (status == "connected") {
            Serial.println("[WS] Conexão estabelecida com sucesso");
          }
        }
      }
      break;
      
    case WStype_DISCONNECTED:
      Serial.println("[WS] ❌ Desconectado do servidor");
      g_websocketConectado = false;
      atualizarEstado(ReplayState::OCIOSO);
      break;
      
    case WStype_ERROR:
      Serial.printf("[WS] Erro: %s\n", (const char*)payload);
      g_websocketConectado = false;
      break;
      
    default:
      break;
  }
}

bool enviarEvento(const EventoReplay &evento) {
  if (!g_websocketConectado) return false;
  
  // Enviar via WebSocket
  webSocket.sendTXT(evento.payload);
  g_status.totalEnviados++;
  Serial.printf("[ACK] seq=%u via WebSocket\n", evento.seq);
  return true;
}

void salvarCheckpoint() { 
  if (!g_arquivoEventos) return; 
  const char *ckpt = "/eventos.offset"; 
  unsigned long pos = (unsigned long)g_arquivoEventos.position(); 
  File f = SPIFFS.open(ckpt, "w"); 
  if (f) { f.print(String(pos)); f.close(); } 
}

uint32_t calcularBackoff(uint8_t tentativa) { 
  unsigned long res = g_config.backoffBaseMs * (1UL << tentativa); 
  if (g_config.backoffMaxMs>0 && res > g_config.backoffMaxMs) res = g_config.backoffMaxMs; 
  if (g_config.backoffWithJitter) { 
    uint32_t jitter = (uint32_t)(res/4); 
    uint32_t add = (uint32_t)(esp_random() % (jitter+1)); 
    res += add; 
  } 
  return (uint32_t)res; 
}

void atualizarEstado(ReplayState novo) { 
  g_status.estadoAtual = novo; 
  registrarLog("[ESTADO] -> " + String(static_cast<int>(novo))); 
}

void resetarReplay() { 
  if (g_arquivoEventos) g_arquivoEventos.close(); 
  g_status = ReplayStatus{}; 
  g_eventoAtual = EventoReplay{}; 
  g_eventoDisponivel = false; 
  g_pacienteSincronizado = false; 
  g_tentativaAtual = 0; 
  g_proximoEnvioMs = 0; 
  g_ultimaTsIso = ""; 
}

} // namespace

// Public API
void configurarReplay(const ReplayConfig &cfg) { g_config = cfg; }
void iniciarReplay() { 
  if (g_status.replayAtivo) { registrarLog("[INFO] Replay ja em execucao"); return; } 
  registrarLog("[INFO] Iniciando replay"); 
  resetarReplay(); 
  g_status.replayAtivo = true; 
  atualizarEstado(ReplayState::OCIOSO); 
}
void interromperReplay() { 
  registrarLog("[INFO] Parando replay"); 
  g_status.replayAtivo = false; 
  atualizarEstado(ReplayState::FINALIZADO); 
  resetarReplay(); 
}

void tratarComandoSerial() { 
  while (Serial.available()) { 
    String linha = Serial.readStringUntil('\n'); 
    linha.trim(); 
    if (linha.equalsIgnoreCase("CMD_START")) g_comandoPendente = ReplayCommand::CMD_START; 
    else if (linha.equalsIgnoreCase("CMD_STOP")) g_comandoPendente = ReplayCommand::CMD_STOP; 
    else if (!linha.isEmpty()) registrarLog("[WARN] Comando desconhecido: " + linha); 
  } 
}

void processarReplay() {
  // ← NOVO: Manter WebSocket vivo
  webSocket.loop();
  
  tratarComandoSerial();
  if (g_comandoPendente == ReplayCommand::CMD_START) { iniciarReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  else if (g_comandoPendente == ReplayCommand::CMD_STOP) { interromperReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  if (!g_status.replayAtivo) return;
  switch (g_status.estadoAtual) {
    case ReplayState::OCIOSO: {
      conectarWiFi(); 
      
      // ← NOVO: Conectar WebSocket
      if (!g_websocketConectado) {
        String wsUrl = "ws://" + g_config.hostServidor + ":" + String(g_config.portaServidor) + g_config.endpoint;
        Serial.printf("[WS] Conectando a %s...\n", wsUrl.c_str());
        webSocket.begin(g_config.hostServidor.c_str(), g_config.portaServidor, g_config.endpoint.c_str());
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);
        delay(1000);
        return;
      }
      
      if (!abrirArquivoEventos()) { registrarLog("[ERRO] Abortando"); interromperReplay(); break; }
      atualizarEstado(ReplayState::ENVIANDO); 
      break;
    }
    case ReplayState::ENVIANDO: {
      if (!g_eventoDisponivel) { 
        if (!lerProximoEvento(g_eventoAtual)) { 
          registrarLog("[INFO] Fim do arquivo"); 
          atualizarEstado(ReplayState::FINALIZADO); 
          break; 
        } 
        g_eventoDisponivel = true; 
        g_tentativaAtual = 0; 
      }
      if (g_config.respeitarTimestamp) { /* g_proximoEnvioMs set in lerProximoEvento */ }
      else { if (g_proximoEnvioMs==0) g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs; }
      if ((long)g_proximoEnvioMs - (long)millis() > 0) return;
      g_proximoEnvioMs = 0;
      
      atualizarEstado(ReplayState::ESPERANDO_ACK);
      if (enviarEvento(g_eventoAtual)) { 
        g_eventoDisponivel = false; 
        g_tentativaAtual = 0; 
        salvarCheckpoint(); 
        atualizarEstado(ReplayState::ENVIANDO); 
      }
      else { 
        atualizarEstado(ReplayState::REENVIAR); 
      }
      break;
    }
    case ReplayState::ESPERANDO_ACK: { 
      if (g_eventoDisponivel) atualizarEstado(ReplayState::REENVIAR); 
      else atualizarEstado(ReplayState::ENVIANDO); 
      break; 
    }
    case ReplayState::REENVIAR: { 
      if (g_tentativaAtual >= g_config.tentativasMax) { 
        registrarLog("[ERRO] Limite retries atingido"); 
        atualizarEstado(ReplayState::FINALIZADO); 
        break; 
      } 
      const uint32_t aguardar = calcularBackoff(g_tentativaAtual); 
      registrarLog("[INFO] Reenviando em " + String(aguardar) + " ms"); 
      g_proximoEnvioMs = millis() + aguardar; 
      g_tentativaAtual++; 
      return; 
      break; 
    }
    case ReplayState::FINALIZADO: { 
      salvarCheckpoint(); 
      registrarLog("[INFO] Replay finalizado"); 
      g_status.replayAtivo = false; 
      resetarReplay(); 
      break; 
    }
  }
}

void setup() { 
  Serial.begin(115200); 
  registrarLog("[SETUP] ESP32 Replay com WebSocket pronto"); 
  uint32_t seed = ESP.getEfuseMac(); 
  randomSeed((unsigned long)(seed ^ millis())); 
  conectarWiFi(); 
}

void loop() { 
  processarReplay(); 
  delay(10); 
}
