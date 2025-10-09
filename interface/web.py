"""App FastAPI/Jinja2 para visualizar e gerenciar alertas.

Execute com:
    uvicorn interface.web:app --reload
"""

from __future__ import annotations

import json
import re
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from fastapi import FastAPI, HTTPException, Request, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError, validator

from interface.dao import (
    criar_esquema,
    listar_alertas_abertos,
    selecionar_alertas_janela,
    listar_pacientes,
    listar_fichas_pacientes,
    obter_ficha_paciente,
    criar_paciente,
    atualizar_paciente,
    proximo_identificador_paciente,
    DEFAULT_ROTINA_DURACAO_MIN,
    listar_documentos,
    registrar_documento,
    remover_documento,
    obter_documento,
)

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")
BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTOS_DIR = Path(os.getenv("UPP_DOCS_DIR", str(BASE_DIR / "paciente_docs"))).resolve()
MAX_DOCUMENT_BYTES = int(os.getenv("UPP_DOC_MAX_MB", "10")) * 1024 * 1024
MAX_DOCUMENT_MB = max(1, MAX_DOCUMENT_BYTES // (1024 * 1024))
DOCUMENTOS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Monitor de Alertas UPP")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

PERFIS_VALIDOS = {'baixo', 'medio', 'alto'}
ROTINAS_PADRAO_SUGESTAO = [
    {'label': 'Refeicao Manha', 'inicio': '06:30', 'duracao_min': 45, 'descricao': 'Cafe da manha recomendado.'},
    {'label': 'Refeicao Almoco', 'inicio': '12:30', 'duracao_min': 60, 'descricao': 'Almoco sugerido.'},
    {'label': 'Refeicao Jantar', 'inicio': '18:30', 'duracao_min': 60, 'descricao': 'Jantar sugerido.'},
]


_ROTINA_FORM_PATTERN = re.compile(r'^rotinas-(?P<idx>\d+)-(?:label|inicio|duracao|duracao_min|descricao|ativo|sort)$')


def _model_dump(model):
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


class RotinaFormError(ValueError):
    def __init__(self, message: str, rotinas_view: List[dict]):
        super().__init__(message)
        self.rotinas_view = rotinas_view


def _documentos_dir(paciente_id: str) -> Path:
    destino = DOCUMENTOS_DIR / paciente_id
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _sanitize_filename(nome: str) -> str:
    return Path(str(nome or "")).name.replace(' ', '_')


def _documentos_para_view(paciente_id: Optional[str]) -> List[dict]:
    if not paciente_id:
        return []
    return listar_documentos(DB_PATH, paciente_id)


class RotinaEntrada(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    inicio: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    duracao_min: int = Field(default=30, ge=1, le=720)
    descricao: Optional[str] = Field(default=None, max_length=255)
    ativo: bool = True
    sort_order: Optional[int] = None

    @validator("label")
    def _trim_label(cls, valor: str) -> str:
        texto = valor.strip()
        if not texto:
            raise ValueError("Label da rotina nao pode ser vazio.")
        return texto

    @validator("inicio")
    def _validar_inicio(cls, valor: str) -> str:
        texto = valor.strip()
        if len(texto) != 5 or texto[2] != ":":
            raise ValueError("Horario deve estar no formato HH:MM.")
        hora, minuto = texto.split(":")
        if not (hora.isdigit() and minuto.isdigit()):
            raise ValueError("Horario deve conter apenas numeros.")
        h = int(hora)
        m = int(minuto)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Horario fora do intervalo 00:00-23:59.")
        return f"{h:02d}:{m:02d}"



def _ficha_vazia() -> dict:
    return {
        "paciente_id": None,
        "nome": "",
        "perfil": "medio",
        "observacoes": None,
        "rotinas": [],
        "documentos": [],
    }

class PacientePayload(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    perfil: str = Field(..., description="Perfil de risco do paciente")
    observacoes: Optional[str] = Field(default=None, max_length=2000)
    rotinas: List[RotinaEntrada] = Field(default_factory=list)

    @validator("nome")
    def _trim_nome(cls, valor: str) -> str:
        texto = valor.strip()
        if not texto:
            raise ValueError("Nome nao pode ser vazio.")
        return texto

    @validator("perfil")
    def _normalizar_perfil(cls, valor: str) -> str:
        texto = valor.strip().lower()
        if texto not in PERFIS_VALIDOS:
            raise ValueError(f"Perfil deve ser um de {sorted(PERFIS_VALIDOS)}.")
        return texto

    @validator("observacoes", pre=True)
    def _normalizar_obs(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        texto = str(valor).strip()
        return texto or None


def _rotinas_payload_to_dict(rotinas: List[RotinaEntrada]) -> List[dict]:
    dados: List[dict] = []
    for idx_item, rotina in enumerate(rotinas):
        item = _model_dump(rotina)
        if item.get("sort_order") is None:
            item["sort_order"] = idx_item
        dados.append(item)
    return dados


def _parse_rotinas_form(form) -> tuple[List[dict], List[dict]]:
    if hasattr(form, 'multi_items'):
        items = list(form.multi_items())
    else:
        items = list(getattr(form, 'items', lambda: [])())

    buckets: dict[int, dict[str, object]] = {}
    for key, value in items:
        match = _ROTINA_FORM_PATTERN.match(str(key))
        if not match:
            continue
        idx = int(match.group('idx'))
        buckets.setdefault(idx, {})[key.split('-')[-1]] = value

    rotinas: List[dict] = []
    editor_view: List[dict] = []
    for idx in sorted(buckets):
        raw = buckets[idx]
        label = str(raw.get('label', '')).strip()
        inicio = str(raw.get('inicio', '')).strip()
        duracao_raw = str(raw.get('duracao') or raw.get('duracao_min') or '').strip()
        try:
            duracao_int = int(duracao_raw) if duracao_raw else DEFAULT_ROTINA_DURACAO_MIN
        except (TypeError, ValueError):
            duracao_int = DEFAULT_ROTINA_DURACAO_MIN
        if duracao_int <= 0:
            duracao_int = DEFAULT_ROTINA_DURACAO_MIN
        descricao_raw = raw.get('descricao')
        descricao_val = None if descricao_raw is None else str(descricao_raw).strip() or None
        ativo_raw = raw.get('ativo')
        ativo_bool = not (str(ativo_raw).lower() in {'0', 'false'} or ativo_raw in (None, '', 0, False))
        sort_raw = raw.get('sort') or raw.get('sort_order')
        try:
            sort_order = int(sort_raw) if sort_raw is not None else idx
        except (TypeError, ValueError):
            sort_order = idx

        editor_view.append({
            'label': label,
            'inicio': inicio,
            'duracao_min': duracao_int,
            'descricao': descricao_val,
            'ativo': ativo_bool,
            'sort_order': sort_order,
        })

        if not any([label, inicio, duracao_raw, descricao_val]):
            continue
        if not label:
            raise RotinaFormError(f"Rotina #{idx + 1}: descricao obrigatoria.", editor_view)
        if not inicio:
            raise RotinaFormError(f"Rotina #{idx + 1}: horario obrigatorio.", editor_view)

        try:
            rotina_model = RotinaEntrada(
                label=label,
                inicio=inicio,
                duracao_min=duracao_int,
                descricao=descricao_val,
                ativo=ativo_bool,
                sort_order=sort_order,
            )
        except ValidationError as exc:
            detalhes = exc.errors()
            mensagem = detalhes[0]['msg'] if detalhes else str(exc)
            raise RotinaFormError(f"Rotina #{idx + 1}: {mensagem}", editor_view) from exc

        rotinas.append(
            {
                'label': rotina_model.label,
                'inicio': rotina_model.inicio,
                'duracao_min': rotina_model.duracao_min,
                'descricao': rotina_model.descricao,
                'ativo': 1 if rotina_model.ativo else 0,
                'sort_order': rotina_model.sort_order if rotina_model.sort_order is not None else idx,
            }
        )

    return rotinas, editor_view

def _rotinas_para_editor(rotinas: List[dict]) -> List[dict]:
    saida: List[dict] = []
    for idx, raw in enumerate(rotinas):
        label = str(raw.get('label', '')).strip()
        inicio = str(raw.get('inicio', '')).strip()[:5]
        try:
            duracao = int(raw.get('duracao_min', DEFAULT_ROTINA_DURACAO_MIN))
        except (TypeError, ValueError):
            duracao = DEFAULT_ROTINA_DURACAO_MIN
        descricao = raw.get('descricao')
        descricao_val = None if descricao is None else str(descricao).strip() or None
        ativo_val = raw.get('ativo', 1)
        ativo_bool = bool(ativo_val) and str(ativo_val).lower() not in {'0', 'false'}
        try:
            sort_ord = int(raw.get('sort_order', idx))
        except (TypeError, ValueError):
            sort_ord = idx
        saida.append({
            'label': label,
            'inicio': inicio,
            'duracao_min': duracao,
            'descricao': descricao_val,
            'ativo': ativo_bool,
            'sort_order': sort_ord,
        })
    return saida

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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




def _extrair_parametros(request: Request) -> Dict[str, object]:
    horas = _resolver_horas_param(request)
    now_dt, now_iso = _resolver_now_param(request)
    return {
        "horas": horas,
        "now_dt": now_dt,
        "now_iso": now_iso,
        "pid": request.query_params.get("pid"),
        "rate": request.query_params.get("rate"),
        "pacientes": listar_pacientes(DB_PATH, horas),
    }

def _coletar_alertas(
    request: Request,
) -> tuple[List[dict], Dict[str, object]]:
    params = _extrair_parametros(request)
    alertas = selecionar_alertas_janela(DB_PATH, params["horas"])
    pid = params["pid"]
    if pid:
        alertas = [alerta for alerta in alertas if alerta.get("paciente_id") == pid]
    return alertas, params


def _carregar_alertas_para_view(
    request: Request,
) -> tuple[List[dict], Dict[str, object]]:
    alertas, params = _coletar_alertas(request)
    visiveis: List[dict] = []
    now_dt = params["now_dt"]
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
    return visiveis, params


def _contexto_base(request: Request, params: Dict[str, object]) -> Dict[str, object]:
    return {
        "request": request,
        "horas": params.get("horas"),
        "now": params.get("now_iso"),
        "rate": params.get("rate"),
        "pid": params.get("pid"),
        "pacientes": params.get("pacientes", []),
    }

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
            f"Paciente {alerta.get('paciente_id', '')} · {alerta.get('status', '').upper()}\n"
            f"{alerta.get('inicio', '-')} → {alerta.get('fim', '-') or '-'}"
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
                {
                    "status": status_destino,
                    "paciente_id": paciente_id,
                    "inicio": inicio,
                },
            )




@app.get("/pacientes", response_class=HTMLResponse)
def pacientes_index(request: Request) -> HTMLResponse:
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
    contexto = {"request": request, "pacientes": fichas}
    return templates.TemplateResponse("pacientes/index.html", contexto)


@app.get("/partials/pacientes/lista", response_class=HTMLResponse)
def pacientes_lista_partial(request: Request) -> HTMLResponse:
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
    contexto = {"request": request, "pacientes": fichas}
    return templates.TemplateResponse("pacientes/partials/lista.html", contexto)


@app.get("/pacientes/form", response_class=HTMLResponse)
def pacientes_form_novo(request: Request) -> HTMLResponse:
    ficha = _ficha_vazia()
    rotinas_editor = _rotinas_para_editor(ROTINAS_PADRAO_SUGESTAO)
    ficha['rotinas'] = rotinas_editor
    ficha['documentos'] = []
    contexto = {
        'request': request,
        'paciente': ficha,
        'rotinas_sugestao': ROTINAS_PADRAO_SUGESTAO,
        'rotinas_editor': rotinas_editor,
        'proximo_indice': len(rotinas_editor),
        'usar_rotinas_padrao': True,
        'documentos': [],
        'max_document_mb': MAX_DOCUMENT_MB,
    }
    return templates.TemplateResponse('pacientes/partials/form.html', contexto)


@app.get('/pacientes/{paciente_id}/form', response_class=HTMLResponse)
def pacientes_form_editar(request: Request, paciente_id: str) -> HTMLResponse:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=True)
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Paciente nao encontrado.')
    rotinas_editor = _rotinas_para_editor(ficha.get('rotinas', []))
    documentos = listar_documentos(DB_PATH, paciente_id)
    ficha['rotinas'] = rotinas_editor
    ficha['documentos'] = documentos
    contexto = {
        'request': request,
        'paciente': ficha,
        'rotinas_sugestao': ROTINAS_PADRAO_SUGESTAO,
        'rotinas_editor': rotinas_editor,
        'proximo_indice': len(rotinas_editor),
        'usar_rotinas_padrao': False,
        'documentos': documentos,
        'max_document_mb': MAX_DOCUMENT_MB,
    }
    return templates.TemplateResponse('pacientes/partials/form.html', contexto)


@app.post("/pacientes/salvar", response_class=HTMLResponse)
async def pacientes_salvar(request: Request) -> HTMLResponse:
    form = await request.form()
    paciente_id_raw = str(form.get("paciente_id") or "").strip()
    paciente_id = paciente_id_raw or None
    nome_raw = str(form.get("nome") or "")
    perfil_raw = str(form.get("perfil") or "medio")
    observacoes_raw = form.get("observacoes")
    observacoes = None if observacoes_raw is None else str(observacoes_raw).strip() or None
    usar_rotinas_padrao = bool(form.get("usar_rotinas_padrao"))
    perfil = perfil_raw.strip().lower()
    documentos_view = _documentos_para_view(paciente_id)

    if usar_rotinas_padrao:
        rotinas_payload = [dict(item) for item in ROTINAS_PADRAO_SUGESTAO]
        for idx, item in enumerate(rotinas_payload):
            item.setdefault('sort_order', idx)
            item.setdefault('ativo', 1)
        rotinas_editor = _rotinas_para_editor(rotinas_payload)
    else:
        try:
            rotinas_payload, rotinas_editor = _parse_rotinas_form(form)
        except RotinaFormError as exc:
            contexto = {
                'request': request,
                'paciente': {
                    'paciente_id': paciente_id,
                    'nome': nome_raw,
                    'perfil': perfil,
                    'observacoes': observacoes,
                    'rotinas': exc.rotinas_view,
                    'documentos': documentos_view,
                },
                'rotinas_sugestao': ROTINAS_PADRAO_SUGESTAO,
                'rotinas_editor': exc.rotinas_view,
                'proximo_indice': len(exc.rotinas_view),
                'usar_rotinas_padrao': usar_rotinas_padrao,
                'documentos': documentos_view,
                'max_document_mb': MAX_DOCUMENT_MB,
                'form_error': str(exc),
            }
            return templates.TemplateResponse(
                'pacientes/partials/form.html',
                contexto,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    try:
        if paciente_id:
            ficha = atualizar_paciente(
                DB_PATH,
                paciente_id,
                nome_raw,
                perfil,
                observacoes,
                rotinas=rotinas_payload,
            )
        else:
            ficha = criar_paciente(
                DB_PATH,
                nome_raw,
                perfil,
                observacoes,
                rotinas=rotinas_payload,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        contexto = {
            'request': request,
            'paciente': {
                'paciente_id': paciente_id,
                'nome': nome_raw,
                'perfil': perfil,
                'observacoes': observacoes,
                'rotinas': rotinas_editor,
                'documentos': documentos_view,
            },
            'rotinas_sugestao': ROTINAS_PADRAO_SUGESTAO,
            'rotinas_editor': rotinas_editor,
            'proximo_indice': len(rotinas_editor),
            'usar_rotinas_padrao': usar_rotinas_padrao,
            'documentos': documentos_view,
            'max_document_mb': MAX_DOCUMENT_MB,
            'form_error': str(exc),
        }
        return templates.TemplateResponse(
            'pacientes/partials/form.html',
            contexto,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    ficha['rotinas'] = _rotinas_para_editor(ficha.get('rotinas', []))
    documentos_atual = _documentos_para_view(ficha.get('paciente_id'))
    ficha['documentos'] = documentos_atual
    contexto = {
        'request': request,
        'paciente': ficha,
        'rotinas_sugestao': ROTINAS_PADRAO_SUGESTAO,
        'rotinas_editor': ficha['rotinas'],
        'proximo_indice': len(ficha['rotinas']),
        'usar_rotinas_padrao': False,
        'form_success': True,
        'documentos': documentos_atual,
        'max_document_mb': MAX_DOCUMENT_MB,
    }
    response = templates.TemplateResponse('pacientes/partials/form.html', contexto)
    response.headers['HX-Trigger'] = json.dumps(
        {'paciente-atualizado': {'paciente_id': ficha['paciente_id'], 'message': 'Ficha salva com sucesso.'}}
    )
    return response



@app.get('/pacientes/rotinas/linha', response_class=HTMLResponse)
def pacientes_rotina_linha(request: Request, index: int = 0) -> HTMLResponse:
    indice = max(0, int(index))
    rotina_base = {
        'label': '',
        'inicio': '',
        'duracao_min': DEFAULT_ROTINA_DURACAO_MIN,
        'descricao': None,
        'ativo': True,
        'sort_order': indice,
    }
    contexto = {
        'request': request,
        'indice': indice,
        'rotina': rotina_base,
    }
    return templates.TemplateResponse('pacientes/partials/rotina_row.html', contexto)


@app.get('/pacientes/{paciente_id}/documentos', response_class=HTMLResponse)
def pacientes_documentos_lista(request: Request, paciente_id: str) -> HTMLResponse:
    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {
        'request': request,
        'paciente_id': paciente_id,
        'documentos': documentos,
        'max_document_mb': MAX_DOCUMENT_MB,
    }
    return templates.TemplateResponse('pacientes/partials/documentos.html', contexto)


@app.post('/pacientes/{paciente_id}/documentos', response_class=HTMLResponse)
async def pacientes_documento_upload(
    request: Request,
    paciente_id: str,
    arquivo: UploadFile = File(...),
    observacao: Optional[str] = Form(None),
) -> HTMLResponse:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Paciente nao encontrado.')
    if not arquivo.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Arquivo obrigatorio.')
    nome_limpo = _sanitize_filename(arquivo.filename)
    if not nome_limpo.lower().endswith('.pdf'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Apenas arquivos PDF sao aceitos.')
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Arquivo vazio.')
    if len(conteudo) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail='Arquivo excede o limite permitido.',
        )

    destino_dir = _documentos_dir(paciente_id)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    destino_nome = f"{timestamp}_{nome_limpo}"
    destino_path = destino_dir / destino_nome
    contador = 1
    while destino_path.exists():
        destino_nome = f"{timestamp}_{contador}_{nome_limpo}"
        destino_path = destino_dir / destino_nome
        contador += 1
    destino_path.write_bytes(conteudo)
    rel_path = destino_path.relative_to(DOCUMENTOS_DIR)
    registrar_documento(DB_PATH, paciente_id, nome_limpo, str(rel_path), observacao)

    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {
        'request': request,
        'paciente_id': paciente_id,
        'documentos': documentos,
    }
    response = templates.TemplateResponse('pacientes/partials/documentos.html', contexto)
    response.headers['HX-Trigger'] = json.dumps({'documento-atualizado': {'message': 'Documento anexado com sucesso.'}})
    return response


@app.delete('/pacientes/documentos/{documento_id}', response_class=HTMLResponse)
def pacientes_documento_remover(request: Request, documento_id: int) -> HTMLResponse:
    info = remover_documento(DB_PATH, documento_id)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Documento nao encontrado.')
    caminho_rel = info['caminho']
    paciente_id = info['paciente_id']
    arquivo_path = (DOCUMENTOS_DIR / caminho_rel).resolve()
    try:
        arquivo_path.relative_to(DOCUMENTOS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Caminho invalido.') from exc
    if arquivo_path.exists():
        try:
            arquivo_path.unlink()
        except OSError:
            pass
    documentos = listar_documentos(DB_PATH, paciente_id)
    contexto = {
        'request': request,
        'paciente_id': paciente_id,
        'documentos': documentos,
    }
    response = templates.TemplateResponse('pacientes/partials/documentos.html', contexto)
    response.headers['HX-Trigger'] = json.dumps({'documento-atualizado': {'message': 'Documento removido.'}})
    return response


@app.get('/pacientes/documentos/{documento_id}/download')
def pacientes_documento_download(documento_id: int) -> FileResponse:
    documento = obter_documento(DB_PATH, documento_id)
    if documento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Documento nao encontrado.')
    arquivo_path = (DOCUMENTOS_DIR / documento['caminho']).resolve()
    try:
        arquivo_path.relative_to(DOCUMENTOS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Caminho invalido.') from exc
    if not arquivo_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Arquivo nao encontrado no disco.')
    return FileResponse(arquivo_path, filename=documento['nome_arquivo'], media_type='application/pdf')


@app.get("/api/pacientes/proximo-id")
def api_proximo_paciente_id() -> Dict[str, str]:
    return {"paciente_id": proximo_identificador_paciente(DB_PATH)}


@app.get("/api/pacientes")
def api_listar_pacientes() -> List[dict]:
    return listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)


@app.get("/api/pacientes/{paciente_id}")
def api_obter_paciente(paciente_id: str) -> dict:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=True)
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado.")
    return ficha


@app.post("/api/pacientes", status_code=status.HTTP_201_CREATED)
def api_criar_paciente_endpoint(payload: PacientePayload) -> dict:
    rotinas = _rotinas_payload_to_dict(payload.rotinas)
    try:
        ficha = criar_paciente(DB_PATH, payload.nome, payload.perfil, payload.observacoes, rotinas)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ficha


@app.put("/api/pacientes/{paciente_id}")
def api_atualizar_paciente_endpoint(paciente_id: str, payload: PacientePayload) -> dict:
    rotinas = _rotinas_payload_to_dict(payload.rotinas)
    try:
        ficha = atualizar_paciente(DB_PATH, paciente_id, payload.nome, payload.perfil, payload.observacoes, rotinas)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ficha

@app.get("/api/alertas")
def api_alertas() -> List[dict]:
    """Retorna alertas em aberto no formato JSON."""
    return listar_alertas_abertos(DB_PATH)


def _render_alertas_fragment(request: Request) -> HTMLResponse:
    alertas_visiveis, params = _carregar_alertas_para_view(request)
    contexto = _contexto_base(request, params)
    contexto.update({
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
    })
    return templates.TemplateResponse("partials/alertas_rows.html", contexto)


@app.get("/partials/alertas", response_class=HTMLResponse)
def partial_alertas(request: Request) -> HTMLResponse:
    """Retorna fragmento HTML com linhas da tabela de alertas."""
    return _render_alertas_fragment(request)


@app.get("/partials/timeline", response_class=HTMLResponse)
def partial_timeline(request: Request) -> HTMLResponse:
    """Retorna o fragmento de timeline para navegacao temporal."""
    alertas, params = _coletar_alertas(request)
    contexto = _contexto_base(request, params)
    contexto.update(_montar_timeline_context(alertas, params["now_dt"]))
    return templates.TemplateResponse("partials/timeline.html", contexto)



@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Renderiza a pagina principal com a lista de alertas."""
    alertas_visiveis, params = _carregar_alertas_para_view(request)
    contexto = _contexto_base(request, params)
    contexto.update({
        "alertas_abertos": alertas_visiveis,
        "alertas_visiveis": alertas_visiveis,
    })
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
    except Exception as exc:  # pragma: no cover - log mas nao falha startup
        print(f"[WARN] Nao foi possivel garantir schema do banco: {exc}")
























