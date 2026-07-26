// Regras que não dependem de Arduino, rede nem sistema de arquivos.
//
// Estão separadas por um motivo prático: é a parte com decisão de negócio —
// quando desistir de um evento, quanto esperar antes de tentar de novo, como
// interpretar um timestamp — e era justamente a parte sem nenhum teste. Aqui
// elas rodam na máquina de quem desenvolve (`pio test -d firmware -e nativo`),
// sem precisar de um ESP32 na mesa.
//
// Nada aqui pode incluir <Arduino.h>: é essa restrição que mantém o arquivo
// testável.

#ifndef LOGICA_PURA_H
#define LOGICA_PURA_H

#include <stdint.h>
#include <stddef.h>

namespace replay {
namespace pura {

// Desfecho de um envio, sem depender do enum do Arduino (o header principal o
// converte). Mantido em espelho com `ResultadoEnvio` de esp32_replay.h.
enum class Desfecho {
  ACK = 0,
  TRANSIENTE,
  PERMANENTE,
  PENDENTE,
};

// Classifica a resposta HTTP do servidor.
//
// 401/403 contam como TRANSIENTE de propósito: token errado é erro de
// configuração, e o dispositivo deve continuar tentando para se recuperar
// sozinho quando alguém corrigir — pular as amostras nesse caso seria perda
// silenciosa de dado clínico.
inline Desfecho classificarStatusHttp(int status) {
  if (status >= 200 && status < 300) return Desfecho::ACK;
  if (status < 0) return Desfecho::TRANSIENTE;   // erro de rede do cliente
  if (status >= 500) return Desfecho::TRANSIENTE;
  if (status == 408 || status == 429) return Desfecho::TRANSIENTE;
  if (status == 401 || status == 403) return Desfecho::TRANSIENTE;
  if (status >= 400) return Desfecho::PERMANENTE;
  return Desfecho::TRANSIENTE;
}

// Classifica o código de erro que o WebSocket devolve.
//
// O backend responde com código estável (ver `websocket_eventos` em
// interface/routers/ingestao.py) justamente para o firmware poder decidir a
// partir dele.
inline Desfecho classificarErroWebSocket(const char *codigo) {
  if (codigo == nullptr) return Desfecho::TRANSIENTE;
  auto igual = [](const char *a, const char *b) {
    size_t i = 0;
    while (a[i] && b[i] && a[i] == b[i]) ++i;
    return a[i] == '\0' && b[i] == '\0';
  };
  // Falhas do lado do servidor, ou configuração a corrigir: insistir permite
  // que o dispositivo se recupere sozinho.
  if (igual(codigo, "persist_failed") ||
      igual(codigo, "processing_failed") ||
      igual(codigo, "invalid_device_token")) {
    return Desfecho::TRANSIENTE;
  }
  // Conteúdo que o servidor nunca vai aceitar.
  return Desfecho::PERMANENTE;
}

// Espera antes da próxima tentativa, em ms.
//
// `aleatorio` entra por parâmetro (e não com `esp_random()` dentro) para o
// resultado ser determinístico em teste: com jitter embutido não daria para
// afirmar nada sobre o valor.
inline uint32_t calcularBackoffMs(uint32_t baseMs,
                                  uint32_t tetoMs,
                                  uint8_t tentativa,
                                  bool comJitter,
                                  uint32_t aleatorio) {
  // Deslocamento saturado: `1UL << 32` é comportamento indefinido, e uma
  // indisponibilidade longa chega a essa contagem quando `tentativasMax` é
  // infinito — que é o padrão.
  uint64_t fator = (tentativa >= 31) ? (1ULL << 31) : (1ULL << tentativa);
  uint64_t res = (uint64_t)baseMs * fator;
  if (tetoMs > 0 && res > tetoMs) res = tetoMs;
  if (comJitter) {
    uint32_t jitter = (uint32_t)(res / 4);
    res += (jitter == 0) ? 0 : (aleatorio % (jitter + 1));
  }
  return (uint32_t)res;
}

// Já se esgotaram as tentativas? `maximo == 0` = tentar indefinidamente.
//
// `jaFeitas` conta as tentativas anteriores à atual, então `+1` é o total —
// mesma semântica de scripts/envio_resiliente.py.
inline bool esgotouTentativas(uint8_t maximo, uint8_t jaFeitas) {
  if (maximo == 0) return false;
  return (uint16_t)(jaFeitas + 1) >= (uint16_t)maximo;
}

// Converte "YYYY-MM-DDTHH:MM:SS[Z|±HH:MM]" em segundos desde a epoch.
//
// Recebe `const char*` em vez de `String` para não depender do Arduino. O
// deslocamento de fuso é aplicado: um timestamp com `-03:00` representa um
// instante três horas À FRENTE do mesmo horário em UTC.
inline bool epochDeIso(const char *iso, size_t tamanho, unsigned long &saida) {
  if (iso == nullptr || tamanho < 19) return false;
  auto numero = [&](size_t inicio, size_t digitos) -> int {
    int v = 0;
    for (size_t i = 0; i < digitos; ++i) {
      const char c = iso[inicio + i];
      if (c < '0' || c > '9') return -1;
      v = v * 10 + (c - '0');
    }
    return v;
  };
  const int ano = numero(0, 4);
  const int mes = numero(5, 2);
  const int dia = numero(8, 2);
  const int hora = numero(11, 2);
  const int minuto = numero(14, 2);
  const int segundo = numero(17, 2);
  if (ano <= 1970 || mes < 1 || mes > 12 || dia < 1 || dia > 31) return false;
  if (hora < 0 || hora > 23 || minuto < 0 || minuto > 59 || segundo < 0 || segundo > 59) return false;

  // Algoritmo de Howard Hinnant (days_from_civil).
  int y = ano;
  const unsigned m = (unsigned)mes;
  const unsigned d = (unsigned)dia;
  y -= m <= 2;
  const long era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = (unsigned)(y - era * 400);
  const unsigned doy = (153u * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  const long dias = era * 146097L + (long)doe - 719468L;

  unsigned long epoch = (unsigned long)dias * 86400UL +
                        (unsigned long)hora * 3600UL +
                        (unsigned long)minuto * 60UL +
                        (unsigned long)segundo;

  if (tamanho > 19) {
    const char sinal = iso[19];
    if ((sinal == '+' || sinal == '-') && tamanho >= 25) {
      const int oh = numero(20, 2);
      const int om = numero(23, 2);
      if (oh >= 0 && oh <= 23 && om >= 0 && om <= 59) {
        const unsigned long deslocamento = (unsigned long)oh * 3600UL + (unsigned long)om * 60UL;
        if (sinal == '+') epoch -= deslocamento; else epoch += deslocamento;
      }
    }
  }
  saida = epoch;
  return true;
}

}  // namespace pura
}  // namespace replay

#endif  // LOGICA_PURA_H
