#!/usr/bin/env python3
"""
Teste COMPLETO e ADEQUADO da página de Admin com payload no formato ESP32 correto
Testa a reconciliação end-to-end com dados realistas
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

# E402 aqui é intencional: o import só resolve depois do sys.path.insert acima,
# porque este script é executado de dentro de scripts_demo/ e precisa alcançar
# os módulos da raiz do projeto.
from interface.dao import (  # noqa: E402
    listar_device_events,
    inserir_device_event,
    registrar_device,
    criar_paciente,
    start_device_assignment,
)


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_ok(msg: str):
    print(f"[OK] {msg}")


def print_fail(msg: str):
    print(f"[FALHA] {msg}")


def print_info(msg: str):
    print(f"[INFO] {msg}")


def limpar_dados_teste():
    """Remove dados de testes anteriores"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM device_events WHERE device_id LIKE 'TEST_ESP32_%'")
    conn.execute("DELETE FROM device_assignments WHERE device_id LIKE 'TEST_ESP32_%'")
    conn.commit()
    conn.close()
    print_info("Dados de teste anteriores removidos")


def criar_payload_esp32_valido(device_id: str, timestamp: datetime) -> dict:
    """Cria um payload no formato correto do ESP32"""
    return {
        "device_id": device_id,
        "postura": "decubito_dorsal",  # Campo obrigatório
        "confianca": 0.85,  # Campo obrigatório (0.0 - 1.0)
        "amostra_ms": int(timestamp.timestamp() * 1000),  # Campo obrigatório
        "ts_utc": timestamp.isoformat(),  # Campo obrigatório
        "pressao_pico": 420.5,  # Campo opcional
    }


def teste_completo_reconciliacao():
    """Teste completo: criar evento órfão → criar assignment → reconciliar"""
    
    print_header("TESTE COMPLETO DE RECONCILIACAO COM PAYLOAD ESP32 VALIDO")
    
    # Setup
    limpar_dados_teste()
    test_device_id = "TEST_ESP32_RECONCILE_001"
    
    # PASSO 1: Registrar dispositivo
    print_info("PASSO 1: Registrando dispositivo ESP32...")
    try:
        registrar_device(DB_PATH, test_device_id, meta={"tipo": "esp32", "teste": True})
        print_ok(f"Dispositivo registrado: {test_device_id}")
    except Exception:
        print_info(f"Dispositivo já existe: {test_device_id}")
    
    # PASSO 2: Criar evento órfão (ANTES do assignment)
    print_info("\nPASSO 2: Criando evento órfão (sem assignment)...")
    event_timestamp = datetime.now(timezone.utc)
    payload = criar_payload_esp32_valido(test_device_id, event_timestamp)
    
    print_info("Payload ESP32:")
    print(json.dumps(payload, indent=2))
    
    try:
        event_id = inserir_device_event(
            DB_PATH,
            device_id=test_device_id,
            ts=event_timestamp.isoformat(),
            ts_ms=int(event_timestamp.timestamp() * 1000),
            payload=payload  # Passa dict, não JSON string
        )
        print_ok(f"Evento órfão criado com ID: {event_id}")
    except Exception as e:
        print_fail(f"Erro ao criar evento: {e}")
        return False
    
    # PASSO 3: Verificar que está pendente
    print_info("\nPASSO 3: Verificando eventos pendentes...")
    pending = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
    print_info(f"Eventos pendentes: {len(pending)}")
    
    if len(pending) == 0:
        print_fail("Evento órfão NÃO aparece como pendente!")
        return False
    
    print_ok("Evento está pendente (correto)")
    
    # PASSO 4: Tentar reconciliar SEM assignment (deve falhar)
    print_info("\nPASSO 4: Tentando reconciliar sem assignment...")
    from interface.api import _do_reconcile
    
    result = _do_reconcile(device_id=test_device_id, limit=100)
    print_info(f"Resultado: processados={result['processed']}, pulados={result['skipped']}")
    
    if result['processed'] > 0:
        print_fail("NÃO deveria ter processado sem assignment!")
        return False
    
    print_ok("Corretamente pulou evento sem assignment")
    
    # PASSO 5: Criar paciente e assignment
    print_info("\nPASSO 5: Criando paciente e device assignment...")
    
    # Criar paciente
    try:
        paciente = criar_paciente(
            DB_PATH,
            nome="Paciente Teste Reconciliacao",
            perfil="alto",
            cama_id="TESTE_RECONCILE_A1",
            observacoes="Criado para teste de reconciliação"
        )
        test_patient_id = paciente.get('paciente_id')
        cama_id = paciente.get('cama_id', 'TESTE_RECONCILE_A1')
        print_ok(f"Paciente criado: {test_patient_id} na cama {cama_id}")
    except Exception:
        # Se falhar, usar paciente existente
        print_info("Usando paciente existente...")
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT paciente_id, cama_id FROM paciente_fichas LIMIT 1")
        row = cur.fetchone()
        conn.close()
        
        if not row:
            print_fail("Nenhum paciente disponível!")
            return False
        
        test_patient_id = row['paciente_id']
        cama_id = row['cama_id']
        print_info(f"Paciente: {test_patient_id} na cama {cama_id}")
    
    # Criar assignment que cubra o evento (2 horas atrás até agora)
    assignment_start = event_timestamp - timedelta(hours=1)
    
    try:
        assignment_id = start_device_assignment(
            DB_PATH,
            device_id=test_device_id,
            cama_id=cama_id,
            paciente_id=test_patient_id,
            start_ts=assignment_start.isoformat(),
            start_ms=int(assignment_start.timestamp() * 1000)
        )
        print_ok(f"Device assignment criado: ID={assignment_id}")
        print_info(f"  {test_device_id} → {test_patient_id}")
        print_info(f"  Início: {assignment_start.isoformat()}")
    except Exception as e:
        print_fail(f"Erro ao criar assignment: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # PASSO 6: Verificar resolver
    print_info("\nPASSO 6: Verificando resolver_paciente_por_device_em...")
    from interface.dao import resolver_paciente_por_device_em
    
    event_ts_ms = int(event_timestamp.timestamp() * 1000)
    try:
        resolved_pid = resolver_paciente_por_device_em(DB_PATH, test_device_id, event_ts_ms)
        print_info(f"Evento (ts_ms={event_ts_ms})")
        print_ok(f"Resolvido para paciente: {resolved_pid}")
        
        if resolved_pid != test_patient_id:
            print_fail(f"Paciente incorreto! Esperado: {test_patient_id}, obteve: {resolved_pid}")
            return False
    except Exception as e:
        print_fail(f"Erro ao resolver: {e}")
        return False
    
    # PASSO 7: Reconciliar COM assignment (deve funcionar)
    print_info("\nPASSO 7: Reconciliando COM assignment...")
    
    result = _do_reconcile(device_id=test_device_id, limit=100)
    print_info(f"Resultado: processados={result['processed']}, pulados={result['skipped']}")
    
    if result['processed'] == 0:
        print_fail("Deveria ter processado o evento!")
        print_info("\nDiagnosticando o problema...")
        
        # Debug: tentar processar manualmente
        from interface.api import _normalizar_payload, _registrar_evento
        
        events = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
        if events:
            ev = events[0]
            payload_test = ev['payload']
            payload_test['paciente_id'] = test_patient_id
            
            try:
                print_info("Tentando normalizar payload...")
                evento = _normalizar_payload(payload_test, None)
                print_ok("Payload normalizado com sucesso!")
                
                print_info("Tentando registrar evento...")
                _registrar_evento(evento)
                print_ok("Evento registrado com sucesso!")
                
                print_fail("Reconciliação manual funcionou, mas _do_reconcile falhou!")
            except Exception as e:
                print_fail(f"Erro na reconciliação manual: {e}")
                import traceback
                traceback.print_exc()
        
        return False
    
    print_ok(f"{result['processed']} evento(s) processado(s) com sucesso!")
    
    # PASSO 8: Verificar que foi marcado como processado
    print_info("\nPASSO 8: Verificando que evento foi marcado como processado...")
    
    pending_after = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
    all_events = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=True)
    
    print_info(f"Eventos pendentes após reconciliação: {len(pending_after)}")
    print_info(f"Total de eventos (incluindo processados): {len(all_events)}")
    
    processed_events = [e for e in all_events if e['processed_at'] is not None]
    print_info(f"Eventos processados: {len(processed_events)}")
    
    if len(processed_events) == 0:
        print_fail("Nenhum evento foi marcado como processado!")
        return False
    
    print_ok("Evento foi marcado como processado!")
    
    # Mostrar detalhes do evento processado
    proc_ev = processed_events[0]
    print("\nDetalhes do evento processado:")
    print(f"  ID: {proc_ev['id']}")
    print(f"  Device: {proc_ev['device_id']}")
    print(f"  Timestamp: {proc_ev['ts']}")
    print(f"  Processado em: {proc_ev['processed_at']}")
    
    # PASSO 9: Verificar que evento foi registrado na tabela eventos
    print_info("\nPASSO 9: Verificando registro na tabela de eventos...")
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Tabela eventos não tem coluna device_id, apenas paciente_id
    cur = conn.execute(
        "SELECT COUNT(*) as cnt FROM eventos WHERE paciente_id = ?",
        (test_patient_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    event_count = row['cnt']
    print_info(f"Eventos registrados para paciente {test_patient_id}: {event_count}")
    
    if event_count == 0:
        print_fail("Evento NÃO foi registrado na tabela eventos!")
        return False
    
    print_ok(f"{event_count} evento(s) registrado(s) na tabela eventos!")
    
    return True


def main():
    print_header("TESTE ADEQUADO DA PAGINA DE ADMIN")
    print(f"Database: {DB_PATH}")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = teste_completo_reconciliacao()
    
    print_header("RESULTADO FINAL")
    
    if success:
        print_ok("SUCESSO! A pagina de Admin esta 100% funcional!")
        print_info("\nTodos os componentes validados:")
        print_info("  [OK] Criacao de eventos orfaos")
        print_info("  [OK] Listagem de eventos pendentes")
        print_info("  [OK] Reconciliacao com validacao de payload")
        print_info("  [OK] Resolucao de paciente por device")
        print_info("  [OK] Marcacao de eventos como processados")
        print_info("  [OK] Registro de eventos na tabela principal")
        return 0
    else:
        print_fail("FALHA! Verifique os logs acima.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
