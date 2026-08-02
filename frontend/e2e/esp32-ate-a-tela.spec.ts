import { expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { esperarQuadro, leito, linhaDoPaciente, observarWebSocketDeAlertas } from './bancada';

const executar = promisify(execFile);
const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PORTA_SERIAL = process.env.UPP_ESP32_PORT;

/**
 * A jornada inteira, sem nenhuma simulação em ponta nenhuma.
 *
 * Sensor físico → Wi-Fi → WebSocket → ingestão → filtro → motor de alertas →
 * broadcast → WebSocket → React → DOM.
 *
 * Cada trecho já tinha teste. Nenhum teste tinha o trecho inteiro:
 *
 *   - `tests/test_protocolo_firmware.py` reimplementa o dispositivo em Python;
 *   - `tests/test_e2e_esp32.py` usa o aparelho de verdade, mas termina no banco;
 *   - `e2e/alerta-em-tempo-real.spec.ts` chega até a tela, mas as amostras saem
 *     de um `POST` do próprio teste.
 *
 * Aqui a amostra nasce num ESP32 lendo o SPIFFS e termina como uma linha que
 * alguém precisa ler para virar um paciente. A costura entre os dois harnesses
 * deixa de existir.
 *
 * QUEM DIRIGE O QUÊ
 * -----------------
 * O Playwright dirige o navegador; o aparelho é comandado por
 * `scripts/esp32_bancada.py`, chamado aqui pela linha de comando. Reescrever o
 * envelope da serial em TypeScript daria duas definições de "como se fala com o
 * dispositivo", e a errada só apareceria com um ESP32 numa enfermaria.
 *
 * PRÉ-CONDIÇÕES
 * -------------
 * Precisa do aparelho gravado e com o SPIFFS carregado de uma série que
 * sustente a mesma postura além da janela do perfil:
 *
 *   python scripts/gerar_eventos_esp32.py -o firmware/esp32_replay/data/eventos.jsonl \
 *          --horas 2 --intervalo 5 --postura supino
 *   python -m platformio run -d firmware -e websocket -t upload -t uploadfs --upload-port COM3
 *   UPP_ESP32_PORT=COM3 npm run e2e
 *
 * Sem `UPP_ESP32_PORT` esta spec é pulada — a CI não tem placa, e um teste que
 * falha por ausência de hardware treina todo mundo a ignorar vermelho.
 */
test.describe('do ESP32 até a tela', () => {
  test.skip(!PORTA_SERIAL, 'defina UPP_ESP32_PORT (ex.: COM3) para rodar com o aparelho');

  // O replay são 24 amostras a 500 ms, mais Wi-Fi, handshake e a consulta do
  // paciente. Folga porque quem falha aqui é hardware, e hardware falha devagar.
  test.setTimeout(240_000);

  test('o alerta nasce num sensor de verdade e chega na lista', async ({ page }) => {
    const alvo = leito('hardware');
    const { quadros } = observarWebSocketDeAlertas(page);

    await page.goto('/');
    await expect(page.getByText(alvo.nome)).toHaveCount(0);

    // A partir daqui ninguém toca na página. Quem produz o dado é o aparelho.
    const { stdout } = await executar(
      'python',
      ['-m', 'scripts.esp32_bancada', 'replay', '--porta', PORTA_SERIAL!],
      { cwd: RAIZ, env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, maxBuffer: 10 * 1024 * 1024 },
    );
    const replay = JSON.parse(stdout.trim().split(/\r?\n/).pop()!);

    // O que o aparelho diz ter feito. `descartes > 0` seria o formato do
    // arquivo divergindo de `EventPayload` — o defeito que fazia o ESP32 jogar
    // fora o arquivo inteiro respondendo "sucesso".
    expect(replay.erro, `o aparelho falhou: ${replay.erro}`).toBeUndefined();
    expect(replay.descartes).toBe(0);
    expect(replay.acks).toBeGreaterThan(0);
    expect(replay.enviados).toBe(replay.acks);

    // E o que a tela recebeu: o anúncio pelo WebSocket...
    expect(await esperarQuadro(quadros, 'alert_new', 60_000)).toContain(alvo.paciente_id);

    // ...e a linha, sem nenhuma navegação desde o `goto`.
    await expect(linhaDoPaciente(page, 'hardware')).toHaveCount(1);
  });
});
