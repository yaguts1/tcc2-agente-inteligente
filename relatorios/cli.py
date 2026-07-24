from __future__ import annotations
import argparse
from relatorios.relatorios import exportar_csv_alertas, exportar_pdf_resumo

def main() -> None:
    parser = argparse.ArgumentParser(prog="relatorios", description="CLI de relatórios de alertas")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_csv = sub.add_parser("csv", help="exporta CSV de alertas")
    p_csv.add_argument("--db", default="dados.db")
    p_csv.add_argument("--dest", required=True)
    p_csv.add_argument("--horas", type=int, default=24)

    p_pdf = sub.add_parser("pdf", help="exporta PDF resumo de alertas")
    p_pdf.add_argument("--db", default="dados.db")
    p_pdf.add_argument("--dest", required=True)
    p_pdf.add_argument("--horas", type=int, default=24)

    args = parser.parse_args()

    if args.cmd == "csv":
        total = exportar_csv_alertas(args.db, args.dest, horas=args.horas)
        print(f"CSV: {args.dest} | total={total}")
    elif args.cmd == "pdf":
        exportar_pdf_resumo(args.db, args.dest, horas=args.horas)
        print(f"PDF: {args.dest} | OK")

if __name__ == "__main__":
    main()
