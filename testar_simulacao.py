"""Script para testar simulação de dados end-to-end"""

import sys
from datetime import datetime
from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente, PERFIS_PREDEFINIDOS
from modulo_alerta.engine import processar_alertas
from interface.dao import inserir_grade, inserir_alertas, obter_ficha_paciente

DB_PATH = "dados.db"

def test_simulation(paciente_id: str = "P1", duracao_horas: int = 2, perfil_nome: str = "medio"):
    """Testa simulação completa: gerar → processar → salvar"""
    
    print(f"=== TESTE DE SIMULACAO ===")
    print(f"Paciente: {paciente_id}")
    print(f"Duracao: {duracao_horas}h")
    print(f"Perfil: {perfil_nome}\n")
    
    # 1. Verificar se paciente existe
    print("1. Verificando paciente...")
    ficha = obter_ficha_paciente(DB_PATH, paciente_id)
    if not ficha:
        print(f"   ERRO: Paciente {paciente_id} nao encontrado!")
        print("   Crie o paciente primeiro no frontend")
        return False
    print(f"   OK: {ficha.get('nome', paciente_id)}")
    
    # 2. Gerar dados simulados
    print(f"\n2. Gerando {duracao_horas}h de dados simulados...")
    try:
        perfil_params = PERFIS_PREDEFINIDOS.get(perfil_nome, PERFIS_PREDEFINIDOS["medio"])
        perfil = PerfilPaciente(**perfil_params)
        
        df_grade, contextos = gerar_sessao_simulada(
            duracao_horas=duracao_horas,
            seed=42,
            passo_min=5,
            perfil=perfil,
            incluir_contexto=True
        )
        
        print(f"   OK: {len(df_grade)} eventos de postura gerados")
        print(f"   Contextos: {len(contextos)}")
        print(f"   Colunas: {df_grade.columns.tolist()}")
        print(f"   Periodo: {df_grade['timestamp'].min()} ate {df_grade['timestamp'].max()}")
        
    except Exception as e:
        print(f"   ERRO ao gerar dados: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. Adicionar paciente_id ao DataFrame
    print(f"\n3. Adicionando paciente_id ao DataFrame...")
    df_grade.insert(0, "paciente_id", paciente_id)
    print(f"   OK: Colunas atualizadas: {df_grade.columns.tolist()}")
    
    # 4. Salvar grades no banco
    print(f"\n4. Salvando grades no banco...")
    try:
        num_inseridos = inserir_grade(DB_PATH, df_grade, paciente_id=paciente_id)
        print(f"   OK: {num_inseridos} eventos salvos")
    except Exception as e:
        print(f"   ERRO ao salvar grades: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Processar alertas
    print(f"\n5. Processando alertas...")
    try:
        df_norm, alertas = processar_alertas(
            df_grade[["timestamp", "postura"]],
            perfil_nome,
            paciente_id
        )
        print(f"   OK: {len(alertas)} alertas gerados")
        
        if alertas:
            print(f"\n   Primeiros 3 alertas:")
            for i, alerta in enumerate(alertas[:3], 1):
                print(f"     {i}. {alerta.get('inicio')} - {alerta.get('tipo')} - {alerta.get('perfil')}")
        else:
            print(f"   ATENCAO: Nenhum alerta gerado (pode ser normal se periodo curto ou muitos movimentos)")
            
    except Exception as e:
        print(f"   ERRO ao processar alertas: {e}")
        import traceback
        traceback.print_exc()
        alertas = []
    
    # 6. Salvar alertas no banco
    if alertas:
        print(f"\n6. Salvando alertas no banco...")
        try:
            inserir_alertas(DB_PATH, alertas)
            print(f"   OK: {len(alertas)} alertas salvos")
        except Exception as e:
            print(f"   AVISO: Erro ao salvar alertas: {e}")
    else:
        print(f"\n6. Nenhum alerta para salvar")
    
    # 7. Verificar resultados
    print(f"\n7. Verificando resultados no banco...")
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM grade WHERE paciente_id = ?", (paciente_id,))
    grade_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alertas WHERE paciente_id = ?", (paciente_id,))
    alertas_total = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"   Grade total: {grade_total} eventos")
    print(f"   Alertas total: {alertas_total}")
    
    print(f"\n=== SIMULACAO CONCLUIDA COM SUCESSO ===")
    print(f"Eventos: {num_inseridos}")
    print(f"Alertas: {len(alertas)}")
    print(f"\nVerifique no Dashboard e Timeline!")
    
    return True


if __name__ == "__main__":
    paciente_id = sys.argv[1] if len(sys.argv) > 1 else "P1"
    duracao = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    perfil = sys.argv[3] if len(sys.argv) > 3 else "medio"
    
    test_simulation(paciente_id, duracao, perfil)
