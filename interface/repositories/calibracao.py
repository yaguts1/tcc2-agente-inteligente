"""Calibração: a confiança do sensor prediz falso alarme?

POR QUE ISTO EXISTE
-------------------
`grade.confianca` era gravada em toda amostra e **nunca lida** por ninguém — nem
para decidir, nem para relatar. Um campo que só recebe escrita não é informação,
é peso morto: ninguém sabe se 0,62 significa alguma coisa diferente de 0,95.

E o botão "falso alarme" já existia no fechamento (`MotivoFechamento`), então o
dado do outro lado já vinha sendo coletado — só que ninguém somava. A taxa de
falso-positivo da instalação seguia incognoscível não por falta de registro, mas
por falta de leitura.

Este módulo junta as duas pontas. Para cada alerta FECHADO, olha as amostras que
o produziram e pergunta: quem foi marcado como falso alarme tinha confiança mais
baixa?

O QUE LIGA UM ALERTA ÀS AMOSTRAS QUE O GERARAM
-----------------------------------------------
O alerta guarda `paciente_id`, `inicio` e `janela_min`. A imobilidade é
declarada quando a janela fecha, então as amostras responsáveis são as da grade
do paciente no intervalo `[inicio - janela_min, inicio]`. Não é uma
reconstrução aproximada: é a mesma janela que o motor usou para decidir.

LIMITE HONESTO
--------------
Isto mede a confiança **auto-relatada pelo sensor**, não a acurácia do sistema.
Um sensor mal calibrado pode reportar 0,99 e errar; a única forma de saber é
alguém marcar o falso alarme na tela. Por isso a saída sempre carrega o número
de alertas classificados: com poucos, qualquer taxa é ruído, e a decisão de
mexer no limiar não deve sair daqui sem volume.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from interface.db_core import connect
from interface.tempo import agora_utc_naive

# Faixas de confiança, em ordem crescente. O corte em 0,80 não é arbitrário: é
# o `CONF_LIMIAR` padrão do filtro de qualidade, ou seja, a fronteira que a
# instalação já usa para descartar amostra. Ver as faixas separadas em volta
# dele permite responder "o limiar está no lugar certo?" com dado, e não com
# opinião.
FAIXAS: tuple[tuple[str, float, float], ...] = (
    ("<0.70", 0.0, 0.70),
    ("0.70-0.80", 0.70, 0.80),
    ("0.80-0.90", 0.80, 0.90),
    (">=0.90", 0.90, 1.01),
)

# Motivos que significam "o alerta não deveria ter existido".
#
# Só `falso_alarme` conta. "Em procedimento", "recusa do paciente" e
# "contraindicado" são alertas CORRETOS cuja ação não pôde ser executada —
# contá-los como falso-positivo culparia o sensor por uma decisão clínica.
MOTIVOS_FALSO_POSITIVO = frozenset({"falso_alarme"})


def _faixa_de(confianca: float) -> str:
    for rotulo, minimo, maximo in FAIXAS:
        if minimo <= confianca < maximo:
            return rotulo
    return FAIXAS[-1][0]


def _vazio(dias: int) -> dict:
    """Resposta para escopo sem nenhuma unidade: nada a relatar, e dizendo isso.

    `taxa` fica `None`, não 0.0 — usuário sem unidade nenhuma não tem "zero por
    cento de falso alarme", ele não tem dado.
    """
    return {
        "dias": dias,
        "alertas_classificados": 0,
        "falsos_alarmes": 0,
        "taxa_falso_alarme": None,
        "sem_amostras": 0,
        "por_motivo": {},
        "por_faixa": [
            {"faixa": rotulo, "alertas": 0, "falsos": 0, "taxa": None} for rotulo, _, _ in FAIXAS
        ],
    }


def calibracao(db_path: str, dias: int = 30, unidades: set[int] | None = None) -> dict:
    """Taxa de falso alarme por faixa de confiança, nos últimos `dias`.

    Considera apenas alertas **fechados com motivo registrado**: um alerta ainda
    aberto não foi julgado por ninguém, e um fechado sem motivo não diz se era
    verdadeiro. Incluí-los como "verdadeiros" inflaria a qualidade aparente do
    sistema — exatamente o erro que este relatório existe para não cometer.
    """
    desde = (agora_utc_naive() - timedelta(days=max(1, dias))).strftime("%Y-%m-%dT%H:%M:%S")

    # `unidades is None` = admin, vê a instalação inteira. Escopado, o alerta de
    # paciente fora do escopo SAI da conta — mesma regra de `alerts_service`.
    #
    # Não é detalhe de apresentação: uma taxa de falso alarme misturando alas
    # responderia a pergunta errada (a enfermeira de uma ala decidindo limiar com
    # o número de outra) e ainda vazaria volume de alerta de unidade alheia.
    filtro_unidade = ""
    parametros: list[object] = [desde]
    if unidades is not None:
        if not unidades:
            return _vazio(dias)
        marcadores = ",".join("?" for _ in unidades)
        filtro_unidade = (
            " AND a.paciente_id IN (SELECT paciente_id FROM paciente_fichas"
            f" WHERE unidade_id IN ({marcadores}))"
        )
        parametros.extend(sorted(unidades))

    with connect(db_path) as conn:
        alertas = conn.execute(
            f"""
            SELECT a.paciente_id, a.inicio, a.janela_min, a.motivo_fechamento
              FROM alertas a
             WHERE a.status = 'fechado'
               AND a.motivo_fechamento IS NOT NULL
               AND a.inicio >= ?{filtro_unidade}
            """,
            tuple(parametros),
        ).fetchall()

        por_faixa: dict[str, dict[str, int]] = {
            rotulo: {"alertas": 0, "falsos": 0} for rotulo, _, _ in FAIXAS
        }
        por_motivo: dict[str, int] = {}
        sem_amostras = 0
        classificados = 0

        for paciente_id, inicio, janela_min, motivo in alertas:
            motivo = str(motivo)
            por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
            classificados += 1

            janela = int(janela_min or 60)
            try:
                aberto_em = datetime.fromisoformat(str(inicio))
            except ValueError:
                sem_amostras += 1
                continue
            abertura = (aberto_em - timedelta(minutes=janela)).strftime("%Y-%m-%dT%H:%M:%S")

            linha = conn.execute(
                """
                SELECT AVG(confianca) FROM grade
                 WHERE paciente_id = ? AND ts >= ? AND ts <= ? AND confianca IS NOT NULL
                """,
                (paciente_id, abertura, str(inicio)),
            ).fetchone()

            media = linha[0] if linha else None
            if media is None:
                # Alerta cujas amostras já saíram da retenção, ou vindo de uma
                # instalação anterior à coluna `confianca`. Contado à parte, e
                # não jogado numa faixa — inventar faixa aqui é o mesmo que
                # inventar dado.
                sem_amostras += 1
                continue

            faixa = _faixa_de(float(media))
            por_faixa[faixa]["alertas"] += 1
            if motivo in MOTIVOS_FALSO_POSITIVO:
                por_faixa[faixa]["falsos"] += 1

    falsos_total = sum(por_motivo.get(m, 0) for m in MOTIVOS_FALSO_POSITIVO)
    return {
        "dias": dias,
        "alertas_classificados": classificados,
        "falsos_alarmes": falsos_total,
        "taxa_falso_alarme": round(falsos_total / classificados, 4) if classificados else None,
        "sem_amostras": sem_amostras,
        "por_motivo": dict(sorted(por_motivo.items())),
        "por_faixa": [
            {
                "faixa": rotulo,
                "alertas": dados["alertas"],
                "falsos": dados["falsos"],
                # `None`, e não 0.0, quando não há alertas na faixa: "não sei" e
                # "zero por cento" são afirmações diferentes, e a segunda seria
                # mentira num relatório de calibração.
                "taxa": round(dados["falsos"] / dados["alertas"], 4) if dados["alertas"] else None,
            }
            for rotulo, dados in por_faixa.items()
        ],
    }
