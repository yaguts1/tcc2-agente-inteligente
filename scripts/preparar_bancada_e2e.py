#!/usr/bin/env python3
"""Prepara o banco da bancada de E2E do frontend e descreve o que criou.

POR QUE UM SCRIPT, E NÃO UMA FIXTURE
------------------------------------
O E2E do frontend roda no Playwright (Node), mas o banco, o esquema, o hash de
senha e as regras de paciente vivem no Python. Reimplementar qualquer uma
dessas coisas em TypeScript criaria uma segunda definição de "usuário válido" —
e a primeira vez que a política de senha mudasse, o harness passaria a testar
uma instalação que não existe.

Então quem prepara é o Python, com as MESMAS funções que a aplicação usa
(`criar_esquema`, `UserRepository`, `criar_paciente`, `passlib.bcrypt`), e o
Playwright só lê o JSON descrito abaixo.

UM PACIENTE POR SPEC
--------------------
Cada spec que precisa fazer nascer um alerta ganha o próprio leito. O motor não
reabre alerta já aberto e respeita cooldown: duas specs disputando o mesmo
paciente ficariam acopladas à ordem de execução — a segunda passaria só porque
a primeira rodou antes, e sozinha falharia. Leitos separados tornam cada spec
independente e a suíte reordenável.

O banco é recriado a cada chamada: um E2E que herda estado do anterior passa a
depender da ordem em que os testes rodaram.

    python -m scripts.preparar_bancada_e2e
"""

from __future__ import annotations

import json
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

# `perfil=alto` em todos: janela_min=60 é a mais curta, então o alerta de
# imobilidade nasce com a série mais curta possível — menos amostras para
# enviar, suíte mais rápida.
PERFIL = "alto"

# (apelido, cama, nome). O apelido é como a spec pede o seu leito.
#
# Os NOMES não podem conter palavra que apareça em botão da interface. A
# primeira versão usava "Paciente Reconhecer", e o botão "Assumir Paciente
# Reconhecer" passou a casar com o seletor do botão "Reconhecer" — dois
# elementos para o mesmo locator, e uma falha que parecia da tela e era do dado
# de teste.
LEITOS = [
    ("tempo_real", "C-01", "Ana Ribeiro"),
    ("reconhecer", "C-02", "Bruno Salles"),
    ("offline", "C-03", "Carla Nunes"),
]


def amostras_de_imobilidade(
    paciente_id: str, cama: str, minutos: int = 70, passo_min: int = 5
) -> list[dict]:
    """Série que fecha a janela de imobilidade do perfil `alto` (60 min).

    70 minutos, e não mais: com janela de 60 e cooldown de 15, uma série de 90
    fecha DUAS janelas e abre dois alertas para o mesmo paciente. Não é defeito
    — é o motor fazendo o que deve —, mas deixa duas linhas iguais na tela, e
    toda asserção sobre "a linha do paciente" vira ambígua. Com 70, a spec pode
    afirmar `toHaveCount(1)`, que é uma verificação de verdade em vez de um
    `.first()` escondendo a dúvida.

    Mesma postura o tempo todo, terminando AGORA: eventos fora de ±24 h são
    ignorados pelo pipeline, e um alerta ancorado no futuro não aparece na tela.

    Não grava nada — devolve os payloads para a spec enviar por HTTP, porque o
    ponto do E2E é justamente atravessar a ingestão de verdade.
    """
    fim = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    inicio = fim - timedelta(minutes=minutos)
    return [
        {
            # UM DISPOSITIVO POR LEITO — não um só para a bancada inteira.
            #
            # O servidor resolve de quem é a amostra pelo DISPOSITIVO (ele é
            # quem está preso ao leito), não pelo `paciente_id` do payload. Com
            # um `device_id` compartilhado, as amostras dos outros leitos eram
            # atribuídas ao primeiro paciente e sumiam na PK da `grade` — e
            # **todas as requisições respondiam 2xx**. O sintoma aparecia longe
            # dali: a segunda spec esperava um alerta que nunca ia nascer.
            "device_id": f"BANCADA-{cama}",
            "paciente_id": paciente_id,
            "cama_id": cama,
            "postura": "supino",
            "confianca": 0.95,
            "amostra_ms": passo_min * 60 * 1000,
            "ts_utc": (inicio + timedelta(minutes=i * passo_min)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for i in range(minutos // passo_min)
    ]


def preparar(destino: Path | None = None) -> dict:
    """Cria o banco e devolve a descrição da bancada."""
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

    leitos = {}
    for apelido, cama, nome in LEITOS:
        ficha = criar_paciente(str(db_path), nome, PERFIL, cama_id=cama)
        leitos[apelido] = {
            "paciente_id": ficha["paciente_id"],
            "nome": nome,
            "cama": cama,
            # As amostras saem daqui, e não reescritas em TypeScript, pelo mesmo
            # motivo do resto deste script: `EventPayload` tem `extra="forbid"`,
            # e uma segunda definição do payload em outra linguagem é uma
            # segunda coisa para divergir do schema. Já aconteceu neste projeto
            # — ver o cabeçalho de `gerar_eventos_esp32.py`.
            "amostras": amostras_de_imobilidade(ficha["paciente_id"], cama),
        }

    return {"db": str(db_path), "usuario": USUARIO, "senha": SENHA, "leitos": leitos}


if __name__ == "__main__":
    bancada = preparar()
    descricao = Path(bancada["db"]).parent / "bancada.json"
    descricao.write_text(json.dumps(bancada, ensure_ascii=False), encoding="utf-8")
    # Única linha no stdout: o caminho do JSON. O resto o Playwright lê do
    # arquivo, que aguenta estrutura aninhada sem inventar formato.
    print(descricao)
