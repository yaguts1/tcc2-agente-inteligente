"""Upload JSONL em lote: o que o servidor le, o que ele recusa e o que ele conta.

Os tres defeitos cobertos aqui tinham a mesma forma dos que a exportacao tinha:
o resultado nao contava a verdade sobre si mesmo.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.api_shared import iterar_linhas_jsonl, tipo_de_conteudo_aceito


BLOCO = 64 * 1024  # o tamanho de leitura usado por iterar_linhas_jsonl


@pytest_asyncio.fixture()
async def api_client(app_isolado):
    from quality.filtro import reset_filtro

    # O filtro guarda buffer e cache de dedup em modulo; sem zerar, um teste
    # herda o estado do anterior.
    reset_filtro()
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {"client": client, "db_path": Path(app_isolado.db_path)}
    reset_filtro()


class _ArquivoFalso:
    """Minimo que `iterar_linhas_jsonl` consome de um UploadFile."""

    def __init__(self, dados: bytes) -> None:
        self._dados = dados
        self._pos = 0

    async def read(self, n: int) -> bytes:
        pedaco = self._dados[self._pos : self._pos + n]
        self._pos += len(pedaco)
        return pedaco


def _linha_bytes(cama: bytes, ts: str) -> bytes:
    """Uma linha de evento valida, montada em bytes para controlar o offset."""
    return (
        b'{"device_id":"ESP32","paciente_id":"P1","cama_id":"'
        + cama
        + b'","postura":"supino","confianca":0.9,"amostra_ms":300000,"ts_utc":"'
        + ts.encode()
        + b'"}'
    )


def _corpo_com_acento_na_fronteira() -> bytes:
    """JSONL valido em que um "c-cedilha" fica partido entre dois blocos de 64 KiB.

    O byte `BLOCO - 1` e o primeiro do caractere e o byte `BLOCO` e o segundo,
    ou seja, cada metade cai numa leitura diferente. Decodificar cada bloco
    isoladamente falha aqui; o decoder incremental nao.
    """
    prefixo = b'{"device_id":"ESP32","paciente_id":"P1","cama_id":"'

    primeira = _linha_bytes(b"A" * 60_000, "2025-01-01T00:00:00Z") + b"\n"
    inicio_segunda = len(primeira)

    alvo = BLOCO - 1
    enchimento = alvo - (inicio_segunda + len(prefixo))
    assert enchimento > 0, "primeira linha grande demais para posicionar o acento"

    segunda = (
        prefixo
        + b"C" * enchimento
        + "ç".encode()
        + b'","postura":"lateral_direito","confianca":0.9,"amostra_ms":300000,'
        b'"ts_utc":"2025-01-01T01:00:00Z"}'
    )

    corpo = primeira + segunda + b"\n"
    assert corpo[alvo : alvo + 2] == "ç".encode()
    return corpo


def test_corpo_de_teste_realmente_parte_o_caractere():
    """Guarda o proprio teste: sem o acento na fronteira ele nao prova nada."""
    corpo = _corpo_com_acento_na_fronteira()
    with pytest.raises(UnicodeDecodeError):
        # Exatamente o que o leitor antigo fazia: decodificar bloco por bloco.
        corpo[:BLOCO].decode("utf-8")


@pytest.mark.asyncio
async def test_leitor_jsonl_atravessa_fronteira_de_bloco():
    """Caractere multibyte partido entre blocos nao pode quebrar a leitura."""
    corpo = _corpo_com_acento_na_fronteira()
    linhas = [linha async for linha in iterar_linhas_jsonl(_ArquivoFalso(corpo))]

    assert len(linhas) == 2
    assert "ç" in linhas[1]
    assert json.loads(linhas[1])["postura"] == "lateral_direito"


@pytest.mark.asyncio
async def test_leitor_jsonl_recusa_encoding_invalido():
    """Bytes que nao sao UTF-8 viram 400 (culpa do cliente), nao 500."""
    from fastapi import HTTPException

    corpo = b'{"a": "' + b"\xff\xfe" + b'"}\n'
    with pytest.raises(HTTPException) as exc:
        async for _ in iterar_linhas_jsonl(_ArquivoFalso(corpo)):
            pass
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "invalid_encoding"


@pytest.mark.asyncio
async def test_leitor_jsonl_recusa_bytes_truncados_no_fim():
    """Arquivo cortado no meio de um caractere e erro, nao silencio."""
    from fastapi import HTTPException

    corpo = '{"cama":"ç'.encode()[:-1]  # ultimo byte do acento faltando
    with pytest.raises(HTTPException) as exc:
        async for _ in iterar_linhas_jsonl(_ArquivoFalso(corpo)):
            pass
    assert exc.value.detail["code"] == "invalid_encoding"


def test_content_type_com_parametro_e_aceito():
    """`curl -F` manda `text/plain; charset=utf-8`; a checagem antiga recusava."""
    assert tipo_de_conteudo_aceito("text/plain; charset=utf-8")
    assert tipo_de_conteudo_aceito("application/x-ndjson")  # media type do JSONL
    assert tipo_de_conteudo_aceito("APPLICATION/JSONL")
    assert tipo_de_conteudo_aceito(None)  # cliente embarcado omite o header
    assert not tipo_de_conteudo_aceito("image/png")


@pytest.mark.asyncio
async def test_grade_aceita_arquivo_com_acento_na_fronteira(api_client):
    """O upload valido de mais de 64 KiB com acento nao pode virar erro."""
    client = api_client["client"]
    corpo = _corpo_com_acento_na_fronteira()
    files = {"arquivo": ("grade.jsonl", corpo, "text/plain; charset=utf-8")}

    resp = await client.post("/api/grade", files=files)

    assert resp.status_code == 200, resp.text
    corpo_resp = resp.json()
    assert corpo_resp["code"] == "success"
    assert corpo_resp["ids"]["linhas"] == 2
    assert corpo_resp["ids"]["processados"] == 2
    assert corpo_resp["ids"]["rejeitadas"] == 0

    with sqlite3.connect(api_client["db_path"]) as conn:
        total = conn.execute("SELECT COUNT(*) FROM grade").fetchone()[0]
    assert total == 2


@pytest.mark.asyncio
async def test_grade_linha_invalida_nao_aborta_o_lote(api_client):
    """Linha ruim no meio do arquivo: o resto entra e a resposta diz quantas caíram.

    Antes, o JSON invalido devolvia 400 e a estrutura invalida 422, os dois
    abortando o upload DEPOIS de gravar as linhas anteriores — sem numero
    nenhum na resposta, o cliente nao tinha como saber que metade do arquivo
    havia entrado.
    """
    client = api_client["client"]
    linhas = [
        _linha_bytes(b"C01", "2025-03-01T00:00:00Z"),
        b"{isto nao e json}",
        # Estrutura invalida: confianca fora de [0,1] (rejeitada por EventPayload).
        b'{"device_id":"ESP32","paciente_id":"P1","cama_id":"C01","postura":"supino",'
        b'"confianca":7.5,"amostra_ms":300000,"ts_utc":"2025-03-01T01:00:00Z"}',
        _linha_bytes(b"C01", "2025-03-01T02:00:00Z"),
    ]
    files = {"arquivo": ("grade.jsonl", b"\n".join(linhas) + b"\n", "application/jsonl")}

    resp = await client.post("/api/grade", files=files)

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    ids = corpo["ids"]
    assert corpo["code"] == "partial"
    assert ids["linhas"] == 4
    assert ids["processados"] == 2  # as duas validas nao foram perdidas
    assert ids["rejeitadas"] == 2
    assert ids["linhas_rejeitadas"] == [2, 3]
    assert "2 linhas invalidas" in corpo["message"]

    with sqlite3.connect(api_client["db_path"]) as conn:
        total = conn.execute("SELECT COUNT(*) FROM grade").fetchone()[0]
    assert total == 2


@pytest.mark.asyncio
async def test_grade_arquivo_todo_ilegivel_e_erro(api_client):
    """Sem uma linha aproveitavel, 400 — nao ha nada gravado para preservar.

    E a fronteira da regra do teste acima: o lote misto responde 200 porque
    aborta-lo apagaria a contagem do que ja entrou; aqui nada entrou, e chamar
    de sucesso um arquivo que o servidor nao conseguiu ler seria mentira.
    """
    client = api_client["client"]
    files = {"arquivo": ("grade.jsonl", b"nao e json\ntambem nao\n", "application/jsonl")}

    resp = await client.post("/api/grade", files=files)

    assert resp.status_code == 400
    detalhe = resp.json()["detail"]
    assert detalhe["code"] == "invalid_jsonl"
    assert detalhe["linhas_rejeitadas"] == [1, 2]


@pytest.mark.asyncio
async def test_grade_nao_esvazia_buffer_de_outro_dispositivo(api_client):
    """O flush do fim do upload nao pode alcancar quem esta transmitindo ao vivo.

    `flush_filtro()` sem argumento esvaziava o buffer de reordenacao de TODOS
    os dispositivos: as amostras de um ESP32 em transmissao eram liberadas
    antes da janela de jitter fechar, e o buffer que serviria para reorden-las
    deixava de existir.
    """
    from quality import filtro

    client = api_client["client"]

    # Dispositivo AO VIVO com uma amostra retida no buffer de reordenacao.
    #
    # Pelo armazenamento do filtro, e nao mexendo num dicionario de modulo: o
    # estado passou a ter dois backends (memoria e Redis) e o teste precisa
    # valer para os dois. Ver `quality/estado.py`.
    filtro._ESTADO.guardar("ESP-AO-VIVO", 1743465600.0, {"ts_utc": "2025-04-01T00:00:00"})
    assert filtro._ESTADO.pendentes("ESP-AO-VIVO") == 1

    files = {
        "arquivo": (
            "grade.jsonl",
            _linha_bytes(b"C01", "2025-04-02T00:00:00Z") + b"\n",
            "application/jsonl",
        )
    }
    resp = await client.post("/api/grade", files=files)
    assert resp.status_code == 200, resp.text

    assert filtro._ESTADO.pendentes("ESP-AO-VIVO") == 1, (
        "o upload de outro dispositivo esvaziou o buffer do ESP32 ao vivo"
    )


@pytest.mark.asyncio
async def test_grade_arquivo_vazio_reporta_zero_linhas(api_client):
    """Upload sem conteudo nao pode responder um sucesso indistinguivel."""
    client = api_client["client"]
    files = {"arquivo": ("grade.jsonl", b"", "application/jsonl")}

    resp = await client.post("/api/grade", files=files)

    assert resp.status_code == 200
    ids = resp.json()["ids"]
    assert ids["linhas"] == 0
    assert ids["processados"] == 0
    assert "0 linhas lidas" in resp.json()["message"]
