"""
Script para testar simulação e verificar se alertas foram gerados.
Executa tudo em um único processo sem depender de servidor externo.
"""

import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente, PERFIS_PREDEFINIDOS
from interface.dao import inserir_grade, inserir_alertas
from modulo_alerta.engine import processar_alertas


def limpar_dados_paciente(db_path: str, paciente_id: str):
    """Remove dados antigos do paciente."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM grade WHERE paciente_id = ?", (paciente_id,))
    cursor.execute("DELETE FROM alertas WHERE paciente_id = ?", (paciente_id,))
    
    deletados_grade = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deletados_grade


def verificar_dados(db_path: str, paciente_id: str):
    """Verifica dados do paciente no banco."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Grade
    cursor.execute(
        "SELECT COUNT(*), MIN(ts), MAX(ts) FROM grade WHERE paciente_id = ?",
        (paciente_id,)
    )
    grade_info = cursor.fetchone()
    
    # Alertas
    cursor.execute(
        "SELECT COUNT(*), MIN(inicio), MAX(inicio) FROM alertas WHERE paciente_id = ?",
        (paciente_id,)
    )
    alertas_info = cursor.fetchone()
    
    # Alertas últimas 24h
    limite_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM alertas WHERE paciente_id = ? AND inicio >= ?",
        (paciente_id, limite_24h)
    )
    alertas_24h = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'grade_count': grade_info[0],
        'grade_inicio': grade_info[1],
        'grade_fim': grade_info[2],
        'alertas_count': alertas_info[0],
        'alertas_inicio': alertas_info[1],
        'alertas_fim': alertas_info[2],
        'alertas_24h': alertas_24h
    }


def main():
    if len(sys.argv) < 4:
        print("Uso: python testar_simulacao_com_verificacao.py <paciente_id> <horas> <perfil>")
        print("Exemplo: python testar_simulacao_com_verificacao.py P1 4 alto")
        sys.exit(1)
    
    paciente_id = sys.argv[1]
    duracao_horas = int(sys.argv[2])
    perfil_key = sys.argv[3]
    db_path = "dados.db"
    
    print(f"\n{'='*70}")
    print(f"TESTE DE SIMULACAO - {paciente_id}")
    print(f"{'='*70}\n")
    
    # 1. Limpar dados antigos
    print(f"[1] Limpando dados antigos de {paciente_id}...")
    deletados = limpar_dados_paciente(db_path, paciente_id)
    print(f"   OK {deletados} registros removidos\n")
    
    # 2. Gerar dados simulados
    print(f"[2] Gerando simulacao ({duracao_horas}h, perfil {perfil_key})...")
    
    perfil_params = PERFIS_PREDEFINIDOS.get(perfil_key, PERFIS_PREDEFINIDOS["medio"])
    perfil = PerfilPaciente(**perfil_params)
    
    df_grade, contextos = gerar_sessao_simulada(
        duracao_horas=duracao_horas,
        seed=42,
        passo_min=5,
        perfil=perfil,
        incluir_contexto=True
    )
    
    print(f"   OK {len(df_grade)} eventos de postura gerados")
    print(f"   Periodo: {df_grade['timestamp'].min()} ate {df_grade['timestamp'].max()}\n")
    
    # 3. Salvar grade
    print("[3] Salvando grade no banco...")
    df_grade.insert(0, "paciente_id", paciente_id)
    count = inserir_grade(db_path, df_grade, paciente_id=paciente_id)
    print(f"   OK {count} eventos salvos na tabela grade\n")
    
    # 4. Processar alertas
    print("[4] Processando alertas...")
    
    try:
        _, alertas = processar_alertas(
            df_grade[["timestamp", "postura"]],
            perfil_key,
            paciente_id
        )
        
        print(f"   OK {len(alertas)} alertas identificados")
        
        if alertas:
            # Mostrar alguns alertas
            print("\n   Primeiros 3 alertas:")
            for i, alerta in enumerate(alertas[:3], 1):
                # Alertas podem ser dicts ou objetos
                if isinstance(alerta, dict):
                    tipo = alerta.get('tipo_alerta', alerta.get('tipo', 'desconhecido'))
                    inicio = alerta.get('inicio', 'N/A')
                    sev = alerta.get('severidade', 'N/A')
                else:
                    tipo = alerta.tipo_alerta
                    inicio = alerta.inicio
                    sev = alerta.severidade
                print(f"      {i}. {tipo} - {inicio} (severidade: {sev})")
        
        print()
        
    except Exception as e:
        print(f"   ERRO ao processar alertas: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 5. Salvar alertas
    print("[5] Salvando alertas no banco...")
    
    if alertas:
        count = inserir_alertas(db_path, alertas)
        print(f"   OK {count} alertas salvos na tabela alertas\n")
    else:
        print("   AVISO: Nenhum alerta para salvar\n")
    
    # 6. Verificar banco de dados
    print("[6] Verificando dados no banco...")
    dados = verificar_dados(db_path, paciente_id)
    
    print("\n   RESULTADOS:")
    print(f"   {'-'*60}")
    print("   Grade:")
    print(f"     - Total de eventos: {dados['grade_count']}")
    print(f"     - Periodo: {dados['grade_inicio']} ate {dados['grade_fim']}")
    print("\n   Alertas:")
    print(f"     - Total geral: {dados['alertas_count']}")
    
    if dados['alertas_count'] > 0:
        print(f"     - Periodo: {dados['alertas_inicio']} ate {dados['alertas_fim']}")
        print(f"     - Ultimas 24h: {dados['alertas_24h']}")
    
    print(f"   {'-'*60}\n")
    
    # 7. Resumo final
    print(f"{'='*70}")
    if dados['alertas_24h'] > 0:
        print(f"SUCESSO! {dados['alertas_24h']} alertas visiveis no Dashboard")
        print(f"   -> Va para Dashboard e filtre por paciente {paciente_id}")
        print(f"   -> Va para Timeline e selecione paciente {paciente_id}")
    elif dados['alertas_count'] > 0:
        print("ATENCAO! Alertas foram gerados, mas estao fora da janela de 24h")
        print(f"   -> Total de alertas: {dados['alertas_count']}")
        print("   -> Nao aparecerao no Dashboard (mostra apenas ultimas 24h)")
        print("   -> Aparecerao na Timeline (mostra historico completo)")
    else:
        print("PROBLEMA! Nenhum alerta foi gerado")
        print(f"   -> Verifique o perfil {perfil_key}")
        print("   -> Ajuste parametros de duracao ou perfil")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
