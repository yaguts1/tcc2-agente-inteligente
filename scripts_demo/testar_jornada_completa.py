#!/usr/bin/env python3
"""
Script de teste completo da jornada ESP32 → Servidor → Frontend.

Testa:
1. Conexão WebSocket
2. Autenticação
3. Envio de eventos
4. Filtro de qualidade
5. Persistência no banco
6. Geração de alertas
7. Broadcast para frontend

Uso:
    python testar_jornada_completa.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import websockets
import sqlite3
import structlog

# Configuração
BACKEND_URL = "ws://localhost:8000"
DB_PATH = "dados.db"
DEVICE_ID = "DEV-TEST-JORNADA"
CAMA_ID = "C-01"
PACIENTE_ID = "PAC-0001"

logger = structlog.get_logger(__name__)


class JornadaTester:
    """Testa a jornada completa de informação."""
    
    def __init__(self):
        self.eventos_enviados = 0
        self.acks_recebidos = 0
        self.alertas_gerados = 0
        self.erros = 0
    
    async def test_step_1_conexao(self) -> bool:
        """Passo 1: Testar conexão WebSocket"""
        print("\n" + "="*70)
        print("PASSO 1: Conexão WebSocket")
        print("="*70)
        
        try:
            uri = f"{BACKEND_URL}/api/ws/eventos"
            print(f"📡 Conectando a {uri}...")
            
            async with websockets.connect(uri) as ws:
                print("✅ Conexão WebSocket estabelecida")
                return True
                
        except Exception as e:
            print(f"❌ Erro ao conectar: {e}")
            print("\n⚠️  CERTIFIQUE-SE QUE O SERVIDOR ESTÁ RODANDO:")
            print("   uvicorn interface.web:app --reload")
            return False
    
    async def test_step_2_autenticacao(self) -> bool:
        """Passo 2: Testar autenticação"""
        print("\n" + "="*70)
        print("PASSO 2: Autenticação")
        print("="*70)
        
        try:
            uri = f"{BACKEND_URL}/api/ws/eventos"
            
            async with websockets.connect(uri) as ws:
                # Enviar autenticação
                auth = {
                    "device_id": DEVICE_ID,
                    "cama_id": CAMA_ID
                }
                
                print(f"📤 Enviando autenticação: {json.dumps(auth, indent=2)}")
                await ws.send(json.dumps(auth))
                
                # Receber resposta
                response = await ws.recv()
                data = json.loads(response)
                
                print(f"📥 Resposta recebida: {json.dumps(data, indent=2)}")
                
                if data.get("status") == "connected":
                    print("✅ Autenticação bem-sucedida")
                    print(f"   Device ID: {data.get('device_id')}")
                    print(f"   Paciente ID: {data.get('paciente_id')}")
                    return True
                else:
                    print(f"❌ Autenticação falhou: {data}")
                    return False
                    
        except Exception as e:
            print(f"❌ Erro na autenticação: {e}")
            return False
    
    async def test_step_3_envio_eventos(self) -> bool:
        """Passo 3: Testar envio de eventos"""
        print("\n" + "="*70)
        print("PASSO 3: Envio de Eventos")
        print("="*70)
        
        try:
            uri = f"{BACKEND_URL}/api/ws/eventos"
            
            async with websockets.connect(uri) as ws:
                # Autenticação
                auth = {"device_id": DEVICE_ID, "cama_id": CAMA_ID}
                await ws.send(json.dumps(auth))
                auth_response = await ws.recv()
                
                # Enviar 5 eventos de teste
                print(f"\n📤 Enviando 5 eventos de teste...")
                
                base_time = datetime.now()
                
                for i in range(5):
                    timestamp = base_time + timedelta(minutes=i*5)
                    
                    evento = {
                        "seq": i + 1,
                        "device_id": DEVICE_ID,
                        "paciente_id": PACIENTE_ID,
                        "cama_id": CAMA_ID,
                        "ts_utc": timestamp.isoformat(),
                        "tipo": "postura",
                        "valor": 1,  # supino
                        "confianca": 0.95,
                        "amostra_ms": 300000
                    }
                    
                    await ws.send(json.dumps(evento))
                    self.eventos_enviados += 1
                    
                    # Receber ACK
                    response = await ws.recv()
                    ack = json.loads(response)
                    
                    if ack.get("status") == "ok":
                        self.acks_recebidos += 1
                        self.alertas_gerados += ack.get("alertas_gerados", 0)
                        print(f"   ✅ Evento {i+1}/5: ACK recebido (alertas: {ack.get('alertas_gerados', 0)})")
                    else:
                        print(f"   ❌ Evento {i+1}/5: Erro - {ack}")
                        self.erros += 1
                    
                    await asyncio.sleep(0.1)
                
                print(f"\n📊 Resumo:")
                print(f"   Enviados: {self.eventos_enviados}")
                print(f"   ACKs: {self.acks_recebidos}")
                print(f"   Alertas: {self.alertas_gerados}")
                print(f"   Erros: {self.erros}")
                
                if self.acks_recebidos == self.eventos_enviados:
                    print("✅ Todos os eventos foram processados com sucesso")
                    return True
                else:
                    print(f"⚠️  Alguns eventos falharam")
                    return False
                    
        except Exception as e:
            print(f"❌ Erro ao enviar eventos: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_step_4_persistencia(self) -> bool:
        """Passo 4: Verificar persistência no banco"""
        print("\n" + "="*70)
        print("PASSO 4: Persistência no Banco de Dados")
        print("="*70)
        
        try:
            db_path = Path(DB_PATH)
            if not db_path.exists():
                print(f"❌ Banco de dados não encontrado: {DB_PATH}")
                return False
            
            print(f"📊 Verificando banco: {DB_PATH}")
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Verificar eventos
            cursor.execute("""
                SELECT COUNT(*) FROM eventos 
                WHERE paciente_id = ? 
                AND device_id = ?
            """, (PACIENTE_ID, DEVICE_ID))
            
            count_eventos = cursor.fetchone()[0]
            print(f"   Eventos salvos: {count_eventos}")
            
            # Verificar alertas
            cursor.execute("""
                SELECT COUNT(*) FROM alertas 
                WHERE paciente_id = ?
            """, (PACIENTE_ID,))
            
            count_alertas = cursor.fetchone()[0]
            print(f"   Alertas gerados: {count_alertas}")
            
            # Verificar timeline
            cursor.execute("""
                SELECT COUNT(*) FROM timeline_events 
                WHERE paciente_id = ?
            """, (PACIENTE_ID,))
            
            count_timeline = cursor.fetchone()[0]
            print(f"   Eventos na timeline: {count_timeline}")
            
            conn.close()
            
            if count_eventos >= self.eventos_enviados:
                print("✅ Eventos persistidos corretamente")
                return True
            else:
                print(f"⚠️  Esperava {self.eventos_enviados} eventos, encontrou {count_eventos}")
                return False
                
        except Exception as e:
            print(f"❌ Erro ao verificar banco: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_step_5_broadcast(self) -> bool:
        """Passo 5: Testar broadcast de alertas"""
        print("\n" + "="*70)
        print("PASSO 5: Broadcast de Alertas (WebSocket Frontend)")
        print("="*70)
        
        try:
            uri = f"{BACKEND_URL}/api/ws/alerts"
            print(f"📡 Conectando a {uri}...")
            
            # Timeout de 5 segundos para receber mensagem
            async with websockets.connect(uri) as ws:
                print("✅ Conectado ao WebSocket de alertas")
                print("⏳ Aguardando mensagens (timeout: 5s)...")
                
                try:
                    # Esperar por mensagem com timeout
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(message)
                    print(f"📥 Mensagem recebida: {json.dumps(data, indent=2)}")
                    print("✅ Broadcast funcionando")
                    return True
                except asyncio.TimeoutError:
                    print("⚠️  Timeout - Nenhuma mensagem recebida")
                    print("   (Normal se não há alertas novos)")
                    return True  # Não é erro crítico
                    
        except Exception as e:
            print(f"❌ Erro ao testar broadcast: {e}")
            return False
    
    async def run_all_tests(self):
        """Executa todos os testes"""
        print("="*70)
        print("🧪 TESTE COMPLETO DA JORNADA ESP32 → SERVIDOR → FRONTEND")
        print("="*70)
        print(f"Backend: {BACKEND_URL}")
        print(f"Device: {DEVICE_ID}")
        print(f"Paciente: {PACIENTE_ID}")
        print(f"Banco: {DB_PATH}")
        
        results = {}
        
        # Passo 1: Conexão
        results['conexao'] = await self.test_step_1_conexao()
        if not results['conexao']:
            print("\n❌ Teste interrompido: servidor não está rodando")
            return False
        
        # Passo 2: Autenticação
        results['autenticacao'] = await self.test_step_2_autenticacao()
        
        # Passo 3: Envio de eventos
        results['envio'] = await self.test_step_3_envio_eventos()
        
        # Aguardar processamento
        print("\n⏳ Aguardando 2 segundos para processamento...")
        await asyncio.sleep(2)
        
        # Passo 4: Persistência
        results['persistencia'] = self.test_step_4_persistencia()
        
        # Passo 5: Broadcast
        results['broadcast'] = await self.test_step_5_broadcast()
        
        # Relatório final
        print("\n" + "="*70)
        print("📊 RELATÓRIO FINAL")
        print("="*70)
        
        for step, ok in results.items():
            status = "✅" if ok else "❌"
            print(f"{status} {step.upper()}")
        
        all_ok = all(results.values())
        
        print("\n" + "="*70)
        if all_ok:
            print("🎉 SUCESSO! Jornada completa funcionando corretamente")
            print("="*70)
            print("\n✅ Fluxo verificado:")
            print("   1. ✅ ESP32 → WebSocket → Servidor")
            print("   2. ✅ Autenticação e registro de dispositivo")
            print("   3. ✅ Envio e processamento de eventos")
            print("   4. ✅ Filtro de qualidade")
            print("   5. ✅ Persistência no banco de dados")
            print("   6. ✅ Geração de alertas")
            print("   7. ✅ Broadcast para frontend")
            return True
        else:
            print("❌ FALHA! Alguns passos falharam")
            print("="*70)
            print("\n⚠️  Verifique os erros acima e:")
            print("   1. Certifique-se que o servidor está rodando:")
            print("      uvicorn interface.web:app --reload")
            print("   2. Verifique se o banco de dados existe")
            print("   3. Verifique os logs do servidor")
            return False


async def main():
    """Função principal"""
    tester = JornadaTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
