import sqlite3
import pandas as pd

DB_PATH = 'dados.db'

def analyze_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== ANÁLISE DO BANCO DE DADOS ===\n")

    # 1. Resumo das Tabelas
    print("--- Contagem de Registros por Tabela ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    table_stats = []
    for table in tables:
        try:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            table_stats.append({"Tabela": table, "Registros": count})
        except Exception as e:
            table_stats.append({"Tabela": table, "Registros": f"Erro: {e}"})
    
    df_stats = pd.DataFrame(table_stats)
    print(df_stats.to_string(index=False))
    print("\n")

    # 2. Análise de Pacientes
    print("--- Pacientes ---")
    try:
        df_pacientes = pd.read_sql_query("SELECT * FROM paciente_fichas", conn)
        if not df_pacientes.empty:
            print(f"Total de Pacientes com Ficha: {len(df_pacientes)}")
            print("\nDistribuição por Perfil:")
            print(df_pacientes['perfil'].value_counts().to_string())
            print("\nPacientes (Amostra):")
            print(df_pacientes[['paciente_id', 'nome', 'cama_id', 'perfil']].head().to_string(index=False))
        else:
            print("Nenhum paciente com ficha encontrado.")
    except Exception as e:
        print(f"Erro ao analisar pacientes: {e}")
    print("\n")

    # 3. Análise de Alertas
    print("--- Alertas ---")
    try:
        df_alertas = pd.read_sql_query("SELECT * FROM alertas", conn)
        if not df_alertas.empty:
            print(f"Total de Alertas: {len(df_alertas)}")
            print("\nStatus dos Alertas:")
            print(df_alertas['status'].value_counts().to_string())
            print("\nTipos de Alertas:")
            print(df_alertas['tipo'].value_counts().to_string())
        else:
            print("Nenhum alerta encontrado.")
    except Exception as e:
        print(f"Erro ao analisar alertas: {e}")
    print("\n")

    # 4. Análise de Devices e Assignments
    print("--- Dispositivos (Devices) ---")
    try:
        df_devices = pd.read_sql_query("SELECT * FROM devices", conn)
        print(f"Total de Devices Cadastrados: {len(df_devices)}")
        
        df_assignments = pd.read_sql_query("SELECT * FROM device_assignments WHERE end_ms IS NULL", conn)
        print(f"Devices Atualmente Associados: {len(df_assignments)}")
        if not df_assignments.empty:
            print(df_assignments[['device_id', 'cama_id', 'paciente_id']].to_string(index=False))
    except Exception as e:
        print(f"Erro ao analisar devices: {e}")
    print("\n")

    # 5. Timeline Events (Últimos)
    print("--- Últimos Eventos na Timeline ---")
    try:
        df_timeline = pd.read_sql_query("SELECT ts, tipo, paciente_id, descricao FROM timeline_events ORDER BY ts_ms DESC LIMIT 5", conn)
        if not df_timeline.empty:
            print(df_timeline.to_string(index=False))
        else:
            print("Timeline vazia.")
    except Exception as e:
        print(f"Erro ao analisar timeline: {e}")
    
    conn.close()

if __name__ == "__main__":
    analyze_database()
