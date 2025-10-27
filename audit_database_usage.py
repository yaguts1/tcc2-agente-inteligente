#!/usr/bin/env python3
"""
AUDITORIA COMPLETA: Verificar que TODOS os SELECTs/INSERTs/UPDATEs 
estão usando os campos corretos conforme o schema
"""

import sqlite3
import re
from pathlib import Path
from collections import defaultdict

DB_PATH = 'tcc.db'
REPO_ROOT = Path('.')

def get_schema_columns(db_path: str) -> dict:
    """Retorna dict {tabela: [colunas]}"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    schema = {}
    tables = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    
    for (table_name,) in tables:
        columns = c.execute(f"PRAGMA table_info({table_name})").fetchall()
        schema[table_name] = [col[1] for col in columns]
    
    conn.close()
    return schema

def extract_queries_from_file(filepath: str) -> list[dict]:
    """Extrai SELECTs/INSERTs/UPDATEs/DELETEs de um arquivo Python"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return []
    
    queries = []
    
    # Pattern para encontrar SQL strings
    # Busca por sequências entre quotes
    patterns = [
        r'(SELECT\s+.*?FROM\s+\w+.*?)(?=["\'`]|\))',
        r'(INSERT\s+(?:OR\s+\w+\s+)?INTO\s+\w+.*?)(?=["\'`]|\))',
        r'(UPDATE\s+\w+\s+SET.*?)(?=["\'`]|\))',
        r'(DELETE\s+FROM\s+\w+.*?)(?=["\'`]|\))',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            sql = match.group(1).strip()
            if len(sql) > 10:  # Filter out noise
                queries.append({
                    'file': filepath,
                    'sql': sql,
                    'line': content[:match.start()].count('\n') + 1
                })
    
    return queries

def extract_columns_from_query(query: str) -> tuple[str, list[str]]:
    """Extrai tabela e colunas de uma query"""
    query_upper = query.upper()
    
    # Tenta identificar a tabela
    table = None
    if 'FROM' in query_upper:
        match = re.search(r'FROM\s+(\w+)', query_upper)
        if match:
            table = match.group(1).lower()
    elif 'INSERT INTO' in query_upper:
        match = re.search(r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(\w+)', query_upper)
        if match:
            table = match.group(1).lower()
    elif 'UPDATE' in query_upper:
        match = re.search(r'UPDATE\s+(\w+)', query_upper)
        if match:
            table = match.group(1).lower()
    elif 'DELETE FROM' in query_upper:
        match = re.search(r'DELETE\s+FROM\s+(\w+)', query_upper)
        if match:
            table = match.group(1).lower()
    
    # Extrai colunas mencionadas
    columns = re.findall(r'\b(\w+)\s*(?:[=,\(]|FROM|WHERE)', query)
    columns = [c.lower() for c in columns if c not in ['OR', 'AND', 'WHERE', 'FROM', 'INTO']]
    
    return table, list(set(columns))

def audit_python_files(schema: dict) -> dict:
    """Auditoria de todos os arquivos Python"""
    
    issues = defaultdict(list)
    all_queries = []
    
    # Procura em interface/dao.py, interface/api.py, modulo_alerta/engine.py, etc
    python_files = REPO_ROOT.glob('**/*.py')
    
    for py_file in python_files:
        # Skip venv, __pycache__, frontend
        if any(x in str(py_file) for x in ['venv', '__pycache__', 'node_modules', '.pytest']):
            continue
        
        queries = extract_queries_from_file(str(py_file))
        all_queries.extend(queries)
        
        # Verifica cada query
        for q in queries:
            table, cols = extract_columns_from_query(q['sql'])
            
            if table and table in schema:
                schema_cols = set(schema[table])
                used_cols = set(cols)
                
                # Colunas usadas que não existem no schema
                invalid = used_cols - schema_cols
                
                if invalid:
                    issues[str(py_file)].append({
                        'line': q['line'],
                        'table': table,
                        'invalid_cols': invalid,
                        'sql_snippet': q['sql'][:100]
                    })
    
    return dict(issues), all_queries

print("\n" + "="*80)
print("🔍 AUDITORIA DE USO DO BANCO DE DADOS")
print("="*80 + "\n")

# 1. Pega schema
print("📊 Lendo schema do banco...")
schema = get_schema_columns(DB_PATH)

print(f"✅ {len(schema)} tabelas encontradas:\n")
for table_name in sorted(schema.keys()):
    cols = schema[table_name]
    print(f"   {table_name:30} ({len(cols)} cols): {', '.join(cols[:5])}{'...' if len(cols) > 5 else ''}")

# 2. Auditoria de arquivos Python
print("\n🔎 Auditando arquivos Python...\n")
issues, all_queries = audit_python_files(schema)

if not issues:
    print("✅ Nenhum problema encontrado! Todas as queries usam campos válidos.")
else:
    print(f"⚠️  PROBLEMAS ENCONTRADOS:\n")
    for filepath, file_issues in issues.items():
        print(f"  📄 {filepath}")
        for issue in file_issues:
            print(f"     Linha {issue['line']}: Tabela '{issue['table']}'")
            print(f"       Colunas inválidas: {issue['invalid_cols']}")
            print(f"       Query: {issue['sql_snippet']}...")
        print()

# 3. Análise de uso por tabela
print("\n📈 Resumo de uso por tabela:\n")

usage_by_table = defaultdict(set)

# Mapeia queries para tabelas
for py_file in REPO_ROOT.glob('**/*.py'):
    if any(x in str(py_file) for x in ['venv', '__pycache__', 'node_modules']):
        continue
    
    queries = extract_queries_from_file(str(py_file))
    for q in queries:
        table, _ = extract_columns_from_query(q['sql'])
        if table:
            usage_by_table[table].add(str(py_file).split('\\')[-1])

for table_name in sorted(schema.keys()):
    files = usage_by_table.get(table_name, set())
    if files:
        print(f"   ✓ {table_name:25} usado em: {', '.join(sorted(files)[:3])}")
    else:
        print(f"   ⚠️  {table_name:25} NÃO ENCONTRADO EM QUERIES (pode ser de read-only ou novo)")

# 4. Verifica tabelas que não têm queries
print("\n⚠️  Tabelas não usadas em queries (verificação manual recomendada):\n")
unused = [t for t in schema.keys() if t not in usage_by_table]
if unused:
    for t in unused:
        print(f"   • {t}")
else:
    print("   Todas as tabelas têm queries associadas ✓")

print("\n" + "="*80)
print("✅ AUDITORIA CONCLUÍDA")
print("="*80 + "\n")

# 5. Salva relatório detalhado
report_path = Path('AUDIT_DATABASE_USAGE.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("# Auditoria de Uso do Banco de Dados\n\n")
    f.write("## Schema\n\n")
    for table_name in sorted(schema.keys()):
        cols = schema[table_name]
        f.write(f"### {table_name}\n")
        f.write(f"Colunas ({len(cols)}): {', '.join(cols)}\n\n")
    
    if issues:
        f.write("\n## ⚠️ PROBLEMAS ENCONTRADOS\n\n")
        for filepath, file_issues in issues.items():
            f.write(f"### {filepath}\n")
            for issue in file_issues:
                f.write(f"- **Linha {issue['line']}**: Tabela `{issue['table']}`\n")
                f.write(f"  - Colunas inválidas: `{issue['invalid_cols']}`\n")
                f.write(f"  - Query: `{issue['sql_snippet']}...`\n\n")

print(f"📄 Relatório salvo em: {report_path}")
