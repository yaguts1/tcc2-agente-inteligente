// Testes da lógica do firmware que não depende de hardware.
//
// O firmware era a única parte do sistema sem teste algum. Estes rodam na
// máquina de quem desenvolve, sem ESP32 na mesa, e cobrem justamente onde há
// decisão: quando desistir de um evento, quanto esperar antes de tentar de
// novo, como ler um timestamp.
//
//   pio test -d firmware -e nativo

#include <unity.h>
#include "../../esp32_replay/logica_pura.h"

using replay::pura::Desfecho;
using replay::pura::calcularBackoffMs;
using replay::pura::classificarErroWebSocket;
using replay::pura::classificarStatusHttp;
using replay::pura::epochDeIso;
using replay::pura::esgotouTentativas;

void setUp(void) {}
void tearDown(void) {}

// ---------------------------------------------------------------------------
// Classificação da resposta HTTP
// ---------------------------------------------------------------------------
void test_2xx_e_entrega(void) {
    TEST_ASSERT_TRUE(classificarStatusHttp(200) == Desfecho::ACK);
    TEST_ASSERT_TRUE(classificarStatusHttp(204) == Desfecho::ACK);
}

void test_erro_de_rede_e_temporario(void) {
    // HTTPClient devolve negativo quando nem chegou a falar com o servidor.
    TEST_ASSERT_TRUE(classificarStatusHttp(-1) == Desfecho::TRANSIENTE);
}

void test_5xx_e_temporario(void) {
    TEST_ASSERT_TRUE(classificarStatusHttp(500) == Desfecho::TRANSIENTE);
    TEST_ASSERT_TRUE(classificarStatusHttp(503) == Desfecho::TRANSIENTE);
}

void test_401_e_403_insistem(void) {
    // Token errado é erro de CONFIGURAÇÃO. Desistir aqui descartaria amostra
    // clínica por engano de operação; insistindo, o dispositivo se recupera
    // sozinho quando alguém corrigir o token.
    TEST_ASSERT_TRUE(classificarStatusHttp(401) == Desfecho::TRANSIENTE);
    TEST_ASSERT_TRUE(classificarStatusHttp(403) == Desfecho::TRANSIENTE);
}

void test_422_e_definitivo(void) {
    // Linha malformada: insistir travaria a fila inteira atrás dela.
    TEST_ASSERT_TRUE(classificarStatusHttp(422) == Desfecho::PERMANENTE);
    TEST_ASSERT_TRUE(classificarStatusHttp(400) == Desfecho::PERMANENTE);
}

void test_429_insiste(void) {
    // "Devagar", e não "nunca".
    TEST_ASSERT_TRUE(classificarStatusHttp(429) == Desfecho::TRANSIENTE);
}

// ---------------------------------------------------------------------------
// Classificação do erro no WebSocket
// ---------------------------------------------------------------------------
void test_falha_de_persistencia_insiste(void) {
    TEST_ASSERT_TRUE(classificarErroWebSocket("persist_failed") == Desfecho::TRANSIENTE);
    TEST_ASSERT_TRUE(classificarErroWebSocket("processing_failed") == Desfecho::TRANSIENTE);
}

void test_token_invalido_insiste(void) {
    TEST_ASSERT_TRUE(classificarErroWebSocket("invalid_device_token") == Desfecho::TRANSIENTE);
}

void test_conteudo_recusado_nao_insiste(void) {
    TEST_ASSERT_TRUE(classificarErroWebSocket("Invalid JSON") == Desfecho::PERMANENTE);
}

// ---------------------------------------------------------------------------
// Backoff
// ---------------------------------------------------------------------------
void test_backoff_cresce_exponencialmente(void) {
    TEST_ASSERT_EQUAL_UINT32(500,  calcularBackoffMs(500, 60000, 0, false, 0));
    TEST_ASSERT_EQUAL_UINT32(1000, calcularBackoffMs(500, 60000, 1, false, 0));
    TEST_ASSERT_EQUAL_UINT32(2000, calcularBackoffMs(500, 60000, 2, false, 0));
}

void test_backoff_respeita_o_teto(void) {
    // O teto é o que torna "tentar para sempre" viável: o dispositivo passa a
    // bater uma vez por minuto, não a inundar a rede.
    TEST_ASSERT_EQUAL_UINT32(60000, calcularBackoffMs(500, 60000, 20, false, 0));
}

void test_backoff_nao_estoura_com_muitas_tentativas(void) {
    // Com tentativasMax = 0 (o padrão) a contagem cresce sem limite durante uma
    // indisponibilidade longa. Deslocar 1UL por 32 ou mais é comportamento
    // indefinido — o cálculo satura antes disso.
    TEST_ASSERT_EQUAL_UINT32(60000, calcularBackoffMs(500, 60000, 200, false, 0));
}

void test_jitter_fica_dentro_de_um_quarto(void) {
    // Jitter existe para dessincronizar dispositivos que caíram juntos; se
    // passasse do previsto, o atraso deixaria de ser previsível.
    const uint32_t base = calcularBackoffMs(1000, 60000, 0, false, 0);
    const uint32_t com  = calcularBackoffMs(1000, 60000, 0, true, 0xFFFFFFFFu);
    TEST_ASSERT_TRUE(com >= base);
    TEST_ASSERT_TRUE(com <= base + base / 4);
}

// ---------------------------------------------------------------------------
// Limite de tentativas
// ---------------------------------------------------------------------------
void test_zero_significa_infinito(void) {
    // O padrão. Antes eram 5 tentativas (~16 s de backoff somado): qualquer
    // reinício de servidor mais longo parava o replay DE VEZ, e só um
    // CMD_START manual o religava.
    TEST_ASSERT_FALSE(esgotouTentativas(0, 0));
    TEST_ASSERT_FALSE(esgotouTentativas(0, 250));
}

void test_limite_conta_a_primeira_tentativa(void) {
    // jaFeitas são as anteriores à atual, então com máximo 3: 0 e 1 seguem,
    // 2 encerra (é a terceira).
    TEST_ASSERT_FALSE(esgotouTentativas(3, 0));
    TEST_ASSERT_FALSE(esgotouTentativas(3, 1));
    TEST_ASSERT_TRUE(esgotouTentativas(3, 2));
}

// ---------------------------------------------------------------------------
// Timestamp ISO
// ---------------------------------------------------------------------------
void test_iso_utc(void) {
    unsigned long s = 0;
    TEST_ASSERT_TRUE(epochDeIso("2026-07-26T12:00:00Z", 20, s));
    TEST_ASSERT_EQUAL_UINT32(1785067200UL, s);
}

void test_iso_com_fuso_negativo_avanca(void) {
    // 12:00 em -03:00 é 15:00 UTC. Errar o sinal deslocaria a amostra em horas
    // — é a mesma classe de defeito de fuso que já custou correção no backend.
    unsigned long utc = 0, brasilia = 0;
    TEST_ASSERT_TRUE(epochDeIso("2026-07-26T15:00:00Z", 20, utc));
    TEST_ASSERT_TRUE(epochDeIso("2026-07-26T12:00:00-03:00", 25, brasilia));
    TEST_ASSERT_EQUAL_UINT32(utc, brasilia);
}

void test_iso_com_fuso_positivo_recua(void) {
    unsigned long utc = 0, tokio = 0;
    TEST_ASSERT_TRUE(epochDeIso("2026-07-26T03:00:00Z", 20, utc));
    TEST_ASSERT_TRUE(epochDeIso("2026-07-26T12:00:00+09:00", 25, tokio));
    TEST_ASSERT_EQUAL_UINT32(utc, tokio);
}

void test_iso_curto_demais_e_recusado(void) {
    unsigned long s = 0;
    TEST_ASSERT_FALSE(epochDeIso("2026-07-26", 10, s));
}

void test_iso_com_letra_no_lugar_de_digito_e_recusado(void) {
    // A versão anterior usava toInt(), que devolve 0 em texto inválido: uma
    // linha corrompida virava um timestamp plausível em vez de ser rejeitada.
    unsigned long s = 0;
    TEST_ASSERT_FALSE(epochDeIso("2026-07-26T1X:00:00Z", 20, s));
}

void test_iso_com_mes_invalido_e_recusado(void) {
    unsigned long s = 0;
    TEST_ASSERT_FALSE(epochDeIso("2026-13-26T12:00:00Z", 20, s));
}

void test_ordem_temporal_e_preservada(void) {
    // O intervalo entre amostras vem da diferença entre dois timestamps; se a
    // ordem se invertesse, o replay esperaria tempo negativo.
    unsigned long antes = 0, depois = 0;
    epochDeIso("2026-07-26T12:00:00Z", 20, antes);
    epochDeIso("2026-07-26T12:05:00Z", 20, depois);
    TEST_ASSERT_EQUAL_UINT32(300UL, depois - antes);
}

// ---------------------------------------------------------------------------
int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_2xx_e_entrega);
    RUN_TEST(test_erro_de_rede_e_temporario);
    RUN_TEST(test_5xx_e_temporario);
    RUN_TEST(test_401_e_403_insistem);
    RUN_TEST(test_422_e_definitivo);
    RUN_TEST(test_429_insiste);
    RUN_TEST(test_falha_de_persistencia_insiste);
    RUN_TEST(test_token_invalido_insiste);
    RUN_TEST(test_conteudo_recusado_nao_insiste);
    RUN_TEST(test_backoff_cresce_exponencialmente);
    RUN_TEST(test_backoff_respeita_o_teto);
    RUN_TEST(test_backoff_nao_estoura_com_muitas_tentativas);
    RUN_TEST(test_jitter_fica_dentro_de_um_quarto);
    RUN_TEST(test_zero_significa_infinito);
    RUN_TEST(test_limite_conta_a_primeira_tentativa);
    RUN_TEST(test_iso_utc);
    RUN_TEST(test_iso_com_fuso_negativo_avanca);
    RUN_TEST(test_iso_com_fuso_positivo_recua);
    RUN_TEST(test_iso_curto_demais_e_recusado);
    RUN_TEST(test_iso_com_letra_no_lugar_de_digito_e_recusado);
    RUN_TEST(test_iso_com_mes_invalido_e_recusado);
    RUN_TEST(test_ordem_temporal_e_preservada);
    return UNITY_END();
}
