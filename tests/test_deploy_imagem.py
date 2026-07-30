"""A imagem que o CI testa e a imagem que roda na VM.

O deploy era `git pull && docker compose up --build` NA VM. Duas consequencias,
e a segunda e a grave:

  * a imagem testada pelo CI nunca era a que rodava. A VM reconstruia a dela,
    com outra data, outro cache de camadas e outras versoes resolvidas de
    dependencia nao fixada. O CI verde nao dizia nada sobre o que estava no ar;

  * o build acontecia DEPOIS de derrubar o servico. Um `pip install` que
    falhasse por rede, ou uma dependencia que tivesse publicado versao nova
    incompativel, quebrava a producao no meio da atualizacao — e o caminho de
    volta era outro build, com o mesmo risco.

Agora o CI publica no GHCR a MESMA imagem que passou pelo smoke test, com tag
imutavel por SHA de commit, e a VM so puxa.

Os testes aqui leem o workflow e o compose porque essa configuracao nao tem
como ser exercitada localmente: a falha so apareceria num deploy real, que e
justamente quando ela custa mais caro.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml e dependencia deste teste")

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = RAIZ / "docker-compose.yml"


def _carregar(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))



def _workflow() -> dict:
    return _carregar(RAIZ / ".github" / "workflows" / "python-tests.yml")


def test_compose_aceita_imagem_pronta_sem_perder_o_build_local():
    """`UPP_IMAGE` e o que permite a VM RODAR a imagem que o CI testou, em vez
    de reconstruir a dela.

    O default preserva o fluxo local: sem a variavel, `build: .` continua
    valendo e `docker compose up --build` funciona como sempre.
    """
    compose = _carregar(COMPOSE)
    app = compose["services"]["app"]
    assert "UPP_IMAGE" in str(app.get("image", "")), (
        "o compose voltou a ter imagem fixa: a VM nao consegue apontar para a "
        "imagem publicada pelo CI"
    )
    assert "build" in app, "o build local sumiu; desenvolvimento deixaria de funcionar"


def test_o_ci_publica_a_mesma_imagem_que_testou():
    """O ponto inteiro de 3.5.

    Se o passo de publicacao reconstruisse a imagem (`docker build` de novo,
    ou `build-push-action` num job separado), o defeito voltaria em forma mais
    sutil: o artefato publicado nao seria o que passou pelo smoke test, e a
    unica evidencia disso estaria no YAML.
    """
    passos = _workflow()["jobs"]["docker-build"]["steps"]
    nomes = [p.get("name", "") for p in passos]

    i_smoke = next(i for i, n in enumerate(nomes) if "Smoke test" in n)
    i_push = next(i for i, n in enumerate(nomes) if "Publicar" in n)
    assert i_push > i_smoke, "a publicacao acontece ANTES do smoke test"

    publicacao = passos[i_push]["run"]
    assert "docker tag upp-app:ci" in publicacao, (
        "a publicacao nao esta re-etiquetando a imagem do smoke test"
    )
    assert "docker build" not in publicacao, (
        "a publicacao reconstroi a imagem: o que vai para o registry nao e o "
        "que foi testado"
    )


def test_a_tag_publicada_e_imutavel():
    """Tag por SHA de commit. `:main` sozinho e alvo movel — "qual main?" nao
    tem resposta depois do proximo push, e e a ambiguidade que a publicacao com
    tag imutavel existe para eliminar."""
    passos = _workflow()["jobs"]["docker-build"]["steps"]
    publicacao = next(p for p in passos if "Publicar" in p.get("name", ""))["run"]
    assert "sha-${GITHUB_SHA::12}" in publicacao
    assert "docker push \"$REPO:$SHA\"" in publicacao


def test_branch_de_feature_nao_publica():
    """Publicar de qualquer branch encheria o registry de imagens sem
    procedencia e tornaria `:main` mentiroso."""
    passos = _workflow()["jobs"]["docker-build"]["steps"]
    for passo in passos:
        if "Publicar" in passo.get("name", "") or "Autenticar" in passo.get("name", ""):
            condicao = passo.get("if", "")
            assert "refs/heads/main" in condicao, f"{passo['name']} publica de qualquer branch"
