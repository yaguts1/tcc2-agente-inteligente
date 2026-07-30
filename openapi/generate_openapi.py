"""Gera o spec OpenAPI da API, acrescido do schema `FrontendAlert` que a SPA
espera.

O artefato versionado fica em `openapi/openapi.json` e e conferido por
`tests/test_openapi_versionado.py`: spec commitado que ninguem confere vira
documentacao que mente, e mentira em contrato de API custa mais caro que a
ausencia dele — quem integra confia e so descobre no runtime.

Regenerar apos mexer em rota ou schema:

    python -m openapi.generate_openapi

So le `interface.web.app.openapi()`; nao altera comportamento de runtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Caminho do artefato versionado, para o gerador e o teste falarem do mesmo
# arquivo em vez de repetirem a string.
CAMINHO_PADRAO = Path(__file__).resolve().parent / "openapi.json"


def generate_openapi(output: Path | None = None) -> dict[str, Any]:
    # `APP_PREFIX` e detalhe de IMPLANTACAO, nao do contrato: em producao a app
    # sobe sob `/TCC` (ver docker-compose.yml) e toda rota do spec sairia
    # `/TCC/api/...`. Sem fixar aqui, o arquivo gerado dependeria do ambiente de
    # quem rodou o comando, e a conferencia acusaria diferenca a cada maquina.
    # O contrato e publicado sem prefixo; quem consome concatena o seu.
    os.environ["APP_PREFIX"] = ""

    # import here to avoid heavy imports at module import time
    from interface.web import app

    spec = app.openapi() or {}

    # O schema de FrontendAlert NAO e mais escrito aqui.
    #
    # Ele era um JSON-Schema a mao, costurado no spec depois de gerado — a
    # mesma forma tinha TRES definicoes independentes (o dict literal do
    # servico, este bloco, e a interface TypeScript), e as tres so coincidiam
    # por disciplina. Ja tinham divergido: aqui `room`/`bed` eram opcionais,
    # no TS eram obrigatorios.
    #
    # Agora `interface/schemas.FrontendAlert` e um modelo pydantic declarado na
    # rota, entao o FastAPI deriva o schema sozinho e este gerador volta a ser
    # so um gerador.

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serializar(spec), encoding="utf-8")

    return spec


def serializar(spec: dict[str, Any]) -> str:
    """Forma canonica do spec em texto.

    Uma unica funcao para gravar e para conferir: se cada lado formatasse do seu
    jeito, a comparacao acusaria diferenca sem que nada da API tivesse mudado.
    Termina com quebra de linha porque e arquivo versionado.
    """
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO_PADRAO
    generate_openapi(out)
    print("Spec OpenAPI gravado em", out)
