"""Service layer for Patient operations."""
from __future__ import annotations

from typing import List, Optional
from interface.repositories.pacientes import PatientRepository
from interface.schemas import FrontendCreatePatient

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


class PatientService:
    def __init__(self, repository: PatientRepository):
        self.repository = repository

    def _transform_patient(self, ficha: dict) -> dict:
        if not ficha:
            return {}
        
        perfil = ficha.get("perfil", "medio").lower()
        cama_id = ficha.get("cama_id")
        
        room = None
        bed = None
        if cama_id:
            parts = cama_id.split("-")
            if len(parts) >= 2:
                room = parts[0]
                bed = parts[1]
            else:
                room = cama_id
                
        # Map perfil to riskLevel
        perfil_map = {
            "alto": "high",
            "medio": "medium",
            "baixo": "low"
        }
        
        # Map perfil to default interval (hours)
        interval_map = {
            "alto": 2,
            "medio": 3,
            "baixo": 4
        }
        
        return {
            "id": ficha.get("paciente_id"),
            "name": ficha.get("nome"),
            "room": room,
            "bed": bed,
            "riskLevel": perfil_map.get(perfil, "medium"),
            "repositioningInterval": interval_map.get(perfil, 3),
            "createdAt": ficha.get("created_at"),
            "updatedAt": ficha.get("updated_at")
        }

    def list_patients(self) -> List[dict]:
        fichas = self.repository.list_all()
        return [self._transform_patient(ficha) for ficha in fichas]

    def get_patient(self, paciente_id: str) -> Optional[dict]:
        ficha = self.repository.get_by_id(paciente_id)
        if not ficha:
            return None
        return self._transform_patient(ficha)

    def create_patient(self, payload: FrontendCreatePatient) -> dict:
        # riskLevel ja vem validado pelo schema (FrontendCreatePatient), entao
        # aqui nao ha default silencioso: um valor fora do mapa e um bug, nao
        # um paciente rebaixado para risco medio sem aviso.
        perfil = _RISK_PARA_PERFIL[payload.riskLevel.lower()]

        # Construct cama_id
        cama_id = None
        if payload.room and payload.bed:
            cama_id = f"{payload.room}-{payload.bed}"
        elif payload.room:
            cama_id = payload.room
        elif payload.bed:
            cama_id = payload.bed

        novo_paciente = self.repository.create(
            nome=payload.name,
            perfil=perfil,
            cama_id=cama_id,
            observacoes=payload.notes,
            rotinas=None
        )
        return self._transform_patient(novo_paciente)

    def update_patient(self, paciente_id: str, payload: FrontendCreatePatient) -> dict:
        # riskLevel ja vem validado pelo schema (FrontendCreatePatient), entao
        # aqui nao ha default silencioso: um valor fora do mapa e um bug, nao
        # um paciente rebaixado para risco medio sem aviso.
        perfil = _RISK_PARA_PERFIL[payload.riskLevel.lower()]

        # Construct cama_id
        cama_id = None
        if payload.room and payload.bed:
            cama_id = f"{payload.room}-{payload.bed}"
        elif payload.room:
            cama_id = payload.room
        elif payload.bed:
            cama_id = payload.bed

        atualizado = self.repository.update(
            paciente_id=paciente_id,
            nome=payload.name,
            perfil=perfil,
            cama_id=cama_id,
            observacoes=payload.notes,
            rotinas=None
        )
        return self._transform_patient(atualizado)

    def get_patient_by_bed(self, cama_id: str) -> Optional[dict]:
        return self.repository.get_by_cama(cama_id, include_routines=True)
