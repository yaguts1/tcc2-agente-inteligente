"""
Serviço de backup automático do banco de dados SQLite.
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


class BackupService:
    """Gerencia backups automáticos do banco de dados."""
    
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self) -> str:
        """
        Cria um backup do banco de dados usando o método online do SQLite.
        Retorna o caminho do arquivo de backup criado.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename
        
        try:
            # Use SQLite's online backup API (mais seguro que simples cópia)
            source_conn = sqlite3.connect(self.db_path)
            backup_conn = sqlite3.connect(str(backup_path))
            
            # Perform the backup
            with backup_conn:
                source_conn.backup(backup_conn)
            
            source_conn.close()
            backup_conn.close()
            
            # Get file size
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            
            logger.info(
                "backup_created",
                filename=backup_filename,
                size_mb=round(size_mb, 2),
                path=str(backup_path)
            )
            
            return str(backup_path)
        
        except Exception as e:
            logger.error("backup_failed", error=str(e), path=self.db_path)
            raise
    
    def cleanup_old_backups(self, keep_days: int = 7) -> int:
        """
        Remove backups mais antigos que keep_days dias.
        Retorna o número de arquivos removidos.
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now().timestamp() - (keep_days * 86400)
        removed_count = 0
        
        try:
            for backup_file in self.backup_dir.glob("backup_*.db"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    removed_count += 1
                    logger.info("backup_removed", filename=backup_file.name)
            
            if removed_count > 0:
                logger.info("backups_cleaned", removed=removed_count, kept_days=keep_days)
            
            return removed_count
        
        except Exception as e:
            logger.error("backup_cleanup_failed", error=str(e))
            return removed_count
    
    def list_backups(self) -> list[dict]:
        """Lista todos os backups disponíveis com metadados."""
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
    
    def restore_backup(self, backup_filename: str, target_path: str | None = None) -> bool:
        """
        Restaura um backup para o caminho especificado.
        Se target_path não for fornecido, cria uma cópia com sufixo _restored.
        """
        backup_path = self.backup_dir / backup_filename
        
        if not backup_path.exists():
            logger.error("backup_not_found", filename=backup_filename)
            return False
        
        if target_path is None:
            target_path = f"{self.db_path}.restored"
        
        try:
            shutil.copy2(backup_path, target_path)
            logger.info("backup_restored", source=backup_filename, target=target_path)
            return True
        
        except Exception as e:
            logger.error("backup_restore_failed", error=str(e), filename=backup_filename)
            return False


# Scheduled backup task (chamada periodicamente pelo lifespan da app, ver interface/web.py)
def scheduled_backup_task(db_path: str = "dados.db", backup_dir: str = "backups", keep_days: int = 7) -> None:
    """
    Tarefa agendada para criar backup e limpar backups antigos.
    Ideal para executar diariamente.
    """
    service = BackupService(db_path, backup_dir=backup_dir)
    
    try:
        # Create backup
        service.create_backup()
        
        # Cleanup old backups
        service.cleanup_old_backups(keep_days=keep_days)
        
    except Exception as e:
        logger.error("scheduled_backup_failed", error=str(e))
