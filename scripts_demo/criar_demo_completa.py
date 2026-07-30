"""
Script para criar demonstração completa com 10 pacientes.
Demonstra a capacidade do sistema em escala real.
"""

import subprocess
import sys
from pathlib import Path
import requests
from time import sleep


BACKEND_URL = "http://127.0.0.1:8000"
_SCRIPT_DIR = Path(__file__).resolve().parent

# Lista de 10 pacientes com dados variados
PACIENTES_DEMO = [
    # Quarto 201 - Mix alto/médio
    {"name": "Maria Santos", "room": "201", "bed": "A", "risk": "high", "horas": 1},
    {"name": "Joao Silva", "room": "201", "bed": "B", "risk": "medium", "horas": 3},
    
    # Quarto 202 - Mix alto/baixo
    {"name": "Ana Costa", "room": "202", "bed": "A", "risk": "high", "horas": 1},
    {"name": "Pedro Oliveira", "room": "202", "bed": "B", "risk": "low", "horas": 6},
    
    # Quarto 203 - Mix médio/alto
    {"name": "Carlos Mendes", "room": "203", "bed": "A", "risk": "medium", "horas": 3},
    {"name": "Lucia Ferreira", "room": "203", "bed": "B", "risk": "high", "horas": 1},
    
    # Quarto 204 - Mix baixo/médio
    {"name": "Roberto Alves", "room": "204", "bed": "A", "risk": "low", "horas": 6},
    {"name": "Fernanda Lima", "room": "204", "bed": "B", "risk": "medium", "horas": 3},
    
    # Quarto 205 - Mix alto/baixo
    {"name": "Marcos Pereira", "room": "205", "bed": "A", "risk": "high", "horas": 1},
    {"name": "Patricia Souza", "room": "205", "bed": "B", "risk": "low", "horas": 6},
]


def mapear_perfil(risk_level: str) -> str:
    """Mapeia riskLevel (EN) para perfil (PT)."""
    mapping = {
        "high": "alto",
        "medium": "medio",
        "low": "baixo"
    }
    return mapping.get(risk_level, "medio")


def verificar_backend() -> bool:
    """Verifica se o backend está rodando."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/stats", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def criar_paciente(paciente: dict) -> str | None:
    """
    Cria paciente via API.
    Retorna o ID do paciente criado ou None em caso de erro.
    """
    payload = {
        "name": paciente["name"],
        "room": paciente["room"],
        "bed": paciente["bed"],
        "riskLevel": paciente["risk"],
        "notes": f"Paciente demo - Perfil {paciente['risk']}"
    }
    
    try:
        response = requests.post(f"{BACKEND_URL}/api/pacientes", json=payload)
        if response.status_code == 201:
            data = response.json()
            return data["id"]
        print(f"   ERRO ao criar {paciente['name']}: {response.status_code}")
        print(f"   {response.text}")
        return None
    except Exception as e:
        print(f"   ERRO ao criar {paciente['name']}: {e}")
        return None


def gerar_dados_paciente(pac_id: str, horas: int, perfil: str) -> bool:
    """
    Gera dados simulados para o paciente usando o script existente.
    Retorna True se sucesso, False caso contrário.
    """
    try:
        cmd = [
            sys.executable,
            str(_SCRIPT_DIR / "testar_simulacao_com_verificacao.py"),
            pac_id,
            str(horas),
            perfil
        ]
        
        # Executa o script de simulação (silencioso)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"   ERRO ao gerar dados: {e}")
        return False


def main():
    print("\n" + "=" * 80)
    print("CRIACAO DE DEMONSTRACAO COMPLETA - 10 PACIENTES")
    print("=" * 80)
    
    # 1. Verificar backend
    print("\n[1/3] Verificando backend...")
    if not verificar_backend():
        print("   ERRO: Backend nao esta rodando!")
        print("   Execute: .\\venv\\Scripts\\python.exe -m uvicorn interface.web:app --reload")
        sys.exit(1)
    print("   OK Backend rodando")
    
    # 2. Criar pacientes
    print("\n[2/3] Criando 10 pacientes...")
    pacientes_criados = []
    
    for i, pac in enumerate(PACIENTES_DEMO, 1):
        print(f"\n   [{i}/10] {pac['name']} - Quarto {pac['room']}{pac['bed']}")
        print(f"         Perfil: {pac['risk'].upper()}, Dados: {pac['horas']}h")
        
        pac_id = criar_paciente(pac)
        if pac_id:
            print(f"         OK Criado com ID: {pac_id}")
            pacientes_criados.append({
                **pac,
                "id": pac_id
            })
            sleep(0.2)  # Pequeno delay para evitar sobrecarga
        else:
            print("         FALHA ao criar paciente")
    
    if not pacientes_criados:
        print("\n   ERRO: Nenhum paciente foi criado!")
        sys.exit(1)
    
    print(f"\n   OK {len(pacientes_criados)}/10 pacientes criados")
    
    # 3. Gerar dados simulados
    print("\n[3/3] Gerando dados simulados...")
    sucesso = 0
    falhas = 0
    
    for i, pac in enumerate(pacientes_criados, 1):
        perfil = mapear_perfil(pac["risk"])
        print(f"\n   [{i}/{len(pacientes_criados)}] {pac['name']} ({pac['id']})")
        print(f"         Gerando {pac['horas']}h de dados (perfil: {perfil})...", end=" ")
        
        if gerar_dados_paciente(pac["id"], pac["horas"], perfil):
            print("OK")
            sucesso += 1
        else:
            print("FALHA")
            falhas += 1
        
        sleep(0.3)  # Delay entre gerações
    
    # 4. Resumo final
    print("\n" + "=" * 80)
    print("RESUMO DA DEMONSTRACAO")
    print("=" * 80)
    print(f"\nPacientes criados: {len(pacientes_criados)}/10")
    print(f"Dados gerados: {sucesso}/{len(pacientes_criados)}")
    if falhas > 0:
        print(f"Falhas: {falhas}")
    
    print("\nDistribuicao por perfil:")
    perfis = {"high": 0, "medium": 0, "low": 0}
    for pac in pacientes_criados:
        perfis[pac["risk"]] += 1
    
    print(f"   Alto risco:   {perfis['high']} pacientes (1h de dados)")
    print(f"   Medio risco:  {perfis['medium']} pacientes (3h de dados)")
    print(f"   Baixo risco:  {perfis['low']} pacientes (6h de dados)")
    
    print("\nQuartos ocupados:")
    quartos = {f"{pac['room']}{pac['bed']}" for pac in pacientes_criados}
    for q in sorted(quartos):
        print(f"   - Quarto {q}")
    
    print("\n" + "=" * 80)
    print("DEMO PRONTA!")
    print("=" * 80)
    print("\nAcesse o frontend para visualizar:")
    print("   http://localhost:5173")
    print("\nVerifique os dados gerados:")
    print("   .\\venv\\Scripts\\python.exe scripts_demo\\ver_pacientes.py")
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
