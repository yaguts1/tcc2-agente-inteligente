#!/usr/bin/env python3
"""
Script de teste para a página de Admin e funcionalidades de device_events
Testa:
1. Listagem de device_events
2. Criação de evento órfão (sem paciente associado)
3. Reconciliação de eventos
4. Verificação do processamento
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Adicionar diretórios ao path
sys.path.insert(0, str(Path(__file__).parent))

# DB_PATH definido diretamente (como em interface/api.py)
DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

from interface.dao import (
    listar_device_events,
    delete_device_event,
    inserir_device_event,
    registrar_device,
    criar_paciente,
    start_device_assignment,
    listar_pacientes,
)


def print_section(title: str):
    """Imprime uma seção formatada"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_success(msg: str):
    """Imprime mensagem de sucesso"""
    print(f"[OK] {msg}")


def print_error(msg: str):
    """Imprime mensagem de erro"""
    print(f"[X] {msg}")


def print_info(msg: str):
    """Imprime mensagem informativa"""
    print(f"[i] {msg}")


def test_list_device_events():
    """Teste 1: Listar eventos de dispositivos"""
    print_section("Teste 1: Listar Device Events")
    
    try:
        # Listar todos os eventos (incluindo processados)
        all_events = listar_device_events(DB_PATH, include_processed=True, limit=100)
        print_info(f"Total de eventos (incluindo processados): {len(all_events)}")
        
        # Listar apenas eventos pendentes
        pending_events = listar_device_events(DB_PATH, include_processed=False, limit=100)
        print_info(f"Eventos pendentes: {len(pending_events)}")
        
        # Listar eventos processados
        processed_count = len(all_events) - len(pending_events)
        print_info(f"Eventos processados: {processed_count}")
        
        if all_events:
            print("\nExemplo de evento:")
            event = all_events[0]
            print(json.dumps(event, indent=2, ensure_ascii=False))
        
        print_success("Listagem de eventos funcional")
        return True
        
    except Exception as e:
        print_error(f"Erro ao listar eventos: {e}")
        return False


def test_create_orphan_event():
    """Teste 2: Criar evento órfão (sem paciente associado)"""
    print_section("Teste 2: Criar Evento Órfão")
    
    try:
        # Criar ou obter dispositivo de teste
        test_device_id = "TEST_DEVICE_ORPHAN_001"
        
        try:
            registrar_device(DB_PATH, test_device_id, meta={"tipo": "teste"})
            print_info(f"Dispositivo registrado: {test_device_id}")
        except Exception:
            print_info(f"Dispositivo já existe: {test_device_id}")
        
        # Criar evento órfão (sem device_assignment)
        now = datetime.now(timezone.utc)
        ts_iso = now.isoformat()
        ts_ms = int(now.timestamp() * 1000)
        
        payload = {
            "device_id": test_device_id,
            "ts": ts_iso,
            "ts_ms": ts_ms,
            "tipo": "sensor",
            "dados": {
                "pressao_1": 450,
                "pressao_2": 380,
                "pressao_3": 420,
                "pressao_4": 390,
            }
        }
        
        event_id = inserir_device_event(
            DB_PATH,
            device_id=test_device_id,
            ts=ts_iso,
            ts_ms=ts_ms,
            payload=payload  # Passar dict direto, não JSON string
        )
        
        print_success(f"Evento órfão criado com ID: {event_id}")
        print_info(f"Device: {test_device_id}")
        print_info(f"Timestamp: {ts_iso}")
        
        # Verificar se aparece na listagem de pendentes
        pending = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
        orphan_found = any(e['id'] == event_id for e in pending)
        
        if orphan_found:
            print_success("Evento órfão aparece na listagem de pendentes")
        else:
            print_error("Evento órfão NÃO aparece na listagem de pendentes")
        
        return event_id
        
    except Exception as e:
        print_error(f"Erro ao criar evento órfão: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_reconciliation_without_assignment():
    """Teste 3: Tentar reconciliar sem device_assignment (deve falhar)"""
    print_section("Teste 3: Reconciliação sem Assignment (deve falhar)")
    
    try:
        from interface.api import _do_reconcile
        
        # Contar eventos pendentes antes
        before = listar_device_events(DB_PATH, include_processed=False)
        before_count = len(before)
        print_info(f"Eventos pendentes antes: {before_count}")
        
        # Tentar reconciliar
        result = _do_reconcile(device_id="TEST_DEVICE_ORPHAN_001", limit=100)
        
        print_info(f"Resultado da reconciliação:")
        print_info(f"  - Processados: {result['processed']}")
        print_info(f"  - Pulados (skipped): {result['skipped']}")
        
        # Contar eventos pendentes depois
        after = listar_device_events(DB_PATH, include_processed=False)
        after_count = len(after)
        print_info(f"Eventos pendentes depois: {after_count}")
        
        if result['skipped'] > 0 and result['processed'] == 0:
            print_success("Reconciliação corretamente pulou eventos sem assignment")
            return True
        else:
            print_error("Reconciliação deveria ter pulado os eventos")
            return False
        
    except Exception as e:
        print_error(f"Erro na reconciliação: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_create_assignment_and_reconcile():
    """Teste 4: Criar assignment e reconciliar com sucesso"""
    print_section("Teste 4: Criar Assignment e Reconciliar")
    
    try:
        import sqlite3
        test_device_id = "TEST_DEVICE_ORPHAN_001"
        
        # 1. Criar ou obter paciente
        try:
            paciente = criar_paciente(
                DB_PATH,
                nome="Paciente Teste Admin",
                perfil="alto",
                cama_id="TESTE_A1",
                observacoes="Criado para teste da página Admin"
            )
            test_patient_id = paciente.get('paciente_id') or paciente.get('id')
            cama_id = paciente.get('cama_id', 'TESTE_A1')
            print_info(f"Paciente criado: {test_patient_id} na cama {cama_id}")
        except Exception as e:
            # Se já existe, usar um existente
            print_info(f"Tentando usar paciente existente...")
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT paciente_id, cama_id FROM paciente_fichas LIMIT 1")
            row = cur.fetchone()
            conn.close()
            
            if row:
                test_patient_id = row['paciente_id']
                cama_id = row['cama_id']
                print_info(f"Usando paciente: {test_patient_id} na cama {cama_id}")
            else:
                print_error(f"Nenhum paciente disponível para teste: {e}")
                return False
        
        # 2. Criar device_assignment que cubra os eventos passados
        now = datetime.now(timezone.utc)
        # Criar assignment começando 2 horas atrás para cobrir os eventos órfãos
        start_time_iso = (now - timedelta(hours=2)).isoformat()
        start_time_ms = int((now.timestamp() - 7200) * 1000)  # 2 horas = 7200 segundos
        
        if not cama_id:
            print_error("Paciente não tem cama_id definido")
            return False
        
        try:
            assignment_id = start_device_assignment(
                DB_PATH,
                device_id=test_device_id,
                cama_id=cama_id,
                paciente_id=test_patient_id,
                start_ts=start_time_iso,
                start_ms=start_time_ms
            )
            print_success(f"Device assignment criado: {test_device_id} → {test_patient_id}")
            print_info(f"Assignment ID: {assignment_id}, início: {start_time_iso}")
        except Exception as e:
            print_info(f"Assignment pode já existir: {e}")
        
        # 3. Reconciliar novamente
        from interface.api import _do_reconcile
        from interface.dao import resolver_paciente_por_device_em, listar_device_assignments
        
        before = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
        before_count = len(before)
        print_info(f"Eventos pendentes antes: {before_count}")
        
        # Verificar assignments
        assignments = listar_device_assignments(DB_PATH, device_id=test_device_id)
        print_info(f"Assignments encontrados: {len(assignments)}")
        if assignments:
            for assig in assignments:
                print(f"  - {assig['device_id']} → {assig['paciente_id']} ({assig['start_ts']} - {assig['end_ts'] or 'ativo'})")
        
        # Testar resolver para cada evento
        print_info("Testando resolver_paciente_por_device_em para cada evento:")
        for ev in before:
            ts_ms = ev['ts_ms']
            try:
                pid = resolver_paciente_por_device_em(DB_PATH, test_device_id, ts_ms)
                print(f"  - Evento {ev['id']} (ts_ms={ts_ms}): paciente={pid}")
            except Exception as e:
                print(f"  - Evento {ev['id']} (ts_ms={ts_ms}): ERRO={e}")
        
        result = _do_reconcile(device_id=test_device_id, limit=100)
        
        print_info(f"Resultado da reconciliação:")
        print_info(f"  - Processados: {result['processed']}")
        print_info(f"  - Pulados: {result['skipped']}")
        
        after = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=False)
        after_count = len(after)
        print_info(f"Eventos pendentes depois: {after_count}")
        
        if result['processed'] > 0:
            print_success(f"Reconciliação processou {result['processed']} evento(s) com sucesso!")
            
            # Verificar se eventos foram marcados como processados
            all_events = listar_device_events(DB_PATH, device_id=test_device_id, include_processed=True)
            processed = [e for e in all_events if e['processed_at'] is not None]
            print_info(f"Eventos processados agora: {len(processed)}")
            
            if processed:
                print("\nExemplo de evento processado:")
                event = processed[0]
                print(f"  ID: {event['id']}")
                print(f"  Device: {event['device_id']}")
                print(f"  Processado em: {event['processed_at']}")
            
            return True
        else:
            print_error("Nenhum evento foi processado")
            return False
        
    except Exception as e:
        print_error(f"Erro ao criar assignment e reconciliar: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_endpoint_availability():
    """Teste 5: Verificar se endpoints da API estão disponíveis"""
    print_section("Teste 5: Verificar Endpoints da API")
    
    try:
        import inspect
        from interface.api import router
        
        # Verificar rotas registradas
        device_events_routes = []
        for route in router.routes:
            if hasattr(route, 'path'):
                if 'device_events' in route.path:
                    device_events_routes.append({
                        'path': route.path,
                        'methods': route.methods if hasattr(route, 'methods') else [],
                        'name': route.name if hasattr(route, 'name') else 'unknown'
                    })
        
        print_info(f"Rotas de device_events encontradas: {len(device_events_routes)}")
        for route in device_events_routes:
            methods = ', '.join(route['methods']) if route['methods'] else 'N/A'
            print(f"  - {methods:6} {route['path']:40} ({route['name']})")
        
        # Verificar funções específicas
        from interface.api import api_list_device_events, api_reconcile_device_events
        
        print_success("Função api_list_device_events encontrada")
        print_success("Função api_reconcile_device_events encontrada")
        
        # Verificar se reconcile_device_events (async) existe
        from interface.api import reconcile_device_events
        if inspect.iscoroutinefunction(reconcile_device_events):
            print_success("Função reconcile_device_events é async")
        
        return True
        
    except Exception as e:
        print_error(f"Erro ao verificar endpoints: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Executa todos os testes"""
    print_section("Teste da Pagina de Admin - Device Events")
    print(f"Database: {DB_PATH}")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # Teste 1: Listar eventos
    results['list'] = test_list_device_events()
    
    # Teste 2: Criar evento órfão
    orphan_id = test_create_orphan_event()
    results['create_orphan'] = orphan_id is not None
    
    # Teste 3: Reconciliar sem assignment (deve falhar)
    results['reconcile_fail'] = test_reconciliation_without_assignment()
    
    # Teste 4: Criar assignment e reconciliar (deve funcionar)
    results['reconcile_success'] = test_create_assignment_and_reconcile()
    
    # Teste 5: Verificar endpoints
    results['endpoints'] = test_endpoint_availability()
    
    # Resumo
    print_section("Resumo dos Testes")
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    for test_name, result in results.items():
        status = "PASSOU" if result else "FALHOU"
        symbol = "OK" if result else "X"
        print(f"[{symbol}] {status:12} - {test_name}")
    
    print(f"\n{'='*60}")
    print(f"Total: {passed}/{total} testes passaram")
    print(f"{'='*60}\n")
    
    if passed == total:
        print_success("Todos os testes passaram! A pagina de Admin esta funcional.")
        return 0
    else:
        print_error(f"{total - passed} teste(s) falharam. Verifique os logs acima.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
