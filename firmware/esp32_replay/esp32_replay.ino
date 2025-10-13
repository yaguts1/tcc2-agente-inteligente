#include "esp32_replay.h"

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <ctype.h>

// Se estiver usando armazenamento em SD, habilite a biblioteca apropriada.
// #include <SD.h>

namespace {

// ===========================
// Configurações padrão (edite)
// ===========================
ReplayConfig g_config{
    // Arquivo
    .arquivoEventos       = "/eventos.jsonl",

    // Backend
    .hostServidor         = "http://192.168.0.67",
    .portaServidor        = 8000,
    .endpoint             = "/api/eventos",

    // Ritmo
    .delayEntrePacotesMs  = 500,
    .respeitarTimestamp   = false,

    // Retry
    .tentativasMax        = 5,
    .backoffBaseMs        = 500,

    // Armazenamento
    .usarSd               = false,

    // Rede
    .ssid                 = "ZECA PAGODINHO",
    .senha                = "32235496",

    // Identidades fixas (1 paciente)
    .deviceId             = "DEV-001",
    .pacienteId           = "",
    .camaId               = "C-01",
    .perfilPaciente       = "",
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

// Para reprodução “no tempo”
unsigned long g_proximoEnvioMs = 0;
String        g_ultimaTsIso;

// -------------------------------
// Utilitários
// -------------------------------
void registrarLog(const String &mensagem) {
  Serial.println(mensagem);
}

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[WIFI] Conectando em %s ...\n", g_config.ssid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.begin(g_config.ssid.c_str(), g_config.senha.c_str());

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - t0 > 20000) {  // 20s timeout
      Serial.println("\n[WIFI] Timeout");
      break;
    }
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Conectado. IP: %s\n", WiFi.localIP().toString().c_str());
  }
}

bool inicializarArmazenamento() {
  if (g_config.usarSd) {
    // TODO: ajustar pinos e chamada SD.begin(pin)
    // return SD.begin();
    return false;  // placeholder até habilitar SD
  }
  return SPIFFS.begin(true);
}

bool abrirArquivoEventos() {
  if (!inicializarArmazenamento()) {
    registrarLog("[ERRO] Falha ao iniciar armazenamento");
    return false;
  }

  if (g_config.usarSd) {
    // g_arquivoEventos = SD.open(g_config.arquivoEventos, "r");
  } else {
    g_arquivoEventos = SPIFFS.open(g_config.arquivoEventos, "r");
  }

  if (!g_arquivoEventos) {
    registrarLog("[ERRO] Nao foi possivel abrir " + g_config.arquivoEventos);
    return false;
  }
  return true;
}

// Converte "YYYY-MM-DDTHH:MM:SS(Z|+00:00)" -> segundos do dia (aproximação p/ delta local)
bool parseIsoToSeconds(const String& iso, unsigned long &out_s) {
  if (iso.length() < 19) return false;
  int HH = iso.substring(11, 13).toInt();
  int MM = iso.substring(14, 16).toInt();
  int SS = iso.substring(17, 19).toInt();
  if (HH < 0 || HH > 23) return false;
  if (MM < 0 || MM > 59) return false;
  if (SS < 0 || SS > 59) return false;
  out_s = (unsigned long)HH*3600UL + (unsigned long)MM*60UL + (unsigned long)SS;
  return true;
}

// Lê a próxima linha NDJSON, injeta IDs fixos e prepara ritmo por timestamp
bool lerProximoEvento(EventoReplay &evento) {
  while (true) {
    if (!g_arquivoEventos.available()) return false;

    String linha = g_arquivoEventos.readStringUntil('\n');
    linha.trim();
    if (linha.isEmpty()) continue;  // pula linhas em branco

    // Parse do JSON para injetar/forçar IDs fixos
    StaticJsonDocument<768> doc;
    DeserializationError err = deserializeJson(doc, linha);
    if (err) {
      registrarLog("[WARN] JSON invalido; pulando linha");
      continue;
    }

    // Injeta/força identidades (um paciente)
    doc["device_id"]   = g_config.deviceId;
    doc["paciente_id"] = g_config.pacienteId;
    doc["cama_id"]     = g_config.camaId;

    // Normaliza de volta para String
    String out;
    serializeJson(doc, out);

    evento.payload = out;
    evento.seq     = ++g_status.seqAtual;

    // Respeitar ritmo segundo ts_utc, se habilitado
    if (g_config.respeitarTimestamp) {
      String tsIso = doc["ts_utc"] | "";
      if (tsIso.length() >= 19) {
        unsigned long sAtual=0, sUlt=0;
        if (parseIsoToSeconds(tsIso, sAtual)) {
          if (g_ultimaTsIso.length() >= 19 && parseIsoToSeconds(g_ultimaTsIso, sUlt)) {
            long delta = (long)sAtual - (long)sUlt;
            if (delta < 0) delta = 0;  // evita atraso negativo
            g_proximoEnvioMs = millis() + (unsigned long)delta * 1000UL;
          } else {
            g_proximoEnvioMs = millis(); // primeira amostra libera já
          }
          g_ultimaTsIso = tsIso;
        } else {
          g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
        }
      } else {
        g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
      }
    }

    return true;
  }
}

String montarUrl(const String &rotaBruta) {
    // Compor "http://IP:PORTA/rota" sem barras duplas
    String base = g_config.hostServidor;
    if (base.endsWith("/")) base.remove(base.length()-1);
    String rota = rotaBruta;
    if (!rota.startsWith("/")) rota = "/" + rota;
    return base + ":" + String(g_config.portaServidor) + rota;
}

String montarUrlEventos() {
    return montarUrl(g_config.endpoint);
}

String urlEncode(const String &valor) {
    static const char HEX[] = "0123456789ABCDEF";
    String saida;
    saida.reserve(valor.length());
    for (size_t i = 0; i < valor.length(); ++i) {
        const unsigned char c = static_cast<unsigned char>(valor.charAt(i));
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            saida += static_cast<char>(c);
        } else if (c == ' ') {
            saida += "%20";
        } else {
            saida += '%';
            saida += HEX[(c >> 4) & 0x0F];
            saida += HEX[c & 0x0F];
        }
    }
    return saida;
}

bool atualizarPacienteDaCama() {
    if (g_config.camaId.isEmpty()) {
        registrarLog("[ERRO] Cama ID nao configurado");
        return false;
    }

    if (WiFi.status() != WL_CONNECTED) {
        conectarWiFi();
        if (WiFi.status() != WL_CONNECTED) {
            registrarLog("[ERRO] Sem Wi-Fi para consultar paciente");
            return false;
        }
    }

    String rota = "/api/pacientes/cama/" + urlEncode(g_config.camaId);
    String url = montarUrl(rota);

    registrarLog("[PACIENTE] Consultando configuracoes em " + url);

    g_http.begin(g_client, url);
    g_http.addHeader("Accept", "application/json");
    int status = g_http.GET();

    if (status != 200) {
        registrarLog("[ERRO] Falha ao obter paciente da cama. HTTP=" + String(status));
        g_http.end();
        return false;
    }

    String corpo = g_http.getString();
    g_http.end();

    DynamicJsonDocument doc(2048);
    DeserializationError err = deserializeJson(doc, corpo);
    if (err) {
        registrarLog("[ERRO] Resposta de paciente invalida: " + String(err.c_str()));
        return false;
    }

    const char* pacienteId = doc["paciente_id"] | "";
    const char* perfil     = doc["perfil"] | "";

    if (strlen(pacienteId) == 0) {
        registrarLog("[ERRO] Resposta nao contem paciente_id");
        return false;
    }

    g_config.pacienteId     = String(pacienteId);
    g_config.perfilPaciente = String(perfil);

    String perfilLog = g_config.perfilPaciente;
    if (perfilLog.isEmpty()) perfilLog = "-";
    registrarLog("[PACIENTE] Vinculado a " + g_config.pacienteId + " (perfil=" + perfilLog + ")");
    return true;
}

bool garantirPacienteConfigurado() {
    if (g_pacienteSincronizado) {
        return true;
    }
    if (atualizarPacienteDaCama()) {
        g_pacienteSincronizado = true;
        return true;
    }
    return false;
}

bool enviarEvento(const EventoReplay &evento) {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      registrarLog("[ERRO] Sem Wi-Fi");
      return false;
    }
  }

    String url = montarUrlEventos();
  g_http.begin(g_client, url);
  g_http.addHeader("Content-Type", "application/json");
  g_http.addHeader("X-Seq", String(evento.seq));
  g_http.addHeader("X-Device-Id", g_config.deviceId);

  int status = g_http.POST(evento.payload);
  g_http.end();

  if (status >= 200 && status < 300) {
    g_status.totalEnviados++;
    g_status.ultimaRespostaMs = millis();
    registrarLog("[ACK] seq=" + String(evento.seq) + " status=" + String(status));
    return true;
  }

  g_status.totalFalhas++;
  registrarLog("[FALHA] seq=" + String(evento.seq) + " status=" + String(status));
  return false;
}

void atualizarEstado(ReplayState novoEstado) {
  g_status.estadoAtual = novoEstado;
  // Loga como inteiro para economizar FLASH/heap
  registrarLog("[ESTADO] -> " + String(static_cast<int>(novoEstado)));
}

  void resetarReplay() {
    if (g_arquivoEventos) g_arquivoEventos.close();
    g_status = ReplayStatus{};
    g_eventoAtual      = EventoReplay{};
    g_eventoDisponivel = false;
    g_pacienteSincronizado = false;
    g_tentativaAtual   = 0;
    g_proximoEnvioMs   = 0;
    g_ultimaTsIso      = "";
  }

uint32_t calcularBackoff(uint8_t tentativa) {
  // Backoff exponencial simples: base * 2^tentativa
  return g_config.backoffBaseMs * (1UL << tentativa);
}

} // namespace

// -------------------------------
// API pública
// -------------------------------
void configurarReplay(const ReplayConfig &cfg) {
  g_config = cfg;
}

void iniciarReplay() {
  if (g_status.replayAtivo) {
    registrarLog("[INFO] Replay ja em execucao");
    return;
  }
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
    if (linha.equalsIgnoreCase("CMD_START")) {
      g_comandoPendente = ReplayCommand::CMD_START;
    } else if (linha.equalsIgnoreCase("CMD_STOP")) {
      g_comandoPendente = ReplayCommand::CMD_STOP;
    } else if (!linha.isEmpty()) {
      registrarLog("[WARN] Comando desconhecido: " + linha);
    }
  }
}

void tratarComandoOta(const String &comando) {
  if (comando.equalsIgnoreCase("CMD_START")) {
    g_comandoPendente = ReplayCommand::CMD_START;
  } else if (comando.equalsIgnoreCase("CMD_STOP")) {
    g_comandoPendente = ReplayCommand::CMD_STOP;
  } else {
    registrarLog("[WARN] OTA comando desconhecido: " + comando);
  }
}

// -------------------------------
// Laço principal do replayer
// -------------------------------
void processarReplay() {
  tratarComandoSerial();

  if (g_comandoPendente == ReplayCommand::CMD_START) {
    iniciarReplay();
    g_comandoPendente = ReplayCommand::CMD_NONE;
  } else if (g_comandoPendente == ReplayCommand::CMD_STOP) {
    interromperReplay();
    g_comandoPendente = ReplayCommand::CMD_NONE;
  }

  if (!g_status.replayAtivo) {
    return;
  }

  switch (g_status.estadoAtual) {
    case ReplayState::OCIOSO: {
      conectarWiFi();
      if (!garantirPacienteConfigurado()) {
        registrarLog("[ERRO] Tentando novamente sincronizar paciente...");
        delay(2000);
        break;
      }
      if (!abrirArquivoEventos()) {
        registrarLog("[ERRO] Abortando replay");
        interromperReplay();
        break;
      }
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
        g_tentativaAtual   = 0;
      }

      // Se respeitarTimestamp, aguarda até o horário calculado
      if (g_config.respeitarTimestamp) {
        long restante = (long)g_proximoEnvioMs - (long)millis();
        if (restante > 0) {
          delay((uint32_t)restante);
        }
      } else {
        // Ritmo fixo entre pacotes
        delay(g_config.delayEntrePacotesMs);
      }

      atualizarEstado(ReplayState::ESPERANDO_ACK);
      if (enviarEvento(g_eventoAtual)) {
        g_eventoDisponivel = false;
        g_tentativaAtual   = 0;
        atualizarEstado(ReplayState::ENVIANDO);
      } else {
        atualizarEstado(ReplayState::REENVIAR);
      }
      break;
    }

    case ReplayState::ESPERANDO_ACK: {
      // HTTPClient é síncrono; não há espera adicional.
      if (g_eventoDisponivel) {
        atualizarEstado(ReplayState::REENVIAR);
      } else {
        atualizarEstado(ReplayState::ENVIANDO);
      }
      break;
    }

    case ReplayState::REENVIAR: {
      if (g_tentativaAtual >= g_config.tentativasMax) {
        registrarLog("[ERRO] Limite de retries atingido");
        atualizarEstado(ReplayState::FINALIZADO);
        break;
      }
      const uint32_t aguardar = calcularBackoff(g_tentativaAtual);
      registrarLog("[INFO] Reenviando em " + String(aguardar) + " ms");
      delay(aguardar);
      g_tentativaAtual++;
      atualizarEstado(ReplayState::ENVIANDO);
      break;
    }

    case ReplayState::FINALIZADO: {
      registrarLog("[INFO] Replay finalizado");
      g_status.replayAtivo = false;
      resetarReplay();
      break;
    }
  }
}

// -------------------------------
// Arduino: setup/loop
// -------------------------------
void setup() {
  Serial.begin(115200);
  registrarLog("[SETUP] ESP32 Replay pronto");
  conectarWiFi();
  // Se quiser iniciar automaticamente:
  // iniciarReplay();
}

void loop() {
  processarReplay();
  delay(10);
}
