#!/usr/bin/env python3
import asyncio
import json
import websockets
from datetime import datetime

BACKEND_URL = "ws://localhost:8000"
DEVICE_ID = "DEV-TEST-001"
CAMA_ID = "C-01"
PACIENTE_ID = "PAC-0001"

async def test():
    print("=== TESTE WEBSOCKET SIMPLES ===")
    uri = f"{BACKEND_URL}/ws/eventos"
    
    async with websockets.connect(uri) as ws:
        print(f" Conectado a {uri}")
        
        # 1. Autenticação
        auth = {"device_id": DEVICE_ID, "cama_id": CAMA_ID}
        print(f"\n Enviando autenticação: {auth}")
        await ws.send(json.dumps(auth))
        
        resp = await ws.recv()
        print(f" Resposta: {resp}")
        
        # 2. Enviar evento
        evento = {
            "device_id": DEVICE_ID,
            "paciente_id": PACIENTE_ID,
            "tipo": "decubito_dorsal",
            "inicio": datetime.now().isoformat(),
            "fim": datetime.now().isoformat(),
            "confianca": 0.95
        }
        print(f"\n Enviando evento: {json.dumps(evento, indent=2)}")
        await ws.send(json.dumps(evento))
        
        resp = await ws.recv()
        print(f" ACK: {resp}")
        print("\n Teste concluído com sucesso!")

if __name__ == "__main__":
    asyncio.run(test())
