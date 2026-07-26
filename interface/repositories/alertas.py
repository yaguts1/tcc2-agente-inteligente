"""Repository for alert (alertas) operations."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import structlog

from interface.db_core import connect, ensure_paciente, norm_iso
from interface.tempo import agora_utc_naive

logger = structlog.get_logger(__name__)

_VALID_TABLES = {"grade", "eventos", "alertas"}


# Espelham os CHECK da tabela `alertas` (ver db_core.criar_esquema).
TIPOS_VALIDOS = frozenset({"imobilidade"})
STATUS_VALIDOS = frozenset({"aberto", "reconhecido", "fechado"})


def _registrar_timeline(conn, paciente_id: str, ts: str, ts_ms: int, tipo: str) -> None:
    """Grava um evento de timeline, sem repetir um que ja esta la.

    O mesmo alerta e persistido mais de uma vez no caminho do sensor (abertura e
    depois fechamento), e cada chamada registrava outro `alert_open` no mesmo
    instante. A timeline do paciente — que a equipe usa para reconstruir o que
    aconteceu — mostrava dois disparos onde houve um.
    """
    conn.execute(
        """
        INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta)
        SELECT ?, ?, ?, ?, NULL, NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM timeline_events
            WHERE paciente_id = ? AND ts = ? AND tipo = ?
        )
        """,
        (paciente_id, ts, ts_ms, tipo, paciente_id, ts, tipo),
    )


def inserir_alertas(db_path: str, alertas: List[dict]) -> int:
    """Insere ou atualiza alertas calculados pelo motor."""
    if not alertas:
        return 0

    required = {"paciente_id", "inicio", "tipo", "perfil", "janela_min", "status"}
    for alerta in alertas:
        if not required.issubset(alerta):
            raise ValueError(
                "Alertas devem conter pelo menos paciente_id, inicio, tipo, perfil, janela_min e status."
            )
        # `tipo` e `status` tem CHECK no esquema. Enquanto o INSERT era
        # `OR IGNORE`, a violacao era engolida junto com os conflitos de chave:
        # a importacao respondia ok com a contagem de inseridos menor que a de
        # recebidos, e o alerta simplesmente nao existia. Validar aqui devolve
        # 400 com o motivo (ver routers/admin.py) em vez de descartar em
        # silencio ou estourar 500 la no SQLite.
        if str(alerta["tipo"]) not in TIPOS_VALIDOS:
            raise ValueError(
                f"tipo invalido: {alerta['tipo']!r} (aceitos: {sorted(TIPOS_VALIDOS)})"
            )
        if str(alerta["status"]) not in STATUS_VALIDOS:
            raise ValueError(
                f"status invalido: {alerta['status']!r} (aceitos: {sorted(STATUS_VALIDOS)})"
            )

    inicio_series = norm_iso(pd.Series([alerta.get("inicio") for alerta in alertas], dtype="object"))
    fim_series = norm_iso(pd.Series([alerta.get("fim") for alerta in alertas], dtype="object"))

    registros = []
    pacientes: set[str] = set()
    for idx, alerta in enumerate(alertas):
        paciente_id = str(alerta["paciente_id"])
        inicio_val = inicio_series.iat[idx]
        if inicio_val is None:
            raise ValueError("Alertas precisam de 'inicio' valido para persistencia.")
        fim_val = fim_series.iat[idx]
        duracao = alerta.get("duracao_min")
        duracao_val = float(duracao) if duracao is not None else None
        registros.append(
            (
                paciente_id,
                inicio_val,
                fim_val,
                str(alerta.get("tipo", "")),
                str(alerta.get("perfil", "")),
                int(alerta.get("janela_min", 0)),
                str(alerta.get("status", "")),
                duracao_val,
            )
        )
        pacientes.add(paciente_id)

    if not registros:
        return 0

    with connect(db_path) as conn:
        for paciente in pacientes:
            ensure_paciente(conn, paciente)
        before = conn.total_changes
        # O motor incremental (caminho do sensor real, `processar_amostra`) emite
        # o alerta DUAS vezes: 'aberto' quando a janela estoura e 'fechado'
        # quando detecta o reposicionamento — duas chamadas, mesma chave
        # (paciente_id, inicio). Com `INSERT OR IGNORE` o fechamento era
        # descartado em silencio: o alerta ficava 'aberto' com fim=NULL para
        # sempre, e como `nextRepositioning` de um alerta aberto ja esta vencido,
        # a tela mostrava o paciente em atraso permanente DEPOIS de ele ter sido
        # virado. So a simulacao em lote parecia certa, porque ela emite o alerta
        # uma unica vez, ja fechado.
        #
        # O UPDATE e condicional de proposito:
        #   - `excluded.fim IS NOT NULL` — so um fechamento atualiza; uma
        #     reemissao de 'aberto' nunca rebaixa o status de uma linha que a
        #     enfermagem ja reconheceu ou concluiu pela tela;
        #   - `alertas.fim IS NULL` — nao sobrescreve um fechamento ja gravado.
        conn.executemany(
            """
            INSERT INTO alertas
            (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, inicio) DO UPDATE SET
                fim = excluded.fim,
                status = excluded.status,
                duracao_min = excluded.duracao_min
            WHERE excluded.fim IS NOT NULL AND alertas.fim IS NULL
            """,
            registros,
        )
        # number of DB changes caused by alert inserts only
        delta_alerts = conn.total_changes - before
        # For each alerta we persisted, add timeline event(s) so historical/simulated
        # navigation reflects when alerts were triggered and (if already resolved)
        # when they were closed. `alert_open` is always logged at `inicio`; batch
        # simulations produce alerts that are already 'fechado' (start+end both in
        # the past), so we also log `alert_close` at `fim` for those instead of
        # relying on a live status transition through alterar_status_alerta.
        try:
            for idx, alerta in enumerate(alertas):
                paciente_id = str(alerta["paciente_id"]) if isinstance(alerta, dict) else registros[idx][0]
                inicio_val = inicio_series.iat[idx]
                fim_val = fim_series.iat[idx]
                status_val = str(alerta.get("status", "")) if isinstance(alerta, dict) else registros[idx][6]
                if inicio_val is None:
                    continue
                try:
                    ts_ms_inicio = int(pd.to_datetime(inicio_val).timestamp() * 1000)
                except Exception:
                    ts_ms_inicio = None
                if ts_ms_inicio is not None:
                    _registrar_timeline(conn, paciente_id, inicio_val, ts_ms_inicio, "alert_open")
                if status_val.lower() == "fechado" and fim_val is not None:
                    try:
                        ts_ms_fim = int(pd.to_datetime(fim_val).timestamp() * 1000)
                    except Exception:
                        ts_ms_fim = None
                    if ts_ms_fim is not None:
                        _registrar_timeline(conn, paciente_id, fim_val, ts_ms_fim, "alert_close")
        except Exception:
            # Do not fail alert insertion for timeline logging errors
            pass
        return int(delta_alerts)


def contar_por_paciente(db_path: str, tabela: str) -> Dict[str, int]:
    """Retorna a contagem de registros agrupada por paciente."""
    if tabela not in _VALID_TABLES:
        raise ValueError(f"Tabela desconhecida: {tabela}")

    with connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT paciente_id, COUNT(*) as total FROM {tabela} GROUP BY paciente_id"
        )
        rows = cursor.fetchall()
    return {str(row["paciente_id"]): int(row["total"]) for row in rows}


def listar_alertas_abertos(db_path: str) -> List[dict]:
    """Retorna alertas em aberto."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min"
            " FROM alertas WHERE status = ?",
            ("aberto",),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def selecionar_alertas_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca alertas (qualquer status) dentro de uma janela de tempo.

    Args:
        db_path: Caminho do banco de dados
        horas: Janela de tempo em horas (se None, traz todos)
              Busca alertas de (agora - horas) até (agora + horas)

    Returns:
        Lista de dicts com dados dos alertas ordenados por inicio ASC
    """
    if horas is None:
        # Sem filtro de tempo - retorna todos
        with connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
                "FROM alertas ORDER BY inicio ASC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Com filtro de tempo - busca passado e futuro próximo.
    # `inicio` no banco é UTC naive, então o "agora" da janela também precisa
    # ser UTC (datetime.now() local deslocaria a janela pelo offset do fuso).
    agora = agora_utc_naive()
    limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    limite_superior = (agora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    # Alerta NAO RESOLVIDO ignora a janela, sempre.
    #
    # O filtro era só por `inicio`, independentemente do status: um alerta
    # aberto ha 25 horas e nunca atendido saia da lista. E some justamente o
    # paciente com o reposicionamento MAIS atrasado — o de maior risco de lesao
    # — sem contador, aviso ou qualquer indicacao de que existe algo fora da
    # janela. GET /api/stats usava a mesma consulta, entao ele tambem nao
    # entrava em `activeAlerts`: um paciente 30h sem virar nao aparecia em
    # lugar nenhum do sistema.
    #
    # A janela faz sentido para o HISTORICO (alertas ja fechados). Para um
    # alerta pendente, tempo decorrido nao e motivo para deixar de mostrar — e
    # motivo para priorizar.
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
            "FROM alertas "
            "WHERE (inicio >= ? AND inicio <= ?) OR status IN ('aberto', 'reconhecido') "
            "ORDER BY inicio ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def listar_pacientes(db_path: str, horas: int | None = 24) -> list[str]:
    limite = None
    if horas is not None:
        agora = agora_utc_naive()  # `inicio` no banco é UTC naive
        limite = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    with connect(db_path) as conn:
        if limite is None:
            cur = conn.execute("SELECT DISTINCT paciente_id FROM alertas ORDER BY paciente_id")
        else:
            cur = conn.execute(
                "SELECT DISTINCT paciente_id FROM alertas WHERE inicio >= ? ORDER BY paciente_id",
                (limite,),
            )
        rows = cur.fetchall()
    return [str(row[0]) for row in rows]


# O ciclo de vida de um alerta so anda para a frente. Um reposicionamento
# concluido nao volta a pendente porque alguem clicou no botao errado, e o
# instante em que o paciente foi virado nao muda depois de registrado.
ORDEM_STATUS = {"aberto": 0, "reconhecido": 1, "fechado": 2}


class TransicaoInvalida(ValueError):
    """Tentativa de retroceder o status de um alerta."""


def alterar_status_alerta(
    db_path: str,
    paciente_id: str,
    inicio: str,
    status_destino: str,
    definir_fim: bool = False,
    now_dt: datetime | None = None,
) -> None:
    """Avanca o status de um alerta: aberto -> reconhecido -> fechado.

    Antes nao havia validacao nenhuma, e a consequencia aparecia justamente no
    dado que este sistema existe para registrar:

    - concluir duas vezes SOBRESCREVIA `fim` e `duracao_min`, trocando o
      instante em que o paciente foi realmente reposicionado pelo do segundo
      clique;
    - clicar "Reconhecer" depois de concluido devolvia o alerta para
      'reconhecido' com `fim` preenchido — na tela, um paciente ja virado
      voltava a aparecer como pendente de acao;
    - dava para voltar a 'aberto' com `fim` preenchido.

    Duas pessoas agindo no mesmo alerta em telas diferentes — rotina numa ala —
    produziam qualquer um desses estados.

    Agora:

    - repetir o status atual e no-op (idempotente): o segundo clique, ou o
      retry de uma requisicao, nao altera nada;
    - retroceder levanta `TransicaoInvalida`, que a API traduz em 409;
    - `fim` e `duracao_min` sao gravados UMA vez e nunca reescritos.

    - status_destino: 'aberto'|'reconhecido'|'fechado'
    - if definir_fim is True, sets fim and duracao_min based on now_dt or current time.
    """
    if not paciente_id or not inicio:
        raise ValueError("paciente_id e inicio precisam ser informados")

    destino = str(status_destino).lower()
    if destino not in ORDEM_STATUS:
        raise ValueError(f"status invalido: {status_destino!r}")

    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT status, fim FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (paciente_id, inicio),
        )
        atual = cur.fetchone()
        if atual is None:
            raise LookupError("Alerta nao encontrado.")

        status_atual = str(atual["status"] or "aberto").lower()
        rank_atual = ORDEM_STATUS.get(status_atual, 0)
        rank_destino = ORDEM_STATUS[destino]

        if rank_destino < rank_atual:
            raise TransicaoInvalida(
                f"nao e possivel voltar de '{status_atual}' para '{destino}'"
            )
        if rank_destino == rank_atual:
            # Idempotente: nada muda, e em especial `fim` NAO e reescrito.
            return

        # `fim` ja gravado nunca e substituido — e o registro de quando o
        # paciente foi virado.
        definir_fim = definir_fim and atual["fim"] is None

        params = {"paciente_id": paciente_id, "inicio": inicio}
        if definir_fim:
            # `inicio` é UTC naive; o "agora" (fim) e a duração precisam do
            # mesmo referencial (senão datetime.now() local erraria a duração
            # pelo offset do fuso). Callers podem passar now_dt (relógio virtual).
            base_now = (now_dt or agora_utc_naive()).replace(microsecond=0)
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
        conn.commit()
