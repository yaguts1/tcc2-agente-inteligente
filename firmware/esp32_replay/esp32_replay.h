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
// Desfecho de um POST de evento
// -------------------------------
// A distinção importa: repetir para sempre um evento que o servidor NUNCA vai
// aceitar (linha malformada -> 422) trava a fila inteira atrás dele, e desistir
// de um evento que falhou por queda de rede perde dado de sensor. São reações
// opostas, e antes as duas situações eram o mesmo `false`.
enum class ResultadoEnvio {
  ACK = 0,      // 2xx — entregue
  TRANSIENTE,   // rede caiu, 5xx, 408, 429 — tentar de novo
  PERMANENTE,   // demais 4xx — o servidor recusa este conteúdo, insistir não muda
  // O envio saiu e a resposta ainda não chegou.
  //
  // Existe por causa do WebSocket: `sendTXT()` retorna assim que entrega o
  // quadro ao socket, e o ACK do servidor chega depois, por callback. Sem este
  // estado o firmware trataria "mandei" como "chegou" — foi o que a variante
  // WebSocket fazia, contando ACK e avançando o checkpoint no envio. Sobre
  // HTTP nunca aparece: a resposta vem no retorno do POST.
  PENDENTE,
};

// -------------------------------
// Comandos externos (Serial/OTA)
// -------------------------------
enum class ReplayCommand {
  CMD_NONE = 0,
  CMD_START,
  CMD_STOP,
  // Apaga o checkpoint do SPIFFS: o próximo CMD_START recomeça do início do
  // arquivo. Sem isto não há como repetir um replay — depois do primeiro
  // término o offset gravado aponta para o EOF e o dispositivo fica mudo.
  CMD_RESET,
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
  uint8_t  tentativasMax;        // TOTAL de tentativas por pacote (contando a
                                 // primeira); 0 = infinito
                                 // (recomendado). Com um limite, uma indisponi-
                                 // bilidade do servidor maior que a soma dos
                                 // backoffs para o replay de vez, e so um
                                 // CMD_START manual o traz de volta.
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
  uint32_t totalDescartados{0};    // Eventos recusados em definitivo (4xx)
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

// ---------------------------------------------------------------------------
// Interface de transporte
// ---------------------------------------------------------------------------
// Tudo que difere entre enviar por HTTP e por WebSocket cabe nestas cinco
// funções. O resto — leitura do arquivo, checkpoint, backoff, máquina de
// estados — é igual e passou a existir uma vez só, em `replay_comum.h`.
//
// Antes eram dois sketches inteiros, `.ino` lado a lado, com ~90% de código
// repetido. As duas cópias derivaram: correções feitas numa não chegaram na
// outra, e a que o LEIA-ME recomendava era a que tinha ficado para trás.
// Implementação em `transporte_http.h` / `transporte_ws.h`.

// Prepara o canal (HTTP: nada a fazer; WS: abre a conexão e autentica).
// `false` = ainda não dá para enviar, tentar de novo no próximo ciclo.
bool transporteIniciar();

// Chamado a cada volta do loop, para o transporte cuidar do que precisa
// (o WebSocket precisa ceder tempo à sua própria máquina de estados).
void transporteManter();

// Resolve `paciente_id` a partir da cama, consultando o backend.
bool transporteObterPaciente();

// Coloca o evento no ar. `false` = nem foi possível tentar.
bool transporteEnviar(const EventoReplay &evento);

// Desfecho do último envio. `PENDENTE` enquanto a resposta não chegou —
// só o WebSocket devolve isso; o HTTP já sabe no retorno do POST.
ResultadoEnvio transporteDesfecho();

#endif  // ESP32_REPLAY_H
