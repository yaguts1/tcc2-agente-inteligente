#!/usr/bin/env python3
"""
Script para gerar arquivo eventos.jsonl para ESP32 com timestamps atuais.

Uso:
    python scripts/gerar_eventos_esp32.py --output firmware/esp32_replay/data/eventos_now.jsonl --horas 2

Gera eventos de postura simulados com:
- Timestamps começando AGORA e indo para o futuro
- Intervalos de 5 minutos
- Padrão de posturas realista (principalmente supino, mudanças ocasionais)
- Formato compatível com o backend

O FORMATO É O DE `EventPayload`, E ISSO NÃO É NEGOCIÁVEL
--------------------------------------------------------
`interface/schemas.py` declara `EventPayload` com `extra="forbid"`: qualquer
campo a mais derruba a requisição inteira em 422, e `postura` (string) é
obrigatório.

Este script gerava outra coisa — `{"seq", "tipo": "postura", "valor": 1}` —,
que é o formato do `JORNADA_INFORMACAO_ESP32.md` e não o que o servidor aceita
desde que `EventPayload` passou a proibir extras. O resultado era o pior
possível: **todo** evento voltava 422, o firmware classifica 422 como
PERMANENTE (`classificarResposta`), e então o dispositivo descartava o arquivo
inteiro linha por linha, avançando o checkpoint, sem uma única falha aparente.
Do lado do ESP32 o replay terminava "com sucesso"; do lado do banco não havia
nada. `tests/test_e2e_esp32.py` afirma que nenhuma linha é descartada, que é
como isso volta a aparecer se alguém reintroduzir o formato antigo.

Os campos aceitos são: device_id, paciente_id, cama_id, postura, confianca,
amostra_ms, ts_utc e pressao_pico (opcional). Mais nenhum.
"""

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


def gerar_eventos_esp32(
    horas: int = 24,
    device_id: str = "DEV-001",
    paciente_id: str = "PAC-0001",
    cama_id: str = "C-01",
    intervalo_min: int = 5,
    output_file: str = "eventos_now.jsonl",
    seed: int = 42
):
    """
    Gera arquivo JSONL com eventos de postura para ESP32.
    
    Args:
        horas: Duração da simulação em horas
        device_id: ID do dispositivo ESP32
        paciente_id: ID do paciente
        cama_id: ID da cama
        intervalo_min: Intervalo entre eventos em minutos
        output_file: Caminho do arquivo de saída
        seed: Seed para reproducibilidade
    """
    random.seed(seed)
    
    # Posturas possíveis (mapeamento backend)
    POSTURAS = {
        0: "lateral_direito",
        1: "supino",
        2: "lateral_esquerdo", 
        3: "prono"
    }
    
    # Começar AGORA (não no passado!)
    #
    # `utcnow`, não `now`: o campo se chama `ts_utc` e o servidor o interpreta
    # como UTC (`EventPayload._normalizar_ts`). Gravar hora local aqui
    # deslocava toda a série pelo fuso da máquina — em Brasília, três horas —
    # sem nenhum erro, só um dashboard com os eventos no lugar errado.
    inicio = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    total_eventos = (horas * 60) // intervalo_min
    
    eventos = []
    postura_atual = 1  # Começar em supino
    tempo_na_postura = 0
    
    for i in range(total_eventos):
        timestamp = inicio + timedelta(minutes=i * intervalo_min)
        
        # Modelo simples: paciente fica muito tempo em supino, muda ocasionalmente
        tempo_na_postura += intervalo_min
        
        # Chance de mudar de postura após 1-2 horas
        if tempo_na_postura >= 60 and random.random() < 0.2:
            # Mudar para outra postura
            opcoes = [p for p in POSTURAS if p != postura_atual]
            postura_atual = random.choice(opcoes)
            tempo_na_postura = 0
        
        # Confiança alta (simulando sensor de qualidade)
        confianca = round(random.uniform(0.90, 0.99), 2)
        
        # `EventPayload` exatamente: nem um campo a menos, nem um a mais.
        # `seq` saiu porque o firmware numera as amostras por conta própria
        # (`evento.seq = ++g_status.seqAtual`) e o servidor recusa o extra.
        evento = {
            "device_id": device_id,
            "paciente_id": paciente_id,
            "cama_id": cama_id,
            "postura": POSTURAS[postura_atual],
            "confianca": confianca,
            "amostra_ms": intervalo_min * 60 * 1000,  # Converter para ms
            "ts_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        
        eventos.append(evento)
    
    # Salvar arquivo
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for evento in eventos:
            f.write(json.dumps(evento, ensure_ascii=False) + '\n')
    
    print("✅ Arquivo gerado com sucesso!")
    print(f"📄 Caminho: {output_path.absolute()}")
    print(f"📊 Total de eventos: {len(eventos)}")
    print(f"⏰ Período: {inicio.strftime('%Y-%m-%d %H:%M')} até {eventos[-1]['ts_utc']}")
    print("📈 Distribuição de posturas:")
    
    # Estatísticas
    from collections import Counter
    contagem = Counter(e['postura'] for e in eventos)
    for nome, count in sorted(contagem.items()):
        percentual = (count / len(eventos)) * 100
        print(f"   - {nome}: {count} eventos ({percentual:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Gera eventos simulados para ESP32 com timestamps atuais"
    )
    parser.add_argument(
        "--output", "-o",
        default="firmware/esp32_replay/data/eventos_now.jsonl",
        help="Arquivo de saída (padrão: firmware/esp32_replay/data/eventos_now.jsonl)"
    )
    parser.add_argument(
        "--horas",
        type=int,
        default=24,
        help="Duração da simulação em horas (padrão: 24)"
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=5,
        help="Intervalo entre eventos em minutos (padrão: 5)"
    )
    parser.add_argument(
        "--device-id",
        default="DEV-001",
        help="ID do dispositivo (padrão: DEV-001)"
    )
    parser.add_argument(
        "--paciente-id",
        default="PAC-0001",
        help="ID do paciente (padrão: PAC-0001)"
    )
    parser.add_argument(
        "--cama-id",
        default="C-01",
        help="ID da cama (padrão: C-01)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed para reproducibilidade (padrão: 42)"
    )
    
    args = parser.parse_args()
    
    gerar_eventos_esp32(
        horas=args.horas,
        device_id=args.device_id,
        paciente_id=args.paciente_id,
        cama_id=args.cama_id,
        intervalo_min=args.intervalo,
        output_file=args.output,
        seed=args.seed
    )


if __name__ == "__main__":
    main()
