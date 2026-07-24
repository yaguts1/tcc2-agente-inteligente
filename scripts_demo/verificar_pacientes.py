"""Script helper para preparar demonstração."""
import sqlite3
import sys

def verificar_pacientes():
    """Verifica se existem pacientes cadastrados."""
    conn = sqlite3.connect('dados.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM pacientes')
    total = cursor.fetchone()[0]
    
    if total == 0:
        print("\nERRO: Nenhum paciente cadastrado!\n")
        print("Para preparar a demonstracao, voce precisa primeiro cadastrar pacientes.\n")
        print("Opcoes:")
        print("  1. Abra o frontend: http://localhost:5173")
        print("  2. Va para a pagina Pacientes")
        print("  3. Clique em 'Novo Paciente'")
        print("  4. Cadastre pelo menos 1 paciente com:")
        print("     - Nome")
        print("     - Leito (ex: C-01)")
        print("     - Perfil de risco (alto, medio ou baixo)\n")
        print("Apos cadastrar, execute este script novamente.\n")
        conn.close()
        return False
    
    print(f"OK: {total} paciente(s) encontrado(s)\n")
    
    # Listar pacientes
    cursor.execute('''
        SELECT p.id, COALESCE(f.nome, p.id) as nome, COALESCE(f.perfil, 'medio') as perfil
        FROM pacientes p
        LEFT JOIN paciente_fichas f ON p.id = f.paciente_id
        ORDER BY p.id
    ''')
    
    print("Pacientes cadastrados:")
    print(f"{'ID':<20} {'Nome':<30} {'Perfil'}")
    print("-" * 60)
    for row in cursor.fetchall():
        print(f"{row[0]:<20} {row[1]:<30} {row[2]}")
    
    conn.close()
    return True

def listar_pacientes_para_gerar():
    """Lista pacientes no formato ID|PERFIL."""
    conn = sqlite3.connect('dados.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, COALESCE(f.perfil, 'medio') as perfil
        FROM pacientes p
        LEFT JOIN paciente_fichas f ON p.id = f.paciente_id
        ORDER BY p.id
    ''')
    
    for row in cursor.fetchall():
        print(f"{row[0]}|{row[1]}")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "listar":
        listar_pacientes_para_gerar()
    else:
        if not verificar_pacientes():
            sys.exit(1)
