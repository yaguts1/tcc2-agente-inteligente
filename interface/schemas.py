from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from interface.alert_id import PADRAO_PACIENTE_ID

class EventPayload(BaseModel):
    """Modelo de evento recebido pelos endpoints."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=64)
    # `pattern` porque este campo vira CHAVE: ele compoe o `alert_id`
    # (`{paciente_id}__{inicio}`) e vai direto para `INSERT INTO pacientes(id)`.
    # Era texto livre vindo de payload de dispositivo, entao um `__` fazia o
    # identificador de um alerta resolver para OUTRO, e um `/` quebrava a rota.
    # Ver interface/alert_id.py.
    paciente_id: str | None = Field(
        None, max_length=64, pattern=PADRAO_PACIENTE_ID
    )
    cama_id: str | None = Field(None)
    postura: str = Field(..., min_length=1, max_length=64)
    confianca: float = Field(..., ge=0.0, le=1.0)
    amostra_ms: int = Field(..., gt=0)
    ts_utc: datetime
    pressao_pico: float | None = Field(default=None)

    @field_validator("ts_utc")
    @classmethod
    def _normalizar_ts(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0)


class RotinaConfig(BaseModel):
    label: str
    inicio: str
    duracao_min: int
    descricao: str | None = None
    ativo: bool
    sort_order: int


class PacienteConfigResponse(BaseModel):
    paciente_id: str
    nome: str | None = None
    cama_id: str
    perfil: str
    observacoes: str | None = None
    updated_at: str | None = None
    rotinas: List[RotinaConfig]


class ApiResponse(BaseModel):
    code: str
    message: str
    ids: dict[str, Any]


# Valores aceitos para o perfil de risco. O frontend fala em ingles
# (high/medium/low) e o banco guarda em portugues (alto/medio/baixo); os dois
# vocabularios sao aceitos na entrada.
RISK_LEVELS_VALIDOS = frozenset({"high", "medium", "low", "alto", "medio", "baixo"})


class FrontendCreatePatient(BaseModel):
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    # Aceito por compatibilidade com clientes antigos, mas IGNORADO: o intervalo
    # e derivado do perfil de risco (ver paciente_service.intervalo_horas), que
    # e a mesma fonte usada pelo motor de alertas. Antes o formulario deixava
    # editar este numero, mandava para o backend e o valor era descartado sem
    # aviso — a pessoa achava ter mudado o protocolo do paciente e nao mudara
    # nada.
    repositioningInterval: float | None = None
    notes: str | None = None
    # Em qual ala o paciente esta sendo admitido. Ausente = unidade padrao, para
    # o cliente antigo (e a instalacao de uma ala so) continuar funcionando sem
    # mudanca. E ignorado no PATCH: mudar de ala e transferencia, nao edicao de
    # formulario.
    unitId: int | None = None

    @field_validator("riskLevel")
    @classmethod
    def validar_risco(cls, v: str) -> str:
        """Rejeita perfil de risco desconhecido.

        O service fazia `risk_map.get(valor, "medio")`: qualquer coisa que nao
        estivesse no mapa — um typo, "critical", "alta" — virava MEDIO em
        silencio. E um parametro clinico: ele define a janela de
        reposicionamento (2h para alto risco, 3h para medio), entao o efeito
        pratico era rebaixar o paciente de categoria sem ninguem perceber.
        """
        if str(v).lower() not in RISK_LEVELS_VALIDOS:
            aceitos = ", ".join(sorted(RISK_LEVELS_VALIDOS))
            raise ValueError(f"riskLevel invalido: {v!r}. Valores aceitos: {aceitos}.")
        return v


class FrontendPatient(BaseModel):
    """Paciente no formato que a SPA consome.

    Existia com ZERO referencias: as rotas declaravam `response_model=dict`, que
    nao gera schema nenhum e nao valida nada. O resultado nao era so falta de
    documentacao — era divergencia real e ja instalada:

        `services/paciente_service._transform_patient` devolve `room` e `bed`
        possivelmente `None` (paciente sem leito, e depois da alta e o caso
        NORMAL), enquanto `lib/api.ts` declarava os dois como `string`
        obrigatorio.

    Ou seja, o TypeScript strict do frontend estava mentindo, e `patient.room`
    era `undefined` num campo tipado como `string` — o tipo de erro que so
    aparece em runtime, num `.toLowerCase()` qualquer.

    Ligando o modelo aqui, o `null` passa a constar no spec, o gerador de tipos
    do front o propaga, e o `strict` volta a dizer a verdade.
    """

    # Sem default, pelo mesmo motivo de `FrontendAlert`: `_transform_patient`
    # emite todas as chaves. O valor pode ser nulo (paciente sem leito existe, e
    # depois da alta e o estado normal); a CHAVE nao falta.
    id: str
    name: str
    room: str | None
    bed: str | None
    # `Literal`, e nao `str`: `_transform_patient` faz
    # `perfil_map.get(perfil, "medium")`, entao a saida e sempre um dos tres. O
    # `str` solto obrigava a tela a declarar a uniao por conta propria — que e
    # como as duas pontas passam a discordar sem ninguem notar.
    riskLevel: Literal["high", "medium", "low"]
    # float: com a janela do motor, o perfil medio da 1.5h — um int truncaria
    # para 1h e a tela voltaria a divergir do comportamento real.
    repositioningInterval: float | None
    createdAt: str | None
    updatedAt: str | None
    unitId: int | None


class FrontendAlert(BaseModel):
    """Alerta no formato que a SPA consome.

    Existia como JSON-Schema ESCRITO A MAO dentro de `openapi/generate_openapi.py`,
    costurado no spec depois de gerado. Ou seja, a mesma forma tinha TRES
    definicoes independentes — o dict literal montado em `alerts_service`, o
    JSON-Schema do gerador, e a interface TypeScript — e as tres so coincidiam
    por disciplina.

    Ja tinham divergido: o schema a mao declarava `room`/`bed` opcionais e
    `["string","null"]`, enquanto o TS os declarava `string` obrigatorio.

    Como modelo pydantic, o schema passa a ser DERIVADO do que a rota promete, e
    o gerador volta a ser so um gerador.
    """

    # Sem default: `alerts_service` monta o dict com TODAS estas chaves, sempre.
    # Com `= None` o pydantic as marcaria opcionais no schema, e o tipo gerado
    # viraria `bed?: string | null` — "a chave pode nao vir", que nao e verdade.
    # Nullable e opcional sao coisas diferentes, e descrever a resposta errado e
    # o que faz o consumidor programar defensivamente contra um caso que nao
    # existe (ou deixar de programar contra um que existe).
    id: str
    patientId: str
    patientName: str
    # `str`, e nao `str | None`: diferente de `FrontendPatient`, este caminho
    # passa por `dividir_cama`, que devolve string vazia — nunca `None` — para
    # paciente sem leito. Declarar nullable aqui obrigaria a tela a se defender
    # de um caso que nao acontece, e esconderia que o caso REAL e string vazia.
    room: str
    bed: str
    lastRepositioning: str | None
    nextRepositioning: str | None
    riskLevel: Literal["high", "medium", "low"]
    status: Literal["pending", "acknowledged", "completed"]
    closureOrigin: Literal["equipe", "sensor", "sistema"] | None
    closedBy: str | None


class DeviceRegisterRequest(BaseModel):
    device_id: str
    meta: dict | None = None


class BatchAlertRequest(BaseModel):
    """Request body for batch alert operations."""
    alert_ids: List[str]
    # Por que o alerta foi fechado. Ignorado em `acknowledge`, que so registra
    # que alguem VIU. Ausente vale como `reposicionado`, o caso comum — ver
    # `MotivoFechamento`.
    motivo: str | None = None


class MotivoFechamento(BaseModel):
    """Justificativa de fechamento de alerta.

    Concluir nao recebia justificativa nenhuma: o dialogo era sim/nao. Entao
    "reposicionei o paciente", "estava em cirurgia", "o paciente recusou",
    "contraindicado por retalho na regiao sacral" e "falso alarme, o sensor
    deslocou" viravam exatamente a mesma linha — e cada um e um fato clinico
    diferente, que pede acao diferente.

    O default e `reposicionado`, o caso comum: exigir escolha explicita em toda
    conclusao adicionaria atrito na acao mais frequente da ala, e atrito na
    acao frequente e o que faz a equipe procurar o atalho. Quem faz o comum nao
    escolhe nada; a excecao e que precisa ser dita.
    """

    motivo: str | None = None
    observacao: str | None = Field(None, max_length=255)


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
