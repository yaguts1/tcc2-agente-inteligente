"""E2E com o ESP32 de verdade: firmware compilado, Wi-Fi, SPIFFS e backend.

O QUE ESTE ARQUIVO ACRESCENTA A `test_protocolo_firmware.py`
------------------------------------------------------------
Aquele arquivo diz, no próprio docstring, que NÃO testa o C++ compilado: ele
reimplementa a máquina de estados em Python e a exercita contra o backend. É
excelente para o contrato e para a regra, e roda em qualquer lugar — mas o que
ele valida é a reimplementação, não o binário que vai para o leito.

Aqui o sujeito é o dispositivo. O que só existe neste arquivo:

* a máquina de estados **compilada** (`processarReplay`), não uma cópia dela;
* o SPIFFS — leitura do `.jsonl` e o checkpoint sobrevivendo a queda de energia;
* **reboot físico** (linha EN via DTR/RTS) no meio do replay;
* a pilha de rede real: Wi-Fi, HTTPClient/WebSockets, DNS, MTU.

O ORÁCULO É A SERIAL
--------------------
O dispositivo não expõe API. O que ele expõe é `registrarLog()` na serial
(`replay_comum.h`), e é por lá que o teste comanda (`CMD_START`, `CMD_STOP`,
`CMD_RESET`) e observa (`[ACK] seq=`, `[DESCARTE]`, `[INFO] Fim do arquivo`).
Isso torna as linhas de log **contrato de teste**: mudar o texto de um
`registrarLog` quebra este arquivo de propósito.

COMO RODAR
----------
    # 1. dados frescos no SPIFFS (o pipeline ignora ts fora de ±24 h)
    python scripts/gerar_eventos_esp32.py -o firmware/esp32_replay/data/eventos.jsonl --horas 2

    # 2. gravar firmware + sistema de arquivos (-e http ou -e websocket)
    python -m platformio run -d firmware -e websocket -t upload -t uploadfs --upload-port COM3

    # 3. rodar
    UPP_ESP32_PORT=COM3 pytest tests/test_e2e_esp32.py -m hardware -v

Os dois transportes passam nos mesmos testes: o que este arquivo observa são as
linhas comuns (`[ACK] seq=`, `[INFO] Fim do arquivo`), emitidas por `http` e por
`websocket` igualmente. Era a divergência entre as duas variantes que deixou a
recomendada cinco correções atrás — um E2E que só serve para uma delas repetiria
o mesmo erro.

Sem `UPP_ESP32_PORT` a suíte inteira é pulada — a CI não tem placa, e um teste
de hardware que falha por ausência de hardware treina todo mundo a ignorar
vermelho.
"""

from __future__ import annotations

import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.hardware

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_EVENTOS = RAIZ / "firmware" / "esp32_replay" / "data" / "eventos.jsonl"
CONFIG_FIRMWARE = RAIZ / "firmware" / "esp32_replay" / "config.h"

PORTA_SERIAL = os.getenv("UPP_ESP32_PORT")

# A cama está fixada em `g_config.camaId` (`replay_comum.h`), e é por ela que o
# dispositivo descobre de quem é a amostra. Mudar aqui sem regravar o firmware
# só produz um 404 em `/api/pacientes/cama/...` e um replay que nunca sai do
# estado OCIOSO.
CAMA = "C-01"

# ANTES do import abaixo, e não depois.
#
# `scripts.esp32_bancada` importa `serial` no topo, e `pyserial` NÃO está no
# `requirements.txt` — é dependência de bancada, não de produção, e não tem por
# que entrar na imagem. Sem este `importorskip` na frente, a simples COLETA
# deste arquivo derruba a suíte inteira em qualquer máquina sem pyserial,
# inclusive a CI: o erro não seria "teste de hardware pulado", seria "pytest não
# conseguiu importar" — e nada mais rodaria.
pytest.importorskip("serial", reason="pyserial não instalado")

# O envelope da serial e as linhas de log que valem como contrato moram em
# `scripts/esp32_bancada.py`. Não é só desduplicação: o E2E de navegador também
# dirige o aparelho, e ele roda no Playwright — uma segunda definição de "como
# se fala com o dispositivo" seria descoberta errada com um ESP32 numa
# enfermaria.
from scripts.esp32_bancada import (  # noqa: E402
    CHECKPOINT_GRAVADO,
    CHECKPOINT_ZERADO,
    FIM,
    NA_REDE,
    PRONTO,
    RETOMANDO,
    Esp32,
)

# A recusa por credencial cai em pontos DIFERENTES conforme o transporte, e as
# duas contam:
#   WebSocket — no handshake, antes de qualquer amostra sair
#               (`[FALHA] ws error=invalid_device_token`);
#   HTTP      — no primeiro GET autenticado, a consulta do paciente pela cama
#               (`[ERRO] Falha ao obter paciente da cama. HTTP=401`), porque
#               essa rota também exige o token.
# Em ambos o dispositivo fica preso ANTES de enviar, que é o comportamento
# desejado: sem saber de quem é a amostra, ele não envia.
TOKEN_RECUSADO = r"ws error=invalid_device_token|HTTP=401|status=401"


# ---------------------------------------------------------------------------
# Pré-condições — falhar explicando, nunca por timeout
# ---------------------------------------------------------------------------
def _enderecos_desta_maquina() -> set[str]:
    """Todos os IPv4 do host, não o da rota padrão.

    Sondar a rota de saída (o truque do socket UDP para um IP qualquer) responde
    a pergunta ERRADA aqui: esta máquina tem Ethernet, Wi-Fi, Tailscale e dois
    adaptadores VMware, e a rota padrão sai pela Ethernet (192.168.0.202)
    enquanto o ESP32 está do lado do Wi-Fi (10.0.0.x). A primeira versão desta
    checagem reprovou a bancada inteira por isso.

    A pergunta certa é de posse: **esta máquina atende no endereço que foi
    compilado para dentro do aparelho?**
    """
    return {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}


def _do_firmware(nome: str, com_aspas: bool) -> str | None:
    """Lê um `#define` do `config.h` que foi compilado para dentro do aparelho.

    O firmware é a fonte da verdade sobre ONDE ele vai bater. Fixar o endereço
    também deste lado criaria dois valores para a mesma decisão, e o dia em que
    divergissem produziria um replay parado em OCIOSO sem explicação.
    """
    if not CONFIG_FIRMWARE.exists():
        return None
    padrao = rf'^\s*#define\s+{nome}\s+"([^"]+)"' if com_aspas else rf"^\s*#define\s+{nome}\s+(\S+)"
    m = re.search(padrao, CONFIG_FIRMWARE.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


IP_DO_BACKEND = _do_firmware("SERVER_IP", com_aspas=True)
PORTA_BACKEND = int(os.getenv("UPP_E2E_PORT") or _do_firmware("SERVER_PORT", com_aspas=False) or 8000)


@pytest.fixture(scope="session", autouse=True)
def _pre_condicoes():
    """As três coisas que, faltando, produzem falhas indistinguíveis de bug.

    Todas terminam do mesmo jeito na prática — o dispositivo fica quieto e o
    teste estoura por timeout. Conferir antes é a diferença entre "o firmware
    aponta para 10.0.0.136 e esta máquina não tem esse endereço" e vinte minutos
    perdidos com o analisador de pacotes.
    """
    if not PORTA_SERIAL:
        pytest.skip("defina UPP_ESP32_PORT (ex.: COM3) para rodar o E2E de hardware")

    if not ARQUIVO_EVENTOS.exists():
        pytest.fail(f"{ARQUIVO_EVENTOS} não existe — rode scripts/gerar_eventos_esp32.py")

    # O IP do servidor foi compilado para dentro do aparelho. É DHCP: se a rede
    # reatribuiu o endereço, o ESP32 está falando com quem não existe, e o
    # sintoma seria um replay parado em OCIOSO para sempre.
    if not IP_DO_BACKEND:
        pytest.fail("não consegui ler SERVER_IP de firmware/esp32_replay/config.h")
    meus = _enderecos_desta_maquina()
    if IP_DO_BACKEND not in meus:
        pytest.fail(
            f"o firmware aponta para SERVER_IP={IP_DO_BACKEND}, que não é um endereço desta "
            f"máquina (tenho {sorted(meus)}). Ajuste firmware/esp32_replay/config.h e regrave, "
            "ou fixe o IP no DHCP do roteador."
        )
    yield


def _linhas_do_arquivo() -> list[str]:
    return [linha for linha in ARQUIVO_EVENTOS.read_text(encoding="utf-8").splitlines() if linha.strip()]


# ---------------------------------------------------------------------------
# Backend de verdade, escutando na LAN
# ---------------------------------------------------------------------------
@dataclass
class BackendNaLan:
    """uvicorn em subprocesso, com banco próprio, exposto na rede.

    Não dá para usar `app_isolado`/`TestClient` aqui: aquilo é ASGI em
    processo, e o ESP32 fala TCP. Precisa ser um servidor de verdade, ligado a
    `0.0.0.0` — em `127.0.0.1` o aparelho não alcança.
    """

    db_path: str
    host: str
    porta: int
    # Token exigido de quem envia amostra. Vazio = verificação desligada, que é
    # o estado da bancada. Mutável entre `parar()` e `subir()`: é assim que o
    # teste de credencial simula alguém corrigindo a configuração do servidor
    # com o dispositivo já no ar.
    token: str = ""
    _proc: subprocess.Popen | None = field(default=None, repr=False)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.porta}"

    def subir(self, timeout: float = 60.0) -> None:
        env = {
            **os.environ,
            "UPP_DB_PATH": self.db_path,
            "APP_PREFIX": "",
            "ENVIRONMENT": "development",
            "BACKUP_ON_START": "0",
            # A bancada roda sem token: `UPP_DEVICE_TOKEN` não está provisionado
            # e o `config.h` do aparelho também está com DEVICE_TOKEN vazio. Se
            # sobrasse do ambiente do shell, a ingestão passaria a exigir um
            # header que o firmware não manda, e o sintoma seria 401 tratado
            # como TRANSIENTE — o dispositivo tentando para sempre, em silêncio.
            "UPP_DEVICE_TOKEN": self.token,
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "interface.web:app",
             "--host", "0.0.0.0", "--port", str(self.porta), "--log-level", "warning"],
            cwd=str(RAIZ), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        limite = time.time() + timeout
        while time.time() < limite:
            if self._proc.poll() is not None:
                raise RuntimeError(f"uvicorn morreu na subida (código {self._proc.returncode})")
            try:
                with socket.create_connection((self.host, self.porta), timeout=1):
                    return
            except OSError:
                time.sleep(0.3)
        raise TimeoutError(f"backend não respondeu em {self.base_url} em {timeout}s")

    def parar(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        self._proc = None

    # -- consultas ---------------------------------------------------------
    def amostras_de(self, paciente_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM grade WHERE paciente_id = ?", (paciente_id,)
            ).fetchone()[0]

    def instantes_de(self, paciente_id: str) -> list[str]:
        """Os instantes gravados, em ordem.

        A coluna é `ts` — `inicio` é da tabela `eventos`, que é outra coisa. E
        `grade` tem PRIMARY KEY (paciente_id, ts_ms): duplicata não é uma
        possibilidade que se verifique aqui, é uma que o banco recusa. Por isso
        a asserção que carrega peso nos testes de resiliência é a CONTAGEM —
        uma reentrega duplicada apareceria como amostra faltando no total, não
        como linha repetida.
        """
        with sqlite3.connect(self.db_path) as conn:
            return [
                linha[0]
                for linha in conn.execute(
                    "SELECT ts FROM grade WHERE paciente_id = ? ORDER BY ts", (paciente_id,)
                )
            ]


@pytest.fixture()
def backend(tmp_path):
    """Backend novo e banco vazio por teste — o E2E precisa contar amostras."""
    from interface.db_core import criar_esquema

    db_path = str(tmp_path / "e2e.db")
    criar_esquema(db_path)

    # `host` só serve para a espera de prontidão e para `base_url`: o uvicorn
    # sobe em 0.0.0.0. Mas tem que ser o MESMO endereço que o aparelho procura,
    # senão o teste declara "pronto" olhando para uma interface que o ESP32 não
    # alcança.
    servidor = BackendNaLan(db_path=db_path, host=IP_DO_BACKEND, porta=PORTA_BACKEND)
    servidor.subir()
    try:
        yield servidor
    finally:
        servidor.parar()


@pytest.fixture()
def paciente(backend):
    """O paciente da cama C-01, que é como o aparelho descobre de quem é a amostra."""
    from interface.dao import criar_paciente

    ficha = criar_paciente(backend.db_path, "Paciente E2E", "alto", cama_id=CAMA)
    return ficha["paciente_id"]


# ---------------------------------------------------------------------------
# O dispositivo
# ---------------------------------------------------------------------------
@pytest.fixture()
def esp32():
    aparelho = Esp32(PORTA_SERIAL)
    try:
        yield aparelho
    finally:
        aparelho.fechar()


@pytest.fixture()
def esp32_zerado(esp32):
    """Aparelho reiniciado e com o checkpoint apagado.

    `CMD_RESET` é o que torna este arquivo repetível. Sem ele, o checkpoint
    gravado ao fim do primeiro replay aponta para o EOF e todo teste seguinte
    encontraria um aparelho que não envia nada — ver `limparCheckpoint()` em
    `replay_comum.h`.
    """
    esp32.reiniciar()
    esp32.esperar(PRONTO, timeout=20)
    esp32.esperar(NA_REDE, timeout=60)
    esp32.comandar("CMD_RESET")
    esp32.esperar(CHECKPOINT_ZERADO, timeout=15)
    return esp32


# ---------------------------------------------------------------------------
# 1) Bring-up: o aparelho é o que dizemos que ele é
# ---------------------------------------------------------------------------
def test_o_firmware_gravado_e_o_do_projeto(esp32):
    """Guarda contra o erro mais bobo e mais caro desta bancada.

    A placa já estava com um sketch antigo, só de Wi-Fi, que conectava e ficava
    quieto. Todo teste abaixo falharia por timeout, e nenhum diria o motivo.
    """
    esp32.reiniciar()
    linha = esp32.esperar(PRONTO, timeout=20)
    assert "pronto" in linha


def test_conecta_no_wifi_da_bancada(esp32):
    esp32.reiniciar()
    esp32.esperar(PRONTO, timeout=20)
    esp32.esperar(NA_REDE, timeout=60)


# ---------------------------------------------------------------------------
# 2) A jornada inteira, com hardware nas duas pontas
# ---------------------------------------------------------------------------
def test_replay_completo_chega_ao_banco(backend, paciente, esp32_zerado):
    """Sensor → Wi-Fi → ingestão → filtro → grade, sem simulação em lugar nenhum.

    É o teste que o `test_protocolo_firmware.py` não pode fazer: ali o
    "dispositivo" é um dataclass Python. Aqui é o binário lendo o SPIFFS.
    """
    esperadas = _linhas_do_arquivo()

    esp32_zerado.comandar("CMD_START")
    esp32_zerado.esperar(rf"\[PACIENTE\] Vinculado a {re.escape(paciente)}", timeout=60)
    linhas = esp32_zerado.coletar_ate(FIM, timeout=300)

    acks = Esp32.acks(linhas)
    assert len(acks) == len(esperadas), f"o aparelho confirmou {len(acks)} de {len(esperadas)} amostras"
    assert acks == sorted(acks), "os seq precisam ser monotônicos"
    assert not Esp32.descartes(linhas), "nenhuma linha do arquivo deveria ser recusada"

    # E o que o aparelho diz ter entregue tem que estar no banco.
    time.sleep(2)  # a ingestão termina de gravar depois do ACK
    assert backend.amostras_de(paciente) == len(esperadas)

    # A contabilidade do próprio dispositivo tem que fechar com a do banco.
    # Sem isto, um descarte silencioso passaria: o replay terminaria "com
    # sucesso", com menos linhas na `grade` e ninguém somando as duas contas.
    contas = esp32_zerado.status()
    assert contas["enviados"] == len(esperadas)
    assert contas["descartados"] == 0
    assert contas["ativo"] == 0, "o replay tem que ter terminado"


def test_checkpoint_zerado_permite_repetir_o_replay(backend, paciente, esp32_zerado):
    """O defeito que este trabalho corrigiu, verificado no aparelho.

    Ao chegar em FINALIZADO o checkpoint aponta para o EOF. Antes do
    `CMD_RESET`, um segundo `CMD_START` reabria o arquivo, dava `seek` para o
    fim e não enviava NADA — sem erro e sem log. Numa bancada isso parece o
    dispositivo travado; numa suíte, só o primeiro teste passava.
    """
    total = len(_linhas_do_arquivo())

    esp32_zerado.comandar("CMD_START")
    primeira = esp32_zerado.coletar_ate(FIM, timeout=300)
    assert len(Esp32.acks(primeira)) == total

    # Sem zerar: o replay termina imediatamente, porque já está no fim.
    esp32_zerado.comandar("CMD_START")
    sem_zerar = esp32_zerado.coletar_ate(FIM, timeout=90)
    assert Esp32.acks(sem_zerar) == [], "sem CMD_RESET, retomar do EOF não envia nada — é o comportamento correto"

    # Com CMD_RESET: recomeça do início e entrega o arquivo inteiro de novo.
    esp32_zerado.comandar("CMD_RESET")
    esp32_zerado.esperar(CHECKPOINT_ZERADO, timeout=15)
    esp32_zerado.comandar("CMD_START")
    segunda = esp32_zerado.coletar_ate(FIM, timeout=300)
    assert len(Esp32.acks(segunda)) == total, "depois do CMD_RESET o arquivo inteiro tem que sair de novo"


# ---------------------------------------------------------------------------
# 3) Resiliência — o motivo de o hardware valer o incômodo
# ---------------------------------------------------------------------------
def test_reboot_no_meio_do_replay_retoma_da_amostra_certa(backend, paciente, esp32_zerado):
    """O defeito mais grave do histórico deste firmware, agora no aparelho.

    O checkpoint guardava a posição LIDA, não a ENTREGUE: ao religar, o replay
    retomava DEPOIS do evento que nunca chegou. `test_protocolo_firmware.py`
    prova isso sobre uma reimplementação em Python; aqui a energia cai de
    verdade (linha EN via RTS) e quem retoma é o SPIFFS.
    """
    total = len(_linhas_do_arquivo())

    esp32_zerado.comandar("CMD_START")
    esp32_zerado.esperar(r"\[PACIENTE\] Vinculado a", timeout=60)
    parciais = esp32_zerado.coletar_ate(r"\[ACK\] seq=5", timeout=180)
    entregues_antes = backend.amostras_de(paciente)
    assert entregues_antes >= 5

    # `[ACK] seq=N` NÃO significa "checkpoint gravado".
    #
    # Sobre WebSocket quem imprime essa linha é o callback do socket, assim que
    # o quadro chega (`transporte_ws.h`). Só na volta seguinte do loop a máquina
    # de estados trata o desfecho e chama `confirmarEventoAtual()` ->
    # `salvarCheckpoint()`. Cortar a energia dentro dessa janela pega o SPIFFS
    # no meio da gravação e o checkpoint não sobrevive — o aparelho religa e
    # recomeça do zero.
    #
    # Isso é comportamento correto (o dado não se perde: a PK da `grade` recusa
    # a duplicata), mas torna o instante do reboot uma corrida. Esperar `[CKPT]`
    # — que só sai DEPOIS do `close()` do arquivo — é o que faz este teste medir
    # a RETOMADA em vez de medir o relógio. A primeira versão dormia 2 s e
    # torcia.
    esp32_zerado.esperar(CHECKPOINT_GRAVADO, timeout=30)

    # Puxar o fio no meio do voo.
    esp32_zerado.reiniciar()
    esp32_zerado.esperar(PRONTO, timeout=20)
    esp32_zerado.esperar(NA_REDE, timeout=60)
    esp32_zerado.comandar("CMD_START")  # sem CMD_RESET: tem que RETOMAR
    esp32_zerado.esperar(RETOMANDO, timeout=60)
    esp32_zerado.coletar_ate(FIM, timeout=300)

    time.sleep(2)
    instantes = backend.instantes_de(paciente)
    assert len(instantes) == total, "o reboot não pode custar nem duplicar amostra"
    assert len(set(instantes)) == total, "e nenhuma pode chegar duas vezes"
    assert Esp32.acks(parciais), "o teste só vale se algo tinha sido entregue antes do reboot"


def test_token_errado_faz_o_aparelho_insistir_ate_alguem_corrigir(backend, paciente, esp32_zerado):
    """Credencial errada é erro de OPERAÇÃO, e o firmware trata como tal.

    `classificarResposta` põe 401/403 em TRANSIENTE de propósito, e
    `classificarErroWebSocket` faz o mesmo com `invalid_device_token`: um
    dispositivo preso a um leito não pode descartar amostra clínica porque
    alguém errou o token no `.env`. Ele insiste, e se recupera sozinho quando a
    configuração for corrigida — sem visita ao leito, sem reflash.

    O ROADMAP registrava este caminho como sem cobertura de hardware. É o único
    teste daqui que exercita a ingestão autenticada de ponta a ponta.
    """
    total = len(_linhas_do_arquivo())

    # O servidor passa a exigir um token que o aparelho não tem.
    backend.parar()
    backend.token = "segredo-que-o-aparelho-nao-conhece"
    backend.subir()

    esp32_zerado.comandar("CMD_START")
    esp32_zerado.esperar(TOKEN_RECUSADO, timeout=90)
    recusado = esp32_zerado.drenar(15)

    assert not Esp32.acks(recusado), "sem credencial válida nada pode ser aceito"
    assert not Esp32.descartes(recusado), (
        "e nada pode ser DESCARTADO: token errado é configuração, não amostra ruim"
    )
    assert backend.amostras_de(paciente) == 0

    contas = esp32_zerado.status()
    assert contas["falhas"] > 0, "o aparelho tem que estar contando as recusas"
    assert contas["descartados"] == 0
    assert contas["enviados"] == 0

    # Alguém corrige o `.env` e reinicia o servidor. O dispositivo, que ficou
    # tentando esse tempo todo, tem que voltar sozinho.
    backend.parar()
    backend.token = ""
    backend.subir()

    esp32_zerado.coletar_ate(FIM, timeout=300)
    time.sleep(2)
    assert backend.amostras_de(paciente) == total, (
        "corrigida a configuração, o arquivo inteiro tem que chegar — a recusa só atrasa"
    )


def test_queda_do_servidor_no_meio_do_replay_nao_perde_amostra(backend, paciente, esp32_zerado):
    """O backend cai e volta. O aparelho insiste; nada se perde.

    É o que justifica `tentativasMax = 0` (infinito) com backoff limitado: numa
    ala ninguém está olhando o serial do ESP32 para religá-lo na mão.
    """
    total = len(_linhas_do_arquivo())

    esp32_zerado.comandar("CMD_START")
    esp32_zerado.esperar(r"\[PACIENTE\] Vinculado a", timeout=60)
    esp32_zerado.esperar(r"\[ACK\] seq=3", timeout=180)

    backend.parar()
    esp32_zerado.esperar(r"\[FALHA\]|\[INFO\] Reenviando", timeout=90)
    esp32_zerado.drenar(5)
    backend.subir()

    esp32_zerado.coletar_ate(FIM, timeout=300)

    time.sleep(2)
    instantes = backend.instantes_de(paciente)
    assert len(instantes) == total, "a indisponibilidade só pode atrasar, não perder"
    assert len(set(instantes)) == total, "e a retomada não pode duplicar"
