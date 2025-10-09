"""App FastAPI/Jinja2 para visualizar e gerenciar alertas.

Execute com:
    uvicorn interface.web:app --reload
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from interface.dao import criar_esquema, listar_alertas_abertos, selecionar_alertas_janela

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

app = FastAPI(title="Monitor de Alertas UPP")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _duracao_em_minutos(inicio_iso: str) -> float:
    inicio = datetime.fromisoformat(inicio_iso[:19])
    return round((datetime.now().replace(microsecond=0) - inicio).total_seconds() / 60.0, 2)


def _parse_iso_naive(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor[:19])
    except ValueError:
        return None


def _resolver_horas_param(request: Request) -> int | None:
    valor = request.query_params.get("horas")
    if valor is None:
        return 24
    valor = valor.strip()
    if not valor:
        return 24
    if valor.lower() in {"all", "todos", "none"}:
        return None
    try:
        return int(valor)
    except ValueError:
        return 24


def _resolver_now_param(request: Request) -> tuple[datetime, str]:
    raw = request.query_params.get("now")
    if raw:
        raw = raw.strip()
        if raw:
            try:
                parsed = datetime.fromisoformat(raw[:19])
            except ValueError:
                parsed = None
            else:
                parsed = parsed.replace(microsecond=0)
                return parsed, parsed.strftime("%Y-%m-%dT%H:%M:%S")
    agora = datetime.now().replace(microsecond=0)
    return agora, agora.strftime("%Y-%m-%dT%H:%M:%S")


def _coletar_alertas(
    request: Request,
) -> tuple[List[dict], int | None, datetime, str, str | None, str | None]:
    horas = _resolver_horas_param(request)
    now_dt, now_iso = _resolver_now_param(request)
    pid = request.query_params.get("pid")
    rate = request.query_params.get("rate")
    alertas = selecionar_alertas_janela(DB_PATH, horas)
    if pid:
        alertas = [alerta for alerta in alertas if alerta.get("paciente_id") == pid]
    return alertas, horas, now_dt, now_iso, rate, pid


def _carregar_alertas_para_view(
    request: Request,
) -> tuple[List[dict], int | None, str, str | None, str | None]:
    alertas, horas, now_dt, now_iso, rate, pid = _coletar_alertas(request)
    visiveis: List[dict] = []
    for alerta_raw in alertas:
        inicio_dt = _parse_iso_naive(alerta_raw.get("inicio"))
        fim_dt = _parse_iso_naive(alerta_raw.get("fim"))
        if inicio_dt is None:
            continue
        fim_limite = fim_dt if fim_dt is not None else datetime.max
        if not (inicio_dt <= now_dt < fim_limite):
            continue
        fim_para_dur = fim_dt if fim_dt and fim_dt < now_dt else now_dt
        tempo_min = max(0.0, (fim_para_dur - inicio_dt).total_seconds() / 60.0)
        alerta = dict(alerta_raw)
        alerta["tempo_decorrido_min"] = round(tempo_min, 2)
        visiveis.append(alerta)
    return visiveis, horas, now_iso, rate, pid


def _montar_timeline_context(alertas: List[dict], now_dt: datetime) -> Dict[str, object]:
    entries: List[Tuple[dict, datetime, datetime]] = []
    for alerta in alertas:
        inicio_dt = _parse_iso_naive(alerta.get("inicio"))
        if inicio_dt is None:
            continue
        fim_dt = _parse_iso_naive(alerta.get("fim"))
        if fim_dt is None:
            fim_dt = now_dt if now_dt >= inicio_dt else inicio_dt + timedelta(minutes=1)
        if fim_dt < inicio_dt:
            fim_dt = inicio_dt
        entries.append((alerta, inicio_dt, fim_dt))

    if not entries:
        fallback_end = now_dt + timedelta(minutes=1)
        return {
            "events": [],
            "min_ms": int(now_dt.timestamp() * 1000),
            "max_ms": int(fallback_end.timestamp() * 1000),
            "current_ms": int(now_dt.timestamp() * 1000),
            "cursor_pct": 0.0,
            "window_start": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": fallback_end.strftime("%Y-%m-%d %H:%M:%S"),
        }

    timeline_start = min(min(inicio for _, inicio, _ in entries), now_dt)
    timeline_end = max(max(fim for _, _, fim in entries), now_dt)
    if timeline_end <= timeline_start:
        timeline_end = timeline_start + timedelta(minutes=1)

    min_ms = int(timeline_start.timestamp() * 1000)
    max_ms = int(timeline_end.timestamp() * 1000)
    range_ms = max(1, max_ms - min_ms)

    events: List[dict] = []
    for alerta, inicio_dt, fim_dt in entries:
        start_ms = max(min_ms, int(inicio_dt.timestamp() * 1000))
        end_ms = int(fim_dt.timestamp() * 1000)
        if end_ms < start_ms:
            end_ms = start_ms
        start_pct = max(0.0, min(100.0, ((start_ms - min_ms) / range_ms) * 100.0))
        end_pct = max(start_pct, min(100.0, ((end_ms - min_ms) / range_ms) * 100.0))
        width_pct = max(0.5, end_pct - start_pct)
        width_pct = min(width_pct, 100.0 - start_pct)
        tooltip = (
            f"Paciente {alerta.get('paciente_id', '')} - {alerta.get('status', '').upper()}\n"
            f"{alerta.get('inicio', '-') } -> {alerta.get('fim', '-') or '-'}"
        )
        events.append(
            {
                "status": alerta.get("status", "aberto"),
                "start_pct": round(start_pct, 2),
                "width_pct": round(width_pct, 2),
                "tooltip": tooltip,
            }
        )

    current_ms = int(now_dt.timestamp() * 1000)
    current_ms = max(min_ms, min(max_ms, current_ms))
    cursor_pct = ((current_ms - min_ms) / range_ms) * 100.0

    return {
        "events": events,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "current_ms": current_ms,
        "cursor_pct": round(cursor_pct, 2),
        "window_start": timeline_start.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": timeline_end.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _alterar_status(
    paciente_id: str,
    inicio: str,
    status_destino: str,
    definir_fim: bool = False,
    now_dt: datetime | None = None,
) -> None:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (paciente_id, inicio),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta nao encontrado.")

        params: Dict[str, object] = {"paciente_id": paciente_id, "inicio": inicio}
        if definir_fim:
            base_now = (now_dt or datetime.now()).replace(microsecond=0)
            ini_dt = datetime.fromisoformat(inicio[:19])
            fim_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
            duracao_min = round((base_now - ini_dt).total_seconds() / 60.0, 2)
            conn.execute(
                """
                UPDATE alertas
                SET status = :status, fim = :fim, duracao_min = :duracao_min
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {
                    "status": status_destino,
                    "paciente_id": paciente_id,
                    "inicio": inicio,
                    "fim": fim_iso,
                    "duracao_min": duracao_min,
                },
            )
        else:
            conn.execute(
                """
                UPDATE alertas
                SET status = :status
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {"status": status_destino, **params},
            )


@app.get("/api/alertas")
def api_alertas() -> List[dict]:
    """Retorna alertas em aberto no formato JSON."""
    return listar_alertas_abertos(DB_PATH)


def _render_alertas_fragment(request: Request) -> HTMLResponse:
    alertas_visiveis, horas, now_iso, rate, pid = _carregar_alertas_para_view(request)
    contexto = {
        "request": request,
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
        "horas": horas,
        "now": now_iso,
        "rate": rate,
        "pid": pid,
    }
    return templates.TemplateResponse("partials/alertas_rows.html", contexto)


@app.get("/partials/alertas", response_class=HTMLResponse)
def partial_alertas(request: Request) -> HTMLResponse:
    """Retorna fragmento HTML com linhas da tabela de alertas."""
    return _render_alertas_fragment(request)


@app.get("/partials/timeline", response_class=HTMLResponse)
def partial_timeline(request: Request) -> HTMLResponse:
    """Retorna o fragmento de timeline para navegação temporal."""
    alertas, horas, now_dt, now_iso, rate, pid = _coletar_alertas(request)
    timeline_ctx = _montar_timeline_context(alertas, now_dt)
    contexto = {
        "request": request,
        "events": timeline_ctx["events"],
        "min_ms": timeline_ctx["min_ms"],
        "max_ms": timeline_ctx["max_ms"],
        "current_ms": timeline_ctx["current_ms"],
        "cursor_pct": timeline_ctx["cursor_pct"],
        "window_start": timeline_ctx["window_start"],
        "window_end": timeline_ctx["window_end"],
        "now": now_iso,
        "horas": horas,
        "rate": rate,
        "pid": pid,
    }
    return templates.TemplateResponse("partials/timeline.html", contexto)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Renderiza a página principal com a lista de alertas."""
    alertas_visiveis, horas, now_iso, rate, pid = _carregar_alertas_para_view(request)
    contexto = {
        "request": request,
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
        "horas": horas,
        "now": now_iso,
        "rate": rate,
        "pid": pid,
    }
    return templates.TemplateResponse("index.html", contexto)


@app.post("/alertas/{paciente_id}/{inicio}/reconhecer", response_class=HTMLResponse)
def reconhecer_alerta(request: Request, paciente_id: str, inicio: str) -> HTMLResponse:
    """Atualiza o alerta para o status 'reconhecido'."""
    _alterar_status(paciente_id, inicio, "reconhecido")
    return _render_alertas_fragment(request)


@app.post("/alertas/{paciente_id}/{inicio}/encerrar", response_class=HTMLResponse)
def encerrar_alerta(request: Request, paciente_id: str, inicio: str) -> HTMLResponse:
    """Marca o alerta como encerrado, preenchendo fim e duracao."""
    now_dt, _ = _resolver_now_param(request)
    _alterar_status(paciente_id, inicio, "fechado", definir_fim=True, now_dt=now_dt)
    return _render_alertas_fragment(request)


@app.on_event("startup")
def _init_schema() -> None:
    try:
        criar_esquema(DB_PATH)
    except Exception as exc:  # pragma: no cover - log but do not fail startup
        print(f"[WARN] Nao foi possivel garantir schema do banco: {exc}")
