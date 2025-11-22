from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta

from interface.api_shared import DB_PATH, DEFAULT_PERFIL
from interface.schemas import PacienteConfigResponse, RotinaConfig, FrontendCreatePatient
from interface.repositories.pacientes import PatientRepository
from interface.services.paciente_service import PatientService
from dados_simulados.gerador import (
    gerar_sessao_simulada, 
    gerar_eventos_sessao, 
    PerfilPaciente, 
    PERFIS_PREDEFINIDOS
)
from interface.dao import inserir_grade, inserir_eventos, inserir_alertas
from modulo_alerta.engine import processar_alertas

router = APIRouter(tags=["pacientes"])

# Dependency Injection (Manual for now)
repository = PatientRepository(DB_PATH)
service = PatientService(repository)


@router.post("/pacientes", response_model=dict, status_code=status.HTTP_201_CREATED)
async def criar_paciente_endpoint(payload: FrontendCreatePatient) -> dict:
    """Criar um novo paciente."""
    try:
        return service.create_patient(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/pacientes", response_model=List[dict], status_code=status.HTTP_200_OK)
async def listar_pacientes_endpoint() -> List[dict]:
    """Listar todos os pacientes."""
    return service.list_patients()


@router.get(
    "/pacientes/cama/{cama_id}",
    response_model=PacienteConfigResponse,
    status_code=status.HTTP_200_OK,
)
async def obter_paciente_por_cama_endpoint(cama_id: str) -> PacienteConfigResponse:
    ficha = service.get_patient_by_bed(cama_id)
    if ficha is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "paciente_nao_encontrado",
                "message": "Nenhum paciente vinculado a esta cama.",
            },
        )
    rotinas_payload: List[RotinaConfig] = []
    for idx, rotina in enumerate(ficha.get("rotinas") or []):
        try:
            duracao_val = int(rotina.get("duracao_min", 0) or 0)
        except (TypeError, ValueError):
            duracao_val = 0
        try:
            sort_val = int(rotina.get("sort_order", idx))
        except (TypeError, ValueError):
            sort_val = idx
        rotinas_payload.append(
            RotinaConfig(
                label=str(rotina.get("label", "")),
                inicio=str(rotina.get("inicio", "")),
                duracao_min=duracao_val,
                descricao=rotina.get("descricao"),
                ativo=bool(rotina.get("ativo", True)),
                sort_order=sort_val,
            )
        )
    return PacienteConfigResponse(
        paciente_id=str(ficha.get("paciente_id", "")),
        nome=ficha.get("nome"),
        cama_id=str(ficha.get("cama_id") or ""),
        perfil=str(ficha.get("perfil") or DEFAULT_PERFIL),
        observacoes=ficha.get("observacoes"),
        updated_at=ficha.get("updated_at"),
        rotinas=rotinas_payload,
    )


@router.get("/pacientes/{paciente_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def obter_paciente_endpoint(paciente_id: str) -> dict:
    """Obter um paciente pelo ID."""
    paciente = service.get_patient(paciente_id)
    if not paciente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado")
    return paciente


class SimulationRequest(BaseModel):
    duracao_horas: int
    seed: int = 42
    perfil: str = "medio"

class SimulationResult(BaseModel):
    success: bool
    eventos: int
    alertas: int
    duracao: float
    message: str

@router.post("/pacientes/{paciente_id}/simular", response_model=SimulationResult, status_code=status.HTTP_200_OK)
async def simular_paciente_endpoint(paciente_id: str, payload: SimulationRequest) -> SimulationResult:
    """Simular dados históricos para um paciente."""
    
    # 1. Validate patient exists
    paciente = service.get_patient(paciente_id)
    if not paciente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado")

    # 2. Prepare parameters
    duracao = payload.duracao_horas
    seed = payload.seed
    perfil_nome = payload.perfil.lower()
    
    if perfil_nome not in PERFIS_PREDEFINIDOS:
        perfil_nome = "medio"
        
    perfil_params = PERFIS_PREDEFINIDOS[perfil_nome]
    perfil_obj = PerfilPaciente(**perfil_params)
    
    # 3. Generate Data
    # Start time: now - duration
    agora = datetime.now().replace(second=0, microsecond=0)
    inicio = agora - timedelta(hours=duracao)
    
    # Generate Grade (for engine)
    df_grade, _ = gerar_sessao_simulada(
        duracao_horas=duracao,
        seed=seed,
        passo_min=5,
        inicio=inicio,
        perfil=perfil_obj,
        incluir_contexto=True
    )
    
    # Generate Raw Events (for visualization)
    df_eventos = gerar_eventos_sessao(
        duracao_horas=duracao,
        seed=seed,
        inicio=inicio,
        perfil=perfil_obj
    )
    
    # 4. Persist Data
    # Insert Grade
    grade_count = inserir_grade(DB_PATH, df_grade, paciente_id)
    
    # Insert Events
    # Ensure df_eventos has 'tipo' column (gerar_eventos_sessao returns 'origem')
    if "origem" in df_eventos.columns:
        df_eventos["tipo"] = df_eventos["origem"]
    eventos_count = inserir_eventos(DB_PATH, df_eventos, paciente_id)
    
    # 5. Process Alerts
    # We use the generated grade to calculate alerts
    _, alertas = processar_alertas(df_grade, perfil_nome, paciente_id)
    alertas_count = inserir_alertas(DB_PATH, alertas)
    
    return SimulationResult(
        success=True,
        eventos=grade_count,
        alertas=alertas_count,
        duracao=duracao,
        message=f"Simulacao concluida: {grade_count} amostras, {alertas_count} alertas gerados."
    )

