#!/usr/bin/env python3
"""Script de diagnóstico para entender por que a reconciliação está falhando"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")

from interface.dao import listar_device_events, resolver_paciente_por_device_em
from interface.api import _normalizar_payload, _registrar_evento

# Pegar o primeiro evento órfão
events = listar_device_events(DB_PATH, include_processed=False, limit=1)

if not events:
    print("Nenhum evento órfão encontrado")
    sys.exit(1)

ev = events[0]
print(f"Evento ID: {ev['id']}")
print(f"Device ID: {ev['device_id']}")
print(f"Timestamp (ms): {ev['ts_ms']}")
print(f"Payload type: {type(ev['payload'])}")
print(f"Payload:\n{json.dumps(ev['payload'], indent=2)}\n")

# Tentar resolver paciente
try:
    pid = resolver_paciente_por_device_em(DB_PATH, ev['device_id'], ev['ts_ms'])
    print(f"✓ Paciente resolvido: {pid}\n")
except Exception as e:
    print(f"✗ Erro ao resolver paciente: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Tentar processar o payload
payload = ev['payload']
payload["paciente_id"] = pid
payload["device_id"] = ev['device_id']

print(f"Payload modificado:\n{json.dumps(payload, indent=2)}\n")

# Tentar normalizar
try:
    evento = _normalizar_payload(payload, None)
    print(f"✓ Payload normalizado com sucesso")
    print(f"  Evento normalizado: {evento}\n")
except Exception as e:
    print(f"✗ Erro ao normalizar payload: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Tentar registrar
try:
    _registrar_evento(evento)
    print(f"✓ Evento registrado com sucesso!")
except Exception as e:
    print(f"✗ Erro ao registrar evento: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓✓✓ Reconciliação manual bem-sucedida! ✓✓✓")
