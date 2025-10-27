#ifndef ESP32_REPLAY_H
#define ESP32_REPLAY_H

#include <Arduino.h>

// -------------------------------
// Estados da máquina de replay
// -------------------------------
enum class ReplayState {
  OCIOSO = 0,
  ENVIANDO,
  ESPERANDO_ACK,
  REENVIAR,
  FINALIZADO,
};

// -------------------------------
// Comandos externos (Serial/OTA)
// -------------------------------
enum class ReplayCommand {
  CMD_NONE = 0,
  CMD_START,
  CMD_STOP,
};

// -----------------------------------------
// Parâmetros de configuração do replayer
// -----------------------------------------
struct ReplayConfig {
  // Arquivo
  String arquivoEventos;         // Caminho dentro do SD ou SPIFFS (ex.: "/eventos.jsonl")

  // Destino (backend)
  String hostServidor;           // Ex.: "http://192.168.0.10" (sem barra ao final)
  uint16_t portaServidor;        // Ex.: 8000
  String endpoint;               // Ex.: "/api/eventos"

  // Ritmo
  uint32_t delayEntrePacotesMs;  // Se respeitarTimestamp=false, usa este delay fixo
  bool respeitarTimestamp;       // true -> usa delta entre ts_utc de cada linha

  // Retry
  uint8_t  tentativasMax;        // Nº máximo de retries por pacote
  uint32_t backoffBaseMs;        // Backoff inicial (exponencial)
  uint32_t backoffMaxMs;         // Teto para backoff (ms)
  bool     backoffWithJitter;    // aplicar jitter ao backoff

  // Armazenamento
  bool usarSd;                   // true -> SD, false -> SPIFFS

  // Rede
  String ssid;                   // Wi-Fi SSID
  String senha;                  // Wi-Fi password

  // Identidades fixas (1 paciente)
  String deviceId;
  String pacienteId;
  String camaId;
  String perfilPaciente;
  // Enviar o arquivo inteiro como multipart/form-data para /api/grade
  bool enviarComoArquivo;
};

// -------------------------------
// Status de execução atual
// -------------------------------
struct ReplayStatus {
  ReplayState estadoAtual{ReplayState::OCIOSO};
  uint32_t seqAtual{0};            // Sequência de mensagens
  uint32_t totalEnviados{0};       // Contagem de ACKs (2xx)
  uint32_t totalFalhas{0};         // Contagem de falhas
  uint32_t ultimaRespostaMs{0};    // Timestamp do último ACK
  bool replayAtivo{false};
};

// -------------------------------
// Estrutura do evento em envio
// -------------------------------
struct EventoReplay {
  String payload;   // Linha JSON (NDJSON) preparada para envio
  uint32_t seq;     // Número de sequência (X-Seq)
};

// -------------------------------
// API pública do módulo
// -------------------------------
void configurarReplay(const ReplayConfig &cfg);
void iniciarReplay();
void interromperReplay();
void processarReplay();
void tratarComandoSerial();
void tratarComandoOta(const String &comando);

#endif  // ESP32_REPLAY_H
