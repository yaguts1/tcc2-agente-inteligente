"""Camada de compatibilidade para a antiga API monolitica de persistencia SQLite.

Este modulo era um unico arquivo de ~1300 linhas com SQL cru inline para
todos os dominios (pacientes, usuarios, alertas, timeline, devices, grade).
A logica real foi movida para `interface/repositories/` (um modulo por
dominio) e `interface/db_core.py` (conexao/schema compartilhados). Este
arquivo permanece apenas como fachada de compatibilidade — reexporta as
mesmas funcoes com as mesmas assinaturas, para nao quebrar os ~30 pontos
de import existentes (routers, scripts, testes) nesta mesma leva de
refatoracao. Novo codigo deve importar diretamente de `interface.repositories.*`.
"""

from __future__ import annotations

from typing import List, Sequence

from interface.db_core import (
    ISO_FORMAT,
    connect as _connect,
    ensure_paciente as _ensure_paciente,
    criar_esquema,
)
from interface.repositories.users import UserRepository
from interface.repositories.pacientes import (
    PatientRepository,
    PACIENTE_ID_PREFIX,
    PERFIS_VALIDOS,
)
from interface.repositories.grade import (
    inserir_grade,
    inserir_eventos,
    selecionar_grade_janela,
)
from interface.repositories.alertas import (
    inserir_alertas,
    contar_por_paciente,
    listar_alertas_abertos,
    selecionar_alertas_janela,
    listar_pacientes,
    alterar_status_alerta,
)
from interface.repositories.timeline import (
    inserir_timeline_event,
    selecionar_timeline,
)
from interface.repositories.devices import (
    registrar_device,
    resolver_paciente_por_device_em,
    inserir_device_event,
    listar_device_events,
    listar_devices,
    delete_device_event,
)


# --- Usuarios (delega para UserRepository) ---------------------------------

def criar_usuario(db_path: str, username: str, password_hash: str, display_name: str | None = None) -> None:
    """Cria um usuario novo. Levanta ValueError se ja existir."""
    UserRepository(db_path).create(username, password_hash, display_name)


def obter_usuario_por_nome(db_path: str, username: str) -> dict | None:
    return UserRepository(db_path).get_by_username(username)


# --- Pacientes / fichas / documentos (delega para PatientRepository) ------

def proximo_identificador_paciente(db_path: str, prefixo: str = PACIENTE_ID_PREFIX) -> str:
    return PatientRepository(db_path).proximo_identificador(prefixo)


def listar_fichas_pacientes(db_path: str, incluir_rotinas: bool = False) -> List[dict]:
    return PatientRepository(db_path).list_all(incluir_rotinas)


def obter_ficha_paciente(db_path: str, paciente_id: str, incluir_rotinas: bool = False) -> dict | None:
    return PatientRepository(db_path).get_by_id(paciente_id, incluir_rotinas)


def obter_ficha_por_cama(db_path: str, cama_id: str, incluir_rotinas: bool = False) -> dict | None:
    return PatientRepository(db_path).get_by_cama(cama_id, incluir_rotinas)


def criar_paciente(
    db_path: str,
    nome: str,
    perfil: str,
    cama_id: str | None = None,
    observacoes: str | None = None,
    rotinas: Sequence[dict] | None = None,
) -> dict:
    return PatientRepository(db_path).create(nome, perfil, cama_id, observacoes, rotinas)


def atualizar_paciente(
    db_path: str,
    paciente_id: str,
    nome: str,
    perfil: str,
    cama_id: str | None = None,
    observacoes: str | None = None,
    rotinas: Sequence[dict] | None = None,
) -> dict:
    return PatientRepository(db_path).update(paciente_id, nome, perfil, cama_id, observacoes, rotinas)


def remover_paciente(db_path: str, paciente_id: str) -> int:
    return PatientRepository(db_path).delete(paciente_id)


def ensure_minimal_paciente_ficha(
    db_path: str,
    paciente_id: str,
    nome: str | None = None,
    perfil: str | None = None,
    cama_id: str | None = None,
) -> None:
    PatientRepository(db_path).ensure_minimal_ficha(paciente_id, nome, perfil, cama_id)
