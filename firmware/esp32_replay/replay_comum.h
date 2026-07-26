// Estado e lógica compartilhados entre os transportes (HTTP e WebSocket).
//
// Por que este arquivo existe
// ---------------------------
// Havia dois sketches completos lado a lado — `esp32_replay.ino` e
// `esp32_replay_websocket.ino` — repetindo leitura do arquivo, checkpoint,
// backoff, conexão Wi-Fi, parse de timestamp e a máquina de estados inteira.
// Só o transporte mudava.
//
// Duas cópias derivam, e derivaram: correções aplicadas numa não chegaram na
// outra. A variante WebSocket, que o LEIA-ME recomendava, estava atrás da HTTP
// em cinco pontos — inclusive gravando no checkpoint a posição LIDA em vez da
// ENTREGUE, que é perda silenciosa de amostra depois de um reboot.
//
// Aqui a lógica existe uma vez. O transporte entra pela interface declarada em
// `esp32_replay.h`.
//
// Nota de build: em Arduino, todo `.ino` da pasta é concatenado num único
// arquivo. Por isso o comum mora em `.h` e o sketch é UM `.ino` só — dois
// `.ino` na mesma pasta dão erro de redefinição de `setup()`, `loop()` e de
// cada função repetida.

#ifndef REPLAY_COMUM_H
#define REPLAY_COMUM_H

#include "esp32_replay.h"
#include "config.h"

#include <WiFi.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <ctype.h>

namespace replay {

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
// Nota de compatibilidade: as variáveis abaixo são definidas SEM `inline`.
// Variável `inline` em escopo de namespace é C++17, e o core arduino-esp32 2.x
// compila com `gnu++11` — não haveria como saber disso aqui, e o erro só
// apareceria na hora de gravar. Como o Arduino junta o sketch numa única
// unidade de tradução, definir direto no header não gera símbolo duplicado.
ReplayConfig  g_config{
    .arquivoEventos       = "/eventos.jsonl",
    .hostServidor         = SERVER_IP,
    .portaServidor        = SERVER_PORT,
    .endpoint             = "",  // definido pelo transporte em `configurarPadraoDoTransporte`
    .delayEntrePacotesMs  = 500,
    .respeitarTimestamp   = false,
    // 0 = infinito, e é o padrão para OS DOIS transportes.
    //
    // A variante WebSocket usava 5. Com backoff exponencial, cinco tentativas
    // somam ~16 s: qualquer reinício do servidor mais longo que isso parava o
    // replay DE VEZ, e só um CMD_START manual o religava. Numa ala ninguém
    // está olhando o serial do ESP32 para perceber. O backoff já tem teto
    // (`backoffMaxMs`), então insistir para sempre significa bater uma vez por
    // minuto até o servidor voltar — não inundar a rede.
    .tentativasMax        = 0,
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

ReplayStatus  g_status{};
File          g_arquivoEventos;
ReplayCommand g_comandoPendente = ReplayCommand::CMD_NONE;
EventoReplay  g_eventoAtual{};
bool          g_eventoDisponivel = false;
bool          g_pacienteSincronizado = false;
uint8_t       g_tentativaAtual = 0;
unsigned long g_proximoEnvioMs = 0;
String        g_ultimaTsIso;

// Offset do arquivo até onde a entrega está CONFIRMADA pelo servidor.
//
// O checkpoint gravava `g_arquivoEventos.position()`, que aponta para depois da
// linha que acabou de ser LIDA — não da que foi entregue. Ao desistir de um
// evento, o estado FINALIZADO salvava esse mesmo offset e o replay seguinte
// retomava DEPOIS do evento que nunca chegou: justamente a amostra que falhou
// era a que se perdia, em silêncio.
//
// A variante WebSocket nem tinha esta variável — gravava a posição de leitura.
// Compartilhar o checkpoint corrige as duas de uma vez.
unsigned long g_offsetConfirmado = 0;

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
inline void registrarLog(const String &mensagem) { Serial.println(mensagem); }

inline void conectarWiFi() {
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
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected IP=%s\n", WiFi.localIP().toString().c_str());
  }
}

inline String montarUrl(const String &rotaBruta) {
  String base = g_config.hostServidor;
  if (!base.startsWith("http://") && !base.startsWith("https://")) base = "http://" + base;
  if (base.endsWith("/")) base.remove(base.length() - 1);
  String rota = rotaBruta;
  if (!rota.startsWith("/")) rota = "/" + rota;
  return base + ":" + String(g_config.portaServidor) + rota;
}

inline String urlEncode(const String &valor) {
  static const char HEX_CHARS[] = "0123456789ABCDEF";
  String saida; saida.reserve(valor.length());
  for (size_t i = 0; i < valor.length(); ++i) {
    const unsigned char c = static_cast<unsigned char>(valor.charAt(i));
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') { saida += (char)c; }
    else if (c == ' ') saida += "%20";
    else { saida += '%'; saida += HEX_CHARS[(c >> 4) & 0x0F]; saida += HEX_CHARS[c & 0x0F]; }
  }
  return saida;
}

inline uint32_t calcularBackoff(uint8_t tentativa) {
  unsigned long res = g_config.backoffBaseMs * (1UL << tentativa);
  if (g_config.backoffMaxMs > 0 && res > g_config.backoffMaxMs) res = g_config.backoffMaxMs;
  if (g_config.backoffWithJitter) {
    uint32_t jitter = (uint32_t)(res / 4);
    res += (uint32_t)(esp_random() % (jitter + 1));
  }
  return (uint32_t)res;
}

inline void atualizarEstado(ReplayState novo) {
  g_status.estadoAtual = novo;
  registrarLog("[ESTADO] -> " + String(static_cast<int>(novo)));
}

// ---------------------------------------------------------------------------
// Armazenamento e leitura
// ---------------------------------------------------------------------------
inline bool inicializarArmazenamento() {
  if (g_config.usarSd) return false;  // TODO: SD.begin e pinos
  return SPIFFS.begin(true);
}

inline bool abrirArquivoEventos() {
  if (!inicializarArmazenamento()) { registrarLog("[ERRO] Falha ao iniciar armazenamento"); return false; }
  if (!g_config.usarSd) g_arquivoEventos = SPIFFS.open(g_config.arquivoEventos, "r");
  if (!g_arquivoEventos) { registrarLog("[ERRO] Nao foi possivel abrir " + g_config.arquivoEventos); return false; }

  const char *ckpt = "/eventos.offset";
  if (SPIFFS.exists(ckpt)) {
    File f = SPIFFS.open(ckpt, "r");
    if (f) {
      String s = f.readString(); f.close(); s.trim();
      if (s.length() > 0) {
        unsigned long pos = (unsigned long)s.toInt();
        if (pos > 0 && g_arquivoEventos.seek(pos, SeekSet)) {
          g_offsetConfirmado = pos;
          registrarLog("[INFO] Retomando offset " + String(pos));
        }
      }
    }
  }
  return true;
}

// Grava o offset CONFIRMADO, nunca a posição corrente de leitura: um evento
// lido mas não entregue precisa ser reenviado depois de um reboot.
inline void salvarCheckpoint() {
  if (!g_arquivoEventos) return;
  File f = SPIFFS.open("/eventos.offset", "w");
  if (f) { f.print(String(g_offsetConfirmado)); f.close(); }
}

// Marca o evento corrente como resolvido (entregue ou recusado em definitivo) e
// move o ponto de retomada para depois dele.
inline void confirmarEventoAtual() {
  if (g_arquivoEventos) g_offsetConfirmado = (unsigned long)g_arquivoEventos.position();
  g_eventoDisponivel = false;
  g_tentativaAtual = 0;
  salvarCheckpoint();
}

inline bool parseIsoToEpochSeconds(const String &iso, unsigned long &out_s) {
  if (iso.length() < 19) return false;
  int year = iso.substring(0, 4).toInt();
  int month = iso.substring(5, 7).toInt();
  int day = iso.substring(8, 10).toInt();
  int hour = iso.substring(11, 13).toInt();
  int minute = iso.substring(14, 16).toInt();
  int second = iso.substring(17, 19).toInt();
  if (year <= 1970 || month < 1 || month > 12 || day < 1 || day > 31) return false;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) return false;
  auto days_from_civil = [](int y, unsigned m, unsigned d) -> long {
    y -= m <= 2; const long era = (y >= 0 ? y : y - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(y - era * 400);
    const unsigned doy = (153u * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097L + static_cast<long>(doe) - 719468L;
  };
  long days = days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
  unsigned long epoch = (unsigned long)days * 86400UL + (unsigned long)hour * 3600UL +
                        (unsigned long)minute * 60UL + (unsigned long)second;
  if (iso.length() > 19) {
    String tail = iso.substring(19); tail.trim();
    if (tail.length() > 0 && (tail.charAt(0) == '+' || tail.charAt(0) == '-') && tail.length() >= 6) {
      int sign = (tail.charAt(0) == '+') ? 1 : -1;
      int off_h = tail.substring(1, 3).toInt();
      int off_m = tail.substring(4, 6).toInt();
      if (off_h >= 0 && off_h <= 23 && off_m >= 0 && off_m <= 59) {
        long offs = (long)off_h * 3600L + (long)off_m * 60L;
        if (sign > 0) epoch -= (unsigned long)offs; else epoch += (unsigned long)offs;
      }
    }
  }
  out_s = epoch;
  return true;
}

inline bool lerProximoEvento(EventoReplay &evento) {
  while (true) {
    if (!g_arquivoEventos.available()) return false;
    String linha = g_arquivoEventos.readStringUntil('\n'); linha.trim();
    if (linha.isEmpty()) continue;
    StaticJsonDocument<1536> doc;
    if (deserializeJson(doc, linha)) { registrarLog("[WARN] JSON invalido; pulando linha"); continue; }
    doc["device_id"] = g_config.deviceId;
    doc["paciente_id"] = g_config.pacienteId;
    doc["cama_id"] = g_config.camaId;
    String out; serializeJson(doc, out);
    evento.payload = out;
    evento.seq = ++g_status.seqAtual;
    if (g_config.respeitarTimestamp) {
      String tsIso = doc["ts_utc"] | "";
      unsigned long sAtual = 0, sUlt = 0;
      if (tsIso.length() >= 19 && parseIsoToEpochSeconds(tsIso, sAtual)) {
        if (g_ultimaTsIso.length() >= 19 && parseIsoToEpochSeconds(g_ultimaTsIso, sUlt)) {
          long delta = (long)sAtual - (long)sUlt; if (delta < 0) delta = 0;
          g_proximoEnvioMs = millis() + (unsigned long)delta * 1000UL;
        } else {
          g_proximoEnvioMs = millis();
        }
        g_ultimaTsIso = tsIso;
      } else {
        g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
      }
    }
    return true;
  }
}

// Classifica a resposta do servidor. 401/403 contam como TRANSIENTE de
// propósito: token errado é erro de configuração, e o dispositivo deve
// continuar tentando para se recuperar sozinho quando alguém corrigir — pular
// as amostras nesse caso seria perda silenciosa de dado clínico.
inline ResultadoEnvio classificarResposta(int status) {
  if (status >= 200 && status < 300) return ResultadoEnvio::ACK;
  if (status < 0) return ResultadoEnvio::TRANSIENTE;   // erro de rede
  if (status >= 500) return ResultadoEnvio::TRANSIENTE;
  if (status == 408 || status == 429) return ResultadoEnvio::TRANSIENTE;
  if (status == 401 || status == 403) return ResultadoEnvio::TRANSIENTE;
  if (status >= 400) return ResultadoEnvio::PERMANENTE;
  return ResultadoEnvio::TRANSIENTE;
}

inline void resetarReplay() {
  if (g_arquivoEventos) g_arquivoEventos.close();
  g_status = ReplayStatus{};
  g_eventoAtual = EventoReplay{};
  g_eventoDisponivel = false;
  g_pacienteSincronizado = false;
  g_tentativaAtual = 0;
  g_proximoEnvioMs = 0;
  g_ultimaTsIso = "";
  g_offsetConfirmado = 0;
}

inline bool garantirPacienteConfigurado() {
  if (g_pacienteSincronizado) return true;
  if (transporteObterPaciente()) { g_pacienteSincronizado = true; return true; }
  return false;
}

}  // namespace replay

#endif  // REPLAY_COMUM_H
