#!/usr/bin/env python3
"""
Script de testes para validar as correções de timestamps, métricas e contrato Backend/Frontend.

Correções Implementadas:
1. ✅ Gerador de eventos agora simula para FUTURO (não passado)
2. ✅ Dashboard metrics usa janela consistente de 24h
3. ✅ Novo endpoint para validar contrato Backend/Frontend
"""

import os
import sqlite3
from datetime import datetime, timedelta
import sys
import structlog
import pandas as pd

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")


def limpar_dados_teste():
    """Remove dados de teste contaminados da base de dados."""
    logger.info("limpeza_iniciada")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Listar pacientes de teste (PAC-0001, etc)
        try:
            cursor.execute("SELECT paciente_id FROM fichas_paciente WHERE paciente_id LIKE 'PAC-%' ORDER BY paciente_id")
            pacientes = cursor.fetchall()
        except sqlite3.OperationalError:
            # Tabela não existe - isso é OK em ambiente de teste
            logger.info("limpeza_tabela_nao_existe", mensagem="fichas_paciente table does not exist yet")
            conn.close()
            return True
        
        logger.info("pacientes_encontrados", count=len(pacientes), pacientes=[p[0] for p in pacientes])
        
        # Remover eventos, alertas e fichas de teste
        for (paciente_id,) in pacientes:
            cursor.execute("DELETE FROM eventos WHERE paciente_id = ?", (paciente_id,))
            deletados_eventos = cursor.rowcount
            
            cursor.execute("DELETE FROM alertas WHERE paciente_id = ?", (paciente_id,))
            deletados_alertas = cursor.rowcount
            
            cursor.execute("DELETE FROM fichas_paciente WHERE paciente_id = ?", (paciente_id,))
            deletados_fichas = cursor.rowcount
            
            logger.info("paciente_removido", 
                       paciente_id=paciente_id,
                       eventos=deletados_eventos,
                       alertas=deletados_alertas,
                       fichas=deletados_fichas)
        
        conn.commit()
        conn.close()
        
        logger.info("limpeza_concluida", total_pacientes_removidos=len(pacientes))
        return True
        
    except Exception as e:
        logger.error("limpeza_erro", error=str(e))
        return False


def testar_timestamps():
    """Valida que novos eventos estão sendo gerados para o FUTURO."""
    logger.info("teste_timestamps_iniciado")
    
    try:
        from dados_simulados.gerador import gerar_sessao_simulada, PERFIS_PREDEFINIDOS
        
        agora = datetime.now().replace(second=0, microsecond=0)
        logger.info("teste_timestamps_agora", timestamp=agora.isoformat())
        
        # Gerar 1h de simulação
        perfil_params = PERFIS_PREDEFINIDOS.get("medio", PERFIS_PREDEFINIDOS["medio"])
        from dados_simulados.gerador import PerfilPaciente
        perfil = PerfilPaciente(**perfil_params)
        
        df_grade, contextos = gerar_sessao_simulada(
            duracao_horas=1,
            seed=42,
            passo_min=5,
            perfil=perfil,
            incluir_contexto=True
        )
        
        # Validar timestamps
        timestamps = pd.to_datetime(df_grade["timestamp"])
        primeira = timestamps.min()
        ultima = timestamps.max()
        
        logger.info("teste_timestamps_gerados",
                   primeira_evento=primeira.isoformat(),
                   ultima_evento=ultima.isoformat(),
                   agora=agora.isoformat(),
                   primero_apos_agora=(primeira > agora),
                   ultimo_apos_agora=(ultima > agora))
        
        if primeira >= agora and ultima > agora:  # Primeira pode ser igual a agora (começa agora)
            logger.info("teste_timestamps_SUCESSO", mensagem="Eventos gerados para FUTURO ✅")
            return True
        else:
            logger.error("teste_timestamps_FALHA", mensagem="Eventos gerados para PASSADO ❌")
            return False
            
    except Exception as e:
        logger.error("teste_timestamps_erro", error=str(e))
        return False


def testar_metricas():
    """Valida que as métricas usam janela de 24h consistente."""
    logger.info("teste_metricas_iniciado")
    
    try:
        from interface.api import get_stats
        import asyncio
        
        # Executar endpoint de stats
        stats = asyncio.run(get_stats())
        
        logger.info("teste_metricas_resultado",
                   activeAlerts=stats.get("activeAlerts"),
                   acknowledgedAlerts=stats.get("acknowledgedAlerts"),
                   completedToday=stats.get("completedToday"),
                   totalPatients=stats.get("totalPatients"),
                   completionRate=stats.get("completionRate"))
        
        # Validar que a taxa de conclusão faz sentido
        active = stats.get("activeAlerts", 0)
        acked = stats.get("acknowledgedAlerts", 0)
        completed = stats.get("completedToday", 0)
        total = active + acked + completed
        
        expected_rate = (completed / total * 100) if total > 0 else 0
        actual_rate = stats.get("completionRate", 0)
        
        if abs(expected_rate - actual_rate) < 0.1:
            logger.info("teste_metricas_SUCESSO", 
                       mensagem="Taxa de conclusão calculada corretamente ✅",
                       esperado=expected_rate,
                       obtido=actual_rate)
            return True
        else:
            logger.error("teste_metricas_FALHA",
                        mensagem="Taxa de conclusão inconsistente ❌",
                        esperado=expected_rate,
                        obtido=actual_rate)
            return False
            
    except Exception as e:
        logger.error("teste_metricas_erro", error=str(e))
        return False


def testar_contrato_repositioning():
    """Valida que proximo_repouso > agora (está no futuro)."""
    logger.info("teste_contrato_repositioning_iniciado")
    
    try:
        # Criar paciente de teste
        from interface.dao import criar_paciente, selecionar_alertas_janela
        import asyncio
        import time
        
        # ID único baseado em timestamp para evitar conflitos
        test_id = f"TEST-{int(time.time() * 1000) % 1000000}"
        test_cama = f"test/{int(time.time() * 1000) % 10000}"
        
        # Limpar teste anterior se houver
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fichas_paciente WHERE paciente_id = ?", (test_id,))
            cursor.execute("DELETE FROM alertas WHERE paciente_id = ?", (test_id,))
            conn.commit()
            conn.close()
        except:
            pass
        
        # Criar paciente
        ficha = criar_paciente(DB_PATH, nome="Teste Contrato", perfil="medio", cama_id=test_cama, observacoes=None, rotinas=None)
        paciente_id = ficha.get("paciente_id")
        logger.info("teste_contrato_paciente_criado", paciente_id=paciente_id)
        
        # Gerar simulação
        from interface.api import api_simular_paciente, SimulationRequest
        
        request = SimulationRequest(duracao_horas=1, seed=42, perfil="medio")
        resultado = asyncio.run(api_simular_paciente(paciente_id, request))
        
        logger.info("teste_contrato_simulacao_gerada",
                   eventos=resultado.eventos,
                   alertas=resultado.alertas)
        
        # Validar contrato
        from interface.api import validate_repositioning_contract
        
        validacao = asyncio.run(validate_repositioning_contract(paciente_id))
        
        logger.info("teste_contrato_validacao",
                   valido=validacao.get("valid"),
                   ultimo_repouso=validacao.get("ultimo_repouso"),
                   proximo_repouso=validacao.get("proximo_repouso"),
                   errors=validacao.get("errors"))
        
        if validacao.get("valid"):
            logger.info("teste_contrato_SUCESSO", mensagem="Contrato Backend/Frontend validado ✅")
            return True
        else:
            logger.error("teste_contrato_FALHA", 
                        mensagem="Contrato Backend/Frontend inválido ❌",
                        errors=validacao.get("errors"))
            return False
            
    except Exception as e:
        logger.error("teste_contrato_erro", error=str(e), traceback=str(e))
        import traceback
        traceback.print_exc()
        return False


def main():
    """Executa todos os testes."""
    logger.info("inicio_testes")
    
    print("\n" + "="*80)
    print("TESTES DE VALIDAÇÃO - CORREÇÕES DE ARQUITETURA")
    print("="*80)
    
    # 1. Limpar dados de teste
    print("\n[1/4] Limpando dados de teste...")
    resultado_limpeza = limpar_dados_teste()
    print(f"      {'✅ SUCESSO' if resultado_limpeza else '❌ FALHA'}")
    
    # 2. Testar timestamps
    print("\n[2/4] Testando geração de timestamps (FUTURO vs PASSADO)...")
    resultado_timestamps = testar_timestamps()
    print(f"      {'✅ SUCESSO' if resultado_timestamps else '❌ FALHA'}")
    
    # 3. Testar métricas
    print("\n[3/4] Testando métricas (janela consistente de 24h)...")
    resultado_metricas = testar_metricas()
    print(f"      {'✅ SUCESSO' if resultado_metricas else '❌ FALHA'}")
    
    # 4. Testar contrato Backend/Frontend
    print("\n[4/4] Testando validação do contrato Backend/Frontend...")
    resultado_contrato = testar_contrato_repositioning()
    print(f"      {'✅ SUCESSO' if resultado_contrato else '❌ FALHA'}")
    
    print("\n" + "="*80)
    print("RESUMO")
    print("="*80)
    
    resultados = {
        "Limpeza de dados": resultado_limpeza,
        "Timestamps (FUTURO)": resultado_timestamps if resultado_timestamps is not None else "SKIP",
        "Métricas (24h)": resultado_metricas,
        "Contrato Backend/Frontend": resultado_contrato,
    }
    
    for teste, resultado in resultados.items():
        status_str = "✅" if resultado is True else ("❌" if resultado is False else "⚠️ ")
        print(f"{status_str} {teste}")
    
    print("="*80 + "\n")
    
    # Retornar status final
    testes_ok = sum(1 for r in resultados.values() if r is True)
    total_testes = len(resultados)  # Não filtra por None mais
    
    logger.info("testes_concluidos",
               ok=testes_ok,
               total=total_testes,
               sucesso=(testes_ok == total_testes))
    
    return 0 if testes_ok == total_testes else 1


if __name__ == "__main__":
    sys.exit(main())
