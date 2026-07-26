"""Backup do banco SQLite, com verificacao obrigatoria.

A regra desta camada: **um arquivo que nao foi verificado nao conta como
backup**. Antes, `create_backup` gravava o arquivo, media o tamanho e registrava
`backup_created` — nada jamais abria o resultado. Um backup truncado, vazio ou
corrompido produzia exatamente o mesmo log de sucesso, e a descoberta ficava
para o dia em que alguem precisasse restaurar, que e o pior momento possivel
para descobrir.

O mesmo raciocinio da deteccao de silencio se aplica aqui: um mecanismo de
seguranca em que as pessoas confiam e que falha calado e pior que a ausencia
dele, porque desloca a atencao para longe do risco.
"""

import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from interface.db_core import BUSY_TIMEOUT_MS

logger = structlog.get_logger(__name__)

# Tabelas sem as quais o arquivo nao serve para restaurar o sistema. Nao e o
# esquema inteiro de proposito: migracoes acrescentam tabelas, e a lista existe
# para detectar um backup TRUNCADO, nao para engessar o esquema.
TABELAS_ESSENCIAIS = ("pacientes", "grade", "eventos", "alertas")

# Quantos backups mais recentes nunca sao apagados, por mais velhos que sejam.
# `cleanup_old_backups(keep_days=0)` removia TODOS — inclusive o unico bom.
MANTER_MINIMO = 3


class BackupInvalido(RuntimeError):
    """O arquivo existe mas nao serve para restaurar."""


@dataclass
class Verificacao:
    """Resultado de abrir um backup e conferir se ele presta."""

    ok: bool
    motivo: str | None = None
    tabelas: int = 0
    linhas: dict[str, int] | None = None

    def __bool__(self) -> bool:
        return self.ok


def verificar_arquivo(caminho: str | Path) -> Verificacao:
    """Abre o arquivo e confere que da para restaurar a partir dele.

    Tres perguntas, nesta ordem: o SQLite consegue ler? a estrutura esta
    integra? as tabelas de que o sistema depende estao la? Só responder "o
    arquivo existe e tem N MB" nao diz nada — um arquivo de zeros tem tamanho.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return Verificacao(False, "arquivo nao existe")
    if caminho.stat().st_size == 0:
        return Verificacao(False, "arquivo vazio")

    try:
        with closing(sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)) as conn:
            integridade = conn.execute("PRAGMA integrity_check").fetchone()
            if not integridade or integridade[0] != "ok":
                return Verificacao(False, f"integrity_check: {integridade[0] if integridade else 'sem resposta'}")

            tabelas = {
                linha[0]
                for linha in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            faltando = [t for t in TABELAS_ESSENCIAIS if t not in tabelas]
            if faltando:
                return Verificacao(False, f"tabelas essenciais ausentes: {faltando}", len(tabelas))

            linhas = {
                tabela: conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
                for tabela in TABELAS_ESSENCIAIS
            }
    except sqlite3.DatabaseError as exc:
        return Verificacao(False, f"sqlite recusou o arquivo: {exc}")

    return Verificacao(True, None, len(tabelas), linhas)


class BackupService:
    """Gerencia backups do banco de dados."""

    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        # `parents=True`: com UPP_BACKUP_DIR apontando para um caminho aninhado
        # que ainda nao existe, o mkdir estourava e derrubava a inicializacao.
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> str:
        """Cria um backup e SO retorna se ele passar na verificacao.

        Se o arquivo gerado nao presta, ele e removido e a chamada falha. Deixar
        no diretorio um arquivo que nao restaura e pior que nao ter arquivo
        nenhum: ele aparece na listagem, envelhece o contador de "ultimo
        backup" e passa a impressao de cobertura que nao existe.
        """
        # UTC, como todo timestamp deste sistema (ver interface/tempo.py). Com
        # hora local, a ordenacao dos nomes se embaralha na virada do horario
        # de verao e dois backups podem colidir no mesmo nome.
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}.db"
        # O nome tem resolucao de SEGUNDO: dois backups no mesmo segundo caiam
        # no mesmo arquivo e o segundo sobrescrevia o primeiro em silencio —
        # um ponto de restauracao a menos, sem nada no log dizendo isso. Nunca
        # escrever por cima de um backup existente.
        sufixo = 1
        while backup_path.exists():
            backup_path = self.backup_dir / f"backup_{timestamp}_{sufixo}.db"
            sufixo += 1
        backup_filename = backup_path.name

        try:
            # API de backup online do SQLite: consistente mesmo com escrita
            # concorrente, ao contrario de copiar o arquivo.
            # `closing` garante o fechamento tambem quando o backup falha no
            # meio: antes os dois close() ficavam depois do backup e eram
            # pulados em caso de excecao, vazando as duas conexoes.
            with closing(sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_MS / 1000)) as source_conn, \
                 closing(sqlite3.connect(str(backup_path), timeout=BUSY_TIMEOUT_MS / 1000)) as backup_conn:
                source_conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                with backup_conn:
                    source_conn.backup(backup_conn)
        except Exception as e:
            logger.error("backup_failed", error=str(e), path=self.db_path)
            backup_path.unlink(missing_ok=True)
            raise

        verificacao = verificar_arquivo(backup_path)
        if not verificacao:
            logger.error("backup_invalido", filename=backup_filename, motivo=verificacao.motivo)
            backup_path.unlink(missing_ok=True)
            raise BackupInvalido(
                f"o backup gerado nao passou na verificacao: {verificacao.motivo}"
            )

        size_mb = backup_path.stat().st_size / (1024 * 1024)
        logger.info(
            "backup_created",
            filename=backup_filename,
            size_mb=round(size_mb, 2),
            path=str(backup_path),
            verificado=True,
            linhas=verificacao.linhas,
        )
        return str(backup_path)

    def cleanup_old_backups(self, keep_days: int = 7) -> int:
        """Remove backups antigos, preservando sempre os `MANTER_MINIMO` mais novos.

        A idade sozinha e um criterio perigoso: uma instalacao que ficou parada
        um mes tem todos os backups "velhos", e `keep_days=0` apagava ate o
        unico arquivo bom que existia. O piso por contagem garante que sempre
        sobra de onde restaurar.
        """
        cutoff_time = datetime.now().timestamp() - (keep_days * 86400)
        removed_count = 0

        try:
            arquivos = sorted(
                self.backup_dir.glob("backup_*.db"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            protegidos = set(arquivos[:MANTER_MINIMO])

            for backup_file in arquivos:
                if backup_file in protegidos:
                    continue
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    removed_count += 1
                    logger.info("backup_removed", filename=backup_file.name)

            if removed_count > 0:
                logger.info(
                    "backups_cleaned",
                    removed=removed_count,
                    kept_days=keep_days,
                    protegidos=len(protegidos),
                )

            return removed_count

        except Exception as e:
            logger.error("backup_cleanup_failed", error=str(e))
            return removed_count

    def list_backups(self) -> list[dict]:
        """Lista os backups disponiveis com metadados."""
        backups = []

        try:
            for backup_file in sorted(self.backup_dir.glob("backup_*.db"), reverse=True):
                stat = backup_file.stat()
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "age_hours": round((datetime.now().timestamp() - stat.st_mtime) / 3600, 1)
                })

        except Exception as e:
            logger.error("list_backups_failed", error=str(e))

        return backups

    def verificar_todos(self) -> list[dict]:
        """Verifica cada backup do diretorio. Util antes de confiar em um deles."""
        resultado = []
        for item in self.list_backups():
            verificacao = verificar_arquivo(item["path"])
            resultado.append({
                **item,
                "ok": verificacao.ok,
                "motivo": verificacao.motivo,
                "linhas": verificacao.linhas,
            })
        return resultado

    def estado(self, intervalo_esperado_horas: int = 24) -> dict:
        """Ha um backup recente e utilizavel?

        Existe para a falha ser VISIVEL. O agendador podia estar falhando havia
        semanas — cada ciclo registrava o erro e seguia — sem que nada na
        aplicacao ficasse diferente de uma instalacao saudavel.
        """
        backups = self.verificar_todos()
        validos = [b for b in backups if b["ok"]]
        mais_recente = validos[0] if validos else None
        # Tolerancia de meio intervalo: um ciclo que atrasa alguns minutos nao e
        # um incidente, um ciclo que nao aconteceu e.
        limite = intervalo_esperado_horas * 1.5

        return {
            "total": len(backups),
            "validos": len(validos),
            "invalidos": [b["filename"] for b in backups if not b["ok"]],
            "ultimo_valido": mais_recente["filename"] if mais_recente else None,
            "idade_horas": mais_recente["age_hours"] if mais_recente else None,
            "saudavel": bool(mais_recente) and mais_recente["age_hours"] <= limite,
        }

    def restore_backup(self, backup_filename: str, target_path: str | None = None) -> bool:
        """Restaura um backup, verificando ANTES de copiar e DEPOIS de copiar.

        Restaurar por cima do banco de producao a partir de um arquivo que
        ninguem conferiu troca uma base viva por uma possivelmente corrompida —
        e o estrago so aparece depois, com a base boa ja sobrescrita.
        """
        backup_path = self.backup_dir / backup_filename

        verificacao = verificar_arquivo(backup_path)
        if not verificacao:
            logger.error(
                "backup_restore_recusado", filename=backup_filename, motivo=verificacao.motivo
            )
            return False

        if target_path is None:
            target_path = f"{self.db_path}.restored"

        try:
            shutil.copy2(backup_path, target_path)
        except Exception as e:
            logger.error("backup_restore_failed", error=str(e), filename=backup_filename)
            return False

        # Conferir o DESTINO: a copia pode falhar por disco cheio sem levantar
        # excecao em todos os sistemas de arquivos.
        destino = verificar_arquivo(target_path)
        if not destino:
            logger.error(
                "backup_restore_destino_invalido", target=target_path, motivo=destino.motivo
            )
            return False

        logger.info(
            "backup_restored", source=backup_filename, target=target_path, linhas=destino.linhas
        )
        return True


# Scheduled backup task (chamada periodicamente pelo lifespan da app, ver interface/web.py)
def scheduled_backup_task(db_path: str = "dados.db", backup_dir: str = "backups", keep_days: int = 7) -> None:
    """Cria um backup verificado e limpa os antigos.

    Deixa a excecao subir: quem chama (interface/lifespan_tasks.py) registra o
    erro e mantem o loop vivo. Engolir aqui apagaria a distincao entre "o
    backup foi feito" e "o backup falhou de novo".
    """
    service = BackupService(db_path, backup_dir=backup_dir)
    service.create_backup()
    service.cleanup_old_backups(keep_days=keep_days)
