#!/usr/bin/env python3
"""Prepara o banco da bancada de E2E do frontend e imprime o caminho dele.

POR QUE UM SCRIPT, E NÃO UMA FIXTURE
------------------------------------
O E2E do frontend roda no Playwright (Node), mas o banco, o esquema, o hash de
senha e as regras de paciente vivem no Python. Reimplementar qualquer uma
dessas coisas em TypeScript criaria uma segunda definição de "usuário válido" —
e a primeira vez que a política de senha mudasse, o harness passaria a testar
uma instalação que não existe.

Então quem prepara é o Python, com as MESMAS funções que a aplicação usa
(`criar_esquema`, `UserRepository`, `criar_paciente`, `passlib.bcrypt`), e o
Playwright só lê o caminho impresso na última linha.

O banco é recriado a cada chamada: um E2E que herda estado do anterior passa a
depender da ordem em que os testes rodaram.

    python -m scripts.preparar_bancada_e2e
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Credenciais fixas da bancada. Não são segredo: este banco é descartável e
# nasce vazio a cada execução. A senha respeita `exigir_senha_forte` — se a
# política endurecer, isto quebra aqui, no preparo, e não como um login que
# falha no meio de um teste de interface.
USUARIO = "bancada"
SENHA = "Bancada#E2E#2026"
CAMA = "C-01"
NOME_PACIENTE = "Paciente da Bancada"
PERFIL = "alto"  # janela_min=60, o mais curto — o alerta de imobilidade sai antes


def preparar(destino: Path | None = None) -> tuple[str, str]:
    """Cria o banco e devolve `(caminho, paciente_id)`."""
    pasta = destino or (RAIZ / ".e2e")
    if pasta.exists():
        shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True, exist_ok=True)
    db_path = pasta / "dados.db"

    # Antes de importar qualquer coisa de `interface`: vários módulos resolvem
    # UPP_DB_PATH no import, e o repositório de usuários é instanciado no import
    # do router de auth.
    os.environ["UPP_DB_PATH"] = str(db_path)
    sys.path.insert(0, str(RAIZ))

    from passlib.hash import bcrypt

    from interface.dao import criar_paciente
    from interface.db_core import criar_esquema
    from interface.repositories.users import UserRepository

    criar_esquema(str(db_path))

    # `role="admin"` explícito: a página /admin é parte do que o E2E navega, e
    # depender do "primeiro usuário vira admin" faria o teste de interface
    # depender de uma regra de cadastro que pode mudar.
    UserRepository(str(db_path)).create(
        USUARIO, bcrypt.hash(SENHA), display_name="Bancada E2E", role="admin"
    )

    ficha = criar_paciente(str(db_path), NOME_PACIENTE, PERFIL, cama_id=CAMA)
    return str(db_path), ficha["paciente_id"]


def amostras_de_imobilidade(paciente_id: str, minutos: int = 90, passo_min: int = 5) -> list[dict]:
    """Série que fecha a janela de imobilidade do perfil `alto` (60 min).

    Mesma postura o tempo todo, terminando AGORA: eventos fora de ±24 h são
    ignorados pelo pipeline, e um alerta ancorado no futuro não aparece na tela.

    Não grava nada — devolve os payloads para o teste enviar por HTTP, porque o
    ponto do E2E é justamente atravessar a ingestão de verdade.
    """
    fim = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    inicio = fim - timedelta(minutes=minutos)
    total = minutos // passo_min
    return [
        {
            "device_id": "BANCADA-E2E",
            "paciente_id": paciente_id,
            "cama_id": CAMA,
            "postura": "supino",
            "confianca": 0.95,
            "amostra_ms": passo_min * 60 * 1000,
            "ts_utc": (inicio + timedelta(minutes=i * passo_min)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for i in range(total)
    ]


if __name__ == "__main__":
    import json

    caminho, paciente_id = preparar()

    # As amostras saem em arquivo, e não reescritas em TypeScript, pelo mesmo
    # motivo do resto deste script: `EventPayload` tem `extra="forbid"`, e uma
    # segunda definição do payload em outra linguagem é uma segunda coisa para
    # divergir do schema. Já aconteceu uma vez neste projeto — ver o cabeçalho
    # de `gerar_eventos_esp32.py`.
    amostras = Path(caminho).parent / "amostras_imobilidade.json"
    amostras.write_text(
        json.dumps(amostras_de_imobilidade(paciente_id), ensure_ascii=False), encoding="utf-8"
    )

    # Formato `chave=valor`, uma por linha: o Playwright lê com split, sem
    # precisar de JSON nem de parser.
    print(f"db={caminho}")
    print(f"amostras={amostras}")
    print(f"paciente_id={paciente_id}")
    print(f"usuario={USUARIO}")
    print(f"senha={SENHA}")
    print(f"cama={CAMA}")
