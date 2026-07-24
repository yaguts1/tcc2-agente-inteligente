"""Generate an OpenAPI JSON spec for the app and augment it with a
`FrontendAlert` component schema describing what the SPA expects.

This script is safe to run during tests and will not change app runtime behavior;
it only reads `interface.web.app.openapi()` and writes a JSON file if requested.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def generate_openapi(output: Path | None = None) -> Dict[str, Any]:
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
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)

    return spec


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi/openapi.json")
    spec = generate_openapi(out)
    print("Wrote OpenAPI spec to", out)
