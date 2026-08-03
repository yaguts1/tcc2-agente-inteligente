"""O estado do filtro precisa se comportar igual nos dois backends.

`quality/filtro.py` guardava dedup e buffer de reordenação em dicionários de
módulo. Funciona com um processo; com uma réplica a mais, o dedup vira
desperdício (a PK da grade recusa a duplicata) mas o **buffer perde correção** —
cada réplica reordena metade das amostras contra a própria janela, e o buffer
existe justamente para corrigir chegada fora de ordem.

O QUE ESTES TESTES PROTEGEM
---------------------------
Não é o Redis: é a EQUIVALÊNCIA. Um backend que se comporta quase igual é pior
que nenhum, porque o defeito só aparece na instalação que já escalou — e as duas
implementações usam estruturas completamente diferentes (heap de tuplas vs.
sorted set com membro serializado).

Por isso quase todo caso roda contra os dois, pela mesma bateria.

Os casos de Redis são pulados quando não há servidor: `docker compose up -d
redis`, ou `UPP_REDIS_TESTE=redis://localhost:6379/15`.
"""

from __future__ import annotations

import os

import pytest

from quality.estado import LIMITE_DEDUP, EstadoEmMemoria, EstadoNoRedis, criar_estado

# Banco 15 por padrão: separado do 0 que a aplicação usa, para uma suíte
# distraída nunca apagar o estado de uma instalação em execução.
URL_REDIS = os.getenv("UPP_REDIS_TESTE", "redis://localhost:6379/15")


def _redis_disponivel() -> bool:
    try:
        import redis

        redis.from_url(URL_REDIS, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


@pytest.fixture(params=["memoria", "redis"])
def estado(request):
    if request.param == "memoria":
        yield EstadoEmMemoria()
        return
    if not _redis_disponivel():
        pytest.skip(f"sem Redis em {URL_REDIS} (docker compose up -d redis)")
    e = EstadoNoRedis(URL_REDIS)
    e.limpar()
    try:
        yield e
    finally:
        e.limpar()


def _evt(ts: str, **extra) -> dict:
    return {"ts_utc": ts, "postura": "supino", **extra}


class TestDeduplicacao:
    def test_chave_nova_nao_foi_vista(self, estado):
        assert estado.ja_visto("DEV", "a") is False

    def test_chave_registrada_passa_a_ser_vista(self, estado):
        estado.registrar("DEV", "a")
        assert estado.ja_visto("DEV", "a") is True

    def test_dedup_e_por_dispositivo(self, estado):
        """Dois ESP32 podem legitimamente reportar a mesma postura no mesmo
        instante — são pacientes diferentes. Compartilhar o espaço de chaves
        faria o segundo aparelho perder amostra."""
        estado.registrar("DEV-A", "supino:2026-01-01T00:00:00")
        assert estado.ja_visto("DEV-B", "supino:2026-01-01T00:00:00") is False

    def test_nao_cresce_sem_teto(self, estado):
        """Em processo o reinício limpava sozinho; num armazenamento
        compartilhado, crescer sem teto é vazamento permanente."""
        for i in range(LIMITE_DEDUP + 200):
            estado.registrar("DEV", f"k{i}")
        # A poda é aproximada de propósito (esquecer chave antiga é inofensivo:
        # a PK da grade recusa a duplicata). O que se afirma é o TETO.
        assert estado.ja_visto("DEV", f"k{LIMITE_DEDUP + 199}") is True


class TestBufferDeReordenacao:
    def test_libera_so_o_que_esta_abaixo_do_corte(self, estado):
        estado.guardar("DEV", 100.0, _evt("cedo"))
        estado.guardar("DEV", 300.0, _evt("tarde"))

        liberados = estado.liberar_ate("DEV", 200.0)

        assert [e["ts_utc"] for e in liberados] == ["cedo"]
        assert estado.pendentes("DEV") == 1

    def test_liberacao_remove_do_buffer(self, estado):
        """Se não removesse, a mesma amostra seria entregue ao motor a cada
        chamada seguinte — e o motor a contaria de novo."""
        estado.guardar("DEV", 100.0, _evt("a"))

        assert len(estado.liberar_ate("DEV", 200.0)) == 1
        assert estado.liberar_ate("DEV", 200.0) == []
        assert estado.pendentes("DEV") == 0

    def test_libera_em_ordem_de_instante_mesmo_chegando_fora_de_ordem(self, estado):
        """É a razão de o buffer existir. Chegou tarde-cedo-meio; tem que sair
        cedo-meio-tarde."""
        estado.guardar("DEV", 300.0, _evt("tarde"))
        estado.guardar("DEV", 100.0, _evt("cedo"))
        estado.guardar("DEV", 200.0, _evt("meio"))

        liberados = estado.liberar_ate("DEV", 400.0)

        assert [e["ts_utc"] for e in liberados] == ["cedo", "meio", "tarde"]

    def test_amostras_identicas_no_mesmo_instante_nao_se_engolem(self, estado):
        """O ZSET do Redis é um CONJUNTO: sem desempate no membro, duas amostras
        de conteúdo igual e mesmo score viram uma só — e a segunda some sem
        deixar rastro."""
        estado.guardar("DEV", 100.0, _evt("igual"))
        estado.guardar("DEV", 100.0, _evt("igual"))

        assert estado.pendentes("DEV") == 2
        assert len(estado.liberar_ate("DEV", 100.0)) == 2

    def test_buffer_e_por_dispositivo(self, estado):
        estado.guardar("DEV-A", 100.0, _evt("a"))
        estado.guardar("DEV-B", 100.0, _evt("b"))

        assert [e["ts_utc"] for e in estado.liberar_ate("DEV-A", 200.0)] == ["a"]
        assert estado.pendentes("DEV-B") == 1, "drenar um dispositivo não pode tocar no outro"

    def test_drenar_esvazia_e_devolve_tudo(self, estado):
        estado.guardar("DEV", 300.0, _evt("tarde"))
        estado.guardar("DEV", 100.0, _evt("cedo"))

        drenados = estado.drenar("DEV")

        assert len(drenados) == 2
        assert estado.pendentes("DEV") == 0

    def test_dispositivos_lista_quem_tem_pendencia(self, estado):
        estado.guardar("DEV-X", 100.0, _evt("x"))

        assert "DEV-X" in estado.dispositivos()

    def test_limpar_apaga_dedup_e_buffer(self, estado):
        """Uso operacional: reenviar as MESMAS amostras (replay repetido,
        demonstração) era descartado como duplicata — com ACK, e sem nada na
        tela. A única saída era reiniciar o processo."""
        estado.registrar("DEV", "chave")
        estado.guardar("DEV", 100.0, _evt("a"))

        estado.limpar()

        assert estado.ja_visto("DEV", "chave") is False
        assert estado.pendentes("DEV") == 0


class TestEscolhaDoBackend:
    def test_sem_url_usa_memoria(self):
        """Instalação de uma instância não deve pagar rede nem depender de outro
        serviço — o comportamento histórico continua sendo o padrão."""
        assert isinstance(criar_estado(None), EstadoEmMemoria)
        assert isinstance(criar_estado(""), EstadoEmMemoria)

    def test_redis_inalcancavel_cai_para_memoria(self):
        """Uma ala parar de receber amostra porque o Redis reiniciou seria trocar
        um problema de escala por um de disponibilidade."""
        assert isinstance(criar_estado("redis://127.0.0.1:6399/0"), EstadoEmMemoria)

    def test_com_url_valida_usa_redis(self):
        if not _redis_disponivel():
            pytest.skip("sem Redis")
        assert isinstance(criar_estado(URL_REDIS), EstadoNoRedis)


class TestACiPrecisaExercitarEsteCaminho:
    """Guarda contra o pulo silencioso voltar.

    Os testes acima pulam sem servidor — o que é certo para uma bancada, e era
    catastrófico para a CI: o `docker-compose.yml` LIGA Redis por padrão
    (`${REDIS_URL:-redis://redis:6379/0}`, e `:-` dispara também com string
    vazia), então o caminho que roda em produção era exatamente o que o build
    nunca exercitava. Ficava verde.

    Foi assim que `_RedisStateStore.save()` passou meses sem o parâmetro `conn=`:
    TypeError em toda gravação de estado, nenhum alerta emitido, e o dispositivo
    recebendo ACK.
    """

    def test_workflow_declara_o_servico_redis(self):
        from pathlib import Path

        import yaml

        w = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / ".github/workflows/python-tests.yml").read_text(
                encoding="utf-8"
            )
        )
        servicos = w["jobs"]["test"].get("services", {})

        assert "redis" in servicos, (
            "o job `test` não declara `services: redis` — sem isso os testes de "
            "paridade pulam sempre e o backend que roda em produção fica sem cobertura."
        )

    def test_gate_de_cobertura_inclui_quality(self):
        from pathlib import Path

        texto = (
            Path(__file__).resolve().parents[1] / ".github/workflows/python-tests.yml"
        ).read_text(encoding="utf-8")

        assert "--cov=quality" in texto, (
            "`quality/` está fora do gate. É onde vivem o dedup e o buffer de "
            "reordenação — o componente que o ROADMAP classifica como caso de "
            "CORREÇÃO, não de eficiência."
        )
