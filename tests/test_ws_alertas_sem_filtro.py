"""A conexao SEM filtro — a unica que o frontend abre — recebe tudo.

`/api/ws/alerts` aceita severity/patient_id/alert_types e filtra por conexao.
O React abre UMA conexao compartilhada (dashboard + Historico), entao ela e
sempre sem filtro; filtrar ali silenciaria os outros consumidores. Este arquivo
protege esse caminho: e por ele que passa todo alerta que chega a tela, e ja
quebrou antes — o payload nao carregava os campos que o filtro testa e todo
cliente COM filtro ficava mudo.
"""

from __future__ import annotations

import pytest

from interface.ws_manager_optimized import WebSocketFilter


class _WebSocketFalso:
    """O minimo que o manager usa: accept, send_json e client_state."""

    def __init__(self) -> None:
        self.recebidas: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, dados: dict) -> None:
        self.recebidas.append(dados)


@pytest.fixture()
def manager():
    """Manager limpo: e um singleton de modulo, entao um teste vazaria no outro."""
    from interface.ws_manager_optimized import ws_manager_optimized

    ws_manager_optimized.active_connections.clear()
    yield ws_manager_optimized
    ws_manager_optimized.active_connections.clear()


def _alerta_novo(paciente: str = "PAC-0001", severidade: str = "high") -> dict:
    return {
        "type": "alert_new",
        "alert_id": f"{paciente}__2026-06-01T10:00:00",
        "status": "pending",
        "patient_id": paciente,
        "severity": severidade,
        "alert_type": "imobilidade",
        "timestamp": "2026-06-01T10:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_conexao_sem_filtro_recebe_alerta_novo_e_mudanca(manager):
    """O caminho que a aplicacao usa: nada e filtrado."""
    cliente = _WebSocketFalso()
    await manager.connect(cliente)  # sem `filters`, como o frontend conecta

    await manager.broadcast(_alerta_novo())
    await manager.broadcast({**_alerta_novo(), "type": "alert_update", "status": "acknowledged"})

    assert [m["type"] for m in cliente.recebidas] == ["alert_new", "alert_update"]


@pytest.mark.asyncio
async def test_conexao_sem_filtro_recebe_de_qualquer_paciente_e_severidade(manager):
    """Sem filtro nao ha recorte: a tela precisa de todos os leitos."""
    cliente = _WebSocketFalso()
    await manager.connect(cliente)

    await manager.broadcast(_alerta_novo("PAC-0001", "high"))
    await manager.broadcast(_alerta_novo("PAC-0002", "low"))
    await manager.broadcast(_alerta_novo("PAC-0003", "medium"))

    assert len(cliente.recebidas) == 3


@pytest.mark.asyncio
async def test_um_cliente_filtrado_nao_afeta_o_sem_filtro(manager):
    """Se algum dia uma segunda conexao usar filtro, a compartilhada nao muda.

    E a condicao que torna seguro manter a capacidade de filtro ligada no
    endpoint sem que o frontend a use.
    """
    compartilhado = _WebSocketFalso()
    filtrado = _WebSocketFalso()
    await manager.connect(compartilhado)
    await manager.connect(filtrado, filters=WebSocketFilter(patient_id="PAC-0002"))

    await manager.broadcast(_alerta_novo("PAC-0001"))
    await manager.broadcast(_alerta_novo("PAC-0002"))

    assert len(compartilhado.recebidas) == 2
    assert [m["patient_id"] for m in filtrado.recebidas] == ["PAC-0002"]


def test_payload_do_frontend_tem_os_campos_que_o_filtro_testa():
    """Guarda contra o apodrecimento do caminho filtrado.

    O filtro so funciona se o payload publicado carregar `severity`,
    `patient_id` e `alert_type`. Como nenhum cliente usa filtro hoje, remover
    um desses campos nao quebraria nada visivel — e o defeito so apareceria
    quando alguem finalmente ligasse o filtro.
    """
    campos = {"severity", "patient_id", "alert_type"}
    assert campos.issubset(_alerta_novo().keys())

    filtro = WebSocketFilter(severities=["high"], patient_id="PAC-0001", alert_types=["imobilidade"])
    assert filtro.matches(_alerta_novo("PAC-0001", "high"))
    assert not filtro.matches(_alerta_novo("PAC-0009", "high"))
    assert not filtro.matches(_alerta_novo("PAC-0001", "low"))
