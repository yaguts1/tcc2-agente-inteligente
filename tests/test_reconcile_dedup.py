"""Regressão C2: o reconcile de device_events órfãos não pode contar como
processado (nem silenciar) quando a marcação `processado` falha — senão o
evento é reingerido no próximo ciclo, duplicando grade/alertas.
"""
import interface.services.ingestao_service as svc


def _evento_orfao():
    return {
        "id": 42,
        "device_id": "DEV-1",
        "payload": {"cama_id": "C-1", "postura": "supino"},
    }


def _preparar(monkeypatch, delete_retorno=None, delete_exc=None):
    """Isola _do_reconcile: 1 evento órfão, paciente na cama, ingestão
    sempre 'ok', e um `delete_device_event` controlável."""
    ingeridos = []
    monkeypatch.setattr(svc, "listar_device_events", lambda *a, **k: [_evento_orfao()])
    monkeypatch.setattr(svc, "obter_ficha_por_cama", lambda *a, **k: {"paciente_id": "PAC-1"})
    monkeypatch.setattr(svc, "normalizar_payload", lambda payload, header: payload)
    monkeypatch.setattr(svc, "registrar_evento", lambda evento: ingeridos.append(evento))

    def _delete(_db, _id):
        if delete_exc is not None:
            raise delete_exc
        return delete_retorno

    monkeypatch.setattr(svc, "delete_device_event", _delete)
    return ingeridos


def test_reconcile_delete_ok_conta_processed(monkeypatch):
    ingeridos = _preparar(monkeypatch, delete_retorno=1)  # marcou 1 linha
    res = svc._do_reconcile()
    assert len(ingeridos) == 1
    assert res["processed"] == 1
    assert res["skipped"] == 0


def test_reconcile_delete_zero_nao_conta_processed(monkeypatch):
    # delete_device_event retorna 0 (não marcou) → evento reingeriria no
    # próximo ciclo; não pode ser contado como processado.
    ingeridos = _preparar(monkeypatch, delete_retorno=0)
    res = svc._do_reconcile()
    assert len(ingeridos) == 1        # foi ingerido
    assert res["processed"] == 0      # mas NÃO conta como processado
    assert res["skipped"] == 1


def test_reconcile_delete_excecao_nao_conta_processed(monkeypatch):
    # delete_device_event levanta exceção → antes era engolido com pass e o
    # evento contava como processado; agora conta como skipped.
    ingeridos = _preparar(monkeypatch, delete_exc=RuntimeError("db locked"))
    res = svc._do_reconcile()
    assert len(ingeridos) == 1
    assert res["processed"] == 0
    assert res["skipped"] == 1
