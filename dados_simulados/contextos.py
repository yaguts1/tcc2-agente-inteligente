# -- coding: utf-8 --
# dados_simulados/contextos.py
"""
Framework de eventos contextuais hospitalares.

Modela eventos agendados (refeições, cirurgias, visitas, etc) que não são
'movimento espontâneo' mas sim atividades clínicas que afetam a postura.

Objetivo: Evitar falsos positivos do motor de alertas quando paciente está
em atividade legítima (cirurgia, refeição, higiene).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd


@dataclass
class EventoContextual:
    """Evento agendado que não é 'movimento espontâneo'."""
    
    tipo: str                           # "refeicao", "cirurgia", "visita", "higiene", "medicacao"
    inicio: datetime
    fim: datetime
    postura_esperada: str = "supino"   # Postura durante o evento
    suprime_alerta: bool = True        # Não gera alerta durante este evento
    marca_nos_logs: bool = True        # Marca como "contexto_cirurgico" nos alertas
    descricao: str = ""                # Descrição para auditoria
    
    def __post_init__(self):
        """Valida o evento."""
        if self.inicio >= self.fim:
            raise ValueError(f"Evento {self.tipo}: inicio >= fim")
        if self.tipo not in TIPOS_EVENTO_CONTEXTO:
            raise ValueError(f"Tipo de evento inválido: {self.tipo}")
    
    @property
    def duracao_min(self) -> float:
        """Retorna duração em minutos."""
        return (self.fim - self.inicio).total_seconds() / 60.0


# Configuração padrão de tipos de eventos
TIPOS_EVENTO_CONTEXTO = {
    "refeicao": {
        "descricao": "Refeição agendada",
        "horarios_padrao": [(6, 0), (12, 0), (18, 0)],  # Café, Almoço, Jantar
        "duracao_min_padrao": 30,
        "postura_esperada": "supino",
        "suprime_alerta": True,
        "cor_timeline": "🟢",  # Para visualização
    },
    "higiene": {
        "descricao": "Higiene/Banho",
        "horarios_padrao": [(7, 0), (17, 0)],  # Manhã e tarde
        "duracao_min_padrao": 45,
        "postura_esperada": "variavel",  # Pode mudar durante higiene
        "suprime_alerta": True,
        "cor_timeline": "🔵",
    },
    "medicacao": {
        "descricao": "Administração de medicação",
        "horarios_padrao": [(6, 0), (12, 0), (18, 0), (22, 0)],  # QID
        "duracao_min_padrao": 15,
        "postura_esperada": "supino",
        "suprime_alerta": True,
        "cor_timeline": "🟡",
    },
    "cirurgia": {
        "descricao": "Procedimento cirúrgico",
        "horarios_padrao": [(9, 30)],  # Horário-exemplo (deve ser customizado)
        "duracao_min_padrao": 90,
        "postura_esperada": "supino",
        "suprime_alerta": True,
        "cor_timeline": "🔴",  # Crítico
    },
    "visita": {
        "descricao": "Visita de familiar/acompanhante",
        "horarios_padrao": [(14, 0), (20, 0)],  # Tarde e noite
        "duracao_min_padrao": 60,
        "postura_esperada": "semi_sentado",  # Pode mudar bastante
        "suprime_alerta": False,  # Visita NÃO anula risco
        "cor_timeline": "🟣",
    },
    "avaliacao_medica": {
        "descricao": "Avaliação médica/enfermagem",
        "horarios_padrao": [(8, 0), (14, 0)],
        "duracao_min_padrao": 20,
        "postura_esperada": "supino",
        "suprime_alerta": True,
        "cor_timeline": "🟠",
    },
}


def gerar_eventos_contextuais(
    inicio: datetime,
    fim: datetime,
    tipos_eventos: dict[str, bool] | None = None,
    seed: int = 42,
) -> list[EventoContextual]:
    """
    Gera eventos contextuais para um período.
    
    Args:
        inicio: Timestamp inicial
        fim: Timestamp final
        tipos_eventos: Dict indicando quais tipos incluir
                      Ex: {"refeicao": True, "cirurgia": False}
        seed: Seed para reproducibilidade
    
    Returns:
        Lista de EventoContextual
    """
    import random
    random.seed(seed)
    
    if tipos_eventos is None:
        # Por padrão, inclui todos os eventos comuns (exceto cirurgia)
        tipos_eventos = {
            "refeicao": True,
            "higiene": True,
            "medicacao": True,
            "cirurgia": False,
            "visita": True,
            "avaliacao_medica": True,
        }
    
    eventos = []
    dias_simulacao = (fim - inicio).days + 1
    
    for tipo_evento, incluir in tipos_eventos.items():
        if not incluir:
            continue
        
        if tipo_evento not in TIPOS_EVENTO_CONTEXTO:
            continue
        
        config = TIPOS_EVENTO_CONTEXTO[tipo_evento]
        horarios = config["horarios_padrao"]
        duracao = config["duracao_min_padrao"]
        
        # Gera evento para cada dia dentro do período
        for dia in range(dias_simulacao):
            data_base = inicio.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=dia)
            
            for hora, minuto in horarios:
                ts_evento = data_base.replace(hour=hora, minute=minuto)
                
                # Verifica se está dentro do período. Usamos ">=" (não ">")
                # para o limite superior: um evento que comece exatamente em
                # `fim` teria duração zero (ts_fim = min(..., fim) == ts_evento),
                # o que EventoContextual rejeita (inicio >= fim). Isso é raro
                # mas real: `agora` é truncado pro minuto exato em
                # dados_simulados/gerador.py, e os horarios_padrao também são
                # em minutos exatos, então às vezes coincidem.
                if ts_evento < inicio or ts_evento >= fim:
                    continue
                
                # Para cirurgia, apenas alguns dias (simulação de agendamento)
                if tipo_evento == "cirurgia":
                    if random.random() > 0.3:  # 30% de chance de cirurgia num dia
                        continue
                
                # Cria evento
                ts_fim = min(ts_evento + timedelta(minutes=duracao), fim)
                
                evento = EventoContextual(
                    tipo=tipo_evento,
                    inicio=ts_evento,
                    fim=ts_fim,
                    postura_esperada=config["postura_esperada"],
                    suprime_alerta=config["suprime_alerta"],
                    descricao=config["descricao"],
                )
                
                eventos.append(evento)
    
    # Ordena por tempo
    eventos.sort(key=lambda e: e.inicio)
    
    return eventos


def adicionar_contextos_na_grade(
    grade: pd.DataFrame,
    eventos_contextuais: list[EventoContextual],
) -> pd.DataFrame:
    """
    Adiciona colunas 'contexto' e 'suprime_alerta' na grade.
    
    Args:
        grade: DataFrame original com colunas timestamp, postura
        eventos_contextuais: Lista de EventoContextual
    
    Returns:
        DataFrame com colunas adicionadas:
        - contexto: Tipo de contexto (None se nenhum)
        - suprime_alerta: Bool indicando se alerta deve ser suprimido
    """
    grade = grade.copy()
    grade["contexto"] = None
    grade["suprime_alerta"] = False
    
    # Converte timestamps
    grade["timestamp"] = pd.to_datetime(grade["timestamp"])
    
    # Marca cada linha com seu contexto
    for evento in eventos_contextuais:
        mask = (grade["timestamp"] >= evento.inicio) & \
               (grade["timestamp"] <= evento.fim)
        
        grade.loc[mask, "contexto"] = evento.tipo
        grade.loc[mask, "suprime_alerta"] = evento.suprime_alerta
    
    return grade


def validar_eventos_contextuais(
    eventos: list[EventoContextual],
    period_inicio: datetime,
    period_fim: datetime,
) -> tuple[bool, list[str]]:
    """
    Valida coerência de eventos contextuais.
    
    Args:
        eventos: Lista de EventoContextual
        period_inicio: Início do período esperado
        period_fim: Fim do período esperado
    
    Returns:
        (is_valid, list_of_errors)
    """
    erros = []
    
    # Validação 1: Sem eventos fora do período
    for evento in eventos:
        if evento.inicio < period_inicio:
            erros.append(
                f"❌ Evento {evento.tipo} começa antes do período "
                f"({evento.inicio} < {period_inicio})"
            )
        if evento.fim > period_fim:
            erros.append(
                f"❌ Evento {evento.tipo} termina depois do período "
                f"({evento.fim} > {period_fim})"
            )
    
    # Validação 2: Sem sobreposição (opcional - pode ser válido)
    for i, e1 in enumerate(eventos):
        for e2 in eventos[i+1:]:
            # Verifica sobreposição
            if not (e1.fim <= e2.inicio or e2.fim <= e1.inicio):
                erros.append(
                    f"⚠️ Eventos sobrepostos: {e1.tipo} [{e1.inicio}, {e1.fim}] "
                    f"e {e2.tipo} [{e2.inicio}, {e2.fim}]"
                )
    
    # Validação 3: Tipos válidos
    for evento in eventos:
        if evento.tipo not in TIPOS_EVENTO_CONTEXTO:
            erros.append(f"❌ Tipo de evento inválido: {evento.tipo}")
    
    is_valid = len([e for e in erros if e.startswith("❌")]) == 0
    
    return is_valid, erros


def resumir_contextos(
    eventos: list[EventoContextual],
) -> str:
    """
    Retorna resumo textual dos eventos contextuais.
    """
    if not eventos:
        return "Sem eventos contextuais"
    
    resumo_lines = ["=== EVENTOS CONTEXTUAIS ==="]
    
    for evento in eventos:
        config = TIPOS_EVENTO_CONTEXTO.get(evento.tipo, {})
        cor = config.get("cor_timeline", "⚪")
        
        resumo_lines.append(
            f"{cor} {evento.tipo.upper()}: "
            f"{evento.inicio.strftime('%H:%M')} - {evento.fim.strftime('%H:%M')} "
            f"({evento.duracao_min:.0f}min) "
            f"[suprime_alerta={evento.suprime_alerta}]"
        )
    
    return "\n".join(resumo_lines)


def filtrar_alertas_por_contexto(
    alertas: list[dict],
    contextos: list[EventoContextual],
) -> tuple[list[dict], list[dict]]:
    """
    Filtra alertas baseado em contexto.
    
    Args:
        alertas: Lista de alertas com timestamp
        contextos: Lista de EventoContextual
    
    Returns:
        (alertas_validos, alertas_suprimidos)
    """
    alertas_validos = []
    alertas_suprimidos = []
    
    for alerta in alertas:
        ts_alerta = pd.to_datetime(alerta.get("timestamp"))
        
        # Encontra contexto
        em_contexto = False
        suprime = False
        
        for ctx in contextos:
            if ctx.inicio <= ts_alerta <= ctx.fim:
                em_contexto = True
                suprime = ctx.suprime_alerta
                alerta["contexto_suprimido"] = ctx.tipo
                break
        
        if em_contexto and suprime:
            alertas_suprimidos.append(alerta)
        else:
            alertas_validos.append(alerta)
    
    return alertas_validos, alertas_suprimidos


# Exemplo de uso
if __name__ == "__main__":
    from datetime import datetime
    
    inicio = datetime(2025, 10, 27, 0, 0, 0)
    fim = datetime(2025, 10, 28, 0, 0, 0)
    
    # Gera eventos contextuais
    eventos = gerar_eventos_contextuais(inicio, fim)
    
    print(resumir_contextos(eventos))
    
    # Valida
    is_valid, erros = validar_eventos_contextuais(eventos, inicio, fim)
    if is_valid:
        print("✅ Eventos contextuais validados com sucesso")
    else:
        print("❌ Erros encontrados:")
        for erro in erros:
            print(f"  {erro}")
