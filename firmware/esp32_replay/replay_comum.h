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

// Prefixo da API (ver config.example.h). Compatibilidade: um `config.h` que
// nao o define continua compilando e falando `/api`, como sempre falou.
#ifndef API_PREFIXO
#define API_PREFIXO ""
#endif

// Prefixo de MONTAGEM da aplicacao, espelhando o `APP_PREFIX` do servidor.
//
// Sao coisas diferentes e ficam em posicoes diferentes da URL:
//
//     APP_PREFIXO   /api   API_PREFIXO   /eventos
//        /TCC       /api      /v1        /eventos
//
// O firmware nao tinha o primeiro, entao montava sempre `/api/...` — e o
// docker-compose deste projeto sobe a aplicacao com `APP_PREFIX=/TCC`. Ou seja:
// o dispositivo NAO CONSEGUIA falar com a implantacao real, e todo POST voltava
// 404. Passou despercebido porque os testes de hardware sempre rodaram contra
// um uvicorn avulso, com prefixo vazio.
#ifndef APP_PREFIXO
#define APP_PREFIXO ""
#endif

#include "esp32_replay.h"
#include "config.h"
#include "logica_pura.h"

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

// Caminho de uma rota da API, com os dois prefixos na ordem certa.
//
// Existe uma vez so porque estava escrito a mao em quatro lugares — e as quatro
// copias ja tinham divergido: `transporteObterPacienteImpl` do WebSocket
// montava "/api/pacientes/..." SEM o API_PREFIXO que a versao HTTP aplicava.
// Fixar a versao da API funcionava por HTTP e nao funcionava por WebSocket, em
// silencio, ate o servidor mudar de contrato.
inline String rotaApi(const String &sufixo) {
  return String(APP_PREFIXO) + "/api" + API_PREFIXO + sufixo;
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

// Delega para `logica_pura.h`, que é onde a regra está testada. Aqui fica só
// a parte que depende do hardware: a fonte de aleatoriedade.
inline uint32_t calcularBackoff(uint8_t tentativa) {
  return pura::calcularBackoffMs(g_config.backoffBaseMs, g_config.backoffMaxMs,
                                 tentativa, g_config.backoffWithJitter,
                                 (uint32_t)esp_random());
}

inline void atualizarEstado(ReplayState novo) {
  g_status.estadoAtual = novo;
  registrarLog("[ESTADO] -> " + String(static_cast<int>(novo)));
}

// ---------------------------------------------------------------------------
// Armazenamento e leitura
// ---------------------------------------------------------------------------
// Caminho do checkpoint. Estava escrito à mão em dois lugares (aqui e em
// `salvarCheckpoint`); com um terceiro ponto de uso — `limparCheckpoint` — a
// chance de os literais divergirem deixou de ser aceitável.
constexpr const char *CAMINHO_CHECKPOINT = "/eventos.offset";

inline bool inicializarArmazenamento() {
  if (g_config.usarSd) return false;  // TODO: SD.begin e pinos
  return SPIFFS.begin(true);
}

inline bool abrirArquivoEventos() {
  if (!inicializarArmazenamento()) { registrarLog("[ERRO] Falha ao iniciar armazenamento"); return false; }
  if (!g_config.usarSd) g_arquivoEventos = SPIFFS.open(g_config.arquivoEventos, "r");
  if (!g_arquivoEventos) { registrarLog("[ERRO] Nao foi possivel abrir " + g_config.arquivoEventos); return false; }

  const char *ckpt = CAMINHO_CHECKPOINT;
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
  File f = SPIFFS.open(CAMINHO_CHECKPOINT, "w");
  if (!f) { registrarLog("[ERRO] Nao consegui gravar o checkpoint"); return; }
  f.print(String(g_offsetConfirmado));
  f.close();
  // O ponto de retomada agora esta NO DISCO — e essa e a unica linha do log que
  // diz isso.
  //
  // "[ACK] seq=N" nao serve para saber: sobre WebSocket quem a imprime e o
  // callback do socket, no instante em que o quadro chega, e a gravacao so
  // acontece uma volta de loop depois, quando a maquina de estados trata o
  // desfecho. Quem corta a energia entre as duas pega o SPIFFS no meio da
  // escrita, e o arquivo nao sobrevive.
  //
  // Sem este log, a unica forma de esperar a gravacao assentar era dormir um
  // tempo arbitrario e torcer — foi o que deixou o teste de reboot instavel.
  registrarLog("[CKPT] offset=" + String(g_offsetConfirmado));
}

// Apaga o ponto de retomada, para o próximo CMD_START recomeçar do início do
// arquivo.
//
// Por que existe: `resetarReplay()` zera a RAM, mas o checkpoint vive no
// SPIFFS. Ao chegar em FINALIZADO o offset gravado aponta para o fim do
// arquivo, então um segundo CMD_START reabria, dava `seek` para o EOF e não
// enviava NADA — sem erro, sem log, sem evento. Numa bancada isso parece o
// dispositivo travado; num teste automatizado, só a primeira execução passa e
// as seguintes falham sem explicação.
//
// Deliberadamente NÃO é chamado por `iniciarReplay()`: retomar de onde parou é
// o comportamento correto depois de um reboot ou de uma queda de rede, e é
// justamente o que os testes de resiliência verificam. Zerar é uma decisão de
// quem opera, então é um comando à parte.
inline void limparCheckpoint() {
  if (!inicializarArmazenamento()) { registrarLog("[ERRO] Falha ao iniciar armazenamento"); return; }
  if (SPIFFS.exists(CAMINHO_CHECKPOINT)) SPIFFS.remove(CAMINHO_CHECKPOINT);
  g_offsetConfirmado = 0;
  registrarLog("[INFO] Checkpoint zerado");
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
  // A regra vive em `logica_pura.h` (testada em firmware/test); aqui só se
  // converte o String do Arduino para o que ela recebe.
  return pura::epochDeIso(iso.c_str(), (size_t)iso.length(), out_s);
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
  switch (pura::classificarStatusHttp(status)) {
    case pura::Desfecho::ACK:        return ResultadoEnvio::ACK;
    case pura::Desfecho::PERMANENTE: return ResultadoEnvio::PERMANENTE;
    default:                         return ResultadoEnvio::TRANSIENTE;
  }
}

// Zera a contabilidade. Só uma execução NOVA faz isso — ver `resetarReplay`.
inline void zerarContadores() {
  g_status.totalEnviados = 0;
  g_status.totalFalhas = 0;
  g_status.totalDescartados = 0;
  g_status.ultimaRespostaMs = 0;
}

inline void resetarReplay() {
  if (g_arquivoEventos) g_arquivoEventos.close();
  // Os totais sobrevivem a isto de propósito.
  //
  // `g_status = ReplayStatus{}` zerava estado de execução e contabilidade
  // juntos, e o estado FINALIZADO chama esta função — então os totais eram
  // destruídos no exato instante em que o replay terminava. CMD_STATUS depois
  // de uma execução respondia `enviados=0 descartados=0`, que é indistinguível
  // de "não fiz nada" e de "descartei tudo em silêncio". O aparelho esquecia o
  // que tinha acabado de fazer, que é justamente quando alguém pergunta.
  const uint32_t enviados    = g_status.totalEnviados;
  const uint32_t falhas      = g_status.totalFalhas;
  const uint32_t descartados = g_status.totalDescartados;
  const uint32_t ultima      = g_status.ultimaRespostaMs;
  g_status = ReplayStatus{};
  g_status.totalEnviados    = enviados;
  g_status.totalFalhas      = falhas;
  g_status.totalDescartados = descartados;
  g_status.ultimaRespostaMs = ultima;
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
