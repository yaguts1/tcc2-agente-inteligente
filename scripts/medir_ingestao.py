"""Mede o teto de escrita do caminho de ingestao.

Existe para a otimizacao ser comparavel: sem medir antes, "ficou mais rapido" e
opiniao. Roda contra um banco temporario, nao contra o de producao.

Uso:
    python -m scripts.medir_ingestao [--amostras 300] [--threads 1]

O que ele NAO mede: rede, FastAPI, serializacao. So o caminho de escrita a
partir de `registrar_evento`, que e onde o gargalo foi localizado.
"""
from __future__ import annotations

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta


def _preparar(db_path: str, pacientes: int) -> list[str]:
    os.environ["UPP_DB_PATH"] = db_path
    from interface.db_core import connect, criar_esquema

    criar_esquema(db_path)
    ids = []
    agora = datetime(2026, 3, 10, 8, 0, 0).strftime("%Y-%m-%dT%H:%M:%S")
    with connect(db_path) as conn:
        for i in range(pacientes):
            pid = f"PAC-{i + 1:04d}"
            ids.append(pid)
            conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (pid,))
            conn.execute(
                "INSERT INTO paciente_fichas"
                " (paciente_id, nome, perfil, cama_id, created_at, updated_at, unidade_id)"
                " VALUES (?,?,'alto',?,?,?,1)",
                (pid, f"Paciente {i}", f"L-{i}", agora, agora),
            )
    return ids


def medir(amostras: int, threads: int, pacientes: int) -> dict:
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "bench.db")
    ids = _preparar(db_path, pacientes)

    from interface.schemas import EventPayload
    from interface.services import ingestao_service

    ingestao_service.DB_PATH = db_path

    base = datetime(2026, 3, 10, 8, 0, 0)
    # Uma amostra por paciente por minuto, postura constante: o caminho quente e
    # o de gravar, nao o de alertar.
    trabalho = [
        EventPayload(
            device_id=f"DEV-{i % pacientes:03d}",
            paciente_id=ids[i % pacientes],
            cama_id=f"L-{i % pacientes}",
            postura="supino",
            confianca=0.95,
            amostra_ms=60000,
            ts_utc=(base + timedelta(minutes=i // pacientes)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        for i in range(amostras)
    ]

    inicio = time.perf_counter()
    if threads == 1:
        for payload in trabalho:
            ingestao_service.registrar_evento(payload)
    else:
        # Particionado POR PACIENTE, e nao distribuido livremente entre threads.
        #
        # O decisor recusa timestamp fora de ordem, e com razao. Distribuir as
        # amostras de um mesmo paciente entre threads as entrega embaralhadas e
        # o benchmark quebra — mas o que ele estaria medindo ali nao existe no
        # mundo real: as amostras de um paciente vem de UM device, em ordem. O
        # que e concorrente e o trafego entre pacientes diferentes.
        por_paciente: dict[str, list] = {}
        for payload in trabalho:
            por_paciente.setdefault(payload.paciente_id, []).append(payload)

        def _sequencia(lote):
            for payload in lote:
                ingestao_service.registrar_evento(payload)

        with ThreadPoolExecutor(max_workers=threads) as pool:
            list(pool.map(_sequencia, por_paciente.values()))
    decorrido = time.perf_counter() - inicio

    return {
        "amostras": amostras,
        "threads": threads,
        "segundos": round(decorrido, 2),
        "amostras_por_segundo": round(amostras / decorrido, 1),
        "ms_por_amostra": round(decorrido / amostras * 1000, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amostras", type=int, default=300)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--pacientes", type=int, default=10)
    args = parser.parse_args()

    resultado = medir(args.amostras, args.threads, args.pacientes)
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
