from fastapi.testclient import TestClient
from interface.web import app
import os
from pathlib import Path

client = TestClient(app)


def test_site_ui_index_serves_html():
    # If the SPA dist folder exists the app should serve it at /site-ui/
    dist = Path(__file__).resolve().parents[1] / "site_ui" / "dist"
    if not dist.exists():
        # nothing to assert in this environment
        return

    resp = client.get("/site-ui/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_root_redirects_to_site_ui_when_dist_present():
    dist = Path(__file__).resolve().parents[1] / "site_ui" / "dist"
    if not dist.exists():
        return

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 307)
    loc = resp.headers.get("location", "")
    assert loc.startswith("/site-ui")


def test_main_asset_present():
    dist = Path(__file__).resolve().parents[1] / "site_ui" / "dist"
    if not dist.exists():
        return

    # asset name known from build
    js_path = "/site-ui/assets/index-BNGwks8H.js"
    resp = client.get(js_path)
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/javascript") or "text/javascript" in resp.headers.get("content-type", "")
