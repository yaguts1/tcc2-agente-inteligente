"""Gera o par de chaves VAPID que o Web Push exige.

Sem elas, `servicos/push.py` fica inerte e avisa no boot — nenhuma notificacao
sobrevive a aba fechada.

    python -m scripts.gerar_chaves_vapid

Cole a saida no `.env` da instalacao. AS CHAVES SAO POR INSTALACAO, nao por
ambiente: trocar a privada invalida todas as inscricoes existentes, e cada
aparelho precisa se inscrever de novo — o que ninguem faz, porque a tela nao
avisa que parou de receber. Gere uma vez e guarde.
"""
from __future__ import annotations

import base64


def main() -> None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        raise SystemExit(
            "Falta `cryptography` (vem junto com pywebpush): pip install pywebpush"
        ) from None

    chave = ec.generate_private_key(ec.SECP256R1())

    privada = base64.urlsafe_b64encode(
        chave.private_numbers().private_value.to_bytes(32, "big")
    ).rstrip(b"=").decode()

    publica = base64.urlsafe_b64encode(
        chave.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    ).rstrip(b"=").decode()

    print("# Cole no .env da instalacao. Gere UMA VEZ e guarde:")
    print("# trocar a privada invalida todas as inscricoes, e cada aparelho")
    print("# precisa se inscrever de novo — sem que a tela avise.")
    print(f"VAPID_PUBLIC_KEY={publica}")
    print(f"VAPID_PRIVATE_KEY={privada}")
    print("VAPID_SUBJECT=mailto:ti@seuhospital.com.br")


if __name__ == "__main__":
    main()
