"""Core database connection and helper functions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from interface.tempo import agora_utc_naive

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

def ensure_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if path.suffix == "" and not path.name:
        raise ValueError("Caminho do banco de dados invalido.")
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path

# Quanto tempo o SQLite espera por um lock antes de desistir. Sem isto o
# default e ZERO: a primeira colisao levanta "database is locked" na hora, num
# app que por design tem WebSocket de ingestao, reconciler, backup periodico e
# requests HTTP escrevendo ao mesmo tempo.
BUSY_TIMEOUT_MS = 5000


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Conexao com o banco, para uso em `with connect(...) as conn:`.

    Commita ao sair sem erro, faz rollback se houver excecao e **fecha** em
    qualquer caso.

    O motivo de ser um contextmanager proprio: antes esta funcao devolvia a
    Connection crua e todo o codigo fazia `with connect(...) as conn:`, o que
    parece certo mas nao e — o context manager nativo do sqlite3 commita ou faz
    rollback e NAO fecha a conexao. Cada chamada de repositorio deixava uma
    conexao para o coletor de lixo.
    """
    path = ensure_db_path(db_path)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    try:
        # WAL reduz contencao entre leituras e escritas concorrentes (mesmo numa
        # unica instancia, o app tem WebSocket + reconciler + requests HTTP
        # escrevendo/lendo ao mesmo tempo).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # No SQLite as foreign keys sao POR CONEXAO e vem desligadas por default.
        # Sem esta linha, todo `ON DELETE CASCADE` e todo `REFERENCES` do
        # migrations/0001_baseline.sql eram decoracao: o banco aceitava filho sem
        # pai e a limpeza em cascata nunca acontecia — as remocoes funcionavam
        # so porque `repositories/pacientes.py` apaga tabela por tabela na mao.
        conn.execute("PRAGMA foreign_keys=ON")
        # `synchronous=FULL` (o default) faz um fsync a CADA commit. Com o
        # caminho de ingestao commitando varias vezes por amostra, era o item
        # isolado mais caro do perfil: 24% do tempo total em `commit`.
        #
        # `NORMAL` COM WAL nao e o mesmo afrouxamento que seria sem WAL. A
        # garantia que se perde e estreita e vale ser dita com precisao:
        #
        #   * crash da APLICACAO, kill -9, excecao, container reiniciado: nada
        #     se perde. O WAL ja esta escrito, e o SQLite o recupera na proxima
        #     abertura;
        #   * crash do SISTEMA OPERACIONAL ou queda de energia: as ultimas
        #     transacoes commitadas podem se perder. O banco NAO corrompe — essa
        #     e a diferenca em relacao a desligar o journal.
        #
        # O que se perderia sao os ultimos segundos de amostra de sensor num
        # apagao. O firmware reenvia enquanto a falha for transiente, e o dado
        # e uma serie temporal continua: um buraco de segundos e recuperavel, e
        # menor que o custo de um teto de ingestao que nao aguenta a ala cheia.
        #
        # Recomendacao oficial do SQLite para WAL, e nao um truque.
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def conexao_ou_propria(
    db_path: str, conn: sqlite3.Connection | None
) -> Iterator[sqlite3.Connection]:
    """Usa a conexao recebida, ou abre uma propria se `conn` for None.

    Existe para uma funcao de repositorio poder participar de uma transacao MAIOR
    sem duplicar a versao "com conexao" e a versao "sem".

    Quando `conn` vem de fora, o commit e o fechamento sao de quem abriu — daqui
    sai so o trabalho. Isso e o que torna possivel gravar grade, eventos, estado
    do motor e alertas numa transacao so.

    Por que importa: o caminho de ingestao abria QUATRO conexoes e commitava
    quatro vezes por amostra. Cada conexao paga abertura, quatro PRAGMAs e um
    commit, e no SQLite os commits de escrita serializam entre si — e por isso
    que o teto medido nao melhorava com concorrencia (26 amostras/s com 1 thread,
    36 com 8).

    E ha um ganho de CORRETUDE junto, que sozinho justificaria a mudanca: com
    quatro transacoes, uma falha no meio deixava a grade gravada e o alerta nao.
    Numa so, ou a amostra entra inteira ou nao entra.
    """
    if conn is not None:
        yield conn
        return
    with connect(db_path) as propria:
        yield propria


def utc_now_iso() -> str:
    """`agora` em UTC naive, no mesmo referencial dos timestamps do banco.

    Usava datetime.now() (hora LOCAL) apesar do nome: com TZ=America/Sao_Paulo
    isso gravava created_at/updated_at, as janelas de device_assignments e
    paciente_cama_history 3h deslocados dos ts_ms com que são comparados em
    resolver_paciente_por_device_em() — a query que decide de qual paciente é
    uma leitura de sensor.
    """
    return agora_utc_naive().strftime(ISO_FORMAT)

def norm_iso(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce", utc=False)
    if getattr(s.dtype, "tz", None) is not None:
        s = s.dt.tz_convert(None)
    s = s.dt.floor("s")
    formatted = s.dt.strftime(ISO_FORMAT).astype("object")
    formatted[formatted == "NaT"] = None
    return formatted


def ensure_paciente(conn: sqlite3.Connection, paciente_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))


# Bancos em que a coluna `grade.confianca` ja foi conferida neste processo.
# Ver `_ensure_grade_confianca_column`.
_GRADE_CONFIANCA_CONFERIDA: set[str] = set()


def _ensure_grade_confianca_column(
    conn: sqlite3.Connection, db_path: str | None = None
) -> None:
    """Garante `grade.confianca`, uma vez por banco e por processo.

    Redundante para bancos criados via migrations/0001_baseline.sql (que ja
    inclui a coluna), e mantida como rede para quem chama `inserir_grade`
    diretamente.

    O comentario anterior a chamava de "checagem de baixo custo". Nao era: ela
    roda no caminho de INGESTAO, ou seja a cada amostra de sensor, e custava um
    `PRAGMA table_info` mais um `commit` — que, alem do tempo, ENCERRAVA a
    transacao da amostra pelo meio. Depois de a ingestao passar a gravar tudo
    numa transacao so, isso deixou de ser desperdicio e passou a ser um furo na
    atomicidade.

    Agora: memoizada por caminho de banco, e sem `commit`. Se a coluna precisar
    ser criada, o ALTER participa da transacao de quem chamou — no SQLite DDL e
    transacional — e quem abriu a transacao decide quando commitar.
    """
    chave = str(db_path) if db_path else ""
    if chave and chave in _GRADE_CONFIANCA_CONFERIDA:
        return

    info = conn.execute("PRAGMA table_info(grade)").fetchall()
    colunas = {str(row["name"]) for row in info}
    if "confianca" not in colunas:
        conn.execute("ALTER TABLE grade ADD COLUMN confianca REAL")
    if chave:
        _GRADE_CONFIANCA_CONFERIDA.add(chave)


def criar_esquema(db_path: str = "dados.db") -> None:
    """Garante que o schema do banco está atualizado, aplicando as
    migrations pendentes (ver migrations/runner.py). Substituiu o antigo
    executescript inline + 3 funções ad-hoc de "a coluna existe?" — agora
    mudanças de schema são migrations versionadas e numeradas.
    """
    from migrations.runner import upgrade

    upgrade(db_path)
