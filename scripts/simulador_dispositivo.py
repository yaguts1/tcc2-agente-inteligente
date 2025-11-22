import sys
import time
import requests
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# Add root to path to import dados_simulados
sys.path.insert(0, str(Path(__file__).parent.parent))

from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente

def main():
    parser = argparse.ArgumentParser(description="Simula um dispositivo ESP32 enviando dados para a API.")
    parser.add_argument("--paciente", default="PAC-DEMO", help="ID do paciente")
    parser.add_argument("--device", default="esp32-demo", help="ID do dispositivo")
    parser.add_argument("--cama", default="CAMA-DEMO", help="ID da cama")
    parser.add_argument("--url", default="http://localhost:8000", help="URL da API")
    parser.add_argument("--speed", type=float, default=1.0, help="Fator de aceleração (1.0 = tempo real, 60.0 = 1 min simula 1 hora)")
    parser.add_argument("--duration", type=int, default=1, help="Duração da simulação em horas")
    
    args = parser.parse_args()
    
    print(f"Iniciando simulação para {args.paciente} (Device: {args.device})")
    print(f"API: {args.url}")
    print(f"Velocidade: {args.speed}x")
    
    # 1. Gerar sessão futura
    print("Gerando dados de simulação...")
    inicio = datetime.now()
    df_grade, _ = gerar_sessao_simulada(
        duracao_horas=args.duration,
        passo_min=1,  # 1 minuto de resolução para ficar mais fluido
        inicio=inicio,
        perfil=PerfilPaciente(nome="Demo User")
    )
    
    print(f"Gerados {len(df_grade)} pontos de dados.")
    
    # 2. Loop de envio
    for _, row in df_grade.iterrows():
        ts_simulado = pd.to_datetime(row["timestamp"])
        
        # Calcular delay necessário
        agora = datetime.now()
        tempo_decorrido_real = (agora - inicio).total_seconds()
        tempo_decorrido_simulado = (ts_simulado - inicio).total_seconds()
        
        delay = (tempo_decorrido_simulado / args.speed) - tempo_decorrido_real
        
        if delay > 0:
            time.sleep(delay)
            
        # Montar payload
        payload = {
            "device_id": args.device,
            "paciente_id": args.paciente,
            "cama_id": args.cama,
            "postura": row["postura"],
            "confianca": row.get("confianca", 0.95),
            "amostra_ms": int(ts_simulado.timestamp() * 1000),
            "ts_utc": ts_simulado.isoformat()
        }
        
        try:
            resp = requests.post(f"{args.url}/api/eventos", json=payload, headers={"X-Device-Id": args.device})
            if resp.status_code == 200:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Enviado: {row['postura']} (Conf: {payload['confianca']})")
            else:
                print(f"ERRO {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"ERRO de conexão: {e}")

if __name__ == "__main__":
    main()
