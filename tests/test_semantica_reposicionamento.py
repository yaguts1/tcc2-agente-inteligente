"""O horario certo, na hora certa.

Dois defeitos que faziam a tela informar um vencimento errado para o
reposicionamento — o numero que a equipe usa para decidir quando virar o
paciente.

1. `alerta.inicio` NAO e o inicio da imobilidade. O motor grava nele o instante
   em que a janela ESTOUROU (nucleo/decisor.py: `run_inicio + janela`). O
   servico somava a janela DE NOVO, jogando o vencimento para o futuro: existia
   um alerta ABERTO informando que o reposicionamento so venceria dali a uma
   janela inteira.

2. Os timestamps saiam sem offset. `new Date("2026-07-25T13:44:47")` no browser
   interpreta a string como hora LOCAL, entao para um usuario no Brasil (UTC-3)
   tudo aparecia 3h adiantado.

Somados, um reposicionamento vencido as 09:00 aparecia como 13:00.
"""

from datetime import datetime, timedelta

import pytest

from interface.dao import inserir_alertas
from interface.tempo import agora_utc_naive


@pytest.fixture
def servico(app_isolado, monkeypatch):
    import interface.services.alerts_service as mod

    monkeypatch.setattr(mod, "DB_PATH", app_isolado.db_path)
    return mod


async def _listar(servico):
    await servico.api_cache.clear()
    return await servico.listar_alertas_frontend(horas=24)


def _gravar_alerta(db, *, inicio, status, janela_min=60, fim=None):
    inserir_alertas(db, [{
        "paciente_id": "PAC-SEM",
        "inicio": inicio.strftime("%Y-%m-%dT%H:%M:%S"),
        "fim": fim.strftime("%Y-%m-%dT%H:%M:%S") if fim else None,
        "tipo": "imobilidade",
        "perfil": "alto",
        "janela_min": janela_min,
        "status": status,
        "duracao_min": None,
    }])


@pytest.mark.asyncio
async def test_alerta_aberto_vence_agora_e_nao_no_futuro(app_isolado, servico):
    """Um alerta aberto significa que o paciente JA precisa ser virado."""
    inicio = agora_utc_naive() - timedelta(minutes=30)
    _gravar_alerta(app_isolado.db_path, inicio=inicio, status="aberto")

    alerta = (await _listar(servico))[0]
    vencimento = datetime.fromisoformat(alerta["nextRepositioning"])
    agora = datetime.now(vencimento.tzinfo)

    assert vencimento <= agora, (
        f"alerta ABERTO com vencimento no futuro ({vencimento}): a tela mostraria "
        "'ainda ha tempo' para um paciente que ja passou da hora"
    )


@pytest.mark.asyncio
async def test_alerta_concluido_projeta_o_proximo_a_partir_do_fim(app_isolado, servico):
    """Concluido = paciente virado. O proximo vence uma janela depois DISSO."""
    fim = agora_utc_naive() - timedelta(minutes=10)
    inicio = fim - timedelta(minutes=30)
    _gravar_alerta(app_isolado.db_path, inicio=inicio, status="fechado", fim=fim, janela_min=60)

    alerta = (await _listar(servico))[0]
    vencimento = datetime.fromisoformat(alerta["nextRepositioning"]).replace(tzinfo=None)

    esperado = fim + timedelta(minutes=60)
    assert abs((vencimento - esperado).total_seconds()) < 2, (
        f"esperava {esperado} (fim + janela), veio {vencimento}"
    )


@pytest.mark.asyncio
async def test_timestamps_saem_com_offset(app_isolado, servico):
    """Sem offset o browser le como hora local e exibe 3h adiantado no Brasil."""
    _gravar_alerta(
        app_isolado.db_path, inicio=agora_utc_naive() - timedelta(minutes=5), status="aberto"
    )

    alerta = (await _listar(servico))[0]
    for campo in ("nextRepositioning", "lastRepositioning"):
        valor = alerta[campo]
        assert datetime.fromisoformat(valor).tzinfo is not None, (
            f"{campo} veio sem offset: {valor}"
        )


@pytest.mark.asyncio
async def test_offset_preserva_o_instante(app_isolado, servico):
    """A conversao nao pode DESLOCAR o instante — so explicita-lo."""
    inicio = agora_utc_naive() - timedelta(minutes=45)
    _gravar_alerta(app_isolado.db_path, inicio=inicio, status="aberto")

    alerta = (await _listar(servico))[0]
    devolvido = datetime.fromisoformat(alerta["nextRepositioning"]).replace(tzinfo=None)

    assert abs((devolvido - inicio).total_seconds()) < 2, (
        f"o instante mudou: gravado {inicio}, devolvido {devolvido}"
    )


@pytest.mark.parametrize("perfil,nivel", [("alto", "high"), ("medio", "medium"), ("baixo", "low")])
def test_intervalo_exibido_bate_com_a_janela_do_motor(perfil, nivel):
    """Uma unica fonte de verdade para o intervalo de reposicionamento.

    Havia dois mapas divergentes: o motor usava 60/90/120 min e a tela de
    pacientes exibia 2/3/4 h — o DOBRO. A tela informava "reposicionar a cada
    2h" para um paciente de alto risco enquanto o sistema alertava a cada 1h.
    Num parametro clinico, duas fontes significam que pelo menos uma esta
    errada, e ninguem consegue saber qual olhando a tela.
    """
    from configuracao import carregar_configuracao
    from interface.services.paciente_service import intervalo_horas

    minutos_do_motor = carregar_configuracao().janela_por_perfil[perfil]
    assert intervalo_horas(perfil) == round(minutos_do_motor / 60, 2), (
        f"o intervalo exibido para {nivel} divergiu da janela do motor "
        f"({minutos_do_motor} min)"
    )
