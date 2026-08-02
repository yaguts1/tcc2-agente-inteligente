#!/usr/bin/env python3
"""Demonstração ao vivo: preflight, perfis do aparelho e um ato por comando.

POR QUE UM RUNNER, E NÃO UMA ABA NO FRONTEND
--------------------------------------------
A força desta demo está em as ações serem reais. Quando a energia do ESP32 cai e
ele religa retomando da amostra exata, quem assiste vê um sistema resistindo a
uma falha física — coisa que um botão "simular queda" na tela não consegue
fazer, porque ele só encena. As três cenas mais fortes (energia, servidor, rede)
acontecem fora do navegador.

E uma aba de demo seria código de produção existindo só para a apresentação,
atrás de um usuário especial. Perguntada "isso está no sistema real?", a
resposta honesta enfraqueceria tudo. Do jeito que está, o que se vê É o produto.

DOIS PERFIS, PORQUE O FIRMWARE É GRAVADO PARA UM DESTINO SÓ
------------------------------------------------------------
    bancada  ->  uvicorn avulso, porta 8010, sem prefixo
                 (é como `tests/test_e2e_esp32.py` e o Playwright rodam)

    demo     ->  o CONTAINER, porta 8000, prefixo /TCC
                 (é o sistema de verdade, com Caddy, que a banca vê)

A porta 8000 é do container e não pode ser usada pela bancada — subir ali faria
a suíte semear paciente de teste dentro do banco real. Então o alvo muda, e
mudar de alvo exige regravar. Cada perfil é um comando, e cada harness confere
o perfil de que precisa antes de começar.

    python -m scripts.demo perfil-demo      # regrava o aparelho apontando para o container
    python -m scripts.demo perfil-bancada   # devolve o aparelho para os testes
    python -m scripts.demo checar           # preflight: recusa começar se algo estiver errado
    python -m scripts.demo preparar         # perfil-demo + dados frescos + SPIFFS + paciente
    python -m scripts.demo ato1             # o dado é real: replay -> alerta na tela
    python -m scripts.demo ato2             # cai a energia -> retoma do checkpoint
    python -m scripts.demo ato3             # cai o servidor -> insiste, nada se perde
    python -m scripts.demo ato4             # fila offline (guiado, com celular)
    python -m scripts.demo ato5             # token errado -> insiste, nao descarta
    python -m scripts.demo roteiro          # o que falar, na ordem
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "firmware" / "esp32_replay" / "config.h"
DADOS = RAIZ / "firmware" / "esp32_replay" / "data" / "eventos.jsonl"

CONTAINER = "upp_app"
# A cama é COMPILADA no firmware (`g_config.camaId`). Mudar aqui sem regravar o
# aparelho só produz 404 em /pacientes/cama/... e um replay preso em OCIOSO.
CAMA = "C-01"
PACIENTE_DEMO = "Sr. Antônio Nogueira"
PERFIL_DEMO = "alto"  # janela de 60 min, a mais curta: o alerta nasce mais cedo

PERFIS = {
    "bancada": {"SERVER_PORT": "8010", "APP_PREFIXO": '""'},
    "demo": {"SERVER_PORT": "8000", "APP_PREFIXO": '"/TCC"'},
}


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
def titulo(texto: str) -> None:
    print(f"\n\033[1;36m{texto}\033[0m")


def ok(texto: str) -> None:
    print(f"  \033[32mOK\033[0m   {texto}")


def erro(texto: str) -> None:
    print(f"  \033[31mFALHA\033[0m {texto}")


def aviso(texto: str) -> None:
    print(f"  \033[33m!\033[0m    {texto}")


# ---------------------------------------------------------------------------
# config.h — ler e escrever os defines
# ---------------------------------------------------------------------------
def ler_define(nome: str) -> str | None:
    if not CONFIG.exists():
        return None
    m = re.search(rf"^\s*#define\s+{nome}\s+(\S+)", CONFIG.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def escrever_define(nome: str, valor: str) -> None:
    texto = CONFIG.read_text(encoding="utf-8")
    novo, n = re.subn(rf"^(\s*#define\s+{nome}\s+)(\S+)", rf"\g<1>{valor}", texto, flags=re.M)
    if n == 0:
        raise SystemExit(f"não achei #define {nome} em {CONFIG}")
    CONFIG.write_text(novo, encoding="utf-8")


def perfil_atual() -> str | None:
    atual = {k: ler_define(k) for k in ("SERVER_PORT", "APP_PREFIXO")}
    for nome, esperado in PERFIS.items():
        if atual == esperado:
            return nome
    return None


# ---------------------------------------------------------------------------
# Peças da bancada
# ---------------------------------------------------------------------------
def enderecos_locais() -> set[str]:
    return {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}


def base_url() -> str:
    porta = ler_define("SERVER_PORT") or "8000"
    prefixo = (ler_define("APP_PREFIXO") or '""').strip('"')
    return f"http://localhost:{porta}{prefixo}"


def http(caminho: str, metodo: str = "GET", corpo: dict | None = None, timeout: float = 10.0):
    req = urllib.request.Request(
        base_url() + caminho,
        method=metodo,
        data=None if corpo is None else json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # rede fora, container parado
        return 0, str(e)


def no_container(codigo: str) -> tuple[int, str]:
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "-c", codigo],
        capture_output=True, text=True,
    )
    return r.returncode, (r.stdout or r.stderr).strip()


def pio(*args: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "platformio", *args], cwd=RAIZ
    ).returncode


# ---------------------------------------------------------------------------
# checar — o preflight que se recusa a dizer "pronto"
# ---------------------------------------------------------------------------
@dataclass
class Achado:
    grave: bool
    texto: str


def checar(porta_serial: str | None) -> list[Achado]:
    problemas: list[Achado] = []
    titulo("PREFLIGHT")

    # 1. perfil do firmware
    perfil = perfil_atual()
    if perfil == "demo":
        ok(f"firmware no perfil DEMO (porta {ler_define('SERVER_PORT')}, prefixo {ler_define('APP_PREFIXO')})")
    else:
        erro(f"firmware não está no perfil demo (está em: {perfil or 'personalizado'})")
        problemas.append(Achado(True, "rode: python -m scripts.demo perfil-demo"))

    # 2. container
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
        capture_output=True, text=True,
    )
    if r.returncode == 0 and r.stdout.strip() == "healthy":
        ok(f"container {CONTAINER} saudável")
    else:
        erro(f"container {CONTAINER} não está saudável ({r.stdout.strip() or r.stderr.strip()})")
        problemas.append(Achado(True, "rode: docker compose up -d --build app"))

    # 3. a aplicação responde no caminho que o aparelho vai usar
    status, _ = http("/api/versoes")
    if status == 200:
        ok(f"API responde em {base_url()}/api/versoes")
    else:
        erro(f"API não responde em {base_url()}/api/versoes (HTTP {status})")
        problemas.append(Achado(True, "confira APP_PREFIXO/SERVER_PORT no config.h"))

    # 4. o IP compilado no aparelho é desta máquina
    #
    # É DHCP. Se a rede reatribuiu o endereço entre o ensaio e a apresentação, o
    # ESP32 fala com o vazio e o replay fica parado em OCIOSO, sem dizer por quê.
    ip = (ler_define("SERVER_IP") or "").strip('"')
    meus = enderecos_locais()
    if ip in meus:
        ok(f"SERVER_IP={ip} é um endereço desta máquina")
    else:
        erro(f"SERVER_IP={ip} não é desta máquina (tenho {sorted(meus)})")
        problemas.append(Achado(True, f"ajuste SERVER_IP no config.h e rode perfil-demo"))

    # 5. paciente no leito do aparelho
    status, corpo = http(f"/api/pacientes/cama/{CAMA}")
    if status == 200:
        ok(f"leito {CAMA} tem paciente ({corpo.get('paciente_id')})")
    else:
        erro(f"leito {CAMA} sem paciente (HTTP {status})")
        problemas.append(Achado(True, "rode: python -m scripts.demo preparar"))

    # 6. dados dentro da janela de ±24 h
    #
    # O pipeline ignora evento fora dessa janela, e o modo de falha é o pior:
    # o replay termina "com sucesso" e nada aparece na tela.
    if not DADOS.exists():
        erro(f"{DADOS} não existe")
        problemas.append(Achado(True, "rode: python -m scripts.demo preparar"))
    else:
        primeira = json.loads(DADOS.read_text(encoding="utf-8").splitlines()[0])
        from datetime import UTC, datetime

        ts = datetime.fromisoformat(primeira["ts_utc"].replace("Z", "+00:00"))
        idade_h = (datetime.now(UTC) - ts).total_seconds() / 3600
        if -24 < idade_h < 24:
            ok(f"dados do SPIFFS com {idade_h:.1f} h (dentro de ±24 h)")
        else:
            erro(f"dados do SPIFFS com {idade_h:.1f} h — o pipeline vai ignorar tudo")
            problemas.append(Achado(True, "rode: python -m scripts.demo preparar"))

    # 7. o aparelho na serial — e o alvo que ELE diz ter
    #
    # "Gravei" nao e o mesmo que "esta la". Perguntar ao dispositivo para onde
    # ele fala e a unica forma de saber qual binario esta rodando; sem isso, um
    # upload que nao pegou vira um WebSocket em laco no meio da apresentacao.
    if porta_serial:
        try:
            from scripts.esp32_bancada import Esp32

            aparelho = Esp32(porta_serial)
            try:
                estado = aparelho.status(timeout=20)
            finally:
                aparelho.fechar()
            alvo = str(estado.get("alvo", ""))
            esperado = f"{ip}:{ler_define('SERVER_PORT')}"
            prefixo = (ler_define("APP_PREFIXO") or '""').strip('"')
            if alvo.startswith(esperado) and prefixo in alvo:
                ok(f"aparelho gravado e apontando para {alvo}")
            else:
                erro(f"o aparelho fala com {alvo}, mas o config.h pede {esperado}{prefixo}/api/...")
                problemas.append(Achado(True, "o upload do firmware nao pegou: rode perfil-demo"))
        except Exception as e:
            erro(f"nao consegui falar com o ESP32 em {porta_serial}: {e}")
            problemas.append(Achado(True, "confira o cabo USB, a porta, e se o firmware esta gravado"))
    else:
        aviso("porta serial não informada (--porta COM3); os atos com o aparelho não vão rodar")

    print()
    if problemas:
        print("\033[31mNÃO ESTÁ PRONTO\033[0m — resolva antes de apresentar:")
        for p in problemas:
            print(f"    - {p.texto}")
    else:
        print("\033[32mPRONTO PARA APRESENTAR\033[0m")
    return problemas


# ---------------------------------------------------------------------------
# perfis e preparação
# ---------------------------------------------------------------------------
def aplicar_perfil(nome: str, porta_serial: str | None, gravar: bool = True) -> None:
    titulo(f"PERFIL {nome.upper()}")
    for chave, valor in PERFIS[nome].items():
        escrever_define(chave, valor)
        ok(f"{chave} = {valor}")
    if gravar:
        if pio("run", "-d", "firmware", "-e", "websocket", "-t", "upload",
               *(["--upload-port", porta_serial] if porta_serial else [])) != 0:
            raise SystemExit("falha ao gravar o firmware")
        ok("firmware gravado")


def paciente_do_leito() -> str | None:
    """Quem está na cama do aparelho, segundo a própria aplicação.

    Pela API, e não por SQL: a cama não é coluna de `pacientes` — ela vive em
    `internacoes`/`paciente_cama_history`, porque um leito tem histórico de
    ocupação. A primeira versão disto consultava `pacientes.cama_id` e quebrava
    com "no such column". Perguntar à rota que o próprio firmware usa evita
    reimplementar a regra e sobrevive a mudanças de esquema.
    """
    status, corpo = http(f"/api/pacientes/cama/{CAMA}")
    return corpo.get("paciente_id") if status == 200 and isinstance(corpo, dict) else None


def semear_paciente() -> str:
    """Garante um paciente no leito do aparelho, dentro do container.

    Criação vai por `criar_paciente` — o MESMO caminho da aplicação, que cuida
    de paciente, internação e histórico de cama de uma vez. Rodar direto no
    container evita depender de eu conhecer a senha de um admin, e evita
    reimplementar a criação em SQL.
    """
    existente = paciente_do_leito()
    if existente:
        ok(f"leito {CAMA} já ocupado por {existente}")
        return existente

    codigo = (
        "import os\n"
        "from interface.dao import criar_paciente\n"
        "db=os.getenv('UPP_DB_PATH','/data/dados.db')\n"
        f"print(criar_paciente(db,{PACIENTE_DEMO!r},{PERFIL_DEMO!r},cama_id={CAMA!r})['paciente_id'])\n"
    )
    rc, saida = no_container(codigo)
    if rc != 0:
        raise SystemExit(f"não consegui semear o paciente: {saida}")
    pid = saida.splitlines()[-1].strip()
    ok(f"paciente criado no leito {CAMA}: {pid}")
    return pid


def limpar_leito() -> None:
    """Apaga alertas e grade do paciente da demo.

    É o que torna cada ato repetível: sem isto, o segundo `ato1` não faria
    nascer alerta nenhum — o motor não reabre alerta que já está aberto — e a
    demo daria a impressão de ter quebrado bem na hora da apresentação.

    Toca SÓ o paciente do leito do aparelho; o resto do banco fica intacto.
    """
    pid = paciente_do_leito()
    if not pid:
        aviso(f"leito {CAMA} sem paciente; nada a limpar")
        return
    codigo = (
        "import os,sqlite3\n"
        "db=os.getenv('UPP_DB_PATH','/data/dados.db')\n"
        "c=sqlite3.connect(db)\n"
        f"p={pid!r}\n"
        # `estado_incremental` e `timeline_events` entram aqui, e não são
        # detalhe: o motor guarda `alerta_atual` no estado, e enquanto ele achar
        # que o alerta está ABERTO, não emite de novo. Apagar só a tabela
        # `alertas` deixa o paciente num limbo — o dashboard vazio, o motor
        # convencido de que já avisou, e o replay seguinte sem produzir nada.
        #
        # Zerar um paciente são três coisas: as linhas, o estado do motor, e a
        # memória do processo (o restart logo abaixo). Duas delas não aparecem
        # em lugar nenhum da interface.
        "for t in ('alertas','grade','eventos','device_events','estado_incremental','timeline_events'):\n"
        "    try: c.execute(f'DELETE FROM {t} WHERE paciente_id=?',(p,))\n"
        "    except Exception: pass\n"
        "c.commit(); print('limpo')\n"
    )
    rc, saida = no_container(codigo)
    if rc != 0:
        raise SystemExit(f"não consegui limpar o leito: {saida}")
    ok(f"histórico de {pid} limpo (alertas, grade, eventos)")

    # E o estado EM MEMÓRIA do processo, que apagar linhas do banco não alcança.
    #
    # `quality/filtro.py` guarda `_DEDUP_CACHE[device_id]` com chave
    # `(device_id, postura, ts_iso)` dentro do processo. O SPIFFS do aparelho
    # tem sempre as MESMAS amostras, então o segundo replay repete exatamente as
    # mesmas chaves: tudo é descartado como duplicado — e o servidor ainda
    # responde ACK, porque descartar duplicata não é erro. Do lado do aparelho o
    # replay termina "com sucesso"; do lado da tela não aparece nada.
    #
    # É o item 3.3 do ROADMAP ("estado em processo bloqueia réplicas") aparecendo
    # como demo que só funciona na primeira vez. Enquanto o dedup não sair para o
    # Redis, reiniciar é o jeito honesto de recomeçar do zero.
    subprocess.run(["docker", "restart", CONTAINER], capture_output=True, text=True)
    limite = time.time() + 90
    while time.time() < limite:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
                           capture_output=True, text=True)
        if r.stdout.strip() == "healthy":
            ok("container reiniciado (dedup e estado incremental zerados)")
            return
        time.sleep(2)
    raise SystemExit("o container não voltou a ficar saudável depois do restart")


def preparar(porta_serial: str | None) -> None:
    aplicar_perfil("demo", porta_serial, gravar=False)

    titulo("DADOS")
    # `--postura supino` é o que garante o alerta: o motor só abre imobilidade
    # se a MESMA postura se sustentar além da janela do perfil, e a série padrão
    # troca de postura por sorteio.
    r = subprocess.run(
        [sys.executable, "scripts/gerar_eventos_esp32.py", "-o", str(DADOS),
         "--horas", "2", "--intervalo", "5", "--postura", "supino"],
        cwd=RAIZ, capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if r.returncode != 0:
        raise SystemExit(f"falha ao gerar dados: {r.stderr}")
    ok(f"{len(DADOS.read_text(encoding='utf-8').splitlines())} amostras, supino sustentado")

    titulo("APARELHO")
    # Duas invocacoes, e nao `-t upload -t uploadfs` numa so.
    #
    # Combinados, o PlatformIO chegou a executar apenas o segundo: o SPIFFS
    # subiu e o BINARIO ANTIGO ficou no aparelho, ainda falando com a porta e o
    # prefixo anteriores. O sintoma foi um WebSocket reconectando em laco, e
    # nada no log dizia que o firmware nao era o esperado.
    porta = ["--upload-port", porta_serial] if porta_serial else []
    for etapa, alvo in (("firmware", "upload"), ("SPIFFS", "uploadfs")):
        if pio("run", "-d", "firmware", "-e", "websocket", "-t", alvo, *porta) != 0:
            raise SystemExit(f"falha ao gravar {etapa}")
        ok(f"{etapa} gravado")

    titulo("BANCO")
    semear_paciente()
    limpar_leito()

    checar(porta_serial)


# ---------------------------------------------------------------------------
# Atos
# ---------------------------------------------------------------------------
def alertas_do_leito() -> list[dict]:
    """Alertas do paciente da demo, lidos do banco do container.

    Pelo banco, e não por `/api/frontend/alerts`: aquela rota exige sessão de
    admin (401 sem cookie), e o runner não deveria depender de eu conhecer a
    senha de alguém. A primeira versão chamava a API e engolia o 401 devolvendo
    lista vazia — o ato reportava "nenhum alerta" quando o problema era
    autenticação.
    """
    pid = paciente_do_leito()
    if not pid:
        return []
    codigo = "\n".join([
        "import os,sqlite3,json",
        "db=os.getenv('UPP_DB_PATH','/data/dados.db')",
        "c=sqlite3.connect(db)",
        f"p={pid!r}",
        "linhas=c.execute('SELECT inicio,tipo,status FROM alertas WHERE paciente_id=?',(p,)).fetchall()",
        "print(json.dumps([{'inicio':a,'tipo':b,'status':s} for a,b,s in linhas]))",
    ])
    rc, saida = no_container(codigo)
    if rc != 0:
        return []
    try:
        return json.loads(saida.splitlines()[-1])
    except Exception:
        return []


def grade_do_leito() -> int:
    """Quantas amostras o paciente da demo tem no banco."""
    pid = paciente_do_leito()
    if not pid:
        return 0
    codigo = "\n".join([
        "import os,sqlite3",
        "c=sqlite3.connect(os.getenv('UPP_DB_PATH','/data/dados.db'))",
        f"p={pid!r}",
        "print(c.execute('SELECT COUNT(*) FROM grade WHERE paciente_id=?',(p,)).fetchone()[0])",
    ])
    rc, saida = no_container(codigo)
    try:
        return int(saida.splitlines()[-1]) if rc == 0 else 0
    except ValueError:
        return 0


def amostras_no_arquivo() -> int:
    return len([x for x in DADOS.read_text(encoding="utf-8").splitlines() if x.strip()])


def abrir_aparelho(porta_serial: str):
    """Envelope da serial com eco na tela — o log do ESP32 É parte da demo."""
    from scripts.esp32_bancada import Esp32

    aparelho = Esp32(porta_serial)
    original = aparelho._ler_linha

    def espelhar():
        linha = original()
        if linha:
            print(f"  \033[90m[esp32]\033[0m {linha}", flush=True)
        return linha

    aparelho._ler_linha = espelhar  # type: ignore[method-assign]
    return aparelho


def acordar(aparelho, zerar: bool = True) -> None:
    """Reinicia o aparelho e (opcionalmente) apaga o checkpoint.

    `zerar=False` é o que faz os atos de resiliência valerem: sem apagar o
    checkpoint, o CMD_START seguinte tem que RETOMAR de onde parou — que é
    justamente o comportamento em julgamento.
    """
    from scripts.esp32_bancada import CHECKPOINT_ZERADO, NA_REDE, PRONTO

    aparelho.reiniciar()
    aparelho.esperar(PRONTO, timeout=30)
    aparelho.esperar(NA_REDE, timeout=90)
    if zerar:
        aparelho.comandar("CMD_RESET")
        aparelho.esperar(CHECKPOINT_ZERADO, timeout=20)


def ato1(porta_serial: str, manual: bool) -> int:
    titulo("ATO 1 — O DADO É REAL")
    print(f"  Projete: {base_url()}/  e este terminal, lado a lado.\n")
    limpar_leito()

    antes = len(alertas_do_leito())
    if antes:
        aviso(f"ainda há {antes} alerta(s) deste paciente na tela; recarregue o dashboard")

    if manual:
        input("\n  >> Ligue/reinicie o ESP32 e tecle ENTER quando ele estiver na rede... ")
        argumentos = ["replay", "--porta", porta_serial]
    else:
        argumentos = ["replay", "--porta", porta_serial]

    print("\n  O aparelho vai enviar. Nada será tocado no navegador.\n")
    inicio = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "scripts.esp32_bancada", *argumentos],
        cwd=RAIZ, capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    for linha in r.stderr.splitlines():
        print(f"  {linha}")
    if r.returncode != 0:
        erro("o aparelho não completou o replay")
        return 1

    resultado = json.loads(r.stdout.strip().splitlines()[-1])
    ok(f"aparelho: {resultado['acks']} confirmadas, {resultado['descartes']} descartadas")

    # O alerta aparece assim que a janela fecha; dá alguns segundos ao motor.
    limite = time.time() + 30
    while time.time() < limite and not alertas_do_leito():
        time.sleep(1)
    achados = alertas_do_leito()

    if achados:
        a = achados[0]
        ok(f"alerta na tela em {time.time() - inicio:.0f}s: {PACIENTE_DEMO} — "
           f"{a.get('tipo')} desde {a.get('inicio')} ({a.get('status')})")
        print("\n  \033[1mDiga:\033[0m ninguém tocou no navegador. O dado saiu do sensor,")
        print("  atravessou Wi-Fi, ingestão, filtro e motor, e voltou pela mesma")
        print("  conexão que a tela já mantinha aberta.")
        return 0
    erro("nenhum alerta apareceu para o paciente da demo")
    return 1


def ato2(porta_serial: str, manual: bool) -> int:
    """Queda de energia no meio do envio.

    É o ato com mais densidade de engenharia: reproduz, ao vivo, o defeito que
    este projeto corrigiu — o checkpoint gravava a posição LIDA em vez da
    ENTREGUE, e o replay retomava DEPOIS do evento que nunca chegou, perdendo em
    silêncio justamente a amostra que falhou.
    """
    from scripts.esp32_bancada import CHECKPOINT_GRAVADO, FIM, RETOMANDO, Esp32

    titulo("ATO 2 — CAI A ENERGIA")
    esperadas = amostras_no_arquivo()
    limpar_leito()

    aparelho = abrir_aparelho(porta_serial)
    try:
        acordar(aparelho)
        aparelho.comandar("CMD_START")
        aparelho.esperar(r"\[PACIENTE\] Vinculado a", timeout=90)
        print("\n  \033[1mDiga:\033[0m ele está enviando. Vou cortar a energia no meio.\n")
        aparelho.esperar(r"\[ACK\] seq=5", timeout=180)

        # `[ACK]` não significa "checkpoint gravado": sobre WebSocket quem
        # imprime é o callback do socket, e a gravação vem uma volta de loop
        # depois. Cortar a energia dentro dessa janela pega o SPIFFS no meio da
        # escrita — o aparelho religa e recomeça do zero, o que é correto mas
        # arruinaria a cena.
        aparelho.esperar(CHECKPOINT_GRAVADO, timeout=30)
        parciais = len(Esp32.acks(aparelho.log))
        entregues = grade_do_leito()
        ok(f"{parciais} amostras confirmadas, {entregues} já no banco")

        if manual:
            input("\n  >> ARRANQUE O CABO do ESP32 agora, recoloque, e tecle ENTER... ")
            aparelho.serial.reset_input_buffer()
            from scripts.esp32_bancada import NA_REDE, PRONTO

            aparelho.esperar(PRONTO, timeout=60)
            aparelho.esperar(NA_REDE, timeout=90)
        else:
            print("\n  >> cortando a energia (linha EN)...\n")
            acordar(aparelho, zerar=False)

        # Sem CMD_RESET: tem que RETOMAR.
        aparelho.comandar("CMD_START")
        aparelho.esperar(RETOMANDO, timeout=90)
        ok("o aparelho retomou do checkpoint, não do início")
        aparelho.coletar_ate(FIM, timeout=300)
    finally:
        aparelho.fechar()

    time.sleep(3)
    total = grade_do_leito()
    if total == esperadas:
        ok(f"{total} de {esperadas} amostras no banco — nenhuma perdida, nenhuma duplicada")
        print("\n  \033[1mDiga:\033[0m o checkpoint guarda o que foi ENTREGUE, não o que foi lido.")
        print("  Por isso a amostra que estava em voo quando a energia caiu foi reenviada,")
        print("  e a chave primária da grade recusou a duplicata.")
        return 0
    erro(f"{total} de {esperadas} amostras no banco")
    return 1


def ato3(porta_serial: str) -> int:
    """O servidor cai e volta. O aparelho insiste; nada se perde."""
    from scripts.esp32_bancada import FIM, Esp32

    titulo("ATO 3 — CAI O SERVIDOR")
    esperadas = amostras_no_arquivo()
    limpar_leito()

    aparelho = abrir_aparelho(porta_serial)
    try:
        acordar(aparelho)
        aparelho.comandar("CMD_START")
        aparelho.esperar(r"\[PACIENTE\] Vinculado a", timeout=90)
        aparelho.esperar(r"\[ACK\] seq=3", timeout=180)

        print("\n  \033[1mDiga:\033[0m agora eu derrubo o servidor, com o sensor transmitindo.\n")
        subprocess.run(["docker", "stop", CONTAINER], capture_output=True, text=True)
        ok("container parado")

        # O firmware usa `tentativasMax = 0` (infinito) com backoff limitado:
        # numa ala ninguém está olhando o serial do ESP32 para religá-lo na mão.
        aparelho.esperar(r"\[FALHA\]|\[WS\] Desconectado|\[INFO\] Reenviando", timeout=120)
        ok("o aparelho detectou a queda e começou a insistir")
        aparelho.drenar(8)

        print("\n  >> religando o servidor...\n")
        subprocess.run(["docker", "start", CONTAINER], capture_output=True, text=True)
        limite = time.time() + 120
        while time.time() < limite:
            r = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
                               capture_output=True, text=True)
            if r.stdout.strip() == "healthy":
                break
            aparelho.drenar(2)
        ok("container de volta")

        aparelho.coletar_ate(FIM, timeout=420)
    finally:
        aparelho.fechar()

    time.sleep(3)
    total = grade_do_leito()
    if total == esperadas:
        ok(f"{total} de {esperadas} amostras no banco — a indisponibilidade só atrasou")
        print("\n  \033[1mDiga:\033[0m o dispositivo não desiste. O backoff tem teto, então ele")
        print("  bate no servidor uma vez por minuto até ele voltar — em vez de parar")
        print("  de vez e esperar alguém ir até o leito apertar um botão.")
        return 0
    erro(f"{total} de {esperadas} amostras no banco")
    return 1


def ato4() -> int:
    """A enfermeira está no elevador. Guiado: modo avião é no aparelho dela.

    Único ato que não dá para automatizar de ponta a ponta — e nem deveria: o
    ponto é justamente uma pessoa agindo com a rede fora. O runner verifica o
    desfecho.
    """
    titulo("ATO 4 — A ENFERMEIRA ESTÁ NO ELEVADOR")

    abertos = [a for a in alertas_do_leito() if a.get("status") in (None, "aberto")]
    if not abertos:
        erro("não há alerta aberto para reconhecer")
        aviso("rode antes: python -m scripts.demo ato1 --porta COM3")
        return 1
    ok(f"alerta aberto desde {abertos[0].get('inicio')}")

    print(f"""
  \033[1mNo celular/tablet\033[0m, com a sessão aberta em {base_url()}/ :

    1. ative o MODO AVIÃO
    2. toque em "Reconhecer" no alerta de {PACIENTE_DEMO}
    3. mostre que a tela aceitou — a ação foi para a fila local
    4. desative o modo avião

  \033[1mDiga:\033[0m Wi-Fi hospitalar cai em corredor, escada e elevador. Não é caso
  de borda, é a topologia. Sem a fila, quem marcou quatro pacientes numa zona
  morta perdia os quatro — e sem saber quais.
""")
    input("  >> tecle ENTER depois de tirar do modo avião... ")

    print("\n  aguardando a fila drenar...")
    limite = time.time() + 90
    while time.time() < limite:
        reconhecidos = [a for a in alertas_do_leito() if a.get("status") == "reconhecido"]
        if reconhecidos:
            ok("a ação registrada offline chegou ao servidor")
            print("\n  \033[1mDiga:\033[0m o reenvio é seguro porque o `alert_id` é chave natural")
            print("  (paciente, início) e o servidor é idempotente — reconhecer duas vezes")
            print("  é um no-op, não um registro clínico duplicado.")
            return 0
        time.sleep(3)
    erro("a ação não chegou ao servidor em 90s")
    aviso("estados vistos: " + ", ".join(sorted({str(a.get('status')) for a in alertas_do_leito()})))
    return 1


def _recriar_com_token(token: str) -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", "app"],
        cwd=RAIZ, capture_output=True, text=True,
        env={**os.environ, "UPP_DEVICE_TOKEN": token},
    )
    limite = time.time() + 120
    while time.time() < limite:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
                           capture_output=True, text=True)
        if r.stdout.strip() == "healthy":
            return
        time.sleep(2)
    raise SystemExit("o container não voltou a ficar saudável")


def ato5(porta_serial: str) -> int:
    """Alguém errou o token. O aparelho insiste em vez de descartar."""
    from scripts.esp32_bancada import FIM, Esp32

    titulo("ATO 5 — ALGUÉM ERROU A CREDENCIAL")
    esperadas = amostras_no_arquivo()
    limpar_leito()

    print("\n  >> configurando o servidor para exigir um token que o aparelho não tem...\n")
    _recriar_com_token("segredo-que-o-aparelho-nao-conhece")
    ok("servidor exigindo credencial")

    aparelho = abrir_aparelho(porta_serial)
    try:
        acordar(aparelho)
        aparelho.comandar("CMD_START")
        aparelho.esperar(r"ws error=invalid_device_token|HTTP=401|status=401", timeout=120)
        recusas = aparelho.drenar(15)
        if Esp32.acks(recusas) or Esp32.descartes(recusas):
            erro("houve ACK ou DESCARTE com credencial inválida")
            return 1
        contas = aparelho.status()
        ok(f"recusado: {contas['falhas']} falhas, {contas['descartados']} descartes, "
           f"{contas['enviados']} enviados")
        print("\n  \033[1mDiga:\033[0m ele NÃO descarta. 401 é erro de configuração, não amostra")
        print("  ruim — descartar aqui jogaria fora dado clínico por engano de operação.\n")

        print("  >> alguém corrige o .env e reinicia...\n")
        _recriar_com_token("")
        aparelho.coletar_ate(FIM, timeout=420)
    finally:
        aparelho.fechar()

    time.sleep(3)
    total = grade_do_leito()
    if total == esperadas:
        ok(f"{total} de {esperadas} amostras no banco — a recusa só atrasou")
        print("\n  \033[1mDiga:\033[0m o aparelho se recuperou sozinho. Sem visita ao leito,")
        print("  sem reflash, sem ninguém perceber que ficou parado.")
        return 0
    erro(f"{total} de {esperadas} amostras no banco")
    return 1


def roteiro() -> None:
    titulo("ROTEIRO")
    print(f"""
  Antes  : python -m scripts.demo preparar --porta COM3
           python -m scripts.demo checar   --porta COM3
  Tela   : {base_url()}/   (Ctrl+Shift+R antes de comecar)
  Depois : python -m scripts.demo perfil-bancada --porta COM3

  Cada ato cronometra a si mesmo e imprime a duracao no fim — ensaie uma vez e
  use os numeros reais para pedir tempo na banca, em vez de estimar.

  Cada ato limpa o leito e reinicia o container antes de comecar, entao pode
  ser repetido a vontade e rodado em qualquer ordem — menos o ato 4, que
  precisa de um alerta aberto (rode o ato 1 antes).

  ATO 1  O dado e real
         python -m scripts.demo ato1 --porta COM3
         Alerta nasce num sensor fisico e aparece sem ninguem tocar na tela.

  ATO 2  Cai a energia
         python -m scripts.demo ato2 --porta COM3 [--manual]
         Religa e retoma da amostra exata. Com --manual, voce arranca o cabo.

  ATO 3  Cai o servidor
         python -m scripts.demo ato3 --porta COM3
         O aparelho insiste com backoff; nada se perde.

  ATO 4  A enfermeira esta no elevador
         python -m scripts.demo ato4
         Modo aviao no celular, reconhece, volta a rede, sincroniza.

  ATO 5  Alguem errou a credencial
         python -m scripts.demo ato5 --porta COM3
         401 nao e amostra ruim: ele insiste e se recupera sozinho.

  Fechamento: rode a suite. Tudo que a banca viu, o CI verifica a cada push.
""")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Demonstração ao vivo do sistema")
    p.add_argument("acao", choices=["checar", "preparar", "perfil-demo", "perfil-bancada",
                                    "ato1", "ato2", "ato3", "ato4", "ato5", "roteiro"])
    p.add_argument("--porta", default=os.getenv("UPP_ESP32_PORT"), help="serial do ESP32 (ex.: COM3)")
    p.add_argument("--manual", action="store_true",
                   help="espera você mexer no aparelho em vez de comandá-lo")
    a = p.parse_args(argv)

    if a.acao == "checar":
        return 1 if checar(a.porta) else 0
    if a.acao == "preparar":
        preparar(a.porta)
        return 0
    if a.acao == "perfil-demo":
        aplicar_perfil("demo", a.porta)
        return 0
    if a.acao == "perfil-bancada":
        aplicar_perfil("bancada", a.porta)
        return 0
    if a.acao == "roteiro":
        roteiro()
        return 0
    if a.acao.startswith("ato"):
        if a.acao != "ato4" and not a.porta:
            print("informe --porta (ou UPP_ESP32_PORT)", file=sys.stderr)
            return 2
        comecou = time.time()
        codigo = {
            "ato1": lambda: ato1(a.porta, a.manual),
            "ato2": lambda: ato2(a.porta, a.manual),
            "ato3": lambda: ato3(a.porta),
            "ato4": ato4,
            "ato5": lambda: ato5(a.porta),
        }[a.acao]()
        # Cronometrado, e nao estimado: e este numero que diz quanto tempo pedir
        # na banca. O ato 4 inclui o tempo em que alguem esteve mexendo no
        # celular, entao so o dele nao serve para planejamento.
        titulo(f"{a.acao} levou {time.time() - comecou:.0f}s")
        return codigo
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
