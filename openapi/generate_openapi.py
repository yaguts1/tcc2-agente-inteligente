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
from typing import Any, Dict

# Caminho do artefato versionado, para o gerador e o teste falarem do mesmo
# arquivo em vez de repetirem a string.
CAMINHO_PADRAO = Path(__file__).resolve().parent / "openapi.json"


def generate_openapi(output: Path | None = None) -> Dict[str, Any]:
    # `APP_PREFIX` e detalhe de IMPLANTACAO, nao do contrato: em producao a app
    # sobe sob `/TCC` (ver docker-compose.yml) e toda rota do spec sairia
    # `/TCC/api/...`. Sem fixar aqui, o arquivo gerado dependeria do ambiente de
    # quem rodou o comando, e a conferencia acusaria diferenca a cada maquina.
    # O contrato e publicado sem prefixo; quem consome concatena o seu.
    os.environ["APP_PREFIX"] = ""

    # import here to avoid heavy imports at module import time
    from interface.web import app

    spec = app.openapi() or {}

    # ensure components.schemas exists
    components = spec.setdefault("components", {})
    schemas = components.setdefault("schemas", {})

    # Define the FrontendAlert schema expected by the React app
    frontend_alert_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "patientName": {"type": "string"},
            "room": {"type": "string"},
            "bed": {"type": "string"},
            "lastRepositioning": {"type": ["string", "null"], "format": "date-time"},
            "nextRepositioning": {"type": ["string", "null"], "format": "date-time"},
            "riskLevel": {"type": "string", "enum": ["high", "medium", "low"]},
            "status": {"type": "string", "enum": ["pending", "acknowledged", "completed"]},
        },
        "required": ["id", "patientName", "riskLevel", "status"],
        "additionalProperties": True,
    }

    schemas["FrontendAlert"] = frontend_alert_schema

    # Patch the /api/frontend/alerts GET response to reference this schema
    paths = spec.setdefault("paths", {})
    target = "/api/frontend/alerts"
    if target not in paths:
        paths[target] = {}
    get_op = paths[target].setdefault("get", {})
    responses = get_op.setdefault("responses", {})
    resp200 = responses.setdefault("200", {})
    content = resp200.setdefault("content", {})
    app_json = content.setdefault("application/json", {})
    # set schema to array of FrontendAlert
    app_json["schema"] = {"type": "array", "items": {"$ref": "#/components/schemas/FrontendAlert"}}

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serializar(spec), encoding="utf-8")

    return spec


def serializar(spec: Dict[str, Any]) -> str:
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
