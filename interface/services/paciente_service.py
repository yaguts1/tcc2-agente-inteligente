"""Service layer for Patient operations."""
from __future__ import annotations

from typing import List, Optional

import structlog

from interface.repositories.pacientes import PatientRepository
from interface.schemas import FrontendCreatePatient

logger = structlog.get_logger(__name__)

# Vocabulário do frontend (en) e do banco (pt) para o perfil de risco. A
# validação de quais valores são aceitos fica no schema, que rejeita na borda.
_RISK_PARA_PERFIL = {
    "high": "alto",
    "medium": "medio",
    "low": "baixo",
    "alto": "alto",
    "medio": "medio",
    "baixo": "baixo",
}


def intervalo_horas(perfil: str) -> float:
    """Intervalo de reposicionamento do perfil, em horas.

    Derivado de `config.janela_por_perfil`, que é a MESMA fonte que o motor de
    alertas usa para decidir quando disparar. Antes havia um mapa fixo aqui
    ({alto: 2, medio: 3, baixo: 4}) que divergia do motor (60/90/120 min) por um
    fator de DOIS: a tela informava "reposicionar a cada 2h" para um paciente de
    alto risco enquanto o sistema alertava a cada 1h.

    Num parâmetro clínico, duas fontes de verdade significam que pelo menos uma
    está errada — e ninguém consegue saber qual olhando a tela.
    """
    from configuracao import carregar_configuracao

    minutos = carregar_configuracao().janela_por_perfil.get(perfil)
    if not minutos:
        minutos = carregar_configuracao().janela_por_perfil["medio"]
    return round(minutos / 60, 2)


# Quarto e leito viajam juntos num unico `cama_id`. A composicao e a separacao
# precisam sair DAQUI, e nao de cada tela.
#
# Havia duas convencoes no mesmo sistema: o cadastro juntava com hifen
# (`f"{room}-{bed}"`), a tela de Pacientes separava por hifen (certo) e o
# dashboard de alertas separava por BARRA — que nunca casa. Efeito visivel: um
# paciente cadastrado no quarto "TESTE", leito "01" aparecia no dashboard como
# quarto "TESTE-01" e leito VAZIO. A coluna de leito estava sempre vazia para
# quem foi cadastrado pela interface.
SEPARADOR_CAMA = "-"


def compor_cama(room: str | None, bed: str | None) -> str | None:
    """Junta quarto e leito no `cama_id` gravado na ficha."""
    quarto = (room or "").strip()
    leito = (bed or "").strip()
    if quarto and leito:
        return f"{quarto}{SEPARADOR_CAMA}{leito}"
    return quarto or leito or None


def dividir_cama(cama_id: str | None) -> tuple[str, str]:
    """Separa o `cama_id` de volta em (quarto, leito).

    `rsplit` com limite 1, e nao `split`: um quarto pode ter hifen no nome
    ("UTI-2"), e dividir pelo PRIMEIRO separador devolveria quarto "UTI" e
    leito "2", descartando o resto. O separador que importa e o ultimo, que foi
    o inserido na composicao.

    Barra e aceita por compatibilidade com fichas antigas preenchidas a mao.
    """
    texto = (cama_id or "").strip()
    if not texto:
        return "", ""
    for sep in (SEPARADOR_CAMA, "/"):
        if sep in texto:
            quarto, leito = texto.rsplit(sep, 1)
            return quarto.strip(), leito.strip()
    return texto, ""


class PatientService:
    def __init__(self, repository: PatientRepository):
        self.repository = repository

    def _transform_patient(self, ficha: dict) -> dict:
        if not ficha:
            return {}
        
        perfil = ficha.get("perfil", "medio").lower()
        cama_id = ficha.get("cama_id")
        
        quarto, leito = dividir_cama(cama_id)
        room = quarto or None
        bed = leito or None

        # Map perfil to riskLevel
        perfil_map = {
            "alto": "high",
            "medio": "medium",
            "baixo": "low"
        }

        return {
            "id": ficha.get("paciente_id"),
            "name": ficha.get("nome"),
            "room": room,
            "bed": bed,
            "riskLevel": perfil_map.get(perfil, "medium"),
            "repositioningInterval": intervalo_horas(perfil),
            "createdAt": ficha.get("created_at"),
            "updatedAt": ficha.get("updated_at"),
            # A tela precisa saber a qual ala o paciente pertence: com duas
            # unidades, "Leito 12" sozinho e ambiguo — existe um em cada.
            "unitId": ficha.get("unidade_id"),
        }

    def list_patients(
        self, unidades: set[int] | None = None, incluir_alta: bool = False
    ) -> List[dict]:
        fichas = self.repository.list_all(unidades=unidades, incluir_alta=incluir_alta)
        return [self._transform_patient(ficha) for ficha in fichas]

    def get_patient(self, paciente_id: str) -> Optional[dict]:
        ficha = self.repository.get_by_id(paciente_id)
        if not ficha:
            return None
        return self._transform_patient(ficha)

    def _esquecer_no_motor(self, paciente_id: str) -> None:
        """Tira o paciente do cache em memoria do PROCESSADOR.

        O repositorio apaga a linha em `estado_incremental`, mas o motor guarda
        os estados num dict em memoria e so le o banco na subida. Sem os dois, o
        paciente transferido continuaria sendo avaliado com `run_inicio`,
        `baseline_postura` e `_ultima_ts` do leito anterior ate o proximo
        restart — que e justamente o que a transferencia precisa zerar.

        Import tardio: `ingestao_service` importa deste modulo.
        """
        try:
            from interface.services.ingestao_service import PROCESSADOR

            PROCESSADOR.esquecer_paciente(paciente_id)
        except Exception:
            logger.warning("motor_nao_esqueceu_paciente", paciente_id=paciente_id, exc_info=True)

    def admit_patient(self, payload: FrontendCreatePatient, usuario: str | None = None) -> dict:
        return self.create_patient(payload, usuario=usuario)

    def discharge_patient(
        self, paciente_id: str, motivo: str | None = None, usuario: str | None = None
    ) -> dict:
        resultado = self.repository.dar_alta(paciente_id, motivo=motivo, usuario=usuario)
        self._esquecer_no_motor(paciente_id)
        return resultado

    def transfer_patient(
        self, paciente_id: str, room: str | None, bed: str | None, usuario: str | None = None
    ) -> dict:
        resultado = self.repository.transferir(
            paciente_id, compor_cama(room, bed), usuario=usuario
        )
        self._esquecer_no_motor(paciente_id)
        return resultado

    def swap_beds(self, paciente_a: str, paciente_b: str, usuario: str | None = None) -> dict:
        resultado = self.repository.trocar_leitos(paciente_a, paciente_b, usuario=usuario)
        for pid in (paciente_a, paciente_b):
            self._esquecer_no_motor(pid)
        return resultado

    def create_patient(self, payload: FrontendCreatePatient, usuario: str | None = None) -> dict:
        # riskLevel ja vem validado pelo schema (FrontendCreatePatient), entao
        # aqui nao ha default silencioso: um valor fora do mapa e um bug, nao
        # um paciente rebaixado para risco medio sem aviso.
        perfil = _RISK_PARA_PERFIL[payload.riskLevel.lower()]

        cama_id = compor_cama(payload.room, payload.bed)

        novo_paciente = self.repository.create(
            nome=payload.name,
            perfil=perfil,
            cama_id=cama_id,
            observacoes=payload.notes,
            rotinas=None,
            registrado_por=usuario,
            unidade_id=payload.unitId,
        )
        return self._transform_patient(novo_paciente)

    def update_patient(self, paciente_id: str, payload: FrontendCreatePatient) -> dict:
        # riskLevel ja vem validado pelo schema (FrontendCreatePatient), entao
        # aqui nao ha default silencioso: um valor fora do mapa e um bug, nao
        # um paciente rebaixado para risco medio sem aviso.
        perfil = _RISK_PARA_PERFIL[payload.riskLevel.lower()]

        cama_id = compor_cama(payload.room, payload.bed)

        atualizado = self.repository.update(
            paciente_id=paciente_id,
            nome=payload.name,
            perfil=perfil,
            cama_id=cama_id,
            observacoes=payload.notes,
            rotinas=None
        )
        return self._transform_patient(atualizado)

    def delete_patient(self, paciente_id: str) -> Optional[dict]:
        """Remove o paciente. Devolve o que foi apagado, ou None se nao existia."""
        return self.repository.delete(paciente_id)

    def get_patient_by_bed(self, cama_id: str) -> Optional[dict]:
        return self.repository.get_by_cama(cama_id, include_routines=True)
