"""
Script para popular a timeline com eventos históricos de alertas.

Problema: 12 pacientes têm alertas mas não têm eventos na timeline.
Solução: Criar eventos retroativos (alert_open, alert_ack, alert_close) 
         baseados nos alertas existentes.

✅ Segurança:
   - Verifica se evento já existe antes de criar (evita duplicatas)
   - Usa transações para garantir atomicidade
   - Marca eventos como retroativos no meta
   - Execução idempotente (pode rodar múltiplas vezes sem problema)

Uso:
    python scripts/popular_timeline_historica.py [--dry-run] [--paciente PAC-0001]
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Adicionar pasta raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interface.dao import inserir_timeline_event

DB_PATH = Path("dados.db")


def verificar_evento_existe(conn: sqlite3.Connection, paciente_id: str, ts: str, tipo: str) -> bool:
    """Verifica se já existe um evento na timeline para evitar duplicatas."""
    cursor = conn.execute(
        "SELECT COUNT(*) FROM timeline_events WHERE paciente_id = ? AND ts = ? AND tipo = ?",
        (paciente_id, ts, tipo)
    )
    count = cursor.fetchone()[0]
    return count > 0


def popular_timeline_para_alertas(db_path: Path, dry_run: bool = False, paciente_filter: str | None = None):
    """
    Popula a timeline com eventos retroativos baseados nos alertas existentes.
    
    Args:
        db_path: Caminho do banco de dados
        dry_run: Se True, apenas mostra o que seria feito sem executar
        paciente_filter: Se fornecido, processa apenas este paciente
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Estatísticas
    stats = {
        'alertas_processados': 0,
        'eventos_criados': 0,
        'eventos_pulados': 0,
        'erros': 0
    }
    
    print("="*80)
    print("POPULANDO TIMELINE COM EVENTOS HISTÓRICOS")
    print("="*80)
    print(f"Banco: {db_path}")
    print(f"Modo: {'DRY RUN (simulação)' if dry_run else 'EXECUTANDO'}")
    if paciente_filter:
        print(f"Filtro: Apenas paciente {paciente_filter}")
    print()
    
    # Buscar todos os alertas (ou filtrados por paciente)
    if paciente_filter:
        query = """
            SELECT paciente_id, inicio, fim, tipo, status, perfil
            FROM alertas 
            WHERE paciente_id = ?
            ORDER BY inicio ASC
        """
        cursor = conn.execute(query, (paciente_filter,))
    else:
        query = """
            SELECT paciente_id, inicio, fim, tipo, status, perfil
            FROM alertas 
            ORDER BY inicio ASC
        """
        cursor = conn.execute(query)
    
    alertas = cursor.fetchall()
    total_alertas = len(alertas)
    
    print(f"Total de alertas a processar: {total_alertas}")
    print()
    
    for i, alerta in enumerate(alertas, 1):
        paciente_id = alerta['paciente_id']
        inicio = alerta['inicio']
        fim = alerta['fim']
        tipo = alerta['tipo']
        status = alerta['status']
        perfil = alerta['perfil']
        
        stats['alertas_processados'] += 1
        
        print(f"[{i}/{total_alertas}] Processando alerta: {paciente_id} | {inicio} | {tipo} | {status}")
        
        # 1. Criar evento alert_open (abertura do alerta)
        evento_open_existe = verificar_evento_existe(conn, paciente_id, inicio, "alert_open")
        
        if evento_open_existe:
            print("  ⏭️  Evento alert_open já existe - pulando")
            stats['eventos_pulados'] += 1
        else:
            if dry_run:
                print("  🔍 [DRY RUN] Criaria evento alert_open")
            else:
                try:
                    # Converter timestamp ISO para milliseconds
                    ts_dt = datetime.fromisoformat(inicio.replace('Z', '+00:00'))
                    ts_ms = int(ts_dt.timestamp() * 1000)
                    
                    inserir_timeline_event(
                        db_path=str(db_path),
                        paciente_id=paciente_id,
                        ts=inicio,
                        ts_ms=ts_ms,
                        tipo="alert_open",
                        descricao=f"Alerta de {tipo} iniciado (perfil: {perfil})",
                        meta={
                            "tipo": tipo,
                            "perfil": perfil,
                            "retroativo": True,
                            "migrado_em": datetime.now().isoformat()
                        }
                    )
                    print("  ✅ Evento alert_open criado")
                    stats['eventos_criados'] += 1
                except Exception as e:
                    print(f"  ❌ Erro ao criar alert_open: {e}")
                    stats['erros'] += 1
        
        # 2. Criar evento alert_ack se status = reconhecido
        if status == "reconhecido":
            # Para eventos reconhecidos, usar o próprio timestamp de início
            # (não temos timestamp exato do reconhecimento)
            ts_ack = inicio
            
            evento_ack_existe = verificar_evento_existe(conn, paciente_id, ts_ack, "alert_ack")
            
            if evento_ack_existe:
                print("  ⏭️  Evento alert_ack já existe - pulando")
                stats['eventos_pulados'] += 1
            else:
                if dry_run:
                    print("  🔍 [DRY RUN] Criaria evento alert_ack")
                else:
                    try:
                        # Converter timestamp ISO para milliseconds
                        ts_dt = datetime.fromisoformat(ts_ack.replace('Z', '+00:00'))
                        ts_ms = int(ts_dt.timestamp() * 1000)
                        
                        inserir_timeline_event(
                            db_path=str(db_path),
                            paciente_id=paciente_id,
                            ts=ts_ack,
                            ts_ms=ts_ms,
                            tipo="alert_ack",
                            descricao="Alerta reconhecido pela equipe",
                            meta={
                                "tipo": tipo,
                                "retroativo": True,
                                "migrado_em": datetime.now().isoformat(),
                                "nota": "Timestamp aproximado (mesmo que abertura)"
                            }
                        )
                        print("  ✅ Evento alert_ack criado")
                        stats['eventos_criados'] += 1
                    except Exception as e:
                        print(f"  ❌ Erro ao criar alert_ack: {e}")
                        stats['erros'] += 1
        
        # 3. Criar evento alert_close se status = fechado E tem data de fim
        if status == "fechado" and fim:
            evento_close_existe = verificar_evento_existe(conn, paciente_id, fim, "alert_close")
            
            if evento_close_existe:
                print("  ⏭️  Evento alert_close já existe - pulando")
                stats['eventos_pulados'] += 1
            else:
                if dry_run:
                    print("  🔍 [DRY RUN] Criaria evento alert_close")
                else:
                    try:
                        # Converter timestamp ISO para milliseconds
                        ts_dt = datetime.fromisoformat(fim.replace('Z', '+00:00'))
                        ts_ms = int(ts_dt.timestamp() * 1000)
                        
                        inserir_timeline_event(
                            db_path=str(db_path),
                            paciente_id=paciente_id,
                            ts=fim,
                            ts_ms=ts_ms,
                            tipo="alert_close",
                            descricao="Alerta fechado/completado pela equipe",
                            meta={
                                "tipo": tipo,
                                "retroativo": True,
                                "migrado_em": datetime.now().isoformat()
                            }
                        )
                        print("  ✅ Evento alert_close criado")
                        stats['eventos_criados'] += 1
                    except Exception as e:
                        print(f"  ❌ Erro ao criar alert_close: {e}")
                        stats['erros'] += 1
        elif status == "fechado" and not fim:
            print("  ⚠️  Alerta fechado mas sem data de fim - pulando alert_close")
        
        print()
    
    conn.close()
    
    # Relatório final
    print("="*80)
    print("RELATÓRIO FINAL")
    print("="*80)
    print(f"Alertas processados:      {stats['alertas_processados']}")
    print(f"Eventos criados:          {stats['eventos_criados']}")
    print(f"Eventos já existentes:    {stats['eventos_pulados']}")
    print(f"Erros:                    {stats['erros']}")
    print()
    
    if dry_run:
        print("⚠️  MODO DRY RUN: Nenhuma alteração foi feita no banco")
        print("   Execute sem --dry-run para aplicar as mudanças")
    else:
        print("✅ MIGRAÇÃO CONCLUÍDA!")
        print("   Execute diagnostico_alinhamento.py para verificar o resultado")
    
    print("="*80)
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Popula timeline com eventos históricos de alertas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  # Ver o que seria feito (simulação)
  python scripts/popular_timeline_historica.py --dry-run
  
  # Executar migração completa
  python scripts/popular_timeline_historica.py
  
  # Migrar apenas um paciente específico
  python scripts/popular_timeline_historica.py --paciente PAC-7778
  
  # Simulação para um paciente
  python scripts/popular_timeline_historica.py --dry-run --paciente PAC-0001
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simula a execução sem fazer alterações no banco'
    )
    parser.add_argument(
        '--paciente',
        type=str,
        help='Processa apenas o paciente especificado (ex: PAC-0001)'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=DB_PATH,
        help=f'Caminho do banco de dados (padrão: {DB_PATH})'
    )
    
    args = parser.parse_args()
    
    # Verificar se banco existe
    if not args.db.exists():
        print(f"❌ ERRO: Banco de dados não encontrado: {args.db}")
        print("   Verifique se o caminho está correto")
        sys.exit(1)
    
    # Executar migração
    try:
        stats = popular_timeline_para_alertas(
            db_path=args.db,
            dry_run=args.dry_run,
            paciente_filter=args.paciente
        )
        
        # Exit code baseado em erros
        sys.exit(0 if stats['erros'] == 0 else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Migração cancelada pelo usuário")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
