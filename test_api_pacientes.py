#!/usr/bin/env python3
"""
Script para testar se a API de pacientes está funcionando corretamente
"""

import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_list_patients():
    """Testar listagem de pacientes"""
    print("=" * 60)
    print("TESTE 1: Listar pacientes")
    print("=" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/pacientes")
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            patients = resp.json()
            print(f"✅ Total de pacientes: {len(patients)}")
            
            if patients:
                print("\nPrimeiros 3 pacientes:")
                for patient in patients[:3]:
                    print(f"  - ID: {patient.get('paciente_id', 'N/A')}")
                    print(f"    Nome: {patient.get('nome', 'N/A')}")
                    print(f"    Cama: {patient.get('cama_id', 'N/A')}")
                    print(f"    Perfil: {patient.get('perfil', 'N/A')}")
                    print()
            else:
                print("Lista vazia - nenhum paciente cadastrado")
        else:
            print(f"❌ Erro: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")

def test_create_patient():
    """Testar criação de paciente"""
    print("\n" + "=" * 60)
    print("TESTE 2: Criar novo paciente")
    print("=" * 60)
    
    payload = {
        "name": "Paciente Teste API",
        "room": "999",
        "bed": "Leito API",
        "riskLevel": "medium",
        "repositioningInterval": 2
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/pacientes", json=payload)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 201:
            new_patient = resp.json()
            print(f"✅ Paciente criado:")
            print(f"  ID: {new_patient.get('id', 'N/A')}")
            print(f"  Nome: {new_patient.get('name', 'N/A')}")
            print(f"  Cama: {new_patient.get('room', 'N/A')} / {new_patient.get('bed', 'N/A')}")
            print(f"  Risco: {new_patient.get('riskLevel', 'N/A')}")
            return new_patient.get('id')
        else:
            print(f"❌ Erro: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
    
    return None

def test_list_after_create():
    """Testar listagem após criação"""
    print("\n" + "=" * 60)
    print("TESTE 3: Listar pacientes após criar novo")
    print("=" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/pacientes")
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            patients = resp.json()
            print(f"✅ Total de pacientes agora: {len(patients)}")
            
            # Procurar pelo paciente que criamos
            test_patient = next(
                (p for p in patients if p.get('nome') == 'Paciente Teste API'),
                None
            )
            
            if test_patient:
                print(f"✅ Paciente 'Paciente Teste API' foi encontrado na listagem!")
                print(f"  ID: {test_patient.get('paciente_id', 'N/A')}")
            else:
                print(f"⚠️  Paciente 'Paciente Teste API' NÃO foi encontrado na listagem")
        else:
            print(f"❌ Erro: {resp.status_code}")
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")

if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  TESTE DE API DE PACIENTES".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    test_list_patients()
    test_create_patient()
    test_list_after_create()
    
    print("\n" + "=" * 60)
    print("TESTES CONCLUÍDOS")
    print("=" * 60 + "\n")
