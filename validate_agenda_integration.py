"""
Script de validação simples da integração do Sistema de Agenda
Testa importação e estrutura dos componentes
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Testa se todos os módulos podem ser importados"""
    print("\n🔍 TEST 1: Validando imports do backend...")
    
    try:
        from interface.dao_agenda import (
            criar_agenda,
            listar_agendas,
            obter_agenda,
            atualizar_agenda,
            deletar_agenda,
            is_timestamp_in_suppressed_period
        )
        print("✅ DAO Agenda importado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao importar DAO: {e}")
        return False
    
    try:
        from interface.endpoints_agenda import router
        print("✅ Endpoints Agenda importado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao importar Endpoints: {e}")
        return False
    
    try:
        from modulo_alerta.engine import processar_alertas_lote
        print("✅ Alert Engine importado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao importar Alert Engine: {e}")
        return False
    
    return True

def test_database_structure():
    """Testa estrutura da database"""
    print("\n📊 TEST 2: Validando estrutura do banco de dados...")
    
    try:
        from interface.dao_agenda import ensure_agendas_table
        import sqlite3
        import os
        
        db_path = "hospital.db"
        
        if os.path.exists(db_path):
            ensure_agendas_table(db_path)
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agendas_paciente'")
            result = cursor.fetchone()
            
            if result:
                print("✅ Tabela 'agendas_paciente' existe")
                
                # Check columns
                cursor.execute("PRAGMA table_info(agendas_paciente)")
                columns = cursor.fetchall()
                print(f"✅ Tabela tem {len(columns)} colunas:")
                for col in columns:
                    print(f"   - {col[1]}: {col[2]}")
                
                conn.close()
                return True
            else:
                print("❌ Tabela 'agendas_paciente' não encontrada")
                conn.close()
                return False
        else:
            print("⚠️  Database não encontrado (será criado no primeiro uso)")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao validar database: {e}")
        return False

def test_frontend_files():
    """Testa se arquivos frontend existem"""
    print("\n🎨 TEST 3: Validando arquivos frontend...")
    
    frontend_files = [
        "frontend/src/api/agendaApi.ts",
        "frontend/src/hooks/useAgenda.ts",
        "frontend/src/components/patients/AgendaForm.tsx",
        "frontend/src/components/patients/AgendaList.tsx",
        "frontend/src/components/patients/AgendaPanel.tsx",
        "frontend/src/components/patients/AgendaForm.css",
        "frontend/src/components/patients/AgendaList.css",
        "frontend/src/components/patients/AgendaPanel.css",
    ]
    
    all_exist = True
    for file_path in frontend_files:
        full_path = os.path.join(os.path.dirname(__file__), file_path)
        if os.path.exists(full_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} não encontrado")
            all_exist = False
    
    return all_exist

def test_pages_integration():
    """Testa se PatientsPage foi modificado"""
    print("\n📝 TEST 4: Validando integração em PatientsPage...")
    
    patients_page_path = "frontend/src/components/pages/PatientsPage.tsx"
    full_path = os.path.join(os.path.dirname(__file__), patients_page_path)
    
    if not os.path.exists(full_path):
        print(f"❌ Arquivo não encontrado: {patients_page_path}")
        return False
    
    with open(full_path, 'r') as f:
        content = f.read()
    
    checks = [
        ("import AgendaPanel", "AgendaPanel importado"),
        ("Calendar", "ícone Calendar importado"),
        ("selectedPatientForAgenda", "estado adicionado"),
        ("onClick={() => setSelectedPatientForAgenda", "botão Agendas adicionado"),
        ('📅 Agendas', "label de agendas adicionado"),
    ]
    
    all_ok = True
    for pattern, description in checks:
        if pattern in content:
            print(f"✅ {description}")
        else:
            print(f"❌ {description} - padrão não encontrado: '{pattern}'")
            all_ok = False
    
    return all_ok

def main():
    """Executa todos os testes"""
    print("=" * 70)
    print("🧪 VALIDAÇÃO DA INTEGRAÇÃO - SISTEMA DE AGENDA (Estrutura)")
    print("=" * 70)
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports Backend", test_imports()))
    
    # Test 2: Database
    results.append(("Estrutura Database", test_database_structure()))
    
    # Test 3: Frontend Files
    results.append(("Arquivos Frontend", test_frontend_files()))
    
    # Test 4: Pages Integration
    results.append(("Integração PatientsPage", test_pages_integration()))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 RESUMO DA VALIDAÇÃO")
    print("=" * 70)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for test_name, ok in results:
        status = "✅" if ok else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Resultado: {passed}/{total} validações passaram")
    
    if passed == total:
        print("\n🎉 INTEGRAÇÃO VALIDADA COM SUCESSO!")
        print("\n📋 Próximos passos:")
        print("1. Verificar que backend está rodando: uvicorn interface.web:app --reload")
        print("2. Verificar que frontend está rodando: cd frontend && npm run dev")
        print("3. Acessar: http://localhost:5173/pacientes")
        print("4. Clicar em '📅 Agendas' em qualquer paciente")
        print("5. Testar CRUD de agendas")
        return True
    else:
        print(f"\n⚠️  {total - passed} validação(ões) falharam")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
