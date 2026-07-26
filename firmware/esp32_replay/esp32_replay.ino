// ESP32 NDJSON replayer — sketch único, transporte escolhido em tempo de
// compilação.
//
// Antes eram dois sketches completos na MESMA pasta (`esp32_replay.ino` e
// `esp32_replay_websocket.ino`), com ~90% de código repetido. Isso não
// compilava: o Arduino concatena todos os `.ino` da pasta num único arquivo, e
// os dois definiam `setup()`, `loop()` e mais onze funções — erro de
// redefinição em cada uma. Quem abrisse o sketch recebia uma parede de erros.
//
// Agora: um `.ino`, a lógica comum em `replay_comum.h` e o transporte em
// `transporte_http.h` / `transporte_ws.h`. Escolha em `config.h`:
//
//     #define USAR_WEBSOCKET   // comente para usar HTTP
//
// Ver `LEIA-ME.md`.

#include "esp32_replay.h"
#include "config.h"
#include "replay_comum.h"

#if defined(USAR_WEBSOCKET)
  #include "transporte_ws.h"
#else
  #include "transporte_http.h"
#endif

using namespace replay;

// A interface declarada em esp32_replay.h aponta para a implementação do
// transporte compilado. Uma indireção fina, para a máquina de estados abaixo
// não saber qual dos dois está em uso.
bool transporteIniciar()                              { return transporteIniciarImpl(); }
void transporteManter()                               { transporteManterImpl(); }
bool transporteObterPaciente()                        { return transporteObterPacienteImpl(); }
bool transporteEnviar(const EventoReplay &evento)     { return transporteEnviarImpl(evento); }
ResultadoEnvio transporteDesfecho()                   { return transporteDesfechoImpl(); }

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------
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

void tratarComandoOta(const String &comando) {
  if (comando.equalsIgnoreCase("CMD_START")) g_comandoPendente = ReplayCommand::CMD_START;
  else if (comando.equalsIgnoreCase("CMD_STOP")) g_comandoPendente = ReplayCommand::CMD_STOP;
  else registrarLog("[WARN] OTA comando desconhecido: " + comando);
}

// ---------------------------------------------------------------------------
// Máquina de estados (uma só, para os dois transportes)
// ---------------------------------------------------------------------------
void processarReplay() {
  transporteManter();

  tratarComandoSerial();
  if (g_comandoPendente == ReplayCommand::CMD_START) { iniciarReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  else if (g_comandoPendente == ReplayCommand::CMD_STOP) { interromperReplay(); g_comandoPendente = ReplayCommand::CMD_NONE; }
  if (!g_status.replayAtivo) return;

  switch (g_status.estadoAtual) {
    case ReplayState::OCIOSO: {
      // O WebSocket precisa de algumas voltas do loop até autenticar; o HTTP
      // responde na primeira. Nos dois casos, sair daqui e tentar de novo é
      // melhor que bloquear com `delay()`.
      if (!transporteIniciar()) return;
      if (!garantirPacienteConfigurado()) { registrarLog("[ERRO] Tentando sincronizar paciente..."); return; }
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
      if (!g_config.respeitarTimestamp && g_proximoEnvioMs == 0) {
        g_proximoEnvioMs = millis() + g_config.delayEntrePacotesMs;
      }
      if ((long)g_proximoEnvioMs - (long)millis() > 0) return;
      g_proximoEnvioMs = 0;

      if (!transporteEnviar(g_eventoAtual)) { atualizarEstado(ReplayState::REENVIAR); break; }
      atualizarEstado(ReplayState::ESPERANDO_ACK);
      break;
    }

    case ReplayState::ESPERANDO_ACK: {
      // Sobre HTTP o desfecho já está pronto; sobre WebSocket, espera-se o
      // callback (com o timeout de `transporteDesfecho`). O checkpoint só anda
      // com ACK ou recusa definitiva — nunca com "mandei".
      switch (transporteDesfecho()) {
        case ResultadoEnvio::PENDENTE:
          return;

        case ResultadoEnvio::ACK:
          confirmarEventoAtual();
          atualizarEstado(ReplayState::ENVIANDO);
          break;

        case ResultadoEnvio::PERMANENTE:
          // O servidor nunca vai aceitar este conteúdo (ex.: linha malformada
          // -> 422). Insistir travaria toda a fila atrás dele, então pula — mas
          // contabiliza, para o descarte não passar despercebido.
          g_status.totalDescartados++;
          registrarLog("[DESCARTE] seq=" + String(g_eventoAtual.seq) + " recusado em definitivo; seguindo");
          confirmarEventoAtual();
          atualizarEstado(ReplayState::ENVIANDO);
          break;

        case ResultadoEnvio::TRANSIENTE:
          atualizarEstado(ReplayState::REENVIAR);
          break;
      }
      break;
    }

    case ReplayState::REENVIAR: {
      // `tentativasMax == 0` = tentar indefinidamente, que é o padrão. O backoff
      // já tem teto (`backoffMaxMs`), então o dispositivo passa a bater no
      // servidor uma vez por minuto até ele voltar, em vez de desistir.
      //
      // `g_tentativaAtual` conta as tentativas já feitas menos a primeira, então
      // +1 é o total — mesma semântica de scripts/envio_resiliente.py.
      if (g_config.tentativasMax > 0 && (g_tentativaAtual + 1) >= g_config.tentativasMax) {
        registrarLog("[ERRO] Limite de tentativas atingido; evento preservado para a proxima execucao");
        atualizarEstado(ReplayState::FINALIZADO);
        break;
      }
      const uint32_t aguardar = calcularBackoff(g_tentativaAtual);
      registrarLog("[INFO] Reenviando em " + String(aguardar) + " ms (tentativa " + String(g_tentativaAtual + 1) + ")");
      g_proximoEnvioMs = millis() + aguardar;
      g_tentativaAtual++;
      // Voltar para ENVIANDO é o que faz o backoff ser DE FATO esperado: é lá
      // que `g_proximoEnvioMs` é conferido. A variante WebSocket ficava parada
      // em REENVIAR e recalculava o backoff a cada volta do loop, queimando
      // todas as tentativas em poucas dezenas de milissegundos — a primeira
      // oscilação de rede encerrava o replay.
      atualizarEstado(ReplayState::ENVIANDO);
      return;
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
#if defined(USAR_WEBSOCKET)
  registrarLog("[SETUP] ESP32 Replay (WebSocket) pronto");
#else
  registrarLog("[SETUP] ESP32 Replay (HTTP) pronto");
#endif
  configurarPadraoDoTransporte();
  uint32_t seed = ESP.getEfuseMac();
  randomSeed((unsigned long)(seed ^ millis()));
  conectarWiFi();
}

void loop() {
  processarReplay();
  delay(10);
}
