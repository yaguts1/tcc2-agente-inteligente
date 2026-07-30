"""
Módulo DAO para Sistema de Agenda/Schedule.

Gerencia agendas de supressão de alertas para pacientes.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Union
import json

from interface.dao import _connect, _ensure_paciente
from interface.tempo import agora_utc_naive


def ensure_agendas_table(db_path: str) -> None:
    """Cria tabela de agendas se não existir.

    O dono do schema e `migrations/0006_agendas_no_schema.sql`; esta funcao
    sobrevive como rede de seguranca para quem chama o DAO sem passar pelo
    startup do app (script, teste). As duas definicoes precisam concordar — em
    especial a FK, que apontava para `fichas_paciente` (tabela inexistente; a
    real e `paciente_fichas`) e so nao quebrava porque as foreign keys do SQLite
    vinham desligadas.

    A referencia e `pacientes(id)` e nao a ficha: quem cria agenda chama
    `_ensure_paciente`, que garante a linha em `pacientes`, e nada no fluxo
    garante que exista ficha.
    """
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agendas_paciente (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                descricao TEXT,
                
                -- Recorrência semanal
                dias_semana TEXT,  -- JSON: [0,1,2,3,4,5,6] ou null
                
                -- Horários
                hora_inicio TEXT,  -- HH:MM
                hora_fim TEXT,     -- HH:MM
                
                -- Para agendamentos únicos
                data_inicio TEXT,  -- YYYY-MM-DD
                data_fim TEXT,     -- YYYY-MM-DD
                
                -- Configuração
                modo TEXT DEFAULT 'suprimir',
                reducao_janela_min INTEGER,
                
                ativo BOOLEAN DEFAULT 1,
                
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            )
        """)
        
        # Índices
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agendas_paciente_id 
            ON agendas_paciente(paciente_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agendas_ativo 
            ON agendas_paciente(ativo)
        """)


def criar_agenda(
    db_path: str,
    paciente_id: str,
    tipo: str,
    descricao: Optional[str] = None,
    dias_semana: Optional[list[int]] = None,
    hora_inicio: str = "00:00",
    hora_fim: str = "23:59",
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    modo: str = "suprimir",
    reducao_janela_min: Optional[int] = None,
) -> dict:
    """
    Cria uma nova agenda de supressão.
    
    Args:
        db_path: Caminho do banco
        paciente_id: ID do paciente
        tipo: Tipo de agenda (refeicao, cirurgia, procedimento, atendimento, outro)
        descricao: Descrição legível
        dias_semana: Lista [0-6] para recorrência semanal (None = não recorrente)
        hora_inicio: HH:MM
        hora_fim: HH:MM
        data_inicio: YYYY-MM-DD (para agendamentos únicos)
        data_fim: YYYY-MM-DD (para multi-dia)
        modo: 'suprimir', 'reduzir', 'monitorar'
        reducao_janela_min: Se modo='reduzir', redução em minutos
        
    Returns:
        dict com dados da agenda criada
    """
    # Validar
    if tipo not in ("refeicao", "cirurgia", "procedimento", "atendimento", "outro"):
        raise ValueError(f"Tipo inválido: {tipo}")
    
    if modo not in ("suprimir", "reduzir", "monitorar"):
        raise ValueError(f"Modo inválido: {modo}")
    
    if modo == "reduzir" and (reducao_janela_min is None or reducao_janela_min < 5 or reducao_janela_min > 60):
        raise ValueError("reducao_janela_min deve estar entre 5 e 60")
    
    if dias_semana:
        if not all(0 <= d <= 6 for d in dias_semana):
            raise ValueError("dias_semana deve conter apenas valores 0-6")
    
    dias_json = json.dumps(dias_semana) if dias_semana else None
    
    with _connect(db_path) as conn:
        _ensure_paciente(conn, paciente_id)
        
        cursor = conn.execute("""
            INSERT INTO agendas_paciente (
                paciente_id, tipo, descricao,
                dias_semana, hora_inicio, hora_fim,
                data_inicio, data_fim,
                modo, reducao_janela_min, ativo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            paciente_id, tipo, descricao,
            dias_json, hora_inicio, hora_fim,
            data_inicio, data_fim,
            modo, reducao_janela_min
        ))
        
        agenda_id = cursor.lastrowid
        conn.commit()
    
    return obter_agenda(db_path, paciente_id, agenda_id)


def obter_agenda(db_path: str, paciente_id: str, agenda_id: int) -> dict:
    """Obtém uma agenda específica."""
    with _connect(db_path) as conn:
        cursor = conn.execute("""
            SELECT id, paciente_id, tipo, descricao,
                   dias_semana, hora_inicio, hora_fim,
                   data_inicio, data_fim,
                   modo, reducao_janela_min, ativo,
                   created_at, updated_at
            FROM agendas_paciente
            WHERE id = ? AND paciente_id = ?
        """, (agenda_id, paciente_id))
        
        row = cursor.fetchone()
    
    if not row:
        raise LookupError(f"Agenda {agenda_id} não encontrada")
    
    return _agenda_row_to_dict(row)


def listar_agendas(
    db_path: str,
    paciente_id: str,
    ativo_only: bool = True,
    conn=None,
) -> list[dict]:
    """Lista agendas de um paciente.

    Aceita conexao de fora porque esta consulta roda a CADA amostra de sensor,
    pelo caminho de supressao. Com conexao propria ela custava 14% do tempo de
    ingestao — nao pela consulta em si, que e trivial, mas por abrir conexao e
    rodar os PRAGMAs de novo.
    """
    from interface.db_core import conexao_ou_propria

    with conexao_ou_propria(db_path, conn) as conn:
        query = """
            SELECT id, paciente_id, tipo, descricao,
                   dias_semana, hora_inicio, hora_fim,
                   data_inicio, data_fim,
                   modo, reducao_janela_min, ativo,
                   created_at, updated_at
            FROM agendas_paciente
            WHERE paciente_id = ?
        """
        params = [paciente_id]
        
        if ativo_only:
            query += " AND ativo = 1"
        
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
    
    return [_agenda_row_to_dict(row) for row in rows]


def atualizar_agenda(
    db_path: str,
    paciente_id: str,
    agenda_id: int,
    **kwargs
) -> dict:
    """Atualiza campos de uma agenda."""
    # Validar campos permitidos
    allowed = {
        "tipo", "descricao", "dias_semana", "hora_inicio", "hora_fim",
        "data_inicio", "data_fim", "modo", "reducao_janela_min", "ativo"
    }
    
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if not updates:
        return obter_agenda(db_path, paciente_id, agenda_id)
    
    # Converter dias_semana para JSON se presente
    if "dias_semana" in updates:
        updates["dias_semana"] = json.dumps(updates["dias_semana"]) if updates["dias_semana"] else None
    
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    # updated_at segue o mesmo referencial do resto do banco: UTC naive.
    values = list(updates.values()) + [agora_utc_naive().isoformat(), agenda_id, paciente_id]
    
    with _connect(db_path) as conn:
        conn.execute(f"""
            UPDATE agendas_paciente
            SET {set_clause}, updated_at = ?
            WHERE id = ? AND paciente_id = ?
        """, values)
        conn.commit()
    
    return obter_agenda(db_path, paciente_id, agenda_id)


def deletar_agenda(db_path: str, paciente_id: str, agenda_id: int) -> bool:
    """Deleta uma agenda."""
    with _connect(db_path) as conn:
        cursor = conn.execute("""
            DELETE FROM agendas_paciente
            WHERE id = ? AND paciente_id = ?
        """, (agenda_id, paciente_id))
        
        conn.commit()
        return cursor.rowcount > 0


def is_timestamp_in_suppressed_period(
    db_path: str,
    paciente_id: str,
    timestamp: datetime,
    conn=None,
) -> tuple[bool, str]:
    """
    Verifica se um timestamp está dentro de período suprimido.
    
    Args:
        db_path: Caminho do banco
        paciente_id: ID do paciente
        timestamp: datetime para verificar
        
    Returns:
        (is_suppressed, modo_resultado)
        - is_suppressed: True se em período suprimido
        - modo_resultado: Modo resultante (suprimir, reduzir, monitorar)
    """
    agendas = listar_agendas(db_path, paciente_id, ativo_only=True, conn=conn)
    
    matching_agendas = []
    
    for agenda in agendas:
        if _timestamp_matches_agenda(timestamp, agenda):
            matching_agendas.append(agenda)
    
    if not matching_agendas:
        return False, None
    
    # Se alguma agenda é 'suprimir', retorna suprimir
    for agenda in matching_agendas:
        if agenda["modo"] == "suprimir":
            return True, "suprimir"
    
    # Caso contrário, retorna o modo mais restritivo
    # reduzir > monitorar
    for agenda in matching_agendas:
        if agenda["modo"] == "reduzir":
            return True, "reduzir"
    
    return True, "monitorar"


def get_reducao_janela(db_path: str, paciente_id: str, timestamp: Union[datetime, str]) -> int:
    """Retorna a maior `reducao_janela_min` entre as agendas 'reduzir' ATIVAS
    do paciente que casam com o `timestamp`. Retorna 0 se nenhuma casar.

    Reusa `listar_agendas`/`_timestamp_matches_agenda` (não faz SQL cru nem
    filtra por uma coluna `deletado` inexistente — bug anterior que deixava a
    redução de janela 100% morta).
    """
    agendas = listar_agendas(db_path, paciente_id, ativo_only=True)
    reducoes = [
        int(a["reducao_janela_min"])
        for a in agendas
        if a.get("modo") == "reduzir"
        and a.get("reducao_janela_min")
        and _timestamp_matches_agenda(timestamp, a)
    ]
    return max(reducoes) if reducoes else 0


def _timestamp_matches_agenda(timestamp: Union[datetime, str], agenda: dict) -> bool:
    """Verifica se timestamp corresponde ao horário/data da agenda."""
    
    # Convert string timestamp to datetime if needed
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)
        except (ValueError, AttributeError):
            return False
    
    ts_time = timestamp.time()
    ts_date = timestamp.date()

    # Parse horários
    hora_inicio = datetime.strptime(agenda["hora_inicio"], "%H:%M").time()
    hora_fim = datetime.strptime(agenda["hora_fim"], "%H:%M").time()

    # Janela que CRUZA A MEIA-NOITE (ex. 22:00–06:00, "não perturbar durante o
    # sono"). A comparação simples `inicio <= ts <= fim` é sempre falsa quando
    # fim < inicio, então a agenda era aceita pela API, aparecia na tela e nunca
    # suprimia nada — o pior modo de falha para uma regra de supressão, porque a
    # equipe acredita que o período está configurado.
    #
    # Nesse caso a ocorrência da janela COMEÇA no dia anterior para os
    # timestamps da madrugada, e é a data desse início que vale para a checagem
    # de dia da semana / data específica: uma agenda de segunda 22:00–06:00
    # cobre a madrugada de terça.
    if hora_fim < hora_inicio:
        if ts_time >= hora_inicio:
            pass                      # noite: a janela começou hoje
        elif ts_time <= hora_fim:
            ts_date = ts_date - timedelta(days=1)   # madrugada: começou ontem
        else:
            return False
    elif not (hora_inicio <= ts_time <= hora_fim):
        return False

    # Verificar dia/data
    if agenda["dias_semana"]:
        # Recorrente - verificar dia da semana
        dias = agenda["dias_semana"]
        # Handle both list and JSON string formats
        if isinstance(dias, str):
            dias = json.loads(dias)
        if ts_date.weekday() not in dias:
            return False
    else:
        # Único - verificar data específica
        if not agenda["data_inicio"]:
            # Agenda sem recorrencia E sem data: nao diz quando vale. A API
            # passou a recusar (AgendaCreate.exigir_recorrencia_ou_data), mas
            # linhas antigas podem existir. Antes isto fazia
            # `fromisoformat(None)` levantar TypeError, e quem chama trata
            # excecao como fail-safe "nao suprime" — ou seja, a agenda ficava
            # inerte por um caminho que ninguem via. Sair por False e o mesmo
            # resultado, sem esconder um erro no meio.
            return False
        data_inicio = datetime.fromisoformat(agenda["data_inicio"]).date()
        
        if agenda["data_fim"]:
            data_fim = datetime.fromisoformat(agenda["data_fim"]).date()
        else:
            data_fim = data_inicio
        
        if not (data_inicio <= ts_date <= data_fim):
            return False
    
    return True


def _agenda_row_to_dict(row) -> dict:
    """Converte row de SQLite para dict."""
    return {
        "id": row[0],
        "paciente_id": row[1],
        "tipo": row[2],
        "descricao": row[3],
        "dias_semana": json.loads(row[4]) if row[4] else None,
        "hora_inicio": row[5],
        "hora_fim": row[6],
        "data_inicio": row[7],
        "data_fim": row[8],
        "modo": row[9],
        "reducao_janela_min": row[10],
        "ativo": bool(row[11]),
        "created_at": row[12],
        "updated_at": row[13],
    }
