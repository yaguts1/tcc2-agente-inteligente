#!/usr/bin/env python3
"""
AUDITORIA MANUAL E INTELIGENTE: Verificar consumo real do banco
Verificando as queries que realmente importam
"""

import sqlite3
from pathlib import Path

DB_PATH = 'tcc.db'

print("\n" + "="*80)
print("🔍 AUDITORIA COMPLETA - Verificando todas as queries vs schema")
print("="*80 + "\n")

# Schema correto
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

schema = {}
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

for (table_name,) in tables:
    columns = c.execute(f"PRAGMA table_info({table_name})").fetchall()
    schema[table_name] = [col[1] for col in columns]

conn.close()

print("📊 SCHEMA DO BANCO:\n")
for table_name in sorted(schema.keys()):
    if table_name == 'sqlite_sequence':
        continue
    cols = schema[table_name]
    print(f"  {table_name:30} cols: {', '.join(cols)}")

print("\n" + "="*80)
print("🔎 VERIFICANDO QUERIES CRÍTICAS\n")

# Lista de queries críticas que encontramos (do DAO e scripts)
critical_queries = {
    "alertas - SELECT principais": {
        "file": "interface/dao.py",
        "table": "alertas",
        "fields": ["paciente_id", "inicio", "fim", "tipo", "perfil", "janela_min", "status", "duracao_min"],
        "sample": "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min FROM alertas"
    },
    "alertas - INSERT": {
        "file": "interface/dao.py + create_alerts.py",
        "table": "alertas",
        "fields": ["paciente_id", "inicio", "fim", "tipo", "perfil", "janela_min", "status", "duracao_min"],
        "sample": "INSERT INTO alertas (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min) VALUES (...)"
    },
    "alertas - UPDATE status": {
        "file": "interface/dao.py",
        "table": "alertas",
        "fields": ["status", "paciente_id", "inicio"],
        "sample": "UPDATE alertas SET status = ? WHERE paciente_id = ? AND inicio = ?"
    },
    "paciente_fichas - SELECT": {
        "file": "interface/dao.py",
        "table": "paciente_fichas",
        "fields": ["paciente_id", "nome", "perfil", "cama_id", "observacoes", "created_at", "updated_at"],
        "sample": "SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at FROM paciente_fichas"
    },
    "paciente_rotinas - SELECT": {
        "file": "interface/dao.py",
        "table": "paciente_rotinas",
        "fields": ["id", "label", "inicio", "duracao_min", "descricao", "ativo", "sort_order"],
        "sample": "SELECT id, label, inicio, duracao_min, descricao, ativo, sort_order FROM paciente_rotinas"
    },
    "timeline_events - SELECT": {
        "file": "interface/dao.py",
        "table": "timeline_events",
        "fields": ["id", "paciente_id", "ts", "ts_ms", "tipo", "descricao", "meta", "created_at"],
        "sample": "SELECT id, paciente_id, ts, ts_ms, tipo, descricao, meta, created_at FROM timeline_events"
    },
    "timeline_events - INSERT": {
        "file": "interface/dao.py",
        "table": "timeline_events",
        "fields": ["paciente_id", "ts", "ts_ms", "tipo", "descricao", "meta"],
        "sample": "INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta) VALUES (...)"
    },
    "device_assignments - SELECT": {
        "file": "interface/dao.py",
        "table": "device_assignments",
        "fields": ["id", "device_id", "cama_id", "paciente_id", "start_ts", "start_ms", "end_ts", "end_ms", "created_at"],
        "sample": "SELECT id, device_id, cama_id, paciente_id, start_ts, start_ms, end_ts, end_ms, created_at FROM device_assignments"
    },
    "device_events - INSERT": {
        "file": "interface/dao.py",
        "table": "device_events",
        "fields": ["device_id", "ts", "ts_ms", "payload"],
        "sample": "INSERT INTO device_events (device_id, ts, ts_ms, payload) VALUES (...)"
    },
    "usuarios - SELECT": {
        "file": "interface/dao.py",
        "table": "users",
        "fields": ["username", "password_hash", "display_name", "created_at", "role"],
        "sample": "SELECT username, password_hash, display_name, created_at, role FROM users"
    },
}

issues = []
ok_count = 0

for query_name, info in critical_queries.items():
    table = info["table"]
    fields_used = info["fields"]
    
    if table not in schema:
        issues.append(f"❌ {query_name}: TABELA '{table}' NÃO EXISTE")
        continue
    
    schema_fields = schema[table]
    missing_fields = []
    
    for field in fields_used:
        if field not in schema_fields:
            missing_fields.append(field)
    
    if missing_fields:
        issues.append(f"❌ {query_name}: CAMPOS FALTAM NO SCHEMA")
        issues.append(f"   Esperado: {fields_used}")
        issues.append(f"   Schema tem: {schema_fields}")
        issues.append(f"   FALTAM: {missing_fields}\n")
    else:
        print(f"✅ {query_name}")
        print(f"   Tabela: {table}")
        print(f"   Campos: {', '.join(fields_used)}\n")
        ok_count += 1

if issues:
    print("\n" + "="*80)
    print("⚠️  PROBLEMAS ENCONTRADOS:\n")
    for issue in issues:
        print(issue)
else:
    print(f"\n✅ TUDO OK! {ok_count}/{len(critical_queries)} queries têm esquema correto")

print("\n" + "="*80)
print("🔍 ANÁLISE DE DADOS REAIS\n")

# Verifica dados reais no banco
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print("📈 Resumo de dados:\n")

tables_to_check = ['alertas', 'pacientes', 'paciente_fichas', 'timeline_events', 'users', 'paciente_rotinas']

for table in tables_to_check:
    try:
        count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:30} {count:5} registros")
    except:
        print(f"  {table:30} ERRO ao contar")

print("\n" + "="*80)
print("🎯 AMOSTRA DE DADOS:\n")

# Amostra alertas
print("Alertas (primeiros 3):")
alertas = c.execute("SELECT paciente_id, inicio, tipo, status FROM alertas LIMIT 3").fetchall()
for row in alertas:
    print(f"  {row}")

# Amostra pacientes
print("\nPacientes:")
pacientes = c.execute("SELECT id FROM pacientes LIMIT 3").fetchall()
for row in pacientes:
    print(f"  {row}")

# Amostra timeline
print("\nTimeline events (primeiros 3):")
timeline = c.execute("SELECT paciente_id, tipo, descricao FROM timeline_events LIMIT 3").fetchall()
for row in timeline:
    print(f"  {row}")

# Verificar se há dados inconsistentes
print("\n" + "="*80)
print("🔎 VERIFICANDO INTEGRIDADE\n")

# Alertas com paciente_id que não existe
orfaos = c.execute("""
    SELECT COUNT(*) FROM alertas a 
    WHERE NOT EXISTS (SELECT 1 FROM pacientes p WHERE p.id = a.paciente_id)
""").fetchone()[0]

if orfaos > 0:
    print(f"⚠️  {orfaos} alertas com paciente_id órfão (não existe em pacientes)")
else:
    print(f"✅ Todos os alertas têm paciente_id válido")

# Timeline events com paciente_id que não existe
orfaos2 = c.execute("""
    SELECT COUNT(*) FROM timeline_events t 
    WHERE NOT EXISTS (SELECT 1 FROM pacientes p WHERE p.id = t.paciente_id)
""").fetchone()[0]

if orfaos2 > 0:
    print(f"⚠️  {orfaos2} timeline events com paciente_id órfão")
else:
    print(f"✅ Todos os timeline events têm paciente_id válido")

conn.close()

print("\n" + "="*80)
print("✅ AUDITORIA CONCLUÍDA")
print("="*80 + "\n")
