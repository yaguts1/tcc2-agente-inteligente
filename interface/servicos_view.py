"""Servicos auxiliares para a camada de visualizacao (View).

Separa a logica de preparacao de dados, parsing de formularios e calculos de apresentacao
do controlador principal (web.py).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from fastapi import Request

from interface.repositories.alertas import selecionar_alertas_janela
from interface.repositories.grade import selecionar_grade_janela

DEFAULT_PACIENTE_PERFIL = "medio"

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


def rotinas_sugeridas(perfil: str | None) -> List[dict]:
    perfil_norm = (perfil or DEFAULT_PACIENTE_PERFIL).lower()
    base = _ROTINAS_SUGESTOES.get(perfil_norm, _ROTINAS_SUGESTOES[DEFAULT_PACIENTE_PERFIL])
    return [dict(item) for item in base]


def rotinas_para_editor(rotinas: List[dict] | None) -> List[dict]:
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


def montar_paciente_base(
    ficha: dict | None,
    documentos: List[dict] | None,
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


def montar_contexto_formulario(
    request: Request,
    paciente: dict,
    rotinas_editor: List[dict] | None = None,
    *,
    form_error: str | None = None,
    form_success: bool = False,
    usar_rotinas_padrao: bool = False,
    max_document_mb: int = 5,
) -> Dict[str, Any]:
    perfil = str(paciente.get("perfil", DEFAULT_PACIENTE_PERFIL) or DEFAULT_PACIENTE_PERFIL)
    editor = rotinas_editor if rotinas_editor is not None else rotinas_para_editor(paciente.get("rotinas"))
    contexto: Dict[str, Any] = {
        "request": request,
        "paciente": paciente,
        "rotinas_sugestao": rotinas_sugeridas(perfil),
        "rotinas_editor": editor,
        "proximo_indice": len(editor),
        "usar_rotinas_padrao": usar_rotinas_padrao,
        "form_error": form_error,
        "form_success": form_success,
        "documentos": paciente.get("documentos", []),
        "max_document_mb": max_document_mb,
    }
    return contexto


def parse_rotinas_form(form: Any) -> List[dict]:
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


def resolver_indice_rotina(request: Request, index_raw: str | None) -> int:
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


def duracao_em_minutos(inicio_iso: str) -> float:
    inicio = datetime.fromisoformat(inicio_iso[:19])
    return round((datetime.now().replace(microsecond=0) - inicio).total_seconds() / 60.0, 2)


def parse_iso_naive(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor[:19])
    except ValueError:
        return None


def resolver_horas_param(request: Request) -> int | None:
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


def resolver_now_param(request: Request) -> tuple[datetime, str]:
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


def coletar_alertas(
    request: Request,
    db_path: str,
) -> tuple[List[dict], int | None, datetime, str, str | None, str | None]:
    horas = resolver_horas_param(request)
    now_dt, now_iso = resolver_now_param(request)
    pid = request.query_params.get("pid")
    rate = request.query_params.get("rate")
    alertas = selecionar_alertas_janela(db_path, horas)
    if pid:
        alertas = [alerta for alerta in alertas if alerta.get("paciente_id") == pid]
    return alertas, horas, now_dt, now_iso, rate, pid


def carregar_alertas_para_view(
    request: Request,
    db_path: str,
) -> tuple[List[dict], int | None, str, str | None, str | None]:
    alertas, horas, now_dt, now_iso, rate, pid = coletar_alertas(request, db_path)
    visiveis: List[dict] = []
    for alerta_raw in alertas:
        inicio_dt = parse_iso_naive(alerta_raw.get("inicio"))
        fim_dt = parse_iso_naive(alerta_raw.get("fim"))
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


def montar_timeline_context(alertas: List[dict], grade: List[dict], now_dt: datetime) -> Dict[str, object]:
    entries: List[Tuple[dict, datetime, datetime, str]] = []
    
    # Process alerts
    for alerta in alertas:
        inicio_dt = parse_iso_naive(alerta.get("inicio"))
        if inicio_dt is None:
            continue
        fim_dt = parse_iso_naive(alerta.get("fim"))
        if fim_dt is None:
            fim_dt = now_dt if now_dt >= inicio_dt else inicio_dt + timedelta(minutes=1)
        if fim_dt < inicio_dt:
            fim_dt = inicio_dt
        entries.append((alerta, inicio_dt, fim_dt, "alert"))

    # Process grade (posture) events
    # Group by patient to calculate duration
    grade_by_patient = {}
    for g in grade:
        pid = g.get("paciente_id")
        if pid not in grade_by_patient:
            grade_by_patient[pid] = []
        grade_by_patient[pid].append(g)
    
    for pid, events in grade_by_patient.items():
        sorted_events = sorted(events, key=lambda x: x.get("ts") or "")
        for i, event in enumerate(sorted_events):
            ts_start = parse_iso_naive(event.get("ts"))
            if ts_start is None:
                continue
            
            # Determine end time (next event or now)
            if i < len(sorted_events) - 1:
                ts_end = parse_iso_naive(sorted_events[i+1].get("ts"))
            else:
                ts_end = now_dt
            
            if ts_end is None or ts_end < ts_start:
                ts_end = ts_start + timedelta(minutes=5) # Default duration
            
            entries.append((event, ts_start, ts_end, "posture"))

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

    timeline_start = min(min(inicio for _, inicio, _, _ in entries), now_dt)
    timeline_end = max(max(fim for _, _, fim, _ in entries), now_dt)
    if timeline_end <= timeline_start:
        timeline_end = timeline_start + timedelta(minutes=1)

    min_ms = int(timeline_start.timestamp() * 1000)
    max_ms = int(timeline_end.timestamp() * 1000)
    range_ms = max(1, max_ms - min_ms)

    events_out: List[dict] = []
    for item, inicio_dt, fim_dt, type_ in entries:
        start_ms = max(min_ms, int(inicio_dt.timestamp() * 1000))
        end_ms = int(fim_dt.timestamp() * 1000)
        if end_ms < start_ms:
            end_ms = start_ms
        start_pct = max(0.0, min(100.0, ((start_ms - min_ms) / range_ms) * 100.0))
        end_pct = max(start_pct, min(100.0, ((end_ms - min_ms) / range_ms) * 100.0))
        width_pct = max(0.5, end_pct - start_pct)
        width_pct = min(width_pct, 100.0 - start_pct)
        
        if type_ == "alert":
            tooltip = (
                f"ALERTA: Paciente {item.get('paciente_id', '')} - {item.get('status', '').upper()}\n"
                f"{item.get('inicio', '-') } -> {item.get('fim', '-') or '-'}"
            )
            status_class = item.get("status", "aberto")
        else:
            tooltip = (
                f"POSTURA: Paciente {item.get('paciente_id', '')} - {item.get('postura', '')}\n"
                f"{item.get('ts', '-')}"
            )
            status_class = "posture"

        events_out.append(
            {
                "status": status_class,
                "start_pct": round(start_pct, 2),
                "width_pct": round(width_pct, 2),
                "tooltip": tooltip,
                "type": type_
            }
        )

    current_ms = int(now_dt.timestamp() * 1000)
    current_ms = max(min_ms, min(max_ms, current_ms))
    cursor_pct = ((current_ms - min_ms) / range_ms) * 100.0

    return {
        "events": events_out,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "current_ms": current_ms,
        "cursor_pct": round(cursor_pct, 2),
        "window_start": timeline_start.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": timeline_end.strftime("%Y-%m-%d %H:%M:%S"),
    }
