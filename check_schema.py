import sqlite3
conn = sqlite3.connect('tcc.db')
c = conn.cursor()
info = c.execute("PRAGMA table_info(pacientes)").fetchall()
print("Colunas em pacientes:")
for col in info:
    print(f"  {col[1]} - {col[2]}")
