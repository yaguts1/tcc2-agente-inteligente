"""Configuracao documentada precisa CHEGAR ao container.

Este defeito ja aconteceu duas vezes no projeto. O `docker-compose.yml` lista
as variaveis uma a uma (nao ha `env_file:`), entao qualquer variavel nova fica
de fora por padrao: quem preenchesse o `.env` acreditaria ter configurado algo
e o sistema seguiria com o default, em silencio — porque o default existe e
funciona.

Da primeira vez foram `UPP_DEVICE_TOKEN` e `UPP_AUDIT_KEY` (autenticacao dos
ESP32 e assinatura da trilha de auditoria, ambas desligadas sem que ninguem
percebesse). Corrigiram essas duas e as outras nove ficaram.

Ninguem vai lembrar de editar o compose ao criar a decima segunda. Este teste
lembra.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = RAIZ / "docker-compose.yml"
ENV_EXAMPLE = RAIZ / ".env.example"

# Variaveis do .env.example que sao do HOST e nao devem entrar no container.
# `BACKUP_DESTINO*` e `BACKUP_SSH_KEY` pertencem ao script de replicacao, que
# roda no host justamente para a chave SSH NAO ficar dentro do container.
SO_DO_HOST = {
    "DOMAIN",           # Caddy
    "BACKUP_DESTINO",
    "BACKUP_DESTINO_LABEL",
    "BACKUP_SSH_KEY",
    "COMPOSE_DIR",
    "BACKUP_SERVICO",
}


def _documentadas() -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))


def _lidas_pelo_codigo() -> set[str]:
    nomes: set[str] = set()
    for py in RAIZ.rglob("*.py"):
        partes = py.parts
        if "__pycache__" in partes or "node_modules" in partes or "tests" in partes:
            continue
        conteudo = py.read_text(encoding="utf-8", errors="replace")
        nomes |= set(re.findall(r"getenv\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']", conteudo))
    return nomes


def _repassadas_ao_app() -> set[str]:
    """Nomes que aparecem na secao `environment:` do servico `app`."""
    texto = COMPOSE.read_text(encoding="utf-8")
    trecho = texto.split("caddy:")[0]  # so o servico da aplicacao
    return set(re.findall(r"^\s*-\s*([A-Z][A-Z0-9_]+)=", trecho, re.M))


def test_variavel_documentada_e_lida_chega_ao_container():
    esperadas = (_documentadas() & _lidas_pelo_codigo()) - SO_DO_HOST
    faltando = sorted(esperadas - _repassadas_ao_app())

    assert not faltando, (
        "Estas variaveis estao no .env.example e sao lidas pelo codigo, mas nao "
        "sao repassadas ao container em docker-compose.yml. Quem preencher o "
        ".env vai achar que configurou e o sistema seguira no default, calado:\n  "
        + "\n  ".join(faltando)
    )


def test_o_teste_enxerga_as_variaveis(monkeypatch):
    """Guarda do proprio teste: se as extracoes voltarem vazias, ele passaria
    sempre e nao protegeria nada."""
    assert len(_documentadas()) > 5
    assert len(_lidas_pelo_codigo()) > 5
    assert len(_repassadas_ao_app()) > 5


@pytest.mark.parametrize(
    "variavel, default_no_codigo",
    [
        ("UPP_ADMIN_USER", "admin"),
        ("PROCESSADOR_ESTRATEGIA", "estado_em_memoria"),
    ],
)
def test_variavel_com_default_real_nao_e_repassada_vazia(variavel, default_no_codigo):
    """`${VAR:-}` manda string VAZIA, que nao e o mesmo que ausente.

    Para quem le com `os.getenv(VAR, "algo")`, a variavel definida como ""
    substitui o default por "" — o default deixa de valer. Repassar assim seria
    trocar um bug (config ignorada) por outro (default destruido).
    """
    texto = COMPOSE.read_text(encoding="utf-8")
    linha = next(
        (linha for linha in texto.splitlines() if linha.strip().startswith(f"- {variavel}=")),
        None,
    )
    assert linha is not None, f"{variavel} nao esta no compose"
    assert f":-{default_no_codigo}}}" in linha, (
        f"{variavel} precisa carregar o default real ({default_no_codigo}) no compose; "
        f"linha atual: {linha.strip()}"
    )
