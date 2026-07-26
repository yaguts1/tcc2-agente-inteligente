from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import timedelta

from interface.api_shared import DB_PATH, DEFAULT_PERFIL
from interface.dependencies import exigir_papel, get_current_user, verificar_token_dispositivo
from interface.tempo import agora_utc_naive
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

# Todo o CRUD de pacientes exige sessao autenticada: sao dados clinicos
# identificaveis (nome, leito, perfil de risco). Antes o router inteiro era
# publico — dava para ler, criar e alterar pacientes sem credencial nenhuma.
router = APIRouter(tags=["pacientes"], dependencies=[Depends(get_current_user)])

# Router separado para o endpoint que o FIRMWARE consome
# (GET /api/pacientes/cama/{cama_id}, ver firmware/esp32_replay/esp32_replay.ino):
# um ESP32 nao tem sessao de usuario, entao aqui vale o token de dispositivo,
# o mesmo usado por /eventos e /grade — e nao o JWT.
router_dispositivos = APIRouter(
    tags=["pacientes"], dependencies=[Depends(verificar_token_dispositivo)]
)

# Dependency Injection (Manual for now)
repository = PatientRepository(DB_PATH)
service = PatientService(repository)


@router.post("/pacientes", response_model=dict, status_code=status.HTTP_201_CREATED)
def criar_paciente_endpoint(payload: FrontendCreatePatient) -> dict:
    """Criar um novo paciente."""
    try:
        return service.create_patient(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/pacientes", response_model=List[dict], status_code=status.HTTP_200_OK)
def listar_pacientes_endpoint() -> List[dict]:
    """Listar todos os pacientes."""
    return service.list_patients()


@router.get("/perfis-risco", status_code=status.HTTP_200_OK)
def listar_perfis_risco() -> dict:
    """Intervalo de reposicionamento de cada perfil de risco.

    Existe para o formulário mostrar o intervalo correto ANTES de salvar, sem
    manter uma cópia da tabela no frontend. Já houve dois mapas divergentes
    (motor 60/90/120 min vs. tela 2/3/4 h, o dobro) informando coisas
    diferentes sobre o mesmo paciente; um terceiro no JavaScript repetiria o
    problema. A fonte é a configuração que o motor de alertas usa.
    """
    from interface.services.paciente_service import intervalo_horas

    return {
        nivel: intervalo_horas(perfil)
        for nivel, perfil in (("high", "alto"), ("medium", "medio"), ("low", "baixo"))
    }


@router_dispositivos.get(
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
def obter_paciente_endpoint(paciente_id: str) -> dict:
    """Obter um paciente pelo ID."""
    paciente = service.get_patient(paciente_id)
    if not paciente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado")
    return paciente

@router.patch("/pacientes/{paciente_id}", response_model=dict, status_code=status.HTTP_200_OK)
def atualizar_paciente_endpoint(paciente_id: str, payload: FrontendCreatePatient) -> dict:
    """Atualizar um paciente existente."""
    try:
        return service.update_patient(paciente_id, payload)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente nao encontrado")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/pacientes/{paciente_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(exigir_papel("admin"))],
)
async def remover_paciente_endpoint(paciente_id: str) -> dict:
    """Remove um paciente e todo o rastro clinico dele.

    A rota nao existia. O `PatientRepository.delete` e o `dao.remover_paciente`
    ja estavam escritos e sem nenhum chamador, e a tela de Pacientes tinha o
    botao "Excluir" com dialogo de confirmacao chamando `DELETE /api/pacientes/
    {id}` — que respondia 405. O usuario confirmava a exclusao, via "Erro ao
    remover paciente" e o paciente continuava na lista.

    Restrito a admin, pelo mesmo motivo de `/simular`: e uma acao irreversivel
    sobre o historico clinico de uma pessoa. O acesso ja entra na trilha de
    auditoria pelo middleware (a rota casa com `/api/pacientes`), entao fica
    registrado QUEM removeu e QUANDO.
    """
    try:
        removidos = service.delete_patient(paciente_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if removidos is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "paciente_nao_encontrado", "message": "Paciente nao encontrado"},
        )
    # A listagem de alertas e cacheada por 30s. Sem invalidar, os alertas do
    # paciente recem-removido continuariam sendo servidos do cache — a tela
    # mostraria por meio minuto alertas de alguem que ja nao existe.
    from interface.api_shared import api_cache

    await api_cache.clear()
    return {"ok": True, "paciente_id": paciente_id, "removidos": removidos}


class SimulationRequest(BaseModel):
    duracao_horas: int
    seed: int = 42
    perfil: str = "medio"

class SimulationResult(BaseModel):
    success: bool
    eventos: int
    """Eventos brutos gravados (tabela `eventos`)."""
    amostras: int = 0
    """Amostras da grade de postura gravadas (tabela `grade`)."""
    alertas: int
    duracao: float
    message: str

@router.post(
    "/pacientes/{paciente_id}/simular",
    response_model=SimulationResult,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(exigir_papel("admin"))],
)
def simular_paciente_endpoint(paciente_id: str, payload: SimulationRequest) -> SimulationResult:
    """Simular dados históricos para um paciente.

    Restrito a admin: grava eventos, grade e ALERTAS sintéticos no mesmo banco
    dos dados reais. Num ambiente de produção, dado simulado misturado ao
    histórico clínico do paciente é indistinguível do que veio do sensor.
    """
    
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
    # Start time: now - duration. `inicio` no banco é UTC naive (ver interface/tempo.py),
    # entao "agora" precisa ser UTC — datetime.now() local deslocaria os timestamps
    # gerados pelo offset do fuso do servidor.
    agora = agora_utc_naive().replace(microsecond=0)
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
    
    # `eventos` reportava grade_count — a contagem de AMOSTRAS da grade — e o
    # eventos_count real era calculado e descartado. A tela exibia "N eventos"
    # mostrando outro numero. Agora cada campo carrega a grandeza do seu nome.
    return SimulationResult(
        success=True,
        eventos=eventos_count,
        amostras=grade_count,
        alertas=alertas_count,
        duracao=duracao,
        message=(
            f"Simulacao concluida: {grade_count} amostras, {eventos_count} eventos "
            f"e {alertas_count} alertas gerados."
        ),
    )

