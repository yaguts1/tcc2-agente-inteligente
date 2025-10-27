#!/usr/bin/env python3
"""
Script de validação da integração do Sistema de Agenda

Testa:
1. Backend endpoints estão respondendo
2. CRUD operations funcionando
3. Alert engine suprime corretamente
4. Database persiste dados
"""

import requests
import json
from datetime import datetime, timedelta
import sys

BASE_URL = "http://localhost:8000"
PACIENTE_ID = "PAC-001"

def test_connection():
    """Testa se o backend está respondendo"""
    print("\n🔌 TEST 1: Testando conexão com backend...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✅ Backend conectado!")
            return True
    except Exception as e:
        print(f"❌ Não foi possível conectar: {e}")
        print(f"   Certifique-se de que o backend está rodando:")
        print(f"   uvicorn interface.web:app --reload")
        return False

def test_list_agendas():
    """Testa listagem de agendas"""
    print("\n📋 TEST 2: Listando agendas...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda",
            timeout=5
        )
        if response.status_code == 200:
            agendas = response.json()
            print(f"✅ Agendas encontradas: {len(agendas.get('agendas', []))}")
            return True
        else:
            print(f"❌ Erro: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def test_create_agenda():
    """Testa criação de agenda"""
    print("\n✨ TEST 3: Criando nova agenda...")
    
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    data = {
        "tipo": "refeicao",
        "descricao": "Teste de integração",
        "modo": "suprimir",
        "data_inicio": tomorrow,
        "data_fim": None,
        "hora_inicio": "08:00",
        "hora_fim": "09:00",
        "dias_semana": ["MON", "WED", "FRI"],
        "ativo": True
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda",
            json=data,
            timeout=5
        )
        
        if response.status_code == 201:
            agenda = response.json()
            agenda_id = agenda.get('id')
            print(f"✅ Agenda criada com ID: {agenda_id}")
            print(f"   - Tipo: {agenda.get('tipo')}")
            print(f"   - Modo: {agenda.get('modo')}")
            print(f"   - Horário: {agenda.get('hora_inicio')} - {agenda.get('hora_fim')}")
            return True, agenda_id
        else:
            print(f"❌ Erro: {response.status_code}")
            print(f"   Resposta: {response.text}")
            return False, None
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False, None

def test_get_agenda(agenda_id):
    """Testa obtenção de agenda específica"""
    print(f"\n🔍 TEST 4: Obtendo agenda {agenda_id}...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda/{agenda_id}",
            timeout=5
        )
        
        if response.status_code == 200:
            agenda = response.json()
            print(f"✅ Agenda obtida:")
            print(f"   - Tipo: {agenda.get('tipo')}")
            print(f"   - Modo: {agenda.get('modo')}")
            print(f"   - Ativo: {agenda.get('ativo')}")
            return True
        else:
            print(f"❌ Erro: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def test_update_agenda(agenda_id):
    """Testa atualização de agenda"""
    print(f"\n✏️  TEST 5: Atualizando agenda {agenda_id}...")
    
    data = {
        "descricao": "Atualizado em teste",
        "modo": "reduzir",
        "reducao_janela_min": 15
    }
    
    try:
        response = requests.patch(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda/{agenda_id}",
            json=data,
            timeout=5
        )
        
        if response.status_code == 200:
            agenda = response.json()
            print(f"✅ Agenda atualizada:")
            print(f"   - Novo modo: {agenda.get('modo')}")
            print(f"   - Redução: {agenda.get('reducao_janela_min')} min")
            return True
        else:
            print(f"❌ Erro: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def test_check_suppression():
    """Testa verificação de supressão"""
    print(f"\n🛡️  TEST 6: Verificando supressão...")
    
    now = datetime.now().isoformat()
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda/check",
            params={"timestamp": now},
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            is_suppressed = result.get('is_suppressed')
            modo = result.get('modo')
            print(f"✅ Verificação concluída:")
            print(f"   - Suprimido agora: {is_suppressed}")
            print(f"   - Modo ativo: {modo or 'nenhum'}")
            return True
        else:
            print(f"❌ Erro: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def test_delete_agenda(agenda_id):
    """Testa deleção de agenda"""
    print(f"\n🗑️  TEST 7: Deletando agenda {agenda_id}...")
    
    try:
        response = requests.delete(
            f"{BASE_URL}/api/pacientes/{PACIENTE_ID}/agenda/{agenda_id}",
            timeout=5
        )
        
        if response.status_code == 204:
            print(f"✅ Agenda deletada com sucesso")
            return True
        else:
            print(f"❌ Erro: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

def main():
    """Executa todos os testes"""
    print("=" * 60)
    print("🧪 VALIDAÇÃO DA INTEGRAÇÃO - SISTEMA DE AGENDA")
    print("=" * 60)
    print(f"\n📍 Base URL: {BASE_URL}")
    print(f"👤 Paciente ID: {PACIENTE_ID}")
    
    results = []
    
    # Test 1: Connection
    if not test_connection():
        print("\n❌ Falha na conexão - abortando testes")
        return
    
    # Test 2: List
    results.append(("Listagem", test_list_agendas()))
    
    # Test 3: Create
    create_ok, agenda_id = test_create_agenda()
    results.append(("Criação", create_ok))
    
    if not create_ok or not agenda_id:
        print("\n❌ Falha na criação - abortando testes")
    else:
        # Test 4: Get
        results.append(("Obtenção", test_get_agenda(agenda_id)))
        
        # Test 5: Update
        results.append(("Atualização", test_update_agenda(agenda_id)))
        
        # Test 6: Check Suppression
        results.append(("Verificação", test_check_suppression()))
        
        # Test 7: Delete
        results.append(("Deleção", test_delete_agenda(agenda_id)))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for test_name, ok in results:
        status = "✅" if ok else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Resultado: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 INTEGRAÇÃO VALIDADA COM SUCESSO!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam")
        sys.exit(1)

if __name__ == "__main__":
    main()
