#!/usr/bin/env python3
"""
Script para testar as principais funcionalidades da API sem iniciar o servidor.
"""

import sys
from pathlib import Path

def test_dao():
    """Testa operações do DAO"""
    print("\n📊 Testando DAO...")
    
    from interface.dao import (
        listar_alertas_abertos,
        listar_fichas_pacientes,
        selecionar_alertas_janela,
    )
    
    db_path = "dados.db"
    
    # Testar listagem de alertas
    try:
        alertas = listar_alertas_abertos(db_path)
        print(f"✅ Alertas abertos: {len(alertas)}")
    except Exception as e:
        print(f"❌ Erro ao listar alertas: {e}")
        return False
    
    # Testar listagem de pacientes
    try:
        pacientes = listar_fichas_pacientes(db_path)
        print(f"✅ Pacientes cadastrados: {len(pacientes)}")
    except Exception as e:
        print(f"❌ Erro ao listar pacientes: {e}")
        return False
    
    # Testar seleção de alertas em janela
    try:
        from datetime import datetime, timedelta
        inicio = datetime.now() - timedelta(days=7)
        fim = datetime.now()
        alertas_janela = selecionar_alertas_janela(db_path, inicio, fim)
        print(f"✅ Alertas na última semana: {len(alertas_janela)}")
    except Exception as e:
        print(f"❌ Erro ao selecionar alertas: {e}")
        return False
    
    return True

def test_alert_engine():
    """Testa motor de alertas"""
    print("\n⚙️  Testando motor de alertas...")
    
    from modulo_alerta.engine import processar_alertas
    import pandas as pd
    from datetime import datetime, timedelta
    
    # Criar dados de teste
    inicio = datetime.now() - timedelta(hours=2)
    timestamps = [inicio + timedelta(minutes=i*5) for i in range(25)]
    postura = ['supino'] * 25  # 2 horas na mesma postura
    
    df_teste = pd.DataFrame({
        'timestamp': timestamps,
        'postura': postura
    })
    
    try:
        _, alertas = processar_alertas(df_teste, 'medio', 'PAC-TEST')
        print(f"✅ Alertas gerados: {len(alertas)}")
        if alertas:
            print(f"   Tipo: {alertas[0]['tipo']}")
    except Exception as e:
        print(f"❌ Erro no motor de alertas: {e}")
        return False
    
    return True

def test_data_generator():
    """Testa gerador de dados simulados"""
    print("\n🎲 Testando gerador de dados...")
    
    from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente
    
    try:
        perfil = PerfilPaciente()
        df = gerar_sessao_simulada(
            duracao_horas=1,
            seed=42,
            passo_min=5,
            perfil=perfil
        )
        print(f"✅ Sessão gerada: {len(df)} registros")
        print(f"   Posturas únicas: {df['postura'].nunique()}")
    except Exception as e:
        print(f"❌ Erro no gerador: {e}")
        return False
    
    return True

def test_exportador():
    """Testa exportador de relatórios"""
    print("\n📄 Testando exportador...")
    
    from ferramentas.exportador import ExportService, ExportFilters
    
    try:
        service = ExportService("dados.db")
        filters = ExportFilters()
        
        # Testar CSV
        csv_content = service.export_to_csv(filters)
        print(f"✅ CSV gerado: {len(csv_content)} caracteres")
        
        # Testar PDF
        pdf_bytes = service.export_to_pdf(filters)
        print(f"✅ PDF gerado: {len(pdf_bytes)} bytes")
    except Exception as e:
        print(f"❌ Erro no exportador: {e}")
        return False
    
    return True

def main():
    print("=" * 70)
    print("🧪 TESTE DE FUNCIONALIDADES DA API")
    print("=" * 70)
    
    results = {
        'DAO': test_dao(),
        'Motor de Alertas': test_alert_engine(),
        'Gerador de Dados': test_data_generator(),
        'Exportador': test_exportador(),
    }
    
    print("\n" + "=" * 70)
    print("📊 RESUMO DOS TESTES")
    print("=" * 70)
    
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"{status} {name}")
    
    all_ok = all(results.values())
    
    if all_ok:
        print("\n🎉 Todos os testes passaram!")
        print("\n✅ O sistema está funcionando corretamente.")
        return 0
    else:
        print("\n⚠️  Alguns testes falharam. Verifique os erros acima.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
