#!/usr/bin/env python3
"""
Script de limpeza de dados após demonstração do sistema.

ATENÇÃO: Remove APENAS DADOS, mantendo a estrutura (schema) intacta.
Ideal para executar após demos/apresentações para resetar o ambiente.
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path


def fazer_backup(db_path: str) -> str:
    """Cria backup do banco antes da limpeza."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def limpar_pos_demo(db_path: str = "dados.db", fazer_backup_antes: bool = True):
    """
    Limpa dados de demonstração do banco.
    
    O QUE SERÁ REMOVIDO:
    - ✓ Todos os eventos de postura (grade)
    - ✓ Todos os alertas
    - ✓ Timeline events
    - ✓ Eventos de dispositivos
    - ✓ Cache de processamento
    - ✓ TODOS os pacientes (inclusive reais)
    - ✓ Agendas e rotinas
    - ✓ Históricos de leito
    - ✓ Atribuições de devices
    
    O QUE SERÁ MANTIDO:
    - ✓ Usuários do sistema
    - ✓ Devices cadastrados (ESP32-001, etc.)
    - ✓ Estrutura das tabelas (schema)
    
    Args:
        db_path: Caminho do banco de dados
        fazer_backup_antes: Se True, cria backup antes de limpar
    """
    
    if not Path(db_path).exists():
        print(f"❌ Banco de dados '{db_path}' não encontrado!")
        return False
    
    print("=" * 80)
    print("🧹 LIMPEZA PÓS-DEMONSTRAÇÃO")
    print("=" * 80)
    print(f"Banco: {db_path}")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    print("⚠️  ATENÇÃO: Esta operação irá REMOVER:")
    print()
    print("  ❌ TODOS os eventos de postura (grade)")
    print("  ❌ TODOS os alertas")
    print("  ❌ TODOS os pacientes (incluindo dados reais)")
    print("  ❌ Timeline events")
    print("  ❌ Eventos de dispositivos")
    print("  ❌ Agendas e rotinas")
    print("  ❌ Históricos de leito")
    print("  ❌ Cache de processamento")
    print()
    print("✅ Será MANTIDO:")
    print()
    print("  ✓ Usuários do sistema")
    print("  ✓ Devices cadastrados")
    print("  ✓ Estrutura das tabelas")
    print()
    
    if fazer_backup_antes:
        print(f"💾 Backup será criado automaticamente")
    
    print("=" * 80)
    print()
    
    resposta = input("Confirma limpeza? (digite 'SIM' para confirmar): ")
    if resposta.strip().upper() != "SIM":
        print("❌ Operação cancelada pelo usuário")
        return False
    
    try:
        # Criar backup
        if fazer_backup_antes:
            print("\n💾 Criando backup...")
            backup_path = fazer_backup(db_path)
            print(f"   ✓ Backup criado: {backup_path}")
        
        print("\n" + "=" * 80)
        print("Iniciando limpeza...")
        print("=" * 80 + "\n")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Estatísticas antes
        print("📊 Coletando estatísticas...")
        tabelas_para_limpar = {
            'grade': 'Eventos de postura',
            'alertas': 'Alertas gerados',
            'timeline_events': 'Eventos da timeline',
            'device_events': 'Eventos de dispositivos',
            'estado_incremental': 'Cache de processamento',
            'eventos': 'Eventos genéricos',
            'pacientes': 'Pacientes',
            'paciente_fichas': 'Fichas de pacientes',
            'agendas_paciente': 'Agendas',
            'paciente_rotinas': 'Rotinas',
            'paciente_documentos': 'Documentos',
            'paciente_cama_history': 'Histórico de leitos',
            'device_assignments': 'Atribuições de devices'
        }
        
        stats_antes = {}
        for tabela in tabelas_para_limpar.keys():
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            stats_antes[tabela] = cursor.fetchone()[0]
        
        print()
        
        # EXECUTAR LIMPEZA
        total_removidos = 0
        
        # 1. Limpar tabelas de dados de pacientes (ordem importa devido a FKs)
        print("🗑️  Removendo dados de pacientes...")
        
        cursor.execute("DELETE FROM paciente_documentos")
        docs = cursor.rowcount
        print(f"   ✓ paciente_documentos: {docs} removidos")
        total_removidos += docs
        
        cursor.execute("DELETE FROM paciente_rotinas")
        rotinas = cursor.rowcount
        print(f"   ✓ paciente_rotinas: {rotinas} removidos")
        total_removidos += rotinas
        
        cursor.execute("DELETE FROM agendas_paciente")
        agendas = cursor.rowcount
        print(f"   ✓ agendas_paciente: {agendas} removidos")
        total_removidos += agendas
        
        cursor.execute("DELETE FROM paciente_fichas")
        fichas = cursor.rowcount
        print(f"   ✓ paciente_fichas: {fichas} removidos")
        total_removidos += fichas
        
        cursor.execute("DELETE FROM pacientes")
        pacientes = cursor.rowcount
        print(f"   ✓ pacientes: {pacientes} removidos")
        total_removidos += pacientes
        
        # 2. Limpar eventos e alertas
        print("\n🗑️  Removendo eventos e alertas...")
        
        cursor.execute("DELETE FROM grade")
        grade = cursor.rowcount
        print(f"   ✓ grade: {grade} removidos")
        total_removidos += grade
        
        cursor.execute("DELETE FROM alertas")
        alertas = cursor.rowcount
        print(f"   ✓ alertas: {alertas} removidos")
        total_removidos += alertas
        
        cursor.execute("DELETE FROM timeline_events")
        timeline = cursor.rowcount
        print(f"   ✓ timeline_events: {timeline} removidos")
        total_removidos += timeline
        
        cursor.execute("DELETE FROM device_events")
        device_ev = cursor.rowcount
        print(f"   ✓ device_events: {device_ev} removidos")
        total_removidos += device_ev
        
        cursor.execute("DELETE FROM eventos")
        eventos = cursor.rowcount
        print(f"   ✓ eventos: {eventos} removidos")
        total_removidos += eventos
        
        cursor.execute("DELETE FROM estado_incremental")
        estado = cursor.rowcount
        print(f"   ✓ estado_incremental: {estado} removidos")
        total_removidos += estado
        
        # 3. Limpar históricos
        print("\n🗑️  Removendo históricos...")
        
        cursor.execute("DELETE FROM paciente_cama_history")
        cama_hist = cursor.rowcount
        print(f"   ✓ paciente_cama_history: {cama_hist} removidos")
        total_removidos += cama_hist
        
        cursor.execute("DELETE FROM device_assignments")
        dev_assign = cursor.rowcount
        print(f"   ✓ device_assignments: {dev_assign} removidos")
        total_removidos += dev_assign
        
        # Commit
        print("\n💾 Salvando alterações...")
        conn.commit()
        
        # Estatísticas depois
        print("\n" + "=" * 80)
        print("📊 RESULTADO DA LIMPEZA")
        print("=" * 80)
        
        stats_depois = {}
        for tabela in tabelas_para_limpar.keys():
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            stats_depois[tabela] = cursor.fetchone()[0]
        
        print(f"\n{'Tabela':<30} {'Antes':<10} {'Depois':<10} {'Removidos':<10}")
        print("-" * 80)
        for tabela, descricao in tabelas_para_limpar.items():
            antes = stats_antes[tabela]
            depois = stats_depois[tabela]
            removidos = antes - depois
            if removidos > 0:
                print(f"{descricao:<30} {antes:<10} {depois:<10} {removidos:<10}")
        
        print("-" * 80)
        print(f"{'TOTAL':<30} {'':<10} {'':<10} {total_removidos:<10}")
        
        # Verificar tabelas mantidas
        print("\n" + "=" * 80)
        print("📊 DADOS MANTIDOS")
        print("=" * 80)
        
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        print(f"   ✓ Usuários: {users_count}")
        
        cursor.execute("SELECT COUNT(*) FROM devices")
        devices_count = cursor.fetchone()[0]
        print(f"   ✓ Devices: {devices_count}")
        
        # VACUUM para recuperar espaço
        print("\n🗜️  Compactando banco de dados (VACUUM)...")
        cursor.execute("VACUUM")
        print("   ✓ Compactação concluída")
        
        conn.close()
        
        # Tamanho do arquivo
        tamanho_mb = Path(db_path).stat().st_size / (1024 * 1024)
        
        print("\n" + "=" * 80)
        print("✅ LIMPEZA CONCLUÍDA COM SUCESSO!")
        print("=" * 80)
        print()
        print(f"📊 Estatísticas finais:")
        print(f"   • Total de registros removidos: {total_removidos}")
        print(f"   • Tamanho do banco: {tamanho_mb:.2f} MB")
        if fazer_backup_antes:
            print(f"   • Backup salvo em: {backup_path}")
        print()
        print("💡 Próximos passos:")
        print("   • Sistema pronto para nova demonstração")
        print("   • Execute: preparar_demo.ps1 para criar pacientes demo")
        print("   • Ou cadastre pacientes manualmente no frontend")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO durante limpeza: {e}")
        import traceback
        traceback.print_exc()
        
        if fazer_backup_antes and 'backup_path' in locals():
            print(f"\n💡 Backup disponível em: {backup_path}")
            print("   Para restaurar: copy {backup_path} {db_path}")
        
        return False


if __name__ == "__main__":
    print()
    print("🧹 LIMPEZA PÓS-DEMONSTRAÇÃO")
    print()
    print("Este script irá limpar TODOS os dados de demonstração,")
    print("mantendo apenas usuários, devices e estrutura das tabelas.")
    print()
    
    try:
        limpar_pos_demo(db_path="dados.db", fazer_backup_antes=True)
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Erro: {e}")
