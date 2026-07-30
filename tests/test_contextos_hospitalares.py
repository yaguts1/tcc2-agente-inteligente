# tests/test_contextos_hospitalares.py
"""
Testes para contextos hospitalares (Problema 1).

Valida que eventos agendados (refeições, cirurgias, visitas, etc)
são corretamente modelados e evitam falsos positivos.
"""

import pytest
from datetime import datetime
import pandas as pd

from dados_simulados.contextos import (
    EventoContextual,
    gerar_eventos_contextuais,
    adicionar_contextos_na_grade,
    validar_eventos_contextuais,
    resumir_contextos,
    filtrar_alertas_por_contexto,
)
from dados_simulados.gerador import (
    gerar_sessao_simulada,
    gerar_sessao_multi,
)


class TestEventoContextual:
    """Testes para classe EventoContextual."""
    
    def test_evento_criacao_valida(self):
        """Evento contextual deve ser criado com dados válidos."""
        inicio = datetime(2025, 10, 27, 6, 0, 0)
        fim = datetime(2025, 10, 27, 6, 30, 0)
        
        evento = EventoContextual(
            tipo="refeicao",
            inicio=inicio,
            fim=fim,
            postura_esperada="supino",
        )
        
        assert evento.tipo == "refeicao"
        assert evento.duracao_min == 30.0
        assert evento.suprime_alerta
    
    def test_evento_inicio_maior_que_fim_falha(self):
        """Evento com inicio >= fim deve falhar."""
        inicio = datetime(2025, 10, 27, 6, 30, 0)
        fim = datetime(2025, 10, 27, 6, 0, 0)
        
        with pytest.raises(ValueError):
            EventoContextual(
                tipo="refeicao",
                inicio=inicio,
                fim=fim,
            )
    
    def test_evento_tipo_invalido_falha(self):
        """Evento com tipo inválido deve falhar."""
        inicio = datetime(2025, 10, 27, 6, 0, 0)
        fim = datetime(2025, 10, 27, 6, 30, 0)
        
        with pytest.raises(ValueError):
            EventoContextual(
                tipo="tipo_invalido",
                inicio=inicio,
                fim=fim,
            )
    
    def test_evento_duracao_calculada(self):
        """Duração deve ser calculada corretamente."""
        inicio = datetime(2025, 10, 27, 6, 0, 0)
        fim = datetime(2025, 10, 27, 7, 0, 0)  # 1 hora
        
        evento = EventoContextual(
            tipo="higiene",
            inicio=inicio,
            fim=fim,
        )
        
        assert evento.duracao_min == 60.0


class TestGerarEventosContextuais:
    """Testes para geração de eventos contextuais."""
    
    def test_gerar_eventos_padrao(self):
        """Deve gerar eventos padrão para um período."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 28, 0, 0, 0)
        
        eventos = gerar_eventos_contextuais(inicio, fim, seed=42)
        
        assert len(eventos) > 0
        assert all(isinstance(e, EventoContextual) for e in eventos)
        assert all(inicio <= e.inicio <= fim for e in eventos)
    
    def test_gerar_eventos_sem_cirurgia(self):
        """Deve respeitar flag para não incluir cirurgia."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 28, 0, 0, 0)
        
        tipos = {
            "refeicao": True,
            "higiene": True,
            "medicacao": True,
            "cirurgia": False,
            "visita": True,
            "avaliacao_medica": True,
        }
        
        eventos = gerar_eventos_contextuais(inicio, fim, tipos_eventos=tipos, seed=42)
        
        # Não deve haver eventos de cirurgia
        cirurgias = [e for e in eventos if e.tipo == "cirurgia"]
        assert len(cirurgias) == 0
    
    def test_gerar_eventos_apenas_refeicao(self):
        """Deve gerar apenas refeições quando configurado."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 28, 0, 0, 0)
        
        tipos = {
            "refeicao": True,
            "higiene": False,
            "medicacao": False,
            "cirurgia": False,
            "visita": False,
            "avaliacao_medica": False,
        }
        
        eventos = gerar_eventos_contextuais(inicio, fim, tipos_eventos=tipos, seed=42)
        
        assert all(e.tipo == "refeicao" for e in eventos)
        assert len(eventos) == 3  # 3 refeições por dia
    
    def test_gerar_eventos_fim_exato_em_horario_padrao_nao_gera_evento_zero(self):
        """Regressão: se `fim` cai exatamente num horario_padrao (ex: 12:00 do
        almoço), o evento não deve ser criado com inicio == fim (duração
        zero). Antes, `ts_evento > fim` deixava passar `ts_evento == fim`,
        e `min(ts_evento + duracao, fim)` produzia ts_fim == ts_evento,
        levantando ValueError em EventoContextual. Isso era raro em produção
        porque dependia de `datetime.now()` coincidir com um horario_padrao
        no minuto exato, mas causava falhas intermitentes nos testes que
        usam `datetime.now()` (test_simulador.py, test_perfis_heterogeneos.py).
        """
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 27, 12, 0, 0)  # exatamente o horário do almoço

        eventos = gerar_eventos_contextuais(
            inicio, fim,
            tipos_eventos={"refeicao": True, "higiene": False, "medicacao": False,
                           "cirurgia": False, "visita": False, "avaliacao_medica": False},
            seed=42,
        )

        # Não deve haver evento com inicio == fim da janela (duração zero)
        assert all(e.inicio < fim for e in eventos)
        assert all(e.duracao_min > 0 for e in eventos)

    def test_eventos_ordenados(self):
        """Eventos devem estar ordenados por tempo."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 28, 0, 0, 0)
        
        eventos = gerar_eventos_contextuais(inicio, fim, seed=42)
        
        tempos = [e.inicio for e in eventos]
        assert tempos == sorted(tempos)


class TestAdicionarContextosNaGrade:
    """Testes para adição de contextos na grade."""
    
    def test_adicionar_contextos_cria_colunas(self):
        """Deve adicionar colunas 'contexto' e 'suprime_alerta'."""
        grade = pd.DataFrame({
            "timestamp": [
                "2025-10-27T06:00:00",
                "2025-10-27T06:05:00",
                "2025-10-27T06:10:00",
            ],
            "postura": ["supino", "supino", "supino"],
        })
        
        contextos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 27, 6, 0, 0),
                fim=datetime(2025, 10, 27, 6, 30, 0),
            )
        ]
        
        grade_com_contexto = adicionar_contextos_na_grade(grade, contextos)
        
        assert "contexto" in grade_com_contexto.columns
        assert "suprime_alerta" in grade_com_contexto.columns
    
    def test_marcar_refeicao_na_grade(self):
        """Deve marcar timestamps durante refeição."""
        grade = pd.DataFrame({
            "timestamp": [
                "2025-10-27T05:55:00",
                "2025-10-27T06:00:00",
                "2025-10-27T06:15:00",
                "2025-10-27T06:30:00",
                "2025-10-27T06:35:00",
            ],
            "postura": ["supino", "supino", "supino", "supino", "supino"],
        })
        
        contextos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 27, 6, 0, 0),
                fim=datetime(2025, 10, 27, 6, 30, 0),
                suprime_alerta=True,
            )
        ]
        
        grade_com_contexto = adicionar_contextos_na_grade(grade, contextos)
        
        # Timestamps dentro da refeição devem ter contexto marcado
        assert grade_com_contexto.loc[1, "contexto"] == "refeicao"
        assert grade_com_contexto.loc[2, "contexto"] == "refeicao"
        assert grade_com_contexto.loc[1, "suprime_alerta"]
        
        # Antes e depois não devem ter contexto
        assert pd.isna(grade_com_contexto.loc[0, "contexto"])
        assert pd.isna(grade_com_contexto.loc[4, "contexto"])


class TestValidarEventosContextuais:
    """Testes para validação de eventos contextuais."""
    
    def test_validar_eventos_validos(self):
        """Eventos válidos devem passar na validação."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 28, 0, 0, 0)
        
        eventos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 27, 6, 0, 0),
                fim=datetime(2025, 10, 27, 6, 30, 0),
            ),
            EventoContextual(
                tipo="higiene",
                inicio=datetime(2025, 10, 27, 7, 0, 0),
                fim=datetime(2025, 10, 27, 7, 45, 0),
            ),
        ]
        
        is_valid, erros = validar_eventos_contextuais(eventos, inicio, fim)
        
        assert is_valid
        assert len([e for e in erros if e.startswith("❌")]) == 0
    
    def test_validar_evento_fora_do_periodo_falha(self):
        """Evento fora do período deve gerar erro."""
        inicio = datetime(2025, 10, 27, 0, 0, 0)
        fim = datetime(2025, 10, 27, 12, 0, 0)
        
        eventos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 26, 23, 0, 0),  # Antes do período
                fim=datetime(2025, 10, 27, 6, 0, 0),
            ),
        ]
        
        is_valid, erros = validar_eventos_contextuais(eventos, inicio, fim)
        
        assert not is_valid
        assert any("❌" in e for e in erros)


class TestGerarSessaoComContexto:
    """Testes para integração de contextos em gerar_sessao_simulada."""
    
    def test_gerar_sessao_com_contexto(self):
        """Deve gerar sessão com contextos."""
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            incluir_contexto=True,
        )
        
        assert isinstance(grade, pd.DataFrame)
        assert isinstance(contextos, list)
        assert "contexto" in grade.columns
        assert "suprime_alerta" in grade.columns
        assert len(contextos) > 0
    
    def test_gerar_sessao_sem_contexto(self):
        """Deve gerar sessão sem contextos quando flag=False."""
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            incluir_contexto=False,
        )
        
        assert isinstance(grade, pd.DataFrame)
        assert isinstance(contextos, list)
        assert len(contextos) == 0
        # Contexto pode estar na grade mas vazio
        if "contexto" in grade.columns:
            assert grade["contexto"].isna().all()
    
    def test_contexto_suprime_alerta(self):
        """Contextos com suprime_alerta=True devem marcar a grade."""
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            incluir_contexto=True,
        )
        
        # Deve haver alguns timestamps com suprime_alerta=True
        assert grade["suprime_alerta"].sum() > 0


class TestGerarSessaoMultiComContexto:
    """Testes para geração multi-paciente com contextos."""
    
    def test_gerar_sessao_multi_com_contexto(self):
        """Deve gerar múltiplos pacientes com contextos."""
        grades_dict, contextos_dict, eventos_df = gerar_sessao_multi(
            pacientes=2,
            horas=24,
            passo_min=5,
            seed=42,
            incluir_contexto=True,
        )
        
        assert len(grades_dict) == 2
        assert len(contextos_dict) == 2
        assert isinstance(eventos_df, pd.DataFrame)
        
        for pac_id, grade in grades_dict.items():
            assert "contexto" in grade.columns
            assert "suprime_alerta" in grade.columns
            assert pac_id in contextos_dict


class TestResumirContextos:
    """Testes para resumo de contextos."""
    
    def test_resumir_contextos_vazio(self):
        """Deve retornar mensagem para contextos vazios."""
        resumo = resumir_contextos([])
        assert "Sem eventos" in resumo
    
    def test_resumir_contextos_completo(self):
        """Deve gerar resumo com todos os eventos."""
        eventos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 27, 6, 0, 0),
                fim=datetime(2025, 10, 27, 6, 30, 0),
            ),
            EventoContextual(
                tipo="cirurgia",
                inicio=datetime(2025, 10, 27, 10, 0, 0),
                fim=datetime(2025, 10, 27, 11, 30, 0),
            ),
        ]
        
        resumo = resumir_contextos(eventos)
        
        assert "REFEICAO" in resumo
        assert "CIRURGIA" in resumo


class TestFiltrarAlertasPorContexto:
    """Testes para filtro de alertas por contexto."""
    
    def test_filtrar_alertas_nao_suprimidos(self):
        """Alertas durante refeição devem ser suprimidos."""
        contextos = [
            EventoContextual(
                tipo="refeicao",
                inicio=datetime(2025, 10, 27, 6, 0, 0),
                fim=datetime(2025, 10, 27, 6, 30, 0),
                suprime_alerta=True,
            ),
        ]
        
        alertas = [
            {
                "paciente_id": "PAC-0001",
                "timestamp": "2025-10-27T06:15:00",
                "postura": "supino",
            },
            {
                "paciente_id": "PAC-0001",
                "timestamp": "2025-10-27T07:00:00",
                "postura": "supino",
            },
        ]
        
        validos, suprimidos = filtrar_alertas_por_contexto(alertas, contextos)
        
        assert len(suprimidos) == 1
        assert len(validos) == 1
        assert validos[0]["timestamp"] == "2025-10-27T07:00:00"


class TestCenarioClinicoRefeicao:
    """Cenário clínico: Detecção de alerta durante refeição."""
    
    def test_cenario_refeicao_suprime_alerta(self):
        """
        Cenário: Paciente em refeição matinal (6:00-6:30).
        
        Esperado: Sistema não deve gerar alerta por imobilidade
                  mesmo que paciente fique em supino por 30 minutos.
        """
        # Gera sessão com contextos
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            incluir_contexto=True,
        )
        
        # Encontra refeição
        refeicoes = [c for c in contextos if c.tipo == "refeicao"]
        assert len(refeicoes) >= 1
        
        refeicao = refeicoes[0]
        
        # Dados durante refeição
        mask_refeicao = (
            (grade["timestamp"] >= refeicao.inicio.isoformat()) &
            (grade["timestamp"] <= refeicao.fim.isoformat())
        )
        grade_refeicao = grade[mask_refeicao]
        
        # Deve haver dados durante refeição
        assert len(grade_refeicao) > 0
        
        # Todos devem ter suprime_alerta=True
        assert grade_refeicao["suprime_alerta"].all()


class TestCenarioClinicoCirurgia:
    """Cenário clínico: Cirurgia agendada."""
    
    def test_cenario_cirurgia_detectada(self):
        """
        Cenário: Sistema deve reconhecer período cirúrgico.
        
        Esperado: Contexto marcado corretamente, alerta suprimido.
        """
        tipos_eventos = {
            "refeicao": False,
            "higiene": False,
            "medicacao": False,
            "cirurgia": True,  # Inclui cirurgia
            "visita": False,
            "avaliacao_medica": False,
        }
        
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            incluir_contexto=True,
            tipos_eventos=tipos_eventos,
        )
        
        # Pode haver cirurgia (probabilidade 30%)
        cirurgias = [c for c in contextos if c.tipo == "cirurgia"]
        
        if cirurgias:
            cirurgia = cirurgias[0]
            
            # Dados durante cirurgia
            mask_cirurgia = (
                (grade["timestamp"] >= cirurgia.inicio.isoformat()) &
                (grade["timestamp"] <= cirurgia.fim.isoformat())
            )
            grade_cirurgia = grade[mask_cirurgia]
            
            # Todos devem ter suprime_alerta=True
            assert grade_cirurgia["suprime_alerta"].all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
