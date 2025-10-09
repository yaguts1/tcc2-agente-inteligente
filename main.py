"""CLI para gerar simulacoes de posturas e alertas de imobilidade."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import pandas as pd

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


def parse_args() -> argparse.Namespace:
    """Configura o parser de argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Gera simulacao de posturas (grade) e, opcionalmente, eventos e alertas.",
    )
    parser.add_argument(
        "--horas",
        type=int,
        default=24,
        help="Duracao da simulacao em horas.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semente para reproducibilidade.",
    )
    parser.add_argument(
        "--passo",
        type=int,
        default=5,
        help="Passo (minutos) entre amostras na grade.",
    )
    parser.add_argument(
        "--pacientes",
        type=int,
        default=1,
        help="Numero de pacientes simulados (ignorado se --pacientes-ids for usado).",
    )
    parser.add_argument(
        "--pacientes-ids",
        type=str,
        default="",
        help="IDs dos pacientes separados por virgula (ex.: P1,P2,P3).",
    )
    parser.add_argument(
        "--saida",
        type=str,
        default="dados_simulados/sessao.csv",
        help="CSV de saida da grade.",
    )
    parser.add_argument(
        "--eventos",
        type=str,
        default="",
        help="(Opcional) CSV para salvar eventos brutos.",
    )
    parser.add_argument(
        "--perfil",
        type=str.lower,
        choices=("baixo", "medio", "alto"),
        default="medio",
        help="Perfil de risco do paciente para os alertas de imobilidade.",
    )
    parser.add_argument(
        "--alertas",
        type=str,
        default="",
        help="(Opcional) CSV para salvar alertas gerados.",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="",
        help="(Opcional) caminho do banco de dados; cria o arquivo se nao existir.",
    )
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()

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
    eventos_count = 0
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
        eventos_count = len(df_eventos_norm)
        print(f"Eventos salvos em: {eventos_path} ({eventos_count} linhas)")
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

    n_grade = 0
    n_evt = 0
    n_alt = 0
    if args.db:
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


if __name__ == "__main__":
    main()
