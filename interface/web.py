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
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.templating import Jinja2Templates

from interface.api import router as api_router
from interface.api import reconcile_device_events
from interface.endpoints_agenda import router as agenda_router
import asyncio

from interface.servicos_view import (
    rotinas_sugeridas as _rotinas_sugeridas,
    rotinas_para_editor as _rotinas_para_editor,
    montar_paciente_base as _montar_paciente_base,
    montar_contexto_formulario as _montar_contexto_formulario,
    parse_rotinas_form as _parse_rotinas_form,
    resolver_indice_rotina as _resolver_indice_rotina,
    resolver_now_param as _resolver_now_param,
    coletar_alertas as _coletar_alertas,
    carregar_alertas_para_view as _carregar_alertas_para_view,
    montar_timeline_context as _montar_timeline_context,
    DEFAULT_PACIENTE_PERFIL,
)

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
    selecionar_grade_janela,
    inserir_timeline_event,
    inserir_timeline_event as _dao_inserir_timeline_event,
    listar_device_events,
    inserir_grade,
    inserir_alertas,
    alterar_status_alerta,
)

from dados_simulados.gerador import (
    gerar_sessao_simulada,
    PerfilPaciente,
)

from modulo_alerta.engine import processar_alertas
from configuracao import carregar_configuracao

config = carregar_configuracao()
DB_PATH = config.db_path

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
web_router = APIRouter()
APP_PREFIX = os.getenv("APP_PREFIX", "")

templates = Jinja2Templates(directory="interface/templates")

@web_router.get("/pacientes", response_class=HTMLResponse)
async def pacientes_index(request: Request):
    return templates.TemplateResponse("pacientes/index.html", {"request": request})

@web_router.get("/partials/pacientes/lista", response_class=HTMLResponse)
async def pacientes_lista_partial(request: Request):
    fichas = listar_fichas_pacientes(DB_PATH)
    return templates.TemplateResponse(
        "pacientes/partials/lista.html",
        {"request": request, "pacientes": fichas}
    )

@web_router.get("/pacientes/novo", response_class=HTMLResponse)
async def pacientes_novo(request: Request):
    paciente = _montar_paciente_base(None, None)
    contexto = _montar_contexto_formulario(request, paciente, usar_rotinas_padrao=True, max_document_mb=MAX_DOCUMENT_MB)
    return templates.TemplateResponse("pacientes/partials/form.html", contexto)

@web_router.get("/pacientes/{paciente_id}", response_class=HTMLResponse)
async def pacientes_editar(request: Request, paciente_id: str):
    ficha = obter_ficha_paciente(DB_PATH, paciente_id)
    if not ficha:
        return Response("Paciente nao encontrado", status_code=404)
    documentos = listar_documentos(DB_PATH, paciente_id)
    paciente = _montar_paciente_base(ficha, documentos)
    contexto = _montar_contexto_formulario(request, paciente, max_document_mb=MAX_DOCUMENT_MB)
    return templates.TemplateResponse("pacientes/partials/form.html", contexto)

@web_router.post("/pacientes/generar", response_class=HTMLResponse)
async def pacientes_generar(request: Request):
    form = await request.form()
    try:
        qtd = int(form.get("gerar_count", 5))
    except ValueError:
        qtd = 5
    
    assign_camas = bool(form.get("assign_camas"))
    cama_prefix = str(form.get("cama_prefix") or "CAMA").strip()
    try:
        cama_start = int(form.get("cama_start") or 1)
    except ValueError:
        cama_start = 1

    generated_count = 0
    for i in range(qtd):
        nome = f"Paciente Gerado {random.randint(10000, 99999)}"
        perfil = random.choice(["baixo", "medio", "alto"])
        
        cama_id = ""
        if assign_camas:
            num = cama_start + i
            cama_id = f"{cama_prefix}-{num:03d}"
        else:
             cama_id = f"CAMA-{random.randint(100, 999)}-{random.choice(string.ascii_uppercase)}"

        try:
            criar_paciente(DB_PATH, nome, perfil, cama_id, "", _rotinas_sugeridas(perfil))
            generated_count += 1
        except Exception:
            pass

    fichas = listar_fichas_pacientes(DB_PATH)
    response = templates.TemplateResponse(
        "pacientes/partials/lista.html",
        {"request": request, "pacientes": fichas}
    )
    _set_hx_trigger(response, "pacientes-gerados", {"count": generated_count})
    return response

@web_router.post("/pacientes/salvar", response_class=HTMLResponse)
async def pacientes_salvar(request: Request):
    form = await request.form()
    paciente_id = str(form.get("paciente_id") or "").strip()
    nome = str(form.get("nome") or "").strip()
    perfil = str(form.get("perfil") or DEFAULT_PACIENTE_PERFIL)
    cama_id = str(form.get("cama_id") or "").strip()
    observacoes = str(form.get("observacoes") or "").strip()
    usar_rotinas_padrao = bool(form.get("usar_rotinas_padrao"))

    rotinas = _parse_rotinas_form(form)
    
    # Se for novo e pediu padrao, e nao veio rotinas no form (ou veio vazio), injeta padrao
    if not paciente_id and usar_rotinas_padrao and not rotinas:
        rotinas = _rotinas_sugeridas(perfil)

    try:
        if paciente_id:
            atualizar_paciente(DB_PATH, paciente_id, nome, perfil, cama_id, observacoes, rotinas)
            pid_final = paciente_id
        else:
            pid_final = criar_paciente(DB_PATH, nome, perfil, cama_id, observacoes, rotinas)["paciente_id"]
        
        # Recarrega para confirmacao
        ficha = obter_ficha_paciente(DB_PATH, pid_final)
        documentos = listar_documentos(DB_PATH, pid_final)
        paciente = _montar_paciente_base(ficha, documentos)
        
        contexto = _montar_contexto_formulario(
            request, 
            paciente, 
            form_success=True
        )
        response = templates.TemplateResponse("pacientes/partials/form.html", contexto)
        _set_hx_trigger(response, "paciente-atualizado", {"paciente_id": pid_final})
        return response

    except ValueError as e:
        # Erro de validacao (ex: cama duplicada)
        # Reconstr�i estado do form para mostrar erro
        paciente_erro = {
            "paciente_id": paciente_id,
            "nome": nome,
            "perfil": perfil,
            "cama_id": cama_id,
            "observacoes": observacoes,
            "rotinas": rotinas,
            "documentos": [] # Nao temos como recuperar docs no erro de form facil, ou buscamos do banco se for edicao
        }
        if paciente_id:
             docs_db = listar_documentos(DB_PATH, paciente_id)
             paciente_erro["documentos"] = docs_db

        contexto = _montar_contexto_formulario(
            request, 
            paciente_erro, 
            rotinas_editor=_rotinas_para_editor(rotinas),
            form_error=str(e)
        )
        return templates.TemplateResponse("pacientes/partials/form.html", contexto)

@web_router.get("/pacientes/rotinas/linha", response_class=HTMLResponse)
async def pacientes_rotina_linha(request: Request):
    idx = _resolver_indice_rotina(request, None)
    return templates.TemplateResponse(
        "pacientes/partials/rotina_row.html",
        {"request": request, "indice": idx, "rotina": {"ativo": True, "duracao_min": 30}}
    )

@web_router.post("/pacientes/{paciente_id}/documentos", response_class=HTMLResponse)
async def pacientes_upload_documento(
    request: Request,
    paciente_id: str,
    arquivo: UploadFile = File(...),
    observacao: str = Form("")
):
    try:
        contents = await arquivo.read()
        if len(contents) > MAX_DOCUMENT_BYTES:
             raise HTTPException(413, "Arquivo muito grande")
        
        nome_safe = _sanitize_filename(arquivo.filename)
        destino_dir = _ensure_docs_dir(paciente_id)
        destino_path = _make_unique_filename(destino_dir / nome_safe)
        
        with open(destino_path, "wb") as f:
            f.write(contents)
            
        caminho_relativo = str(destino_path.relative_to(PACIENTE_DOCS_DIR))
        registrar_documento(DB_PATH, paciente_id, nome_safe, caminho_relativo, observacao)
        
        documentos = listar_documentos(DB_PATH, paciente_id)
        response = templates.TemplateResponse(
            "pacientes/partials/documentos.html",
            {"request": request, "documentos": documentos, "paciente": {"paciente_id": paciente_id}}
        )
        _set_hx_trigger(response, "documento-atualizado")
        return response
    except Exception as e:
        logger.error("upload_erro", erro=str(e))
        return Response(f"Erro no upload: {str(e)}", status_code=500)

@web_router.get("/pacientes/documentos/{documento_id}/download")
async def pacientes_download_documento(documento_id: int):
    return paciente_documento_download(documento_id)

@web_router.delete("/pacientes/documentos/{documento_id}")
async def pacientes_remover_documento(request: Request, documento_id: int):
    doc = obter_documento(DB_PATH, documento_id)
    if not doc:
        return Response(status_code=404)
    
    paciente_id = doc["paciente_id"]
    caminho = _document_path_from_db(doc["caminho"])
    
    remover_documento(DB_PATH, documento_id)
    try:
        if caminho.exists():
            os.remove(caminho)
    except OSError:
        pass
        
    documentos = listar_documentos(DB_PATH, paciente_id)
    response = templates.TemplateResponse(
        "pacientes/partials/documentos.html",
        {"request": request, "documentos": documentos, "paciente": {"paciente_id": paciente_id}}
    )
    _set_hx_trigger(response, "documento-atualizado")
    return response

# Add Prometheus metrics middleware
from starlette.middleware.base import BaseHTTPMiddleware
from servicos import metricas

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware para coletar m�tricas Prometheus de todas as requisi��es."""
    
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

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if SITE_UI_DIST and (SITE_UI_DIST / "favicon.ico").exists():
        return FileResponse(str(SITE_UI_DIST / "favicon.ico"))
    return Response(status_code=404)

# Include routers BEFORE mounting static files to ensure API routes take precedence
app.include_router(web_router, prefix=APP_PREFIX)
app.include_router(api_router, prefix=APP_PREFIX)

# Global health check for Docker (outside prefix)
@app.get("/healthz")
def global_health_check() -> Dict[str, str]:
    return {"status": "ok"}

# Serve built SPA (if present) under /TCC/ (APP_PREFIX). Support multiple possible build locations
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
        # Mount at APP_PREFIX to serve at /TCC/
        mount_path = APP_PREFIX if APP_PREFIX else "/"
        app.mount(mount_path, StaticFiles(directory=str(SITE_UI_DIST), html=True), name="site_ui")
    except Exception:
        # Do not fail if static mounting is not possible
        SITE_UI_DIST = None
logger = structlog.get_logger(__name__)

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

@web_router.get("/api/alertas")
def api_alertas() -> List[dict]:
    """Retorna alertas em aberto no formato JSON."""
    return listar_alertas_abertos(DB_PATH)

@web_router.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@web_router.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}

@web_router.get("/partials/alertas", response_class=HTMLResponse)
async def partials_alertas(request: Request):
    visiveis, horas, now_iso, rate, pid = _carregar_alertas_para_view(request, DB_PATH)
    return templates.TemplateResponse(
        "partials/alertas_rows.html",
        {
            "request": request,
            "alertas_abertos": visiveis,
            "now_iso": now_iso,
            "horas": horas,
            "rate": rate,
            "pid": pid,
        },
    )

@web_router.get("/partials/timeline", response_class=HTMLResponse)
async def partials_timeline(request: Request):
    alertas, horas, now_dt, _, _, pid = _coletar_alertas(request, DB_PATH)
    
    # Fetch grade events
    grade = selecionar_grade_janela(DB_PATH, horas)
    if pid:
        grade = [g for g in grade if g.get("paciente_id") == pid]
        
    contexto = _montar_timeline_context(alertas, grade, now_dt)
    contexto["request"] = request
    return templates.TemplateResponse("partials/timeline.html", contexto)

@web_router.post("/alertas/{paciente_id}/{inicio}/encerrar", response_class=HTMLResponse)
async def alertas_encerrar(request: Request, paciente_id: str, inicio: str):
    now_dt, now_iso = _resolver_now_param(request)
    try:
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "fechado", definir_fim=True, now_dt=now_dt)
    except LookupError:
        raise HTTPException(status_code=404, detail="Alerta nao encontrado.")
    
    # Retorna a lista atualizada (HTMX pattern)
    visiveis, horas, _, rate, pid = _carregar_alertas_para_view(request, DB_PATH)
    return templates.TemplateResponse(
        "partials/alertas_rows.html",
        {
            "request": request,
            "alertas_abertos": visiveis,
            "now_iso": now_iso,
            "horas": horas,
            "rate": rate,
            "pid": pid,
        },
    )

@web_router.post("/alertas/{paciente_id}/{inicio}/reconhecer", response_class=HTMLResponse)
async def alertas_reconhecer(request: Request, paciente_id: str, inicio: str):
    now_dt, now_iso = _resolver_now_param(request)
    try:
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido", now_dt=now_dt)
    except LookupError:
        raise HTTPException(status_code=404, detail="Alerta nao encontrado.")
    
    visiveis, horas, _, rate, pid = _carregar_alertas_para_view(request, DB_PATH)
    return templates.TemplateResponse(
        "partials/alertas_rows.html",
        {
            "request": request,
            "alertas_abertos": visiveis,
            "now_iso": now_iso,
            "horas": horas,
            "rate": rate,
            "pid": pid,
        },
    )

@web_router.get("/pacientes/{paciente_id}/simulacao-panel", response_class=HTMLResponse)
async def pacientes_simulacao_panel(request: Request, paciente_id: str):
    # Fetch latest grade
    # Optimization: We could add a specific DAO method for "latest grade" to avoid fetching all
    grade = selecionar_grade_janela(DB_PATH, horas=24) 
    grade_paciente = [g for g in grade if g.get("paciente_id") == paciente_id]
    ultima_postura = grade_paciente[-1] if grade_paciente else None
    
    # Fetch open alerts
    alertas = listar_alertas_abertos(DB_PATH)
    alertas_paciente = [a for a in alertas if a.get("paciente_id") == paciente_id]
    
    return templates.TemplateResponse(
        "pacientes/partials/simulacao_panel.html",
        {
            "request": request,
            "paciente_id": paciente_id,
            "ultima_postura": ultima_postura,
            "alertas_abertos": alertas_paciente
        }
    )

# Trigger reload 3
