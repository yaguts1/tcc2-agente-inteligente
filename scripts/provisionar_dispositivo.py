#!/usr/bin/env python3
"""Emite, revoga e confere a credencial de um dispositivo.

O ROADMAP registrava a lacuna assim: "`UPP_DEVICE_TOKEN` não está definido no
`.env` atual e nenhum ESP32 foi provisionado: a ingestão aceita qualquer
origem". O servidor já tinha tudo — `emitir`, `revogar`, `validar`, e as rotas
sob sessão de admin. O que faltava era o ato de provisionar, e a ponte para o
`config.h` que vai ser compilado para dentro do aparelho.

POR QUE UM TOKEN POR APARELHO, E NÃO UM DA FROTA
------------------------------------------------
Estes aparelhos ficam presos ao leito, acessíveis, num prédio com circulação de
público. Com um segredo único, um aparelho arrancado da parede entrega a
credencial da frota inteira — e revogar exigiria reflashear todos, ou seja, na
prática nunca se revogaria.

Com token por aparelho, revogar é uma chamada. E devolver o acesso exige tocar
no aparelho, que é exatamente a propriedade que se quer: quem perdeu o
dispositivo não o traz de volta remotamente.

A REGRA QUE TORNA ISSO SEGURO (`interface/dependencies.py`)
------------------------------------------------------------
1. dispositivo JÁ PROVISIONADO responde só pela credencial dele — não aceita o
   token global. "Provisionado" inclui REVOGADO;
2. dispositivo sem token próprio cai no global, se houver;
3. sem nenhum dos dois, a verificação fica desligada.

Ou seja: provisionar um aparelho o TIRA do regime frouxo, mesmo com o
`UPP_DEVICE_TOKEN` global vazio — que é o estado desta instalação.

    python -m scripts.provisionar_dispositivo emitir DEV-001 --gravar-config
    python -m scripts.provisionar_dispositivo estado DEV-001
    python -m scripts.provisionar_dispositivo revogar DEV-001

Por padrão age no CONTAINER (`upp_app`), que é onde o banco de verdade está.
`--local` usa o `UPP_DB_PATH` desta máquina.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "firmware" / "esp32_replay" / "config.h"
CONTAINER = "upp_app"


def _executar(codigo: str, local: bool) -> str:
    """Roda um trecho contra o banco, dentro do container ou aqui."""
    if local:
        r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True)
    else:
        r = subprocess.run(
            ["docker", "exec", CONTAINER, "python", "-c", codigo],
            capture_output=True, text=True,
        )
    if r.returncode != 0:
        raise SystemExit(f"falhou: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


_PREAMBULO = (
    "import os\n"
    "from interface.repositories import device_tokens as dt\n"
    "db=os.getenv('UPP_DB_PATH','/data/dados.db')\n"
)


def emitir(device_id: str, local: bool) -> str:
    """Devolve o token em TEXTO PURO. Sai daqui uma vez e nunca mais."""
    return _executar(
        _PREAMBULO + f"print(dt.emitir(db,{device_id!r},criado_por='provisionar_dispositivo'))",
        local,
    ).splitlines()[-1]


def revogar(device_id: str, local: bool) -> bool:
    saida = _executar(_PREAMBULO + f"print(dt.revogar(db,{device_id!r}))", local)
    return saida.splitlines()[-1].strip() == "True"


def estado(device_id: str, local: bool) -> dict:
    saida = _executar(
        _PREAMBULO
        + "import json\n"
        + f"print(json.dumps({{'provisionado':dt.foi_provisionado(db,{device_id!r}),"
        + f"'registros':[x for x in dt.listar(db) if x.get('device_id')=={device_id!r}]}}))",
        local,
    )
    import json

    return json.loads(saida.splitlines()[-1])


def gravar_no_config(token: str) -> None:
    """Escreve o token no `config.h`, que é git-ignored.

    O aparelho só passa a apresentar a credencial depois de REGRAVADO — o
    `config.h` é compilado para dentro dele. Emitir sem regravar deixa o
    dispositivo provisionado no servidor e mudo na prática: ele passa a ser
    exigido a apresentar um token que ainda não tem, e todo envio é recusado.
    """
    if not CONFIG.exists():
        raise SystemExit(f"{CONFIG} não existe — copie de config.example.h")
    texto = CONFIG.read_text(encoding="utf-8")
    novo, n = re.subn(
        r'^(\s*#define\s+DEVICE_TOKEN\s+)"[^"]*"', rf'\g<1>"{token}"', texto, flags=re.M
    )
    if n == 0:
        raise SystemExit("não achei #define DEVICE_TOKEN no config.h")
    CONFIG.write_text(novo, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Credencial de dispositivo (ESP32)")
    p.add_argument("acao", choices=["emitir", "revogar", "estado"])
    p.add_argument("device_id")
    p.add_argument("--local", action="store_true", help="usa o banco desta máquina, não o container")
    p.add_argument(
        "--gravar-config",
        action="store_true",
        help="escreve o token em firmware/esp32_replay/config.h (exige regravar o aparelho depois)",
    )
    a = p.parse_args(argv)

    if a.acao == "estado":
        info = estado(a.device_id, a.local)
        print(f"{a.device_id}: provisionado={info['provisionado']}")
        for reg in info["registros"]:
            print(f"  {reg}")
        return 0

    if a.acao == "revogar":
        cortou = revogar(a.device_id, a.local)
        print(f"{a.device_id}: {'revogado' if cortou else 'não havia token ativo'}")
        # Revogar NÃO rebaixa o aparelho para o token global: `foi_provisionado`
        # ignora `revogado_em` de propósito. O acesso fica cortado até alguém
        # emitir outro e regravar o dispositivo.
        print("  o aparelho continua PROVISIONADO — não volta a valer o token global")
        return 0

    token = emitir(a.device_id, a.local)
    if a.gravar_config:
        gravar_no_config(token)
        print(f"{a.device_id}: token emitido e gravado em {CONFIG.relative_to(RAIZ)}")
        print("  REGRAVE o aparelho agora, senão ele será recusado:")
        print("  python -m platformio run -d firmware -e websocket -t upload --upload-port COM3")
    else:
        print(f"{a.device_id}: {token}")
        print("  este valor aparece UMA vez; o servidor guarda só o hash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
