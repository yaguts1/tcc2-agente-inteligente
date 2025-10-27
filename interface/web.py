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
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from interface.api import router as api_router
from interface.api import reconcile_device_events
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
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
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



@app.get("/pacientes", response_class=HTMLResponse)
def pacientes_index(request: Request) -> HTMLResponse:
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
    contexto = {"request": request, "pacientes": fichas}
    return templates.TemplateResponse("pacientes/index.html", contexto)


@app.get("/partials/pacientes/lista", response_class=HTMLResponse)
def pacientes_lista(request: Request) -> HTMLResponse:
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
    contexto = {"request": request, "pacientes": fichas}
    return templates.TemplateResponse("pacientes/partials/lista.html", contexto)


@app.get("/pacientes/form", response_class=HTMLResponse)
def paciente_form_novo(request: Request) -> HTMLResponse:
    paciente = _montar_paciente_base()
    contexto = _montar_contexto_formulario(
        request,
        paciente,
        rotinas_editor=[],
        usar_rotinas_padrao=True,
    )
    return templates.TemplateResponse("pacientes/partials/form.html", contexto)


@app.get("/pacientes/{paciente_id}/form", response_class=HTMLResponse)
def paciente_form_existente(request: Request, paciente_id: str) -> HTMLResponse:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=True)
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado.")
    documentos = listar_documentos(DB_PATH, paciente_id)
    paciente = _montar_paciente_base(ficha, documentos=documentos)
    contexto = _montar_contexto_formulario(
        request,
        paciente,
        rotinas_editor=_rotinas_para_editor(ficha.get("rotinas")),
        usar_rotinas_padrao=False,
    )
    return templates.TemplateResponse("pacientes/partials/form.html", contexto)


@app.post("/pacientes/salvar", response_class=HTMLResponse)
async def paciente_salvar(request: Request) -> HTMLResponse:
    form = await request.form()
    paciente_id = str(form.get("paciente_id") or "").strip()
    nome = str(form.get("nome") or "").strip()
    perfil = str(form.get("perfil") or DEFAULT_PACIENTE_PERFIL).strip().lower() or DEFAULT_PACIENTE_PERFIL
    cama_id = str(form.get("cama_id") or "").strip()
    observacoes = str(form.get("observacoes") or "").strip()
    usar_rotinas_padrao = form.get("usar_rotinas_padrao") is not None

    rotinas_form = _parse_rotinas_form(form)
    if usar_rotinas_padrao:
        rotinas_aplicar = _rotinas_sugeridas(perfil)
        rotinas_editor_view = _rotinas_para_editor(rotinas_aplicar)
    else:
        rotinas_aplicar = rotinas_form
        rotinas_editor_view = _rotinas_para_editor(rotinas_form)

    try:
        if paciente_id:
            ficha = atualizar_paciente(
                DB_PATH,
                paciente_id,
                nome,
                perfil,
                cama_id or None,
                observacoes,
                rotinas_aplicar,
            )
        else:
            ficha = criar_paciente(
                DB_PATH,
                nome,
                perfil,
                cama_id or None,
                observacoes,
                rotinas_aplicar,
            )
            paciente_id = ficha["paciente_id"]
    except (ValueError, LookupError) as exc:
        paciente = _montar_paciente_base(
            {
                "paciente_id": paciente_id,
                "nome": nome,
                "perfil": perfil,
                "cama_id": cama_id,
                "observacoes": observacoes,
                "rotinas": rotinas_editor_view,
            }
        )
        contexto = _montar_contexto_formulario(
            request,
            paciente,
            rotinas_editor=rotinas_editor_view,
            form_error=str(exc),
            usar_rotinas_padrao=usar_rotinas_padrao,
        )
        return templates.TemplateResponse("pacientes/partials/form.html", contexto)

    documentos = listar_documentos(DB_PATH, paciente_id)
    paciente = _montar_paciente_base(ficha, documentos=documentos)
    contexto = _montar_contexto_formulario(
        request,
        paciente,
        rotinas_editor=_rotinas_para_editor(ficha.get("rotinas")),
        form_success=True,
        usar_rotinas_padrao=False,
    )
    response = templates.TemplateResponse("pacientes/partials/form.html", contexto)
    _set_hx_trigger(
        response,
        "paciente-atualizado",
        {"paciente_id": paciente_id, "message": "Ficha salva com sucesso."},
    )
    return response


@app.post("/pacientes/generar", response_class=HTMLResponse)
async def pacientes_gerar(request: Request) -> HTMLResponse:
    """Gera em massa N fichas de paciente para testes.

    Recebe o campo form `gerar_count` (int, 1-500) e opcional `seed` para
    gerar nomes determinísticos. Retorna o mesmo fragmento de formulario
    com um indicador de sucesso e dispara o gatilho HTMX `pacientes-gerados`.
    """
    form = await request.form()
    try:
        count_raw = form.get("gerar_count") or form.get("count") or "0"
        count = int(str(count_raw).strip() or "0")
    except ValueError:
        count = 0
    # clamp count
    if count <= 0:
        count = 0
    if count > 500:
        count = 500

    seed_raw = form.get("seed")
    if seed_raw is not None and str(seed_raw).strip() != "":
        try:
            seed_val = int(str(seed_raw))
        except ValueError:
            seed_val = sum(ord(c) for c in str(seed_raw))
        rnd = random.Random(seed_val)
    else:
        rnd = random.Random()

    # small name lists for generation
    first_names = [
        "Ana",
        "Bruno",
        "Carla",
        "Daniel",
        "Eduarda",
        "Fabio",
        "Gabriela",
        "Henrique",
        "Isabela",
        "Joao",
        "Karen",
        "Lucas",
        "Mariana",
        "Nicolas",
        "Olivia",
        "Paulo",
        "Quezia",
        "Rafael",
        "Sofia",
        "Tiago",
    ]
    last_names = [
        "Silva",
        "Souza",
        "Costa",
        "Santos",
        "Oliveira",
        "Pereira",
        "Rodrigues",
        "Almeida",
        "Nascimento",
        "Lima",
        "Araújo",
        "Fernandes",
        "Gomes",
        "Ribeiro",
        "Martins",
    ]

    perfis = ["baixo", "medio", "alto"]

    # generation options: assign_camas (optional), cama_prefix (optional), cama_start (optional)
    assign_camas_raw = form.get("assign_camas") or form.get("assign_cama")
    assign_camas = str(assign_camas_raw).strip() in {"1", "true", "True", "on"} if assign_camas_raw is not None else False
    cama_prefix = str(form.get("cama_prefix") or "LEITO").strip() or "LEITO"
    try:
        cama_start = int(str(form.get("cama_start") or "1"))
    except Exception:
        cama_start = 1

    created_ids: List[str] = []
    assigned_camas: set[str] = set()
    next_cama_index = cama_start

    def _cama_exists(cama_id: str) -> bool:
        # check DB and local assigned set
        if cama_id in assigned_camas:
            return True
        try:
            existing = obter_ficha_por_cama(DB_PATH, cama_id)
            return existing is not None
        except Exception:
            return False

    for i in range(count):
        nome = f"{rnd.choice(first_names)} {rnd.choice(last_names)}"
        # add a short random suffix to reduce collisions
        if rnd.random() < 0.3:
            nome = f"{nome} {rnd.choice(string.ascii_uppercase)}{rnd.randint(1,99)}"
        perfil = rnd.choice(perfis)

        cama_to_use = None
        if assign_camas:
            # find next available cama id (prefix-###)
            attempts = 0
            while attempts < 10000:
                candidato = f"{cama_prefix}-{next_cama_index:03d}"
                next_cama_index += 1
                attempts += 1
                if not _cama_exists(candidato):
                    cama_to_use = candidato
                    assigned_camas.add(candidato)
                    break
            # if none found, leave cama_to_use None

        try:
            ficha = criar_paciente(DB_PATH, nome, perfil, cama_to_use, "Ficha gerada automaticamente para testes.")
            pid = ficha.get("paciente_id")
            if pid:
                created_ids.append(pid)
        except Exception:
            # ignore single creation errors and continue
            continue

    paciente = _montar_paciente_base()
    contexto = _montar_contexto_formulario(
        request,
        paciente,
        rotinas_editor=[],
        form_success=True,
    )
    response = templates.TemplateResponse("pacientes/partials/form.html", contexto)
    # Notify clients that patients were generated and include IDs (if any)
    _set_hx_trigger(response, "pacientes-gerados", {"count": len(created_ids), "ids": created_ids})
    return response


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


@app.get("/pacientes/rotinas/linha", response_class=HTMLResponse)
def paciente_rotina_linha(request: Request, index: str | None = Query(None)) -> HTMLResponse:
    resolved_index = _resolver_indice_rotina(request, index)
    rotina = {
        "label": "",
        "inicio": "08:00",
        "duracao_min": 30,
        "descricao": "",
        "ativo": True,
        "sort_order": resolved_index,
    }
    contexto = {"request": request, "rotina": rotina, "indice": resolved_index}
    return templates.TemplateResponse("pacientes/partials/rotina_row.html", contexto)


@app.get("/pacientes/{paciente_id}/documentos", response_class=HTMLResponse)
def paciente_documentos_lista(request: Request, paciente_id: str) -> HTMLResponse:
    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {"request": request, "documentos": documentos, "paciente_id": paciente_id}
    return templates.TemplateResponse("pacientes/partials/documentos.html", contexto)


@app.post("/pacientes/{paciente_id}/documentos", response_class=HTMLResponse)
async def paciente_documento_upload(
    request: Request,
    paciente_id: str,
    arquivo: UploadFile = File(...),
    observacao: str | None = Form(None),
) -> HTMLResponse:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id)
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado.")

    conteudo = await arquivo.read(MAX_DOCUMENT_BYTES + 1)
    if len(conteudo) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Arquivo excede limite de {MAX_DOCUMENT_MB} MB.",
        )
    if arquivo.content_type not in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apenas PDF e suportado.")

    nome_arquivo = _sanitize_filename(arquivo.filename)
    destino_dir = _ensure_docs_dir(paciente_id)
    destino_arquivo = _make_unique_filename(destino_dir / nome_arquivo)
    destino_arquivo.write_bytes(conteudo)

    try:
        caminho_registro = destino_arquivo.relative_to(PACIENTE_DOCS_DIR).as_posix()
    except ValueError:
        caminho_registro = str(destino_arquivo)

    observacao_limpa = None
    if observacao is not None:
        obs_trim = observacao.strip()
        observacao_limpa = obs_trim or None

    registrar_documento(DB_PATH, paciente_id, destino_arquivo.name, caminho_registro, observacao_limpa)
    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {"request": request, "documentos": documentos, "paciente_id": paciente_id}
    response = templates.TemplateResponse("pacientes/partials/documentos.html", contexto)
    _set_hx_trigger(
        response,
        "documento-atualizado",
        {"paciente_id": paciente_id, "documento": destino_arquivo.name},
    )
    return response


@app.delete("/pacientes/documentos/{documento_id}", response_class=HTMLResponse)
def paciente_documento_remover(request: Request, documento_id: int) -> HTMLResponse:
    registro = remover_documento(DB_PATH, documento_id)
    if registro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento nao encontrado.")

    paciente_id = registro.get("paciente_id", "")
    caminho = registro.get("caminho")
    if caminho:
        try:
            caminho_fs = _document_path_from_db(caminho)
            if caminho_fs.exists():
                caminho_fs.unlink()
        except HTTPException:
            pass
        except OSError:
            pass

    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {"request": request, "documentos": documentos, "paciente_id": paciente_id}
    response = templates.TemplateResponse("pacientes/partials/documentos.html", contexto)
    _set_hx_trigger(
        response,
        "documento-atualizado",
        {"paciente_id": paciente_id, "removido": documento_id},
    )
    return response


# ============================================================================
# ENDPOINTS DE SIMULAÇÃO (novos)
# ============================================================================

@app.get("/pacientes/{paciente_id}/simulacao-panel", response_class=HTMLResponse)
async def paciente_simulacao_panel(request: Request, paciente_id: str) -> HTMLResponse:
    """Retorna o painel de simulação para um paciente."""
    try:
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if not ficha:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")
        
        contexto = {
            "request": request,
            "paciente_id": paciente_id,
            "perfil": ficha.get("perfil", "medio"),
        }
        return templates.TemplateResponse("pacientes/partials/simulacao_panel.html", contexto)
    except Exception as e:
        logger.exception("simulacao_panel_erro", paciente_id=paciente_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pacientes/{paciente_id}/simular", response_class=HTMLResponse)
async def paciente_simular(
    request: Request,
    paciente_id: str,
) -> HTMLResponse:
    """
    Gera dados simulados para um paciente específico.
    
    Form data:
    - duracao_horas: int (1-72)
    - seed: int (optional, default=42)
    - perfil: str (baixo/medio/alto)
    
    Retorna HTML com feedback + trigger HTMX para recarregar dashboard
    """
    try:
        # 1. Validar paciente existe
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if not ficha:
            contexto = {
                "request": request,
                "success": False,
                "error": "Paciente não encontrado",
            }
            response = templates.TemplateResponse("pacientes/partials/simulacao_feedback.html", contexto)
            return response
        
        # 2. Extrair parâmetros do formulário
        form = await request.form()
        try:
            duracao_horas = min(max(int(form.get("duracao_horas", 24)), 1), 72)
        except (ValueError, TypeError):
            duracao_horas = 24
        
        try:
            seed = int(form.get("seed", 42))
        except (ValueError, TypeError):
            seed = 42
        
        perfil_form = form.get("perfil", ficha.get("perfil", "medio"))
        perfil = str(perfil_form).lower()
        if perfil not in ["baixo", "medio", "alto"]:
            perfil = "medio"
        
        logger.info(
            "simulacao_iniciada",
            paciente_id=paciente_id,
            duracao=duracao_horas,
            seed=seed,
            perfil=perfil,
        )
        
        # 3. Gerar dados simulados
        df_grade, contextos = gerar_sessao_simulada(
            duracao_horas=duracao_horas,
            seed=seed,
            passo_min=5,
            perfil=PerfilPaciente(perfil=perfil),
            incluir_contexto=True,
        )
        df_grade.insert(0, "paciente_id", paciente_id)
        
        # 4. Salvar grade no DB
        inserir_grade(DB_PATH, df_grade)
        logger.info("simulacao_grade_salva", paciente_id=paciente_id, linhas=len(df_grade))
        
        # 5. Processar alertas
        _, alertas = processar_alertas(
            df_grade[["timestamp", "postura"]],
            perfil,
            paciente_id,
        )
        if alertas:
            inserir_alertas(DB_PATH, alertas)
            logger.info("simulacao_alertas_salva", paciente_id=paciente_id, quantidade=len(alertas))
        
        # 6. Retornar feedback com trigger HTMX
        contexto = {
            "request": request,
            "success": True,
            "duracao": duracao_horas,
            "eventos": len(df_grade),
            "alertas": len(alertas),
            "paciente_id": paciente_id,
        }
        response = templates.TemplateResponse("pacientes/partials/simulacao_feedback.html", contexto)
        _set_hx_trigger(response, "simulacao-concluida", {
            "paciente_id": paciente_id,
            "eventos": len(df_grade),
            "alertas": len(alertas),
        })
        logger.info("simulacao_concluida", paciente_id=paciente_id, sucesso=True)
        return response
        
    except Exception as e:
        logger.exception("simulacao_erro", paciente_id=paciente_id, error=str(e))
        contexto = {
            "request": request,
            "success": False,
            "error": str(e),
        }
        response = templates.TemplateResponse("pacientes/partials/simulacao_feedback.html", contexto)
        return response


@app.get("/pacientes/documentos/{documento_id}/download")
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


def _render_alertas_fragment(request: Request) -> HTMLResponse:
    alertas_visiveis, horas, now_iso, rate, pid = _carregar_alertas_para_view(request)
    mode = request.query_params.get("mode") or "live"
    contexto = {
        "request": request,
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
        "horas": horas,
        "now": now_iso,
        "rate": rate,
        "pid": pid,
        "mode": mode,
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
        "mode": request.query_params.get("mode") or "live",
    }
    return templates.TemplateResponse("partials/timeline.html", contexto)


@app.get("/admin/device_events", response_class=HTMLResponse)
def admin_device_events(request: Request) -> HTMLResponse:
    """Admin page showing pending device events and a manual reconcile action."""
    events = listar_device_events(DB_PATH, limit=200)
    contexto = {"request": request, "events": events}
    return templates.TemplateResponse("device_events.html", contexto)


@app.get("/partials/device_events", response_class=HTMLResponse)
def partial_device_events(request: Request) -> HTMLResponse:
    events = listar_device_events(DB_PATH, limit=200)
    contexto = {"request": request, "events": events}
    return templates.TemplateResponse("partials/device_events_rows.html", contexto)


@app.post("/admin/device_events/reconcile", response_class=HTMLResponse)
async def admin_device_events_reconcile(request: Request) -> HTMLResponse:
    """Trigger reconciliation and return updated rows fragment (HTMX target)."""
    # run reconcile (uses api helper imported earlier)
    try:
        result = await reconcile_device_events(None, 200)
    except Exception as exc:
        result = {"processed": 0, "skipped": 0, "error": str(exc)}
    events = listar_device_events(DB_PATH, limit=200)
    response = templates.TemplateResponse("partials/device_events_rows.html", {"request": request, "events": events, "result": result})
    # notify client via HTMX trigger
    try:
        _set_hx_trigger(response, "device-events-reconciled", result)
    except Exception:
        pass
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Renderiza a página principal com a lista de alertas."""
    # If the SPA dist exists, redirect root to /site-ui/ so the new front is shown.
    if SITE_UI_DIST is not None and SITE_UI_DIST.exists():
        # keep a trailing slash so relative asset paths in the SPA work correctly
        return RedirectResponse(url="/site-ui/")

    alertas_visiveis, horas, now_iso, rate, pid = _carregar_alertas_para_view(request)
    contexto = {
        "request": request,
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
        "horas": horas,
        "now": now_iso,
        "rate": rate,
        "pid": pid,
        "mode": request.query_params.get("mode") or "live",
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





@app.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}
