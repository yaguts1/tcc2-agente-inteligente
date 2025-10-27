#!/usr/bin/env python3
"""
Script para testar o endpoint de simulação
"""

import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_simulation():
    """Testar simulação de paciente"""
    print("=" * 60)
    print("TESTE: Simular dados para paciente")
    print("=" * 60)
    
    # Primeiro, criar um paciente
    payload_create = {
        "name": "Paciente Teste Simulacao 2",
        "room": "667",
        "bed": "Leito Teste 667",
        "riskLevel": "medium",
        "repositioningInterval": 2
    }
    
    try:
        # Criar paciente
        print("\n1. Criando paciente...")
        resp = requests.post(f"{BASE_URL}/pacientes", json=payload_create)
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code != 201:
            print(f"   ❌ Erro ao criar: {resp.text}")
            return
        
        patient = resp.json()
        patient_id = patient.get('id')
        print(f"   ✅ Paciente criado: {patient_id}")
        
        # Simular dados
        print(f"\n2. Simulando dados para {patient_id}...")
        payload_sim = {
            "duracao_horas": 2,  # Menor para testar rápido
            "seed": 42,
            "perfil": "medio"
        }
        
        resp = requests.post(
            f"{BASE_URL}/pacientes/{patient_id}/simular",
            json=payload_sim
        )
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"   ✅ Simulação concluída:")
            print(f"      - Eventos: {result.get('eventos', 0)}")
            print(f"      - Alertas: {result.get('alertas', 0)}")
            print(f"      - Duração: {result.get('duracao', 0)}h")
        else:
            print(f"   ❌ Erro na simulação:")
            print(f"      Status: {resp.status_code}")
            print(f"      Response: {resp.text}")
            
            # Tentar entender melhor o erro
            try:
                error_detail = resp.json()
                print(f"      Error Detail: {json.dumps(error_detail, indent=2)}")
            except:
                pass
    
    except Exception as e:
        print(f"   ❌ Erro: {e}")

if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  TESTE DE SIMULAÇÃO".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    test_simulation()
    
    print("\n" + "=" * 60)
    print("TESTE CONCLUÍDO")
    print("=" * 60 + "\n")
