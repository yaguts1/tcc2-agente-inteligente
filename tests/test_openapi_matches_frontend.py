"""Test that the generated OpenAPI spec contains the FrontendAlert schema and
that the /api/frontend/alerts GET operation returns an array of that schema.
"""
from __future__ import annotations

from pathlib import Path

from openapi.generate_openapi import generate_openapi


def test_openapi_includes_frontend_alert_schema(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    spec = generate_openapi(out)

    # ensure components.schemas.FrontendAlert exists
    comps = spec.get("components", {})
    schemas = comps.get("schemas", {})
    assert "FrontendAlert" in schemas, "FrontendAlert schema missing from OpenAPI components"

    # ensure path /api/frontend/alerts GET references array of FrontendAlert
    paths = spec.get("paths", {})
    assert "/api/frontend/alerts" in paths, "/api/frontend/alerts missing in OpenAPI paths"
    get_op = paths["/api/frontend/alerts"].get("get")
    assert get_op is not None, "GET operation missing for /api/frontend/alerts"
    responses = get_op.get("responses", {})
    resp200 = responses.get("200")
    assert resp200 is not None, "200 response missing for /api/frontend/alerts GET"
    content = resp200.get("content", {})
    app_json = content.get("application/json")
    assert app_json is not None, "application/json response content missing"
    schema = app_json.get("schema")
    assert schema is not None, "schema missing in response content"
    assert schema.get("type") == "array", "Expected response schema to be an array"
    items = schema.get("items")
    assert isinstance(items, dict) and items.get("$ref") == "#/components/schemas/FrontendAlert", "Response items must reference FrontendAlert"
