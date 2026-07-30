"""Lesao por pressao: a variavel de desfecho.

O sistema media adesao ao reposicionamento e nunca registrava se a lesao
aconteceu. Sem isso, a correlacao que o projeto existe para demonstrar — adesao
ao protocolo vs. incidencia de LPP — nao era computavel nem em principio: media-
se o processo e ignorava-se o resultado.

O estagio ATUAL e sempre derivado da avaliacao mais recente, nunca duplicado
numa coluna. Duas fontes para o mesmo fato divergem, e aqui a que divergiria e
justamente a que alimenta o indicador.
"""
from __future__ import annotations

import structlog

from interface.db_core import connect
from interface.repositories.unidades import filtro_sql as filtro_de_unidades
from interface.tempo import agora_utc_naive
from datetime import UTC

logger = structlog.get_logger(__name__)

ORIGEM_PRESENTE_NA_ADMISSAO = "presente_na_admissao"
ORIGEM_ADQUIRIDA = "adquirida"
ORIGENS_VALIDAS = {ORIGEM_PRESENTE_NA_ADMISSAO, ORIGEM_ADQUIRIDA}

SITIOS_VALIDOS = {
    "sacro", "coccige", "isquio_esquerdo", "isquio_direito",
    "trocanter_esquerdo", "trocanter_direito",
    "calcaneo_esquerdo", "calcaneo_direito",
    "maleolo_esquerdo", "maleolo_direito",
    "occipital", "escapula_esquerda", "escapula_direita",
    "orelha_esquerda", "orelha_direita",
    "cotovelo_esquerdo", "cotovelo_direito",
    "nariz", "outro",
}

ESTAGIOS_VALIDOS = {
    "estagio_1", "estagio_2", "estagio_3", "estagio_4",
    "nao_classificavel", "tissular_profunda",
    "dispositivo_medico", "membrana_mucosa",
}

DESFECHOS_VALIDOS = {"cicatrizada", "alta_com_lesao", "obito", "erro_de_registro"}


def _ts_e_ms(quando: str | None = None) -> tuple[str, int]:
    from datetime import datetime

    dt = datetime.fromisoformat(str(quando)[:19]) if quando else agora_utc_naive().replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%S"), int(
        dt.replace(tzinfo=UTC).timestamp() * 1000
    )


def registrar(
    db_path: str,
    paciente_id: str,
    sitio: str,
    origem: str,
    estagio: str,
    *,
    identificada_em: str | None = None,
    usuario: str | None = None,
    observacoes: str | None = None,
    comprimento_cm: float | None = None,
    largura_cm: float | None = None,
) -> dict:
    """Registra a lesao e a PRIMEIRA avaliacao de estagio, na mesma transacao.

    As duas juntas de proposito: uma lesao sem nenhuma avaliacao nao tem estagio,
    e estagio e o que a torna comparavel com qualquer outra. Permitir o estado
    intermediario criaria lesao que existe e nao diz nada.

    `origem` nao tem default. Uma lesao que o paciente TROUXE e prevalencia na
    admissao, nao falha do cuidado desta unidade; uma que apareceu aqui e
    incidencia. Somar as duas produz um numero que pune a unidade que recebe
    paciente grave de outro servico — e e esse numero que faz uma equipe deixar
    de registrar lesao.
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem invalida: {origem!r} (aceitas: {sorted(ORIGENS_VALIDAS)})")
    if sitio not in SITIOS_VALIDOS:
        raise ValueError(f"sitio invalido: {sitio!r}")
    if estagio not in ESTAGIOS_VALIDOS:
        raise ValueError(f"estagio invalido: {estagio!r} (aceitos: {sorted(ESTAGIOS_VALIDOS)})")

    ts, ms = _ts_e_ms(identificada_em)

    with connect(db_path) as conn:
        ficha = conn.execute(
            "SELECT unidade_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,)
        ).fetchone()
        if ficha is None:
            raise LookupError(f"Paciente {paciente_id} nao encontrado.")

        # A internacao ABERTA no momento do registro. Sem amarrar ao episodio,
        # uma lesao de internacao anterior contaria na atual e o denominador
        # (paciente-dia daquele episodio) nao casaria com o numerador.
        episodio = conn.execute(
            "SELECT id FROM internacoes WHERE paciente_id = ? AND alta_ms IS NULL",
            (paciente_id,),
        ).fetchone()

        cur = conn.execute(
            "INSERT INTO lesoes (paciente_id, internacao_id, unidade_id, sitio, origem,"
            "                    identificada_ts, identificada_ms, identificada_por, observacoes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                paciente_id,
                None if episodio is None else int(episodio["id"]),
                ficha["unidade_id"],
                sitio,
                origem,
                ts,
                ms,
                usuario,
                observacoes,
            ),
        )
        lesao_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO lesao_avaliacoes"
            " (lesao_id, ts, ts_ms, estagio, comprimento_cm, largura_cm, avaliada_por)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lesao_id, ts, ms, estagio, comprimento_cm, largura_cm, usuario),
        )

    logger.info(
        "lesao_registrada",
        lesao_id=lesao_id,
        paciente_id=paciente_id,
        sitio=sitio,
        origem=origem,
        estagio=estagio,
        por=usuario,
    )
    return obter(db_path, lesao_id)  # type: ignore[return-value]


def avaliar(
    db_path: str,
    lesao_id: int,
    estagio: str,
    *,
    usuario: str | None = None,
    comprimento_cm: float | None = None,
    largura_cm: float | None = None,
    observacoes: str | None = None,
    quando: str | None = None,
) -> dict:
    """Acrescenta uma avaliacao de estagio — a evolucao.

    Nao sobrescreve a anterior: a TRAJETORIA e o dado clinico. "Estagio 2 que
    cicatrizou em 6 dias" e "estagio 2 que virou 4" nao sao o mesmo desfecho, e
    guardar so o estado atual apagaria a diferenca a cada reavaliacao.
    """
    if estagio not in ESTAGIOS_VALIDOS:
        raise ValueError(f"estagio invalido: {estagio!r}")
    ts, ms = _ts_e_ms(quando)

    with connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM lesoes WHERE id = ?", (lesao_id,)).fetchone() is None:
            raise LookupError(f"Lesao {lesao_id} nao encontrada.")
        conn.execute(
            "INSERT INTO lesao_avaliacoes"
            " (lesao_id, ts, ts_ms, estagio, comprimento_cm, largura_cm, avaliada_por, observacoes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lesao_id, ts, ms, estagio, comprimento_cm, largura_cm, usuario, observacoes),
        )
    logger.info("lesao_avaliada", lesao_id=lesao_id, estagio=estagio, por=usuario)
    return obter(db_path, lesao_id)  # type: ignore[return-value]


def fechar(
    db_path: str, lesao_id: int, desfecho: str, *, usuario: str | None = None
) -> dict:
    if desfecho not in DESFECHOS_VALIDOS:
        raise ValueError(
            f"desfecho invalido: {desfecho!r} (aceitos: {sorted(DESFECHOS_VALIDOS)})"
        )
    ts, ms = _ts_e_ms()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE lesoes SET fechada_ts = ?, fechada_ms = ?, desfecho = ?"
            " WHERE id = ? AND fechada_ms IS NULL",
            (ts, ms, desfecho, lesao_id),
        )
        if cur.rowcount == 0:
            raise LookupError(f"Lesao {lesao_id} nao encontrada ou ja fechada.")
    logger.info("lesao_fechada", lesao_id=lesao_id, desfecho=desfecho, por=usuario)
    return obter(db_path, lesao_id)  # type: ignore[return-value]


_SELECT_LESAO = """
    SELECT l.*,
           (SELECT a.estagio FROM lesao_avaliacoes a
             WHERE a.lesao_id = l.id ORDER BY a.ts_ms DESC, a.id DESC LIMIT 1) AS estagio_atual,
           (SELECT a.estagio FROM lesao_avaliacoes a
             WHERE a.lesao_id = l.id ORDER BY a.ts_ms ASC, a.id ASC LIMIT 1) AS estagio_inicial,
           (SELECT COUNT(*) FROM lesao_avaliacoes a WHERE a.lesao_id = l.id) AS avaliacoes
      FROM lesoes l
"""


def obter(db_path: str, lesao_id: int) -> dict | None:
    with connect(db_path) as conn:
        linha = conn.execute(f"{_SELECT_LESAO} WHERE l.id = ?", (lesao_id,)).fetchone()
        if linha is None:
            return None
        lesao = dict(linha)
        lesao["historico"] = [
            dict(a)
            for a in conn.execute(
                "SELECT ts, estagio, comprimento_cm, largura_cm, avaliada_por, observacoes"
                "  FROM lesao_avaliacoes WHERE lesao_id = ? ORDER BY ts_ms, id",
                (lesao_id,),
            )
        ]
    return lesao


def listar_do_paciente(db_path: str, paciente_id: str) -> list[dict]:
    with connect(db_path) as conn:
        return [
            dict(linha)
            for linha in conn.execute(
                f"{_SELECT_LESAO} WHERE l.paciente_id = ?"
                " ORDER BY l.identificada_ms DESC",
                (paciente_id,),
            )
        ]


def indicadores(
    db_path: str, horas: int = 720, unidades: set[int] | None = None
) -> dict:
    """Incidencia de LPP e adesao da equipe na mesma janela.

    E o numero que o projeto existe para produzir, e que nao era computavel:
    media-se adesao sem nunca registrar desfecho.

    O denominador e PACIENTE-DIA, tirado de `paciente_cama_history` — nao "numero
    de pacientes". Uma ala com 10 pacientes por 30 dias e uma com 300 por 1 dia
    tem o mesmo numero de pacientes-dia e riscos totalmente diferentes se
    comparadas por cabeca; por paciente-dia sao comparaveis, que e a unidade que
    a literatura de LPP usa.

    So `adquirida` entra no numerador. Lesao presente na admissao e prevalencia,
    nao resultado do cuidado prestado aqui — e incluir puniria a unidade que
    recebe paciente grave de outro servico.
    """
    agora_ms = int(agora_utc_naive().timestamp() * 1000)
    desde_ms = agora_ms - horas * 3_600_000

    cond_lesao, params_lesao = filtro_de_unidades(unidades, coluna="l.unidade_id")
    cond_hist, params_hist = filtro_de_unidades(unidades, coluna="h.unidade_id")
    cond_ficha, params_ficha = filtro_de_unidades(unidades, coluna="f.unidade_id")

    with connect(db_path) as conn:
        adquiridas = conn.execute(
            "SELECT COUNT(*) FROM lesoes l"
            " WHERE l.origem = ? AND l.identificada_ms >= ?" + cond_lesao,
            [ORIGEM_ADQUIRIDA, desde_ms, *params_lesao],
        ).fetchone()[0]

        presentes = conn.execute(
            "SELECT COUNT(*) FROM lesoes l"
            " WHERE l.origem = ? AND l.identificada_ms >= ?" + cond_lesao,
            [ORIGEM_PRESENTE_NA_ADMISSAO, desde_ms, *params_lesao],
        ).fetchone()[0]

        # Paciente-dia: soma dos periodos de leito que se sobrepoem a janela.
        # `MIN(fim, agora)` e `MAX(inicio, desde)` recortam o periodo NA janela —
        # sem isso uma internacao de seis meses contaria inteira numa janela de
        # 30 dias, e o denominador inflaria a ponto de zerar a incidencia.
        sobreposicao_ms = conn.execute(
            "SELECT COALESCE(SUM("
            "   MIN(COALESCE(h.end_ms, ?), ?) - MAX(h.start_ms, ?)"
            " ), 0) FROM paciente_cama_history h"
            " WHERE COALESCE(h.end_ms, ?) > ? AND h.start_ms < ?" + cond_hist,
            [agora_ms, agora_ms, desde_ms, agora_ms, desde_ms, agora_ms, *params_hist],
        ).fetchone()[0]

        internados = conn.execute(
            "SELECT COUNT(*) FROM paciente_fichas f"
            " WHERE EXISTS (SELECT 1 FROM internacoes i"
            "               WHERE i.paciente_id = f.paciente_id AND i.alta_ms IS NULL)"
            + cond_ficha,
            params_ficha,
        ).fetchone()[0]

    paciente_dias = round(max(sobreposicao_ms, 0) / 86_400_000, 2)
    # Por 1000 paciente-dia, como a literatura de LPP reporta.
    incidencia = (
        round(adquiridas / paciente_dias * 1000, 2) if paciente_dias > 0 else None
    )

    return {
        "janela_horas": horas,
        "lesoes_adquiridas": adquiridas,
        "lesoes_presentes_na_admissao": presentes,
        "pacientes_dia": paciente_dias,
        # `None`, e nao 0: sem paciente-dia nenhum a taxa nao e zero, e
        # indefinida — e zero seria o melhor resultado possivel.
        "incidencia_por_1000_pacientes_dia": incidencia,
        "pacientes_internados": internados,
    }
