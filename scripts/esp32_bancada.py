"""Envelope de serial do ESP32: comandar o aparelho e ler o que ele diz.

Vivia dentro de `tests/test_e2e_esp32.py`, mas deixou de ser coisa de teste: o
E2E de navegador também precisa dirigir o dispositivo, e ele roda no Playwright,
do outro lado da cerca. Reescrever isto em TypeScript daria duas definições de
"como se fala com o aparelho" — e a que estivesse errada seria descoberta com um
ESP32 numa enfermaria.

Então mora aqui, e quem precisa importa: os testes em Python direto, o
Playwright pela linha de comando (ver `__main__` no fim do arquivo).

O ORÁCULO É A SERIAL
--------------------
O dispositivo não expõe API. O que ele expõe é `registrarLog()`
(`firmware/esp32_replay/replay_comum.h`), e é por lá que se comanda
(`CMD_START`, `CMD_STOP`, `CMD_RESET`, `CMD_STATUS`) e se observa. Isso torna as
linhas de log um contrato: mudar o texto de um `registrarLog` quebra quem
depende delas, de propósito.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import serial

BAUD = 115200
LINHAS_NO_ERRO = int(os.getenv("UPP_E2E_LOG_LINHAS", "40"))

# Linhas de log tratadas como contrato. Ficam juntas, e não espalhadas por quem
# usa, porque são o acoplamento real com o firmware: mudar um `registrarLog`
# tem que quebrar UM ponto, não seis.
PRONTO = r"\[SETUP\] ESP32 Replay"
NA_REDE = r"\[WIFI\] Connected IP="
CHECKPOINT_ZERADO = r"\[INFO\] Checkpoint zerado"
RETOMANDO = r"\[INFO\] Retomando offset \d+"

# Único marcador que significa "o ponto de retomada está no disco". Ver a nota
# em `salvarCheckpoint()`: `[ACK]` não serve para isso, porque sobre WebSocket
# quem a imprime é o callback do socket e a gravação vem uma volta de loop
# depois.
CHECKPOINT_GRAVADO = r"\[CKPT\] offset=\d+"

# O fim de verdade é "Replay finalizado", NÃO "Fim do arquivo".
#
# "Fim do arquivo" sai quando a última linha foi lida; o replay ainda está
# ativo, e só na volta seguinte o estado FINALIZADO grava o checkpoint, loga
# "Replay finalizado" e baixa `replayAtivo`. Esperar pelo marcador errado faz o
# CMD_START seguinte cair na janela entre os dois e ser recusado com
# "[INFO] Replay ja em execucao" — comando engolido, espera travada.
FIM = r"\[INFO\] Replay finalizado"


class Esp32:
    """Envelope fino sobre a serial: comandar e ler o log.

    Guarda tudo que chegou (`self.log`) para o relatório de falha mostrar o que
    o aparelho estava fazendo — sem isso, um teste de hardware que quebra não
    diz nada além de "timeout".
    """

    def __init__(self, porta: str):
        self.serial = serial.Serial(porta, BAUD, timeout=0.2)
        self.log: list[str] = []

    # -- ciclo de vida -----------------------------------------------------
    def reiniciar(self) -> None:
        """Reset por hardware: pulsa a linha EN pelo RTS do CP210x.

        É a queda de energia de verdade, não um `ESP.restart()` — que roda
        depois de o firmware ter tido a chance de gravar coisas. Para o teste do
        checkpoint essa diferença é o teste inteiro.
        """
        self.serial.setDTR(False)
        self.serial.setRTS(True)
        time.sleep(0.1)
        self.serial.setRTS(False)
        time.sleep(0.05)
        self.serial.reset_input_buffer()

    def fechar(self) -> None:
        try:
            self.serial.close()
        except Exception:
            pass

    # -- comandar ----------------------------------------------------------
    def comandar(self, comando: str) -> None:
        self.serial.write(f"{comando}\n".encode())
        self.serial.flush()

    # -- observar ----------------------------------------------------------
    def esperar(self, padrao: str, timeout: float = 60.0) -> str:
        """Consome o log até casar `padrao`. Falha citando o log recente."""
        rx = re.compile(padrao)
        limite = time.time() + timeout
        while time.time() < limite:
            linha = self._ler_linha()
            if linha is None:
                continue
            if rx.search(linha):
                return linha
        raise AssertionError(
            f"não vi /{padrao}/ em {timeout}s.\nÚltimas linhas do aparelho:\n"
            + "\n".join(f"  {x}" for x in self.log[-LINHAS_NO_ERRO:])
        )

    def coletar_ate(self, padrao: str, timeout: float = 180.0) -> list[str]:
        """Como `esperar`, devolvendo tudo que passou até o casamento."""
        inicio = len(self.log)
        self.esperar(padrao, timeout=timeout)
        return self.log[inicio:]

    def drenar(self, segundos: float) -> list[str]:
        inicio = len(self.log)
        limite = time.time() + segundos
        while time.time() < limite:
            self._ler_linha()
        return self.log[inicio:]

    def _ler_linha(self) -> str | None:
        cru = self.serial.readline()
        if not cru:
            return None
        linha = cru.decode("utf-8", "replace").rstrip()
        if not linha:
            return None
        self.log.append(linha)
        return linha

    def status(self, timeout: float = 15.0) -> dict[str, int | str]:
        """A contabilidade do próprio aparelho, via `CMD_STATUS`.

        Contar linhas `[ACK]` no log mede o que o teste conseguiu ler da serial;
        isto mede o que o dispositivo acha que fez. Quando os dois discordam, o
        interessante é a diferença — um ACK perdido no buffer da serial não é a
        mesma coisa que uma amostra não entregue.
        """
        self.comandar("CMD_STATUS")
        linha = self.esperar(r"\[STATUS\] ", timeout=timeout)
        campos: dict[str, int | str] = {}
        for par in linha.split("[STATUS] ", 1)[1].split():
            chave, _, valor = par.partition("=")
            # `alvo` e texto (host:porta/caminho); o resto e contador. Converter
            # tudo em `int` quebrava assim que o aparelho passou a dizer para
            # onde fala.
            campos[chave] = int(valor) if valor.isdigit() else valor
        return campos

    # -- leitura do log ----------------------------------------------------
    @staticmethod
    def acks(linhas: list[str]) -> list[int]:
        return [int(m.group(1)) for m in (re.match(r"\[ACK\] seq=(\d+)", x) for x in linhas) if m]

    @staticmethod
    def descartes(linhas: list[str]) -> list[str]:
        return [x for x in linhas if x.startswith("[DESCARTE]")]




# ---------------------------------------------------------------------------
# Linha de comando — como o Playwright dirige o aparelho
# ---------------------------------------------------------------------------
# O E2E de navegador roda em Node. Em vez de reescrever este envelope em
# TypeScript (com `serialport`, um módulo nativo, e uma segunda definição do
# protocolo), a spec chama este script e lê o JSON da última linha.
#
#     python -m scripts.esp32_bancada replay --porta COM3
#
# Tudo que o aparelho fala é ecoado no stderr, com prefixo, para o log da spec
# mostrar a sessão inteira quando algo falha. O stdout carrega só o resultado.
def _ligar(porta: str, verboso: bool) -> Esp32:
    aparelho = Esp32(porta)
    if verboso:
        original = aparelho._ler_linha

        def espelhar():
            linha = original()
            if linha:
                print(f"[esp32] {linha}", file=sys.stderr, flush=True)
            return linha

        aparelho._ler_linha = espelhar  # type: ignore[method-assign]
    return aparelho


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dirige o ESP32 da bancada pela serial")
    parser.add_argument("acao", choices=["replay", "status", "zerar"])
    parser.add_argument("--porta", default=os.getenv("UPP_ESP32_PORT"), help="ex.: COM3")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--silencioso", action="store_true")
    args = parser.parse_args(argv)

    if not args.porta:
        print("informe --porta (ou defina UPP_ESP32_PORT)", file=sys.stderr)
        return 2

    aparelho = _ligar(args.porta, not args.silencioso)
    try:
        if args.acao == "status":
            resultado = aparelho.status()
        elif args.acao == "zerar":
            aparelho.reiniciar()
            aparelho.esperar(PRONTO, timeout=30)
            aparelho.esperar(NA_REDE, timeout=90)
            aparelho.comandar("CMD_RESET")
            aparelho.esperar(CHECKPOINT_ZERADO, timeout=20)
            resultado = {"zerado": True}
        else:  # replay
            # Reinicia e zera antes: um replay que retoma do checkpoint da
            # execução anterior não envia nada, e a spec ficaria esperando um
            # alerta que nunca vem — ver `limparCheckpoint()` no firmware.
            aparelho.reiniciar()
            aparelho.esperar(PRONTO, timeout=30)
            aparelho.esperar(NA_REDE, timeout=90)
            aparelho.comandar("CMD_RESET")
            aparelho.esperar(CHECKPOINT_ZERADO, timeout=20)
            aparelho.comandar("CMD_START")
            linhas = aparelho.coletar_ate(FIM, timeout=args.timeout)
            resultado = {"acks": len(Esp32.acks(linhas)), "descartes": len(Esp32.descartes(linhas))}
            resultado.update(aparelho.status())
    except AssertionError as erro:
        print(json.dumps({"erro": str(erro)}, ensure_ascii=False))
        return 1
    finally:
        aparelho.fechar()

    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
