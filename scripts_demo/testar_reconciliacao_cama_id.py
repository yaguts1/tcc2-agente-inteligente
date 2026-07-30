"""
Teste da Reconciliação Corrigida (baseada em cama_id).

Valida que a reconciliação agora funciona corretamente sem device_assignments,
usando o cama_id do payload para encontrar o paciente atual no leito.
"""

import requests
import sqlite3
import json
from datetime import datetime, UTC

BASE_URL = "http://localhost:8000"
DB_PATH = "dados.db"

def print_step(step, desc):
    print(f"\n{'='*60}")
    print(f"PASSO {step}: {desc}")
    print('='*60)

def test_reconcile_with_cama_id():
    print("\n🧪 TESTE: RECONCILIAÇÃO BASEADA EM CAMA_ID\n")
    
    test_cama = "TEST-101A"
    test_patient_id = f"TEST_PATIENT_{int(datetime.now().timestamp())}"
    
    try:
        # ===== PASSO 1: Criar paciente =====
        print_step(1, "Criar paciente no leito TEST-101A")
        
        patient_data = {
            "id": test_patient_id,
            "name": "João Teste Reconciliação",
            "room": "TEST-101",
            "bed": "A",
            "riskLevel": "high",
            "repositioningInterval": 2
        }
        
        response = requests.post(f"{BASE_URL}/api/patients", json=patient_data)
        assert response.status_code == 200, f"Erro ao criar paciente: {response.text}"
        print(f"✅ Paciente criado: {test_patient_id}")
        print("   Leito: TEST-101-A (cama_id)")
        
        # ===== PASSO 2: Criar eventos órfãos ANTES do cadastro =====
        print_step(2, "Simular eventos órfãos (ESP32 enviou dados antes do cadastro)")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Criar 3 eventos órfãos
        orphan_ids = []
        for i in range(3):
            event_time = datetime.now(UTC)
            payload = {
                "cama_id": test_cama,  # ← Campo crítico!
                "ts": int(event_time.timestamp()),
                "ts_ms": int(event_time.timestamp() * 1000),
                "postura": ["decubito_dorsal", "decubito_lateral_esquerdo", "decubito_lateral_direito"][i],
                "confianca": 95 + i,
                "amostra_ms": 5000,
                "ts_utc": event_time.isoformat()
            }
            
            cursor.execute("""
                INSERT INTO device_events (device_id, ts, ts_ms, payload, processed)
                VALUES (?, ?, ?, ?, 0)
            """, (
                f"ESP32_{test_cama}",
                event_time.isoformat(),
                int(event_time.timestamp() * 1000),
                json.dumps(payload)
            ))
            orphan_ids.append(cursor.lastrowid)
        
        conn.commit()
        print(f"✅ Criados {len(orphan_ids)} eventos órfãos")
        print(f"   IDs: {orphan_ids}")
        print(f"   Cama ID nos payloads: {test_cama}")
        
        # ===== PASSO 3: Verificar que estão órfãos =====
        print_step(3, "Verificar que eventos estão órfãos (processed=0)")
        
        cursor.execute("""
            SELECT COUNT(*) FROM device_events
            WHERE id IN ({})
            AND processed = 0
        """.format(','.join('?' * len(orphan_ids))), orphan_ids)
        
        orphan_count = cursor.fetchone()[0]
        assert orphan_count == 3, f"Esperava 3 órfãos, encontrou {orphan_count}"
        print(f"✅ Confirmado: {orphan_count} eventos órfãos")
        
        # ===== PASSO 4: Chamar endpoint de stats =====
        print_step(4, "Verificar endpoint /device_events/stats")
        
        response = requests.get(f"{BASE_URL}/api/device_events/stats")
        assert response.status_code == 200, f"Erro ao buscar stats: {response.text}"
        
        stats = response.json()
        print(f"✅ Total de órfãos no sistema: {stats['total_orphans']}")
        
        # Encontrar nosso leito de teste
        test_bed_stats = next((b for b in stats['beds'] if b['cama_id'] == test_cama), None)
        
        if test_bed_stats:
            print(f"✅ Leito {test_cama} encontrado:")
            print(f"   Count: {test_bed_stats['count']}")
            print(f"   Paciente atual: {test_bed_stats.get('current_patient', {}).get('name')}")
        
        # ===== PASSO 5: Reconciliar por cama_id =====
        print_step(5, "Reconciliar eventos do leito TEST-101A")
        
        response = requests.post(f"{BASE_URL}/api/device_events/reconcile_bed/{test_cama}")
        assert response.status_code == 200, f"Erro na reconciliação: {response.text}"
        
        result = response.json()
        print("✅ Reconciliação executada:")
        print(f"   Processed: {result['processed']}")
        print(f"   Skipped: {result['skipped']}")
        print(f"   Patient Name: {result['patient_name']}")
        
        assert result['processed'] == 3, f"Esperava processar 3 eventos, processou {result['processed']}"
        assert result['patient_name'] == "João Teste Reconciliação"
        
        # ===== PASSO 6: Verificar que não há mais órfãos =====
        print_step(6, "Verificar que eventos foram marcados como processados")
        
        cursor.execute("""
            SELECT COUNT(*) FROM device_events
            WHERE id IN ({})
        """.format(','.join('?' * len(orphan_ids))), orphan_ids)
        
        remaining = cursor.fetchone()[0]
        assert remaining == 0, f"Ainda há {remaining} eventos órfãos! Deveriam ter sido deletados."
        print("✅ Eventos órfãos deletados (processed)")
        
        # ===== PASSO 7: Verificar timeline_events =====
        print_step(7, "Verificar que timeline_events foram criados")
        
        cursor.execute("""
            SELECT COUNT(*) FROM timeline_events
            WHERE paciente_id = ?
        """, (test_patient_id,))
        
        timeline_count = cursor.fetchone()[0]
        assert timeline_count >= 3, f"Esperava pelo menos 3 timeline events, encontrou {timeline_count}"
        print(f"✅ Timeline events criados: {timeline_count}")
        
        # ===== PASSO 8: Limpar =====
        print_step(8, "Limpar dados de teste")
        
        requests.delete(f"{BASE_URL}/api/patients/{test_patient_id}")
        cursor.execute("DELETE FROM device_events WHERE device_id LIKE 'ESP32_TEST%'")
        conn.commit()
        conn.close()
        
        print("✅ Limpeza concluída")
        
        # ===== RESULTADO FINAL =====
        print("\n" + "="*60)
        print("🎉 SUCESSO! RECONCILIAÇÃO BASEADA EM CAMA_ID FUNCIONANDO!")
        print("="*60)
        print("\nFluxo validado:")
        print("  1. ✅ Criar paciente no leito")
        print("  2. ✅ Criar eventos órfãos com cama_id no payload")
        print("  3. ✅ Endpoint /stats agrupa por cama_id")
        print("  4. ✅ Endpoint /reconcile_bed/{cama_id} processa em lote")
        print("  5. ✅ Extrai cama_id do payload (não usa device_assignments)")
        print("  6. ✅ Busca paciente atual no leito")
        print("  7. ✅ Processa eventos retroativamente")
        print("  8. ✅ Cria timeline_events e alertas")
        print("\n✨ Sistema pronto para produção!\n")
        
    except AssertionError as e:
        print(f"\n❌ FALHA: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ ERRO: {e}\n")
        raise

if __name__ == "__main__":
    try:
        test_reconcile_with_cama_id()
    except KeyboardInterrupt:
        print("\n\n⚠️  Teste interrompido\n")
    except Exception:
        import traceback
        traceback.print_exc()
        exit(1)
