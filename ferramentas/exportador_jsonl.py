"""Conversores para exportar grade de posturas em formato JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

ISO_FMT = "%Y-%m-%dT%H:%M:%S"

REQUIRED_KEYS = ("device_id", "paciente_id", "cama_id", "postura", "confianca", "amostra_ms", "ts_utc")
OPTIONAL_KEYS = ("pressao_pico",)
FALLBACKS = {
    "ts_utc": ("timestamp", "ts"),
}


class ExportacaoInvalidaError(ValueError):
    """Erro disparado quando algum registro nao atende aos requisitos do schema."""


def _resolver_ts(valor: object) -> str:
    if valor is None:
        raise ExportacaoInvalidaError("Campo 'ts_utc' obrigatorio.")

    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).strip()
        if not texto:
            raise ExportacaoInvalidaError("Campo 'ts_utc' nao pode ser vazio.")
        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(texto)
        except ValueError as exc:
            raise ExportacaoInvalidaError(f"Timestamp invalido: {valor!r}") from exc

    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    dt = dt.replace(tzinfo=None, microsecond=0)
    return dt.strftime(ISO_FMT)


def _resolver_float(nome: str, valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ExportacaoInvalidaError(f"Campo '{nome}' deve ser numerico.") from exc
    return numero


def _resolver_confianca(valor: object) -> float:
    numero = _resolver_float("confianca", valor)
    if not (0.0 <= numero <= 1.0):
        raise ExportacaoInvalidaError("Campo 'confianca' deve estar entre 0.0 e 1.0.")
    return numero


def _resolver_amostra_ms(valor: object) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ExportacaoInvalidaError("Campo 'amostra_ms' deve ser inteiro.") from exc
    if numero <= 0:
        raise ExportacaoInvalidaError("Campo 'amostra_ms' deve ser positivo.")
    return numero


def _normalizar_chave(registro: MutableMapping[str, object], chave: str) -> object:
    if chave in registro and registro[chave] not in ("", None):
        return registro[chave]
    for alternativo in FALLBACKS.get(chave, ()):
        if alternativo in registro and registro[alternativo] not in ("", None):
            return registro[alternativo]
    raise ExportacaoInvalidaError(f"Campo '{chave}' obrigatorio nao encontrado.")


def _preparar_registro(raw: Mapping[str, object]) -> dict:
    registro = dict(raw)

    preparado: dict[str, object] = {}
    for chave in REQUIRED_KEYS:
        if chave == "ts_utc":
            preparado[chave] = _resolver_ts(_normalizar_chave(registro, chave))
        elif chave == "confianca":
            preparado[chave] = _resolver_confianca(_normalizar_chave(registro, chave))
        elif chave == "amostra_ms":
            preparado[chave] = _resolver_amostra_ms(_normalizar_chave(registro, chave))
        else:
            valor = _normalizar_chave(registro, chave)
            texto = str(valor).strip()
            if not texto:
                raise ExportacaoInvalidaError(f"Campo '{chave}' nao pode ser vazio.")
            preparado[chave] = texto

    for opcional in OPTIONAL_KEYS:
        if opcional in registro and registro[opcional] not in ("", None):
            preparado[opcional] = _resolver_float(opcional, registro[opcional])

    return preparado


def exportar_grade_para_jsonl(
    caminho_saida: str | Path,
    grade_iter: Iterable[Mapping[str, object]],
    *,
    defaults: Mapping[str, object] | None = None,
) -> int:
    """Exporta iteravel de amostras para arquivo JSONL.

    Args:
        caminho_saida: destino do arquivo (será sobrescrito).
        grade_iter: iteravel com registros contendo o schema esperado.
        defaults: valores padrao aplicados antes de validar cada registro.

    Returns:
        Numero de registros exportados.
    """
    destino_path = Path(caminho_saida)
    destino_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    defaults = dict(defaults or {})

    with destino_path.open("w", encoding="utf-8", newline="\n") as arquivo:
        for index, linha in enumerate(grade_iter, start=1):
            if not isinstance(linha, Mapping):
                raise TypeError(f"Registro #{index} precisa ser um mapeamento, recebido {type(linha)!r}")
            combinado = {**defaults, **linha}
            preparado = _preparar_registro(combinado)
            arquivo.write(json.dumps(preparado, ensure_ascii=False))
            arquivo.write("\n")
            total += 1

    return total


def _iterar_csv(caminho: Path) -> Iterable[Mapping[str, object]]:
    with caminho.open("r", encoding="utf-8", newline="") as origem:
        leitor = csv.DictReader(origem)
        if leitor.fieldnames is None:
            raise ExportacaoInvalidaError("Arquivo CSV sem cabecalho.")
        for linha in leitor:
            yield linha


def _montar_defaults(args: argparse.Namespace) -> dict[str, object]:
    defaults: dict[str, object] = {}
    if args.device_id is not None:
        defaults["device_id"] = args.device_id
    if args.cama_id is not None:
        defaults["cama_id"] = args.cama_id
    if args.confianca is not None:
        defaults["confianca"] = args.confianca
    if args.amostra_ms is not None:
        defaults["amostra_ms"] = args.amostra_ms
    return defaults


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Converte uma grade CSV em JSONL pronto para transmissao.",
    )
    parser.add_argument(
        "--entrada",
        required=True,
        help="Arquivo CSV de entrada (grade).",
    )
    parser.add_argument(
        "--saida",
        required=True,
        help="Arquivo JSONL de saida.",
    )
    parser.add_argument(
        "--device-id",
        default=None,
        help="Sobrescreve o campo device_id caso ausente na grade.",
    )
    parser.add_argument(
        "--cama-id",
        default=None,
        help="Sobrescreve o campo cama_id caso ausente na grade.",
    )
    parser.add_argument(
        "--confianca",
        type=float,
        default=None,
        help="Valor padrao para confianca quando ausente (0.0-1.0).",
    )
    parser.add_argument(
        "--amostra-ms",
        type=int,
        default=None,
        help="Valor padrao para amostra_ms quando ausente.",
    )

    args = parser.parse_args(args=argv)

    entrada = Path(args.entrada)
    if not entrada.exists():
        raise FileNotFoundError(f"Arquivo de entrada nao encontrado: {entrada}")

    defaults = _montar_defaults(args)
    total = exportar_grade_para_jsonl(Path(args.saida), _iterar_csv(entrada), defaults=defaults)
    print(f"{total} registros exportados para {args.saida}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
