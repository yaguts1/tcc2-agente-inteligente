# main.py
import argparse
from pathlib import Path
import pandas as pd

from dados_simulados.gerador import (
    gerar_sessao_simulada,
    gerar_eventos_sessao,   # novo
    PerfilPaciente
)

def parse_args():
    p = argparse.ArgumentParser(description="Gera simulação de posturas (grade) e, opcionalmente, eventos.")
    p.add_argument("--horas", type=int, default=24, help="Duração da simulação em horas.")
    p.add_argument("--seed", type=int, default=42, help="Semente para reprodutibilidade.")
    p.add_argument("--passo", type=int, default=5, help="Passo (minutos) entre amostras na grade.")
    p.add_argument("--saida", type=str, default="dados_simulados/sessao.csv", help="CSV de saída (grade).")
    p.add_argument("--eventos", type=str, default="", help="(Opcional) CSV para salvar eventos brutos.")
    # flags futuras (ex.: limites por paciente). Deixei PerfilPaciente plugável sem CLI para simplificar.
    return p.parse_args()

def main():
    args = parse_args()

    # Gera grade regular (timestamp, postura)
    df_grade = gerar_sessao_simulada(
        duracao_horas=args.horas,
        seed=args.seed,
        passo_min=args.passo,
        perfil=PerfilPaciente(),  # padrão; no futuro podemos expor no CLI
    )

    # Salva grade
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    df_grade.to_csv(saida, index=False, encoding="utf-8")
    print(f"✅ Grade salva em: {saida} ({len(df_grade)} linhas)")

    # (Opcional) salvar eventos brutos
    if args.eventos:
        df_ev = gerar_eventos_sessao(
            duracao_horas=args.horas,
            seed=args.seed,
            perfil=PerfilPaciente(),
        )
        eventos_path = Path(args.eventos)
        eventos_path.parent.mkdir(parents=True, exist_ok=True)
        # Converte datetime para ISO antes de salvar
        df_ev = df_ev.copy()
        for col in ("timestamp", "inicio", "fim"):
            df_ev[col] = pd.to_datetime(df_ev[col]).dt.strftime("%Y-%m-%dT%H:%M:%S")
        df_ev.to_csv(eventos_path, index=False, encoding="utf-8")
        print(f"📝 Eventos salvos em: {eventos_path} ({len(df_ev)} blocos)")

if __name__ == "__main__":
    main()
