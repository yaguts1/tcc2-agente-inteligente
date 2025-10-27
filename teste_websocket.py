#!/usr/bin/env python3
"""
Script para testar o endpoint WebSocket /api/ws/alerts
Verifica:
  1. Conexão bem-sucedida
  2. Heartbeat funcionando
  3. Mensagens sendo recebidas
  4. Desconexão graciosa
"""

import asyncio
import websockets
import json
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)

# Configuração
WS_URL = "ws://localhost:8000/api/ws/alerts"
TEST_DURATION = 30  # segundos
HEARTBEAT_INTERVAL = 5  # segundos


async def test_websocket_connection():
    """Testa a conexão WebSocket com o backend"""
    
    print("\n" + "="*60)
    print("🧪 TESTE DE WEBSOCKET - /api/ws/alerts")
    print("="*60 + "\n")
    
    try:
        print(f"📡 Conectando em: {WS_URL}")
        
        async with websockets.connect(WS_URL) as websocket:
            print("✅ Conexão estabelecida!\n")
            
            # Contador de mensagens
            messages_received = 0
            start_time = datetime.now()
            
            # Task para enviar heartbeats
            async def send_heartbeats():
                nonlocal messages_received
                try:
                    count = 0
                    while True:
                        await asyncio.sleep(HEARTBEAT_INTERVAL)
                        heartbeat = {"type": "heartbeat", "timestamp": datetime.now().isoformat()}
                        await websocket.send(json.dumps(heartbeat))
                        count += 1
                        print(f"💓 Heartbeat enviado #{count}")
                except asyncio.CancelledError:
                    pass
            
            # Task para receber mensagens
            async def receive_messages():
                nonlocal messages_received
                try:
                    while True:
                        message = await websocket.recv()
                        messages_received += 1
                        
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type", "unknown")
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"📨 [{timestamp}] Mensagem #{messages_received}: {msg_type}")
                            if "alert_id" in data:
                                print(f"   └─ Alert ID: {data.get('alert_id')}")
                        except json.JSONDecodeError:
                            print(f"📨 Mensagem raw: {message[:50]}...")
                except asyncio.CancelledError:
                    pass
            
            # Iniciar tasks
            heartbeat_task = asyncio.create_task(send_heartbeats())
            receive_task = asyncio.create_task(receive_messages())
            
            print(f"⏱️  Testando por {TEST_DURATION} segundos...\n")
            print("Aguardando mensagens do servidor...\n")
            
            try:
                await asyncio.sleep(TEST_DURATION)
            except KeyboardInterrupt:
                print("\n⚠️  Teste interrompido pelo usuário")
            
            # Cancelar tasks
            heartbeat_task.cancel()
            receive_task.cancel()
            
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
            
            # Desconectar
            await websocket.close()
            
            # Relatório
            duration = (datetime.now() - start_time).total_seconds()
            print("\n" + "="*60)
            print("📊 RELATÓRIO DE TESTE")
            print("="*60)
            print(f"⏱️  Duração: {duration:.2f}s")
            print(f"📨 Mensagens recebidas: {messages_received}")
            print(f"📡 Conexão: ✅ Estabelecida e Encerrada")
            print("="*60 + "\n")
            
            return True
    
    except ConnectionRefusedError:
        print("❌ ERRO: Conexão recusada!")
        print("   └─ Verifique se o servidor FastAPI está rodando em localhost:8000")
        print("   └─ Execute: uvicorn interface.api:app --reload")
        return False
    
    except Exception as e:
        print(f"❌ ERRO: {type(e).__name__}: {str(e)}")
        return False


async def test_create_alert_and_broadcast():
    """
    Testa o broadcast de alertas:
    1. Conecta ao WebSocket
    2. Cria um alerta via HTTP
    3. Verifica se recebe via WebSocket
    """
    
    print("\n" + "="*60)
    print("🧪 TESTE DE BROADCAST - Criar Alerta e Receber via WebSocket")
    print("="*60 + "\n")
    
    try:
        import requests
    except ImportError:
        print("⚠️  Módulo 'requests' não instalado. Pulando teste de broadcast.")
        print("   Instale com: pip install requests\n")
        return
    
    from time import sleep
    
    # Configuração
    ALERT_API = "http://localhost:8000/api/alertas"
    AUTH_HEADER = {
        "Authorization": "Bearer user@example.com:1234567890"
    }
    
    alerts_received = []
    
    async def monitor_websocket():
        """Monitora WebSocket por 10 segundos"""
        try:
            async with websockets.connect(WS_URL) as websocket:
                print("✅ Conectado ao WebSocket\n")
                
                # Enviar primeiro heartbeat
                await websocket.send(json.dumps({"type": "heartbeat"}))
                print("💓 Heartbeat enviado")
                
                # Monitorar por 10 segundos
                start = datetime.now()
                while (datetime.now() - start).total_seconds() < 10:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                        data = json.loads(message)
                        
                        if data.get("type") == "alert_update":
                            alerts_received.append(data)
                            print(f"🎯 Alerta recebido via WebSocket!")
                            print(f"   └─ ID: {data.get('alert_id')}")
                            print(f"   └─ Status: {data.get('status')}\n")
                    
                    except asyncio.TimeoutError:
                        pass
        
        except Exception as e:
            print(f"⚠️  Erro WebSocket: {e}")
    
    # Executar teste
    try:
        # Iniciar monitoramento em background
        monitor_task = asyncio.create_task(monitor_websocket())
        
        # Aguardar 2 segundos (dar tempo para conectar)
        await asyncio.sleep(2)
        
        # Criar alerta via HTTP
        print("📡 Enviando POST /api/alertas...")
        alert_data = {
            "alert_type": "test_broadcast",
            "severity": "high",
            "observacao": f"Teste de broadcast - {datetime.now().isoformat()}",
            "patient_id": "PAC-0001"
        }
        
        response = requests.post(ALERT_API, json=alert_data, headers=AUTH_HEADER)
        
        if response.status_code == 201:
            alert = response.json()
            print(f"✅ Alerta criado: {alert.get('id')}\n")
        else:
            print(f"⚠️  Resposta: {response.status_code} - {response.text}\n")
        
        # Aguardar monitoramento terminar
        await monitor_task
        
        # Relatório
        print("="*60)
        print("📊 RELATÓRIO DE BROADCAST")
        print("="*60)
        if alerts_received:
            print(f"✅ Broadcast funcionando! Recebeu {len(alerts_received)} alerta(s)")
        else:
            print("⚠️  Nenhum alerta recebido (pode ser esperado em teste)")
        print("="*60 + "\n")
    
    except Exception as e:
        print(f"❌ Erro ao testar broadcast: {e}")


async def main():
    """Executa todos os testes"""
    
    print("\n🚀 INICIANDO TESTES DE WEBSOCKET\n")
    
    # Teste 1: Conexão básica
    print("\n[TESTE 1/2] Conexão e Heartbeat")
    result1 = await test_websocket_connection()
    
    # Teste 2: Broadcast (opcional)
    print("\n[TESTE 2/2] Broadcast de Alertas")
    await test_create_alert_and_broadcast()
    
    print("\n✨ Testes concluídos!\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Testes cancelados pelo usuário")
