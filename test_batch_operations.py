#!/usr/bin/env python3
"""
Script para testar a função batch_acknowledge e batch_complete
e descobrir onde está o problema
"""

import sqlite3
from datetime import datetime
import sys
sys.path.insert(0, '.')

from interface.dao import alterar_status_alerta, listar_alertas_abertos

DB_PATH = 'tcc.db'

print("\n" + "="*80)
print("🧪 TESTANDO BATCH OPERATIONS")
print("="*80 + "\n")

# Primeiro, vê quantos alertas "abertos" existem
print("1️⃣ Verificando alertas disponíveis...\n")
try:
    abertos = listar_alertas_abertos(DB_PATH)
    print(f"✅ Encontrados {len(abertos)} alertas abertos:\n")
    for i, alerta in enumerate(abertos[:3]):  # Mostra apenas 3 primeiros
        paciente_id = alerta.get('paciente_id', 'UNKNOWN')
        inicio = alerta.get('inicio', 'UNKNOWN')
        status = alerta.get('status', 'UNKNOWN')
        print(f"   {i+1}. {paciente_id} | {inicio} | {status}")
        
        if i == 2:
            break
except Exception as e:
    print(f"❌ ERRO ao listar alertas: {e}")
    import traceback
    traceback.print_exc()

# Agora testa alterar_status_alerta com um alerta
print("\n2️⃣ Testando alterar_status_alerta (reconhecer 1 alerta)...\n")

if abertos and len(abertos) > 0:
    alerta_teste = abertos[0]
    paciente_id = alerta_teste.get('paciente_id')
    inicio = alerta_teste.get('inicio')
    
    print(f"   Tentando reconhecer:")
    print(f"   - paciente_id: {paciente_id}")
    print(f"   - inicio: {inicio}\n")
    
    try:
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
        print(f"✅ Alerta reconhecido com sucesso!")
    except Exception as e:
        print(f"❌ ERRO ao reconhecer: {e}")
        import traceback
        traceback.print_exc()

# Testa batch com múltiplos alertas
print("\n3️⃣ Testando batch de reconhecimento (3 alertas)...\n")

try:
    abertos_refresh = listar_alertas_abertos(DB_PATH)
    alert_ids = [f"{a.get('paciente_id')}__{a.get('inicio')}" for a in abertos_refresh[:3]]
    
    print(f"   Reconhecendo IDs:")
    for aid in alert_ids:
        print(f"   - {aid}")
    print()
    
    processed = 0
    failed = 0
    errors = []
    
    for alert_id in alert_ids:
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
            processed += 1
            print(f"   ✅ {alert_id}")
        except Exception as exc:
            failed += 1
            errors.append({"alert_id": alert_id, "error": str(exc)})
            print(f"   ❌ {alert_id}: {exc}")
    
    print(f"\n✅ Resultado: {processed} sucesso, {failed} falhas")
    if errors:
        print(f"\n   Erros: {errors}")
        
except Exception as e:
    print(f"❌ ERRO na batch: {e}")
    import traceback
    traceback.print_exc()

# Testa batch de conclusão
print("\n4️⃣ Testando batch de conclusão (com definir_fim=True)...\n")

try:
    abertos_refresh = listar_alertas_abertos(DB_PATH)
    alert_ids = [f"{a.get('paciente_id')}__{a.get('inicio')}" for a in abertos_refresh[:2]]
    
    print(f"   Fechando IDs:")
    for aid in alert_ids:
        print(f"   - {aid}")
    print()
    
    processed = 0
    failed = 0
    errors = []
    
    for alert_id in alert_ids:
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            alterar_status_alerta(DB_PATH, paciente_id, inicio, "fechado", definir_fim=True)
            processed += 1
            print(f"   ✅ {alert_id}")
        except Exception as exc:
            failed += 1
            errors.append({"alert_id": alert_id, "error": str(exc)})
            print(f"   ❌ {alert_id}: {exc}")
    
    print(f"\n✅ Resultado: {processed} sucesso, {failed} falhas")
    if errors:
        print(f"\n   Erros detalhados: {errors}")
        
except Exception as e:
    print(f"❌ ERRO na batch: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("✅ TESTE CONCLUÍDO")
print("="*80 + "\n")
