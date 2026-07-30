"""Repository for alert (alertas) operations."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import structlog

from interface.db_core import conexao_ou_propria, connect, ensure_paciente, norm_iso
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


def inserir_alertas(
    db_path: str, alertas: list[dict], conn: sqlite3.Connection | None = None
) -> int:
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
                alerta.get("sitio"),
                # Quem chega aqui e o MOTOR, nunca a tela: a enfermagem passa por
                # `alterar_status_alerta`. Entao um fechamento vindo deste caminho
                # e, por construcao, movimento espontaneo do paciente — e e isso
                # que precisa ficar registrado para nao virar adesao da equipe na
                # hora de contar.
                ORIGEM_SENSOR if fim_val is not None else None,
            )
        )
        pacientes.add(paciente_id)

    if not registros:
        return 0

    with conexao_ou_propria(db_path, conn) as cx:
        for paciente in pacientes:
            ensure_paciente(cx, paciente)
        before = cx.total_changes
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
        cx.executemany(
            """
            INSERT INTO alertas
            (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min,
             sitio, origem_fechamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paciente_id, inicio) DO UPDATE SET
                fim = excluded.fim,
                status = excluded.status,
                duracao_min = excluded.duracao_min,
                origem_fechamento = excluded.origem_fechamento
            WHERE excluded.fim IS NOT NULL AND alertas.fim IS NULL
            """,
            registros,
        )
        # number of DB changes caused by alert inserts only
        delta_alerts = cx.total_changes - before
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
                    _registrar_timeline(cx, paciente_id, inicio_val, ts_ms_inicio, "alert_open")
                if status_val.lower() == "fechado" and fim_val is not None:
                    try:
                        ts_ms_fim = int(pd.to_datetime(fim_val).timestamp() * 1000)
                    except Exception:
                        ts_ms_fim = None
                    if ts_ms_fim is not None:
                        _registrar_timeline(cx, paciente_id, fim_val, ts_ms_fim, "alert_close")
        except Exception:
            # Do not fail alert insertion for timeline logging errors
            pass
        return int(delta_alerts)


def contar_por_paciente(db_path: str, tabela: str) -> dict[str, int]:
    """Retorna a contagem de registros agrupada por paciente."""
    if tabela not in _VALID_TABLES:
        raise ValueError(f"Tabela desconhecida: {tabela}")

    with connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT paciente_id, COUNT(*) as total FROM {tabela} GROUP BY paciente_id"
        )
        rows = cursor.fetchall()
    return {str(row["paciente_id"]): int(row["total"]) for row in rows}


def listar_alertas_abertos(db_path: str) -> list[dict]:
    """Retorna alertas em aberto."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min"
            " FROM alertas WHERE status = ?",
            ("aberto",),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


# Uma lista so: os dois ramos de `selecionar_alertas_janela` (com e sem janela)
# repetiam as colunas, e quem adicionasse uma coluna num ramo e esquecesse o
# outro criaria um bug que so aparece com `horas=None` — que e justamente o
# caminho do EXPORT, o menos exercitado.
_COLUNAS_ALERTA = (
    "paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min, "
    "fechado_por, origem_fechamento, reconhecido_por, reconhecido_em, "
    "motivo_fechamento, sitio"
)


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
                f"SELECT {_COLUNAS_ALERTA} FROM alertas ORDER BY inicio ASC"
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
            f"SELECT {_COLUNAS_ALERTA} FROM alertas "
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

# Por qual caminho o alerta chegou a 'fechado'. Ver migrations/0007: sem isto,
# um paciente que rola sozinho conta como adesao da enfermagem.
ORIGEM_EQUIPE = "equipe"    # alguem clicou na tela
ORIGEM_SENSOR = "sensor"    # o motor detectou movimento espontaneo
ORIGEM_SISTEMA = "sistema"  # regra automatica (alta, transferencia, expurgo)
ORIGENS_VALIDAS = {ORIGEM_EQUIPE, ORIGEM_SENSOR, ORIGEM_SISTEMA}

# Por que o alerta foi fechado.
#
# Concluir nao recebia justificativa nenhuma — o dialogo era sim/nao —, entao
# "reposicionei", "estava em cirurgia", "o paciente recusou", "contraindicado
# por retalho na regiao sacral" e "falso alarme, o sensor deslocou" viravam a
# mesma linha. Cada um e um fato clinico diferente e pede acao diferente.
#
# `FALSO_ALARME` e o que justifica a lista existir: sem separa-lo dos demais, a
# taxa de falso-positivo e estruturalmente incognoscivel — logo, inmelhoravel. E
# fadiga de alarme e a razao dominante pela qual sistemas de alerta clinico sao
# abandonados.
MOTIVO_REPOSICIONADO = "reposicionado"
MOTIVO_EM_PROCEDIMENTO = "em_procedimento"
MOTIVO_RECUSA_DO_PACIENTE = "recusa_do_paciente"
MOTIVO_CONTRAINDICADO = "contraindicado"
MOTIVO_FALSO_ALARME = "falso_alarme"
MOTIVO_SUPERFICIE_ESPECIAL = "superficie_especial"
MOTIVO_OUTRO = "outro"

MOTIVOS_VALIDOS = {
    MOTIVO_REPOSICIONADO,
    MOTIVO_EM_PROCEDIMENTO,
    MOTIVO_RECUSA_DO_PACIENTE,
    MOTIVO_CONTRAINDICADO,
    MOTIVO_FALSO_ALARME,
    MOTIVO_SUPERFICIE_ESPECIAL,
    MOTIVO_OUTRO,
}

# Motivos em que o paciente NAO foi reposicionado. Contam separado na adesao:
# somar "recusa do paciente" a "reposicionei" inflaria a adesao com casos em que
# o alivio de pressao nao aconteceu.
MOTIVOS_SEM_REPOSICIONAMENTO = {
    MOTIVO_EM_PROCEDIMENTO,
    MOTIVO_RECUSA_DO_PACIENTE,
    MOTIVO_CONTRAINDICADO,
    MOTIVO_FALSO_ALARME,
    MOTIVO_SUPERFICIE_ESPECIAL,
}


class TransicaoInvalida(ValueError):
    """Tentativa de retroceder o status de um alerta."""


def alterar_status_alerta(
    db_path: str,
    paciente_id: str,
    inicio: str,
    status_destino: str,
    definir_fim: bool = False,
    now_dt: datetime | None = None,
    fechado_por: str | None = None,
    origem_fechamento: str = ORIGEM_EQUIPE,
    usuario: str | None = None,
    motivo: str | None = None,
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
    if origem_fechamento not in ORIGENS_VALIDAS:
        raise ValueError(f"origem_fechamento invalida: {origem_fechamento!r}")
    if motivo is not None and motivo not in MOTIVOS_VALIDOS:
        raise ValueError(
            f"motivo invalido: {motivo!r} (aceitos: {sorted(MOTIVOS_VALIDOS)})"
        )

    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT status, fim, reconhecido_em FROM alertas"
            " WHERE paciente_id = ? AND inicio = ?",
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
                SET status = :status, fim = :fim, duracao_min = :duracao_min,
                    fechado_por = :fechado_por, origem_fechamento = :origem,
                    motivo_fechamento = :motivo
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {
                    "status": status_destino,
                    "paciente_id": paciente_id,
                    "inicio": inicio,
                    "fim": fim_iso,
                    "duracao_min": duracao_min,
                    "motivo": motivo,
                    # Gravados junto de `fim`, no mesmo UPDATE condicional: a
                    # autoria acompanha o fechamento e herda a mesma garantia de
                    # ser escrita UMA vez. Separar em outro UPDATE abriria a
                    # janela para um alerta com `fim` de um clique e autor de
                    # outro.
                    "fechado_por": fechado_por,
                    "origem": origem_fechamento,
                },
            )
        else:
            # Reconhecimento: grava QUEM viu e QUANDO.
            #
            # E o que torna o tempo-ate-reconhecimento derivavel. `duracao_min`
            # e `fim - inicio` (deteccao -> resolucao); o intervalo que diz se a
            # ala e responsiva — deteccao -> alguem viu — nao existia em lugar
            # nenhum consultavel, so como prosa na timeline.
            #
            # Gravado uma vez so, como `fim`: quem viu primeiro e quem viu, e um
            # segundo clique nao pode reescrever o tempo de resposta da ala.
            escreve_ack = destino == "reconhecido" and atual["reconhecido_em"] is None
            conn.execute(
                """
                UPDATE alertas
                SET status = :status,
                    reconhecido_por = CASE WHEN :escreve_ack THEN :usuario
                                           ELSE reconhecido_por END,
                    reconhecido_em  = CASE WHEN :escreve_ack THEN :agora
                                           ELSE reconhecido_em END
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {
                    "status": status_destino,
                    "escreve_ack": 1 if escreve_ack else 0,
                    "usuario": usuario,
                    "agora": (now_dt or agora_utc_naive())
                    .replace(microsecond=0)
                    .strftime("%Y-%m-%dT%H:%M:%S"),
                    **params,
                },
            )
        conn.commit()
