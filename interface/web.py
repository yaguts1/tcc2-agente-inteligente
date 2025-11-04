"""App FastAPI/Jinja2 para visualizar e gerenciar alertas.

Execute com:
    uvicorn interface.web:app --reload
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
import random
import string

import structlog
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from interface.api import router as api_router
from interface.api import reconcile_device_events
from interface.endpoints_agenda import router as agenda_router
import asyncio

from interface.dao import (
    atualizar_paciente,
    criar_esquema,
    criar_paciente,
    listar_alertas_abertos,
    listar_documentos,
    listar_fichas_pacientes,
    obter_documento,
    obter_ficha_paciente,
    obter_ficha_por_cama,
    registrar_documento,
    remover_documento,
    selecionar_alertas_janela,
    inserir_timeline_event,
    inserir_timeline_event as _dao_inserir_timeline_event,
    listar_device_events,
    inserir_grade,
    inserir_alertas,
)

from dados_simulados.gerador import (
    gerar_sessao_simulada,
    PerfilPaciente,
)

from modulo_alerta.engine import processar_alertas

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Ensure DB schema available at startup (non-fatal)
    try:
        criar_esquema(DB_PATH)
        logger.info("schema_garantido", db_path=DB_PATH)
    except Exception as exc:  # pragma: no cover - log but do not fail startup
        logger.warning("schema_nao_garantido", motivo=str(exc))

    # Start reconciler background task
    try:
        interval_raw = os.getenv("DEVICE_RECONCILE_INTERVAL", "30")
        interval = max(1, int(interval_raw))
    except Exception:
        interval = 30

    async def _loop() -> None:
        logger.info("reconciler_started", interval=interval)
        while True:
            try:
                result = await reconcile_device_events(None, 100)
                if result and (result.get("processed", 0) or result.get("skipped", 0)):
                    logger.info("reconciler_cycle", processed=result.get("processed"), skipped=result.get("skipped"))
            except asyncio.CancelledError:
                logger.info("reconciler_cancelled")
                raise
            except Exception as exc:
                logger.exception("reconciler_error", motivo=str(exc))
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("reconciler_sleep_cancelled")
                raise

    task = asyncio.create_task(_loop(), name="device_reconciler")
    app.state._reconcile_task = task

    try:
        yield
    finally:
        # cancel reconciler on shutdown
        task = getattr(app.state, "_reconcile_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("reconciler_stopped")

app = FastAPI(title="Monitor de Alertas UPP", lifespan=_lifespan)
app.include_router(api_router)
app.include_router(agenda_router)

# Add Prometheus metrics middleware
from starlette.middleware.base import BaseHTTPMiddleware
from servicos import metricas

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware para coletar métricas Prometheus de todas as requisições."""
    
    async def dispatch(self, request, call_next):
        import time
        start_time = time.time()
        
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        method = request.method
        path = request.url.path
        status = response.status_code
        
        # Simplify path for metrics (remove IDs)
        endpoint = path
        for pattern in ["/api/frontend/alerts/", "/api/pacientes/"]:
            if pattern in path:
                parts = path.split(pattern)
                if len(parts) > 1:
                    endpoint = f"{pattern}{{id}}"
                    break
        
        metricas.registrar_request(method, endpoint, status, duration)
        
        return response

app.add_middleware(PrometheusMiddleware)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Enable CORS for local frontend development and common dev ports
_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
try:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    # do not fail startup if middleware cannot be added for some reason
    pass
# Serve built SPA (if present) under /site-ui. Support multiple possible build locations
# (legacy `site_ui/dist`, or `frontend/build` produced by this repo's Vite config).
_ROOT = Path(__file__).resolve().parents[1]
_candidates = [
    _ROOT / "site_ui" / "dist",
    _ROOT / "frontend" / "build",
    _ROOT / "frontend" / "dist",
    _ROOT / "frontend",
]
SITE_UI_DIST = None
for cand in _candidates:
    # Require at least an index.html file to consider this a valid SPA dist
    if (cand / "index.html").exists():
        SITE_UI_DIST = cand
        break

if SITE_UI_DIST is not None:
    try:
        app.mount("/site-ui", StaticFiles(directory=str(SITE_UI_DIST), html=True), name="site_ui")
    except Exception:
        # Do not fail if static mounting is not possible
        SITE_UI_DIST = None
logger = structlog.get_logger(__name__)

DEFAULT_PACIENTE_PERFIL = "medio"

DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[1] / "paciente_docs"
_env_docs_dir = os.getenv("PACIENTE_DOCS_DIR")
if _env_docs_dir:
    PACIENTE_DOCS_DIR = Path(_env_docs_dir).expanduser()
else:
    PACIENTE_DOCS_DIR = DEFAULT_DOCS_DIR
try:
    PACIENTE_DOCS_DIR = PACIENTE_DOCS_DIR.resolve()
except FileNotFoundError:
    PACIENTE_DOCS_DIR = PACIENTE_DOCS_DIR

try:
    MAX_DOCUMENT_MB = max(1, int(os.getenv("PACIENTE_DOC_MAX_MB", "5")))
except ValueError:
    MAX_DOCUMENT_MB = 5
MAX_DOCUMENT_BYTES = MAX_DOCUMENT_MB * 1024 * 1024

_ROTINAS_SUGESTOES = {
    "baixo": [
        {
            "label": "Mudanca decubito",
            "inicio": "06:00",
            "duracao_min": 30,
            "descricao": "Posicao lateral alternada",
            "ativo": True,
            "sort_order": 0,
        },
        {
            "label": "Alongamento leve",
            "inicio": "10:00",
            "duracao_min": 20,
            "descricao": "Exercicios guiados",
            "ativo": True,
            "sort_order": 1,
        },
        {
            "label": "Higiene",
            "inicio": "14:00",
            "duracao_min": 25,
            "descricao": "Cuidados de higiene",
            "ativo": True,
            "sort_order": 2,
        },
        {
            "label": "Mudanca decubito",
            "inicio": "18:00",
            "duracao_min": 30,
            "descricao": "Reposicionamento",
            "ativo": True,
            "sort_order": 3,
        },
    ],
    "medio": [
        {
            "label": "Mudanca decubito",
            "inicio": "06:00",
            "duracao_min": 30,
            "descricao": "Posicao lateral alternada",
            "ativo": True,
            "sort_order": 0,
        },
        {
            "label": "Alongamento assistido",
            "inicio": "09:30",
            "duracao_min": 20,
            "descricao": "Exercicios assistidos",
            "ativo": True,
            "sort_order": 1,
        },
        {
            "label": "Hidratacao",
            "inicio": "13:30",
            "duracao_min": 15,
            "descricao": "Oferta de liquidos",
            "ativo": True,
            "sort_order": 2,
        },
        {
            "label": "Mudanca decubito",
            "inicio": "17:30",
            "duracao_min": 30,
            "descricao": "Reposicionamento",
            "ativo": True,
            "sort_order": 3,
        },
    ],
    "alto": [
        {
            "label": "Mudanca decubito",
            "inicio": "06:00",
            "duracao_min": 20,
            "descricao": "Reposicionamento com apoio",
            "ativo": True,
            "sort_order": 0,
        },
        {
            "label": "Inspecao pele",
            "inicio": "08:30",
            "duracao_min": 15,
            "descricao": "Checagem de pressao",
            "ativo": True,
            "sort_order": 1,
        },
        {
            "label": "Alongamento assistido",
            "inicio": "12:30",
            "duracao_min": 20,
            "descricao": "Movimentos passivos",
            "ativo": True,
            "sort_order": 2,
        },
        {
            "label": "Mudanca decubito",
            "inicio": "16:30",
            "duracao_min": 20,
            "descricao": "Reposicionamento com apoio",
            "ativo": True,
            "sort_order": 3,
        },
    ],
}

ROTINA_KEY_RE = re.compile(r"^rotinas-(\d+)-(label|inicio|duracao|descricao|ativo|sort)$")

def _rotinas_sugeridas(perfil: str | None) -> List[dict]:
    perfil_norm = (perfil or DEFAULT_PACIENTE_PERFIL).lower()
    base = _ROTINAS_SUGESTOES.get(perfil_norm, _ROTINAS_SUGESTOES[DEFAULT_PACIENTE_PERFIL])
    return [dict(item) for item in base]

def _rotinas_para_editor(rotinas: List[dict] | None) -> List[dict]:
    if not rotinas:
        return []
    itens: List[dict] = []
    for idx, rotina in enumerate(rotinas):
        itens.append(
            {
                "label": str(rotina.get("label", "")),
                "inicio": str(rotina.get("inicio", "")),
                "duracao_min": rotina.get("duracao_min", 30),
                "descricao": rotina.get("descricao") or "",
                "ativo": bool(rotina.get("ativo", True)),
                "sort_order": rotina.get("sort_order", idx),
            }
        )
    return itens

def _montar_paciente_base(
    ficha: dict | None = None,
    documentos: List[dict] | None = None,
) -> dict:
    if ficha is None:
        base: dict[str, Any] = {
            "paciente_id": "",
            "nome": "",
            "perfil": DEFAULT_PACIENTE_PERFIL,
            "cama_id": "",
            "observacoes": "",
            "rotinas": [],
        }
    else:
        base = dict(ficha)
        base.setdefault("paciente_id", "")
        base.setdefault("nome", "")
        base["cama_id"] = str(base.get("cama_id") or "")
        base["perfil"] = str(base.get("perfil") or DEFAULT_PACIENTE_PERFIL)
        base["observacoes"] = base.get("observacoes") or ""
        base["rotinas"] = base.get("rotinas") or []
    base["documentos"] = documentos if documentos is not None else list(base.get("documentos", []))
    return base

def _montar_contexto_formulario(
    request: Request,
    paciente: dict,
    rotinas_editor: List[dict] | None = None,
    *,
    form_error: str | None = None,
    form_success: bool = False,
    usar_rotinas_padrao: bool = False,
) -> Dict[str, Any]:
    perfil = str(paciente.get("perfil", DEFAULT_PACIENTE_PERFIL) or DEFAULT_PACIENTE_PERFIL)
    editor = rotinas_editor if rotinas_editor is not None else _rotinas_para_editor(paciente.get("rotinas"))
    contexto: Dict[str, Any] = {
        "request": request,
        "paciente": paciente,
        "rotinas_sugestao": _rotinas_sugeridas(perfil),
        "rotinas_editor": editor,
        "proximo_indice": len(editor),
        "usar_rotinas_padrao": usar_rotinas_padrao,
        "form_error": form_error,
        "form_success": form_success,
        "documentos": paciente.get("documentos", []),
        "max_document_mb": MAX_DOCUMENT_MB,
    }
    return contexto

def _parse_rotinas_form(form: Any) -> List[dict]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for key, value in form.multi_items():
        match = ROTINA_KEY_RE.match(key)
        if not match:
            continue
        idx, campo = match.groups()
        bucket.setdefault(idx, {})[campo] = value
    rotinas: List[dict] = []
    for idx in sorted(bucket, key=lambda item: int(item)):
        data = bucket[idx]
        label = str(data.get("label") or "").strip()
        inicio = str(data.get("inicio") or "").strip()
        if not label or not inicio:
            continue
        descricao_raw = str(data.get("descricao") or "").strip()
        try:
            duracao_val = int(str(data.get("duracao") or "0").strip() or 0)
        except ValueError:
            duracao_val = 0
        try:
            sort_val = int(str(data.get("sort") or idx))
        except ValueError:
            sort_val = int(idx)
        rotinas.append(
            {
                "label": label,
                "inicio": inicio,
                "duracao_min": duracao_val,
                "descricao": descricao_raw or None,
                "ativo": bool(data.get("ativo")),
                "sort_order": sort_val,
            }
        )
    return rotinas

def _ensure_docs_dir(paciente_id: str) -> Path:
    try:
        PACIENTE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    destino = PACIENTE_DOCS_DIR / paciente_id
    destino.mkdir(parents=True, exist_ok=True)
    return destino

def _make_unique_filename(destino: Path) -> Path:
    if not destino.exists():
        return destino
    stem = destino.stem
    sufixo = destino.suffix or ""
    contador = 2
    while True:
        candidato = destino.with_name(f"{stem}_{contador}{sufixo}")
        if not candidato.exists():
            return candidato
        contador += 1

def _sanitize_filename(nome: str | None) -> str:
    bruto = Path(nome or "documento.pdf").name
    normalizado = unicodedata.normalize("NFKD", bruto).encode("ascii", "ignore").decode("ascii")
    if not normalizado:
        normalizado = "documento.pdf"
    sanitizado = re.sub(r"[^A-Za-z0-9._-]", "_", normalizado)
    if not sanitizado.lower().endswith(".pdf"):
        sanitizado += ".pdf"
    return sanitizado

def _set_hx_trigger(response: Response, event: str, payload: Dict[str, Any] | None = None) -> None:
    if payload is None:
        response.headers["HX-Trigger"] = event
    else:
        response.headers["HX-Trigger"] = json.dumps({event: payload})

def _document_path_from_db(caminho: str) -> Path:
    raw_path = Path(caminho or "")
    if raw_path.is_absolute():
        return raw_path
    try:
        base_resolvida = PACIENTE_DOCS_DIR.resolve()
    except FileNotFoundError:
        base_resolvida = PACIENTE_DOCS_DIR
    candidato = (PACIENTE_DOCS_DIR / raw_path).resolve()
    try:
        candidato.relative_to(base_resolvida)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caminho de documento invalido.",
        ) from exc
    return candidato

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
            # log timeline event for alert close
            try:
                ts_iso = fim_iso
                ts_ms = int(base_now.timestamp() * 1000)
                inserir_timeline_event(DB_PATH, paciente_id, ts_iso, ts_ms, "alert_close", descricao=None, meta={"inicio": inicio})
            except Exception:
                # timeline logging must not break normal flow
                pass
        else:
            conn.execute(
                """
                UPDATE alertas
                SET status = :status
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {"status": status_destino, **params},
            )
            # if this is an acknowledgement, log it in the timeline
            try:
                if str(status_destino).lower() == "reconhecido":
                    base_now = datetime.now().replace(microsecond=0)
                    ts_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
                    ts_ms = int(base_now.timestamp() * 1000)
                    inserir_timeline_event(DB_PATH, paciente_id, ts_iso, ts_ms, "alert_ack", descricao=None, meta={"inicio": inicio})
            except Exception:
                pass

def _resolver_indice_rotina(request: Request, index_raw: str | None) -> int:
    candidatos = [
        index_raw,
        request.query_params.get("rotinas_next_index"),
    ]
    for candidato in candidatos:
        if candidato is None:
            continue
        try:
            index_cast = int(candidato)
            if index_cast >= 0:
                return index_cast
        except ValueError:
            continue

    maiores_indices = [
        int(match.group(1))
        for chave, _ in request.query_params.multi_items()
        if (match := ROTINA_KEY_RE.match(chave))
    ]
    if maiores_indices:
        return max(maiores_indices) + 1
    return 0

def paciente_documento_download(documento_id: int) -> FileResponse:
    registro = obter_documento(DB_PATH, documento_id)
    if registro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento nao encontrado.")
    caminho_fs = _document_path_from_db(registro.get("caminho", ""))
    if not caminho_fs.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo nao encontrado.")
    return FileResponse(
        caminho_fs,
        media_type="application/pdf",
        filename=registro.get("nome_arquivo", "documento.pdf"),
    )

@app.get("/api/alertas")
def api_alertas() -> List[dict]:
    """Retorna alertas em aberto no formato JSON."""
    return listar_alertas_abertos(DB_PATH)

@app.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}
