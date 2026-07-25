"""
Script simples para verificar pacientes no banco de dados.
Uso: python ver_pacientes.py
"""

import sqlite3
import sys

def main():
    try:
        conn = sqlite3.connect('dados.db')
        cursor = conn.cursor()
        
        # Obter pacientes com informações
        cursor.execute('''
            SELECT p.id, f.cama_id, f.perfil, f.observacoes
            FROM pacientes p 
            LEFT JOIN paciente_fichas f ON p.id = f.paciente_id 
            ORDER BY p.id
        ''')
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ Nenhum paciente cadastrado no banco.")
            return 1
        
        print(f"\n{'='*70}")
        print(f"{'PACIENTES CADASTRADOS':^70}")
        print(f"{'='*70}\n")
        
        print(f"{'ID':<15} {'Leito':<20} {'Perfil':<12} {'Observações':<30}")
        print('-' * 70)
        
        for pac_id, cama_id, perfil, obs in rows:
            leito = cama_id if cama_id else '(sem leito)'
            perfil_str = perfil if perfil else '(sem perfil)'
            obs_str = obs[:25] + '...' if obs and len(obs) > 25 else (obs if obs else '')
            print(f"{pac_id:<15} {leito:<20} {perfil_str:<12} {obs_str:<30}")
        
        print('-' * 70)
        print(f"Total: {len(rows)} pacientes\n")
        
        # Estatísticas adicionais
        cursor.execute('SELECT COUNT(*) FROM grade')
        total_eventos = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM alertas')
        total_alertas = cursor.fetchone()[0]
        
        print("📊 Estatísticas:")
        print(f"   • Eventos de postura: {total_eventos:,}")
        print(f"   • Alertas gerados: {total_alertas:,}\n")
        
        conn.close()
        return 0
        
    except sqlite3.Error as e:
        print(f"❌ Erro ao acessar banco de dados: {e}")
        return 1
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
