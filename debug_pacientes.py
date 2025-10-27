#!/usr/bin/env python3
"""
Script para debugar por que os pacientes aparecem como skeleton vazio
"""

import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_list_with_detail():
    """Testar listagem com detalhes"""
    print("=" * 60)
    print("DEBUG: Listando pacientes com detalhes")
    print("=" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/pacientes")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            patients = resp.json()
            print(f"\n✅ Total de pacientes: {len(patients)}\n")
            
            for i, patient in enumerate(patients):
                print(f"Paciente #{i+1}:")
                print(json.dumps(patient, indent=2, ensure_ascii=False, default=str))
                print()
        else:
            print(f"❌ Erro: {resp.status_code}")
            print(resp.text)
    
    except Exception as e:
        print(f"❌ Erro: {e}")

def test_single_patient():
    """Testar obtenção de um paciente específico"""
    print("=" * 60)
    print("DEBUG: Obter paciente específico (PAC-7778)")
    print("=" * 60)
    
    try:
        resp = requests.get(f"{BASE_URL}/pacientes/PAC-7778")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            patient = resp.json()
            print(f"\n✅ Paciente encontrado:\n")
            print(json.dumps(patient, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"❌ Erro: {resp.status_code}")
            print(resp.text)
    
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  DEBUG DE PACIENTES".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    test_list_with_detail()
    test_single_patient()
    
    print("\n" + "=" * 60)
    print("DEBUG CONCLUÍDO")
    print("=" * 60 + "\n")
