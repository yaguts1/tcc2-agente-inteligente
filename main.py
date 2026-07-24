"""CLI para gerar simulacoes de posturas e enviar eventos ao backend."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

import httpx
import pandas as pd
import structlog

from configuracao import config
from dados_simulados.gerador import (
    PerfilPaciente,
    gerar_eventos_sessao,
    gerar_sessao_multi,
    gerar_sessao_simulada,
)
from interface.dao import (
    criar_esquema,
    inserir_alertas,
    inserir_eventos,
    inserir_grade,
)
from modulo_alerta.engine import processar_alertas

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
MODOS_VALIDOS = ("batch", "stream")
_DEFAULT_STREAM_ENDPOINT = "/api/eventos"
logger = structlog.get_logger(__name__)


def _norm_iso(series: pd.Series) -> pd.Series:
    """Normaliza timestamps para ISO sem timezone."""
    valores = pd.to_datetime(series, errors="coerce")
    if getattr(valores.dtype, "tz", None) is not None:
        valores = valores.dt.tz_convert(None)
    return valores.dt.floor("s").dt.strftime(ISO_FORMAT)


def processar_alertas_multi(df_grade: pd.DataFrame, perfil: str) -> List[dict]:
    """Executa o motor de alertas por paciente e agrega os resultados."""
    alertas: List[dict] = []
    for paciente_id, grupo in df_grade.groupby("paciente_id", sort=True):
        _, alerta_paciente = processar_alertas(grupo[["timestamp", "postura"]], perfil, paciente_id)
        alertas.extend(alerta_paciente)
    return alertas


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Configura o parser de argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Gera simulacao de posturas (batch) ou envia eventos para a API (stream).",
    )
    parser.add_argument("--ajuda", action="help", help="Exibe esta mensagem de ajuda e encerra a execucao.")
    parser.add_argument(
        "--modo",
        choices=MODOS_VALIDOS,
        default=None,
        help="Modo de operacao: batch (default do .env) ou stream.",
    )

    # Parametros batch
    parser.add_argument("--horas", type=int, default=24, help="Duracao da simulacao em horas (batch).")
    parser.add_argument("--seed", type=int, default=42, help="Semente para reproducibilidade (batch).")
    parser.add_argument("--passo", type=int, default=5, help="Passo (minutos) entre amostras (batch).")
    parser.add_argument("--pacientes", type=int, default=1, help="Numero de pacientes simulados (batch).")
    parser.add_argument("--pacientes-ids", type=str, default="", help="IDs dos pacientes separados por virgula (batch).")
    parser.add_argument("--saida", type=str, default="dados_simulados/sessao.csv", help="CSV de saida da grade (batch).")
    parser.add_argument("--eventos", type=str, default="", help="(Opcional) CSV para salvar eventos brutos (batch).")
    parser.add_argument(
        "--perfil",
        type=str.lower,
        choices=("baixo", "medio", "alto"),
        default="medio",
        help="Perfil de risco para o motor de alertas (batch).",
    )
    parser.add_argument("--alertas", type=str, default="", help="(Opcional) CSV para salvar alertas gerados (batch).")
    parser.add_argument("--db", type=str, default="", help="(Opcional) banco de dados SQLite para persistencia (batch).")

    # Parametros stream
    parser.add_argument("--entrada", type=str, default="", help="Arquivo de entrada (CSV ou JSONL) para modo stream.")
    parser.add_argument(
        "--formato",
        choices=("csv", "jsonl"),
        default="csv",
        help="Formato do arquivo de entrada (stream).",
    )
    parser.add_argument("--ritmo-ms", type=int, default=0, help="Intervalo entre envios em ms (stream).")
    parser.add_argument("--host", type=str, default="http://localhost:8000", help="Host base do servidor (stream).")
    parser.add_argument("--endpoint", type=str, default=_DEFAULT_STREAM_ENDPOINT, help="Endpoint HTTP alvo (stream).")
    parser.add_argument("--retries", type=int, default=3, help="Numero de tentativas em caso de falha (stream).")
    parser.add_argument(
        "--retry-backoff-ms",
        type=int,
        default=500,
        help="Backoff inicial em milissegundos entre tentativas (stream).",
    )
    parser.add_argument(
        "--max-envios",
        type=int,
        default=0,
        help="Limita quantidade de envios (0 = todos os eventos do arquivo).",
    )
    return parser.parse_args(argv)


def _salvar_csv(df: pd.DataFrame, destino: Path, descricao: str) -> None:
    """Salva um DataFrame em CSV e informa o usuario."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding="utf-8")
    print(f"{descricao} salvo em: {destino} ({len(df)} linhas)")


def _parse_pacientes_ids(valor: str) -> List[str]:
    ids = [pid.strip() for pid in valor.split(",") if pid.strip()]
    if valor and not ids:
        raise ValueError("Nenhum identificador valido em --pacientes-ids.")
    return ids


def run_batch(args: argparse.Namespace) -> None:
    pacientes_ids_arg = _parse_pacientes_ids(args.pacientes_ids)
    if args.pacientes < 1 and not pacientes_ids_arg:
        raise ValueError("--pacientes deve ser pelo menos 1.")

    if args.db:
        criar_esquema(args.db)

    if pacientes_ids_arg:
        patient_ids = pacientes_ids_arg
        total_pacientes = len(patient_ids)
    else:
        total_pacientes = args.pacientes
        patient_ids = [f"P{i + 1}" for i in range(total_pacientes)]

    if total_pacientes < 1:
        raise ValueError("Quantidade de pacientes invalida.")

    logger.info(
        "batch_inicio",
        pacientes=total_pacientes,
        horas=args.horas,
        perfil=args.perfil,
        saida=args.saida,
    )

    use_multi_generator = total_pacientes > 1 or bool(pacientes_ids_arg)
    df_eventos_raw: Optional[pd.DataFrame] = None

    if use_multi_generator:
        df_grade_raw, df_eventos_raw = gerar_sessao_multi(
            pacientes=total_pacientes,
            horas=args.horas,
            passo_min=args.passo,
            seed=args.seed,
            perfil=args.perfil,
        )
        if pacientes_ids_arg:
            mapping = {f"P{i + 1}": pid for i, pid in enumerate(patient_ids)}
            df_grade_raw = df_grade_raw.copy()
            df_grade_raw["paciente_id"] = df_grade_raw["paciente_id"].map(mapping)
            if df_grade_raw["paciente_id"].isna().any():
                raise ValueError("IDs insuficientes para mapear todos os pacientes gerados.")
            if df_eventos_raw is not None:
                df_eventos_raw = df_eventos_raw.copy()
                df_eventos_raw["paciente_id"] = df_eventos_raw["paciente_id"].map(mapping)
    else:
        perfil_obj = PerfilPaciente()
        df_grade_raw = gerar_sessao_simulada(
            duracao_horas=args.horas,
            seed=args.seed,
            passo_min=args.passo,
            perfil=perfil_obj,
        ).copy()
        df_grade_raw.insert(0, "paciente_id", patient_ids[0])

    df_grade_norm = df_grade_raw.copy()
    df_grade_norm["timestamp"] = _norm_iso(df_grade_norm["timestamp"])
    df_grade_norm = df_grade_norm.sort_values(["paciente_id", "timestamp"]).reset_index(drop=True)
    df_grade_norm = df_grade_norm[["paciente_id", "timestamp", "postura"]]

    alertas = processar_alertas_multi(df_grade_norm, args.perfil)

    _salvar_csv(df_grade_norm, Path(args.saida), "Grade")
    print(f"Pacientes: {df_grade_norm['paciente_id'].nunique()}")

    df_eventos_norm: Optional[pd.DataFrame] = None
    if args.eventos:
        if df_eventos_raw is None:
            eventos_base = gerar_eventos_sessao(
                duracao_horas=args.horas,
                seed=args.seed,
                perfil=PerfilPaciente(),
            ).copy()
            eventos_base.insert(0, "paciente_id", patient_ids[0])
            df_eventos_raw = eventos_base
        df_eventos_norm = df_eventos_raw.copy()
        for coluna in ("timestamp", "inicio", "fim"):
            if coluna in df_eventos_norm.columns:
                df_eventos_norm[coluna] = _norm_iso(df_eventos_norm[coluna])
        df_eventos_norm = df_eventos_norm.sort_values(["paciente_id", "inicio"]).reset_index(drop=True)
        colunas_eventos = ["paciente_id"] + [c for c in df_eventos_norm.columns if c != "paciente_id"]
        df_eventos_norm = df_eventos_norm[colunas_eventos]

        eventos_path = Path(args.eventos)
        eventos_path.parent.mkdir(parents=True, exist_ok=True)
        df_eventos_norm.to_csv(eventos_path, index=False, encoding="utf-8")
        print(f"Eventos salvos em: {eventos_path} ({len(df_eventos_norm)} linhas)")
    else:
        print("Eventos gerados: 0 (flag --eventos ausente).")

    alertas_count = len(alertas)
    if args.alertas:
        alertas_path = Path(args.alertas)
        alertas_path.parent.mkdir(parents=True, exist_ok=True)
        colunas_alertas = [
            "paciente_id",
            "inicio",
            "fim",
            "tipo",
            "perfil",
            "janela_min",
            "status",
            "duracao_min",
        ]
        df_alertas = pd.DataFrame(alertas)
        if df_alertas.empty:
            df_alertas = pd.DataFrame(columns=colunas_alertas)
        df_alertas = df_alertas.reindex(columns=colunas_alertas)
        df_alertas.to_csv(alertas_path, index=False, encoding="utf-8")
        print(f"Alertas salvos em: {alertas_path} ({alertas_count} linhas)")
    else:
        print(f"Alertas gerados: {alertas_count} (sem persistencia).")

    if args.db:
        n_grade = 0
        n_evt = 0
        n_alt = 0
        for paciente_id, grupo in df_grade_norm.groupby("paciente_id", sort=True):
            n_grade += inserir_grade(args.db, grupo[["timestamp", "postura"]], paciente_id)

        if df_eventos_norm is not None:
            for paciente_id, grupo in df_eventos_norm.groupby("paciente_id", sort=True):
                n_evt += inserir_eventos(args.db, grupo.drop(columns="paciente_id"), paciente_id)

        n_alt = inserir_alertas(args.db, alertas) if alertas else 0

        db_path = Path(args.db)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch(exist_ok=True)
        print(f"Arquivo de banco preparado em: {db_path}")
        print(f"DB -> grade: {n_grade} | eventos: {n_evt} | alertas: {n_alt}")

    logger.info(
        "batch_concluido",
        pacientes=total_pacientes,
        eventos_salvos=args.eventos or "",
        alertas_salvos=args.alertas or "",
        alertas_gerados=alertas_count,
    )


def _create_async_client(base_url: str, transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, transport=transport, timeout=10.0)


def _count_events(path: Path, formato: str) -> int:
    if formato == "csv":
        with path.open("r", encoding="utf-8", newline="") as arquivo:
            reader = csv.reader(arquivo)
            total = sum(1 for _ in reader)
        return max(0, total - 1)
    total = 0
    with path.open("r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                total += 1
    return total


def _iter_events(args: argparse.Namespace) -> Iterable[dict]:
    caminho = Path(args.entrada)
    if args.formato == "csv":
        with caminho.open("r", encoding="utf-8", newline="") as arquivo:
            reader = csv.DictReader(arquivo)
            for linha in reader:
                yield _normalizar_evento(linha)
    else:
        with caminho.open("r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                linha = linha.strip()
                if not linha:
                    continue
                dados = json.loads(linha)
                yield _normalizar_evento(dados)


def _normalizar_evento(dados: Mapping[str, Any]) -> dict:
    def _obter(nome: str, *alternativos: str) -> str:
        for chave in (nome,) + alternativos:
            valor = dados.get(chave)
            if valor is not None and str(valor).strip():
                return str(valor).strip()
        raise ValueError(f"Campo obrigatorio ausente: {nome}")

    device_id = _obter("device_id", "DeviceId")
    paciente_id = _obter("paciente_id", "PacienteId")
    cama_id = _obter("cama_id", "CamaId")
    postura = _obter("postura", "Postura")

    confianca_raw = dados.get("confianca", dados.get("Confianca", config.conf_limiar))
    try:
        confianca = float(confianca_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Confianca invalida") from exc

    amostra_raw = dados.get("amostra_ms", dados.get("AmostraMs", 300000))
    try:
        amostra_ms = int(amostra_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("amostra_ms invalida") from exc

    ts_val = dados.get("ts_utc") or dados.get("timestamp") or dados.get("Timestamp")
    if ts_val is None:
        raise ValueError("timestamp ausente")
    ts = pd.to_datetime(ts_val, errors="coerce")
    if pd.isna(ts):
        raise ValueError("timestamp invalido")
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(None)
    ts_iso = ts.floor("s").strftime(ISO_FORMAT)

    evento = {
        "device_id": device_id,
        "paciente_id": paciente_id,
        "cama_id": cama_id,
        "postura": postura,
        "confianca": confianca,
        "amostra_ms": amostra_ms,
        "ts_utc": ts_iso,
    }
    if "pressao_pico" in dados:
        try:
            evento["pressao_pico"] = float(dados["pressao_pico"])
        except (TypeError, ValueError):
            pass
    return evento


def _percentil(valores: list[float], percentual: float) -> float:
    if not valores:
        return 0.0
    ordenado = sorted(valores)
    k = max(0, min(len(ordenado) - 1, int(round(percentual / 100 * (len(ordenado) - 1)))))
    return ordenado[k]


async def _enviar_evento(
    client: httpx.AsyncClient,
    endpoint: str,
    evento: dict,
    retries: int,
    backoff_ms: int,
) -> bool:
    tentativa = 0
    espera = max(backoff_ms, 1) / 1000.0
    while True:
        try:
            resposta = await client.post(endpoint, json=evento)
            if 200 <= resposta.status_code < 300:
                return True
        except httpx.HTTPError:
            pass
        tentativa += 1
        if tentativa > retries:
            return False
        await asyncio.sleep(espera)
        espera *= 2


async def run_stream(args: argparse.Namespace, *, transport: httpx.BaseTransport | None = None) -> None:
    if not args.entrada:
        raise ValueError("--entrada é obrigatorio no modo stream.")

    caminho = Path(args.entrada)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    total_previsto = _count_events(caminho, args.formato)
    client_candidate = _create_async_client(args.host, transport)
    client = await client_candidate if asyncio.iscoroutine(client_candidate) else client_candidate
    sucesso = 0
    falhas = 0
    duracoes_ms: list[float] = []

    logger.info(
        "stream_inicio",
        entrada=str(caminho),
        formato=args.formato,
        host=args.host,
        endpoint=args.endpoint,
        total_previsto=total_previsto,
    )

    try:
        for idx, evento in enumerate(_iter_events(args), start=1):
            if args.max_envios and idx > args.max_envios:
                break
            try:
                inicio = time.perf_counter()
                enviado = await _enviar_evento(
                    client,
                    args.endpoint,
                    evento,
                    args.retries,
                    args.retry_backoff_ms,
                )
                duracoes_ms.append((time.perf_counter() - inicio) * 1000.0)
            except ValueError:
                enviado = False
            if enviado:
                sucesso += 1
            else:
                falhas += 1
            progresso_total = total_previsto if total_previsto else idx
            print(
                f"Enviados: {sucesso}/{progresso_total} | Falhas: {falhas}",
                end="\r",
                file=sys.stdout,
            )
            if args.ritmo_ms > 0:
                await asyncio.sleep(args.ritmo_ms / 1000.0)
    finally:
        await client.aclose()

    print("\nRelatorio de envio:")
    print(f"  Sucesso: {sucesso}")
    print(f"  Falhas: {falhas}")
    perdas = falhas
    print(f"  Perdas: {perdas}")
    lat_p95 = _percentil(duracoes_ms, 95.0)
    print(f"  Latencia P95: {lat_p95:.2f} ms")

    resumo = {
        "sucesso": sucesso,
        "falhas": falhas,
        "perdas": perdas,
        "processados": sucesso + falhas,
        "lat_p95": lat_p95,
    }

    logger.info("stream_resumo", **resumo)
    return resumo


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    modo_operacao = args.modo or config.modo_operacao

    if modo_operacao == "batch":
        run_batch(args)
    else:
        asyncio.run(run_stream(args))


if __name__ == "__main__":
    main()
