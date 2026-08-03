"""O store Redis do motor precisa aceitar as mesmas chamadas que o SQLite.

`_RedisStateStore` viveu marcado `# pragma: no cover - dependencia nao
exercitada em testes`. Enquanto ninguém configurava `REDIS_URL`, isso era
invisível. Quando o Redis entrou, apareceu: `save()` ganhou `conn=` na versão
SQLite — para entrar na MESMA transação da gravação da amostra — e a versão
Redis nunca acompanhou.

O modo de falha era o pior possível: `TypeError` em toda gravação de estado,
então nenhum alerta era emitido, as amostras caíam no caminho de evento órfão, e
**o dispositivo recebia ACK**. Do lado do ESP32 o replay terminava com sucesso;
do lado da tela, nada. Levou uma sessão inteira de investigação — o sintoma
aparecia como "Timestamps devem estar em ordem crescente", que aponta para o
lugar errado.

Estes testes são de PARIDADE DE INTERFACE: se um store ganha um parâmetro, o
outro tem que aceitar (ou ignorar explicitamente).
"""

from __future__ import annotations

import inspect
import os

import pytest

from servicos.processamento_incremental import _RedisStateStore, _SQLiteStateStore

URL_REDIS = os.getenv("UPP_REDIS_TESTE", "redis://localhost:6379/15")

METODOS = ("load", "save", "delete", "clear")


def _redis_disponivel() -> bool:
    try:
        import redis

        redis.from_url(URL_REDIS, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


class TestParidadeDeAssinatura:
    """Não precisa de Redis: compara as assinaturas.

    É o teste que teria pego o defeito no dia em que `conn=` entrou no SQLite —
    sem servidor, sem container, em milissegundos.
    """

    @pytest.mark.parametrize("metodo", METODOS)
    def test_redis_aceita_o_que_o_sqlite_aceita(self, metodo):
        sqlite_sig = inspect.signature(getattr(_SQLiteStateStore, metodo))
        redis_sig = inspect.signature(getattr(_RedisStateStore, metodo))

        faltando = set(sqlite_sig.parameters) - set(redis_sig.parameters)

        assert not faltando, (
            f"_RedisStateStore.{metodo}() não aceita {sorted(faltando)}, que "
            f"_SQLiteStateStore.{metodo}() aceita. Chamador passa por nome — "
            "isto vira TypeError só quando REDIS_URL estiver configurado."
        )


@pytest.mark.skipif(not _redis_disponivel(), reason=f"sem Redis em {URL_REDIS}")
class TestContraRedisDeVerdade:
    @pytest.fixture()
    def store(self):
        s = _RedisStateStore(URL_REDIS)
        s.clear()
        try:
            yield s
        finally:
            s.clear()

    def test_grava_e_le_de_volta(self, store):
        store.save("PAC-1", {"perfil": "alto", "ultimo_timestamp": "2026-01-01T00:00:00"})

        assert store.load()["PAC-1"]["perfil"] == "alto"

    def test_aceita_conn_e_ignora(self, store):
        """O chamador passa `conn=` sempre; o Redis não participa da transação
        do SQLite, mas precisa aceitar a chamada."""
        store.save("PAC-2", {"perfil": "medio"}, conn=object())

        assert "PAC-2" in store.load()

    def test_delete_remove_so_o_paciente_pedido(self, store):
        store.save("PAC-3", {"a": 1})
        store.save("PAC-4", {"a": 2})

        store.delete("PAC-3", conn=None)

        estados = store.load()
        assert "PAC-3" not in estados
        assert "PAC-4" in estados

    def test_clear_esvazia(self, store):
        store.save("PAC-5", {"a": 1})

        store.clear()

        assert store.load() == {}
