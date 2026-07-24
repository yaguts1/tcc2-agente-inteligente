"""CLI: python -m migrations upgrade [--db-path caminho]"""
from __future__ import annotations

import argparse
import os
import sys

from migrations.runner import upgrade, versao_schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="migrations")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_upgrade = sub.add_parser("upgrade", help="Aplica migrations pendentes")
    p_upgrade.add_argument("--db-path", default=None)

    p_status = sub.add_parser("status", help="Mostra a versao atual do schema")
    p_status.add_argument("--db-path", default=None)

    args = parser.parse_args(argv)
    db_path = args.db_path or os.getenv("UPP_DB_PATH", "dados.db")

    if args.comando == "upgrade":
        versao = upgrade(db_path)
        print(f"Schema em {db_path!r} atualizado para a versao {versao}.")
    elif args.comando == "status":
        versao = versao_schema(db_path)
        print(f"Schema em {db_path!r} esta na versao {versao}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
