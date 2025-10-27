import sqlite3

conn = sqlite3.connect('tcc.db')
c = conn.cursor()

print("\n=== DADOS NO DATABASE ===\n")

# Check data in each table
tables = ['alertas', 'pacientes', 'eventos', 'timeline_events', 'users', 'agendas']

for table in tables:
    try:
        count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"✓ {table:20} {count:5} registros")
    except:
        print(f"✗ {table:20} (tabela não existe)")

print("\n=== SAMPLE DATA ===\n")

# Check sample alertas
alertas = c.execute("SELECT paciente_id, status, COUNT(*) as qty FROM alertas GROUP BY paciente_id, status").fetchall()
print("Alertas por paciente:")
for pac, status, qty in alertas[:5]:
    print(f"  {pac}: {status} ({qty})")

conn.close()
