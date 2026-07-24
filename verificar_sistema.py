#!/usr/bin/env python3
"""
Script para verificar se o sistema está funcionando corretamente.
"""

import sys
import sqlite3
from pathlib import Path

def check_database():
    """Verifica o banco de dados"""
    print("\n📊 Verificando banco de dados...")
    
    db_path = Path("dados.db")
    if not db_path.exists():
        print("❌ Banco de dados não encontrado")
        return False
    
    print(f"✅ Banco de dados encontrado: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verificar tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📋 Tabelas ({len(tables)}): {', '.join(sorted(tables))}")
        
        # Verificar dados
        for table in ['pacientes', 'alertas', 'timeline_events']:
            if table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   - {table}: {count} registros")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Erro ao verificar banco: {e}")
        return False

def check_imports():
    """Verifica se os módulos essenciais podem ser importados"""
    print("\n📦 Verificando imports...")
    
    modules = [
        'fastapi',
        'uvicorn',
        'pandas',
        'numpy',
        'structlog',
        'httpx',
    ]
    
    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            all_ok = False
    
    return all_ok

def check_custom_modules():
    """Verifica módulos customizados"""
    print("\n🔧 Verificando módulos do sistema...")
    
    modules = [
        'configuracao',
        'interface.dao',
        'interface.api',
        'interface.web',
        'modulo_alerta.engine',
        'dados_simulados.gerador',
    ]
    
    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except Exception as e:
            print(f"❌ {module}: {e}")
            all_ok = False
    
    return all_ok

def check_frontend():
    """Verifica se o frontend existe"""
    print("\n🎨 Verificando frontend...")
    
    frontend_path = Path("frontend")
    if not frontend_path.exists():
        print("❌ Pasta frontend não encontrada")
        return False
    
    print(f"✅ Pasta frontend encontrada")
    
    # Verificar arquivos importantes
    important_files = [
        'package.json',
        'index.html',
        'vite.config.ts',
    ]
    
    all_ok = True
    for file in important_files:
        file_path = frontend_path / file
        if file_path.exists():
            print(f"✅ {file}")
        else:
            print(f"❌ {file} não encontrado")
            all_ok = False
    
    # Verificar node_modules
    node_modules = frontend_path / "node_modules"
    if node_modules.exists():
        print(f"✅ node_modules instalado")
    else:
        print(f"⚠️  node_modules não encontrado (execute: cd frontend && npm install)")
    
    return all_ok

def main():
    print("=" * 70)
    print("🔍 VERIFICAÇÃO DO SISTEMA")
    print("=" * 70)
    
    results = {
        'database': check_database(),
        'imports': check_imports(),
        'custom_modules': check_custom_modules(),
        'frontend': check_frontend(),
    }
    
    print("\n" + "=" * 70)
    print("📊 RESUMO")
    print("=" * 70)
    
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"{status} {name.upper()}")
    
    all_ok = all(results.values())
    
    if all_ok:
        print("\n🎉 Sistema OK! Todas as verificações passaram.")
        print("\n💡 Próximos passos:")
        print("   1. Backend: uvicorn interface.web:app --reload")
        print("   2. Frontend: cd frontend && npm run dev")
        return 0
    else:
        print("\n⚠️  Alguns problemas foram encontrados. Verifique os erros acima.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
