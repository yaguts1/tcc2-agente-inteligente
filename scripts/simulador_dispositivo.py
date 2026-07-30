import sys
import time
import requests
import argparse
from datetime import datetime, UTC
from pathlib import Path
import pandas as pd

# Add root to path to import dados_simulados
sys.path.insert(0, str(Path(__file__).parent.parent))

from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente
from scripts.envio_resiliente import Contadores, PoliticaRetry, Resultado, entregar

# Duracao que cada amostra representa. O backend usa `amostra_ms` como DURACAO
# (`fim = inicio + amostra_ms`, ver interface/services/ingestao_service.py), e
# este script mandava o epoch em milissegundos: cada evento gravado ficava com
# `fim` uns 55 anos no futuro.
AMOSTRA_MS = 60_000

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
    # UTC naive, que é o que o banco armazena (ver interface/tempo.py). Com
    # datetime.now() os timestamps saíam no fuso da máquina e as amostras
    # entravam 3h deslocadas — o mesmo defeito que corrompia a correlação
    # sensor->paciente do lado do servidor.
    inicio = datetime.now(UTC).replace(tzinfo=None)
    df_grade, _ = gerar_sessao_simulada(
        duracao_horas=args.duration,
        passo_min=1,  # 1 minuto de resolução para ficar mais fluido
        inicio=inicio,
        perfil=PerfilPaciente(nome="Demo User")
    )
    
    print(f"Gerados {len(df_grade)} pontos de dados.")
    
    politica = PoliticaRetry()
    contadores = Contadores()

    # 2. Loop de envio
    for _, row in df_grade.iterrows():
        ts_simulado = pd.to_datetime(row["timestamp"])

        # Calcular delay necessário
        agora = datetime.now(UTC).replace(tzinfo=None)
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
            "amostra_ms": AMOSTRA_MS,
            "ts_utc": ts_simulado.isoformat()
        }

        def enviar():
            """Devolve o status HTTP, ou None se nem chegou a haver resposta."""
            try:
                resp = requests.post(
                    f"{args.url}/api/eventos",
                    json=payload,
                    headers={"X-Device-Id": args.device},
                    timeout=10,
                )
                return resp.status_code
            except requests.RequestException as e:
                print(f"ERRO de conexão: {e}")
                return None

        # Antes, uma falha era impressa e a amostra seguia perdida — o
        # simulador de bancada nao exercitava a unica coisa que importa quando
        # a rede oscila. Agora vale a mesma politica do firmware.
        resultado = entregar(enviar, politica, contadores)
        if resultado is Resultado.ACK:
            hora = datetime.now().strftime("%H:%M:%S")
            print(f"[{hora}] Enviado: {row['postura']} (Conf: {payload['confianca']})")

    print(
        f"\nFim: {contadores.entregues} entregues, {contadores.descartados} descartados, "
        f"{contadores.tentativas} tentativas."
    )

if __name__ == "__main__":
    main()
