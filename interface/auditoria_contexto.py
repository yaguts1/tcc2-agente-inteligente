"""Como um handler informa à trilha QUAIS pacientes ele tocou.

O `AuditoriaMiddleware` extrai o `paciente_id` do CAMINHO da requisição, o que
resolve `/api/pacientes/PAC-0001/...` e não resolve nada quando os
identificadores viajam no CORPO.

Era exatamente o caso das operações em lote — `POST /api/frontend/alerts/batch/
acknowledge` e `.../complete`, que carregam `alert_ids` no corpo. Elas eram
auditadas (a rota está na lista), mas com `paciente_id = NULL`. Ou seja: a
operação de escrita de MAIOR VOLUME do sistema, a que o botão "selecionar tudo"
dispara, era a única que não dizia sobre quem agiu.

A pergunta do Art. 48 da LGPD — "quais titulares foram afetados por este
incidente?" — era, portanto, inrespondível justamente ali. E a trilha não
parecia incompleta: as linhas existiam, com usuário, rota, IP e horário. Só a
coluna que importa vinha vazia.

O middleware não pode ler o corpo por conta própria: consumir o stream da
requisição antes do handler o deixaria vazio, e bufferizar todo corpo de toda
rota auditada é caro e guarda dado sensível em memória sem necessidade. Quem já
tem os identificadores decodificados é o handler — então é ele que os declara.
"""

from __future__ import annotations

from collections.abc import Iterable

CHAVE = "pacientes_auditados"


def declarar_pacientes(request, pacientes: Iterable[str]) -> None:
    """Registra, para o middleware, os pacientes afetados por esta requisição.

    Chame ANTES de executar a operação. Se ela falhar no meio, a trilha ainda
    precisa registrar a tentativa e sobre quem ela foi — uma tentativa de acesso
    que deu errado é tão auditável quanto uma que deu certo, e o `status` da
    linha distingue as duas.

    Ordenado e sem repetição: o mesmo lote enviado duas vezes produz a mesma
    sequência de linhas, e um `alert_id` duplicado no corpo não vira duas
    linhas para o mesmo paciente.
    """
    unicos = sorted({str(p) for p in pacientes if p})
    if unicos:
        setattr(request.state, CHAVE, unicos)


def pacientes_declarados(request) -> list[str]:
    return list(getattr(request.state, CHAVE, ()) or ())
