"""
Rate Limiter para WebSocket - Proteção contra spam de alertas

Implementa throttling por cliente com contador de sliding window
"""
import time
from typing import Dict, Tuple
from structlog import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Rate limiter com sliding window para proteger WebSocket
    
    Exemplo:
        limiter = RateLimiter(max_alerts_per_minute=100)
        
        if limiter.is_allowed(client_id):
            # Enviar alerta
            pass
        else:
            # Ignorar alerta (limite atingido)
            pass
    """
    
    def __init__(self, max_alerts_per_minute: int = 100, window_seconds: int = 60):
        """
        Args:
            max_alerts_per_minute: Máximo de alertas por minuto (padrão: 100)
            window_seconds: Tamanho da janela deslizante (padrão: 60s)
        """
        self.max_alerts_per_minute = max_alerts_per_minute
        self.window_seconds = window_seconds
        
        # Armazena: {client_id: [(timestamp, count), ...]}
        self.client_windows: Dict[str, list] = {}
        
        # Armazena stats por cliente
        self.client_stats: Dict[str, Dict] = {}
    
    def _get_current_window(self, client_id: str) -> list:
        """Retorna a janela atual do cliente (últimos N segundos)"""
        now = time.time()
        
        if client_id not in self.client_windows:
            self.client_windows[client_id] = []
        
        # Remover timestamps fora da janela
        window = self.client_windows[client_id]
        window[:] = [ts for ts in window if now - ts < self.window_seconds]
        
        return window
    
    def is_allowed(self, client_id: str) -> bool:
        """
        Verifica se alerta é permitido para o cliente
        
        Returns:
            bool: True se alerta pode ser enviado, False se limite foi atingido
        """
        try:
            now = time.time()
            window = self._get_current_window(client_id)
            
            # Verificar se atingiu limite
            if len(window) >= self.max_alerts_per_minute:
                self._record_blocked(client_id)
                logger.warn(
                    "rate_limit_atingido",
                    client_id=client_id,
                    count=len(window),
                    max=self.max_alerts_per_minute
                )
                return False
            
            # Adicionar novo timestamp
            window.append(now)
            self.client_windows[client_id] = window
            
            self._record_allowed(client_id)
            return True
            
        except Exception as e:
            logger.error("rate_limiter_erro", client_id=client_id, error=str(e))
            # Em caso de erro, permitir (fail-open)
            return True
    
    def _record_allowed(self, client_id: str) -> None:
        """Registra alerta permitido"""
        if client_id not in self.client_stats:
            self.client_stats[client_id] = {
                "allowed": 0,
                "blocked": 0,
                "first_seen": time.time(),
                "last_seen": time.time(),
            }
        
        stats = self.client_stats[client_id]
        stats["allowed"] += 1
        stats["last_seen"] = time.time()
    
    def _record_blocked(self, client_id: str) -> None:
        """Registra alerta bloqueado"""
        if client_id not in self.client_stats:
            self.client_stats[client_id] = {
                "allowed": 0,
                "blocked": 0,
                "first_seen": time.time(),
                "last_seen": time.time(),
            }
        
        stats = self.client_stats[client_id]
        stats["blocked"] += 1
        stats["last_seen"] = time.time()
    
    def get_stats(self, client_id: str) -> Dict:
        """Retorna estatísticas para um cliente"""
        if client_id not in self.client_stats:
            return {
                "client_id": client_id,
                "allowed": 0,
                "blocked": 0,
                "total": 0,
                "block_rate": 0.0,
                "first_seen": None,
                "last_seen": None,
            }
        
        stats = self.client_stats[client_id]
        total = stats["allowed"] + stats["blocked"]
        block_rate = (stats["blocked"] / total * 100) if total > 0 else 0.0
        
        return {
            "client_id": client_id,
            "allowed": stats["allowed"],
            "blocked": stats["blocked"],
            "total": total,
            "block_rate": round(block_rate, 2),
            "first_seen": stats["first_seen"],
            "last_seen": stats["last_seen"],
        }
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Retorna estatísticas de todos os clientes"""
        return {
            client_id: self.get_stats(client_id)
            for client_id in self.client_stats.keys()
        }
    
    def reset_client(self, client_id: str) -> None:
        """Reseta limiter para um cliente específico"""
        self.client_windows.pop(client_id, None)
        self.client_stats.pop(client_id, None)
        logger.info("rate_limiter_reset", client_id=client_id)
    
    def reset_all(self) -> None:
        """Reseta todos os limiters"""
        self.client_windows.clear()
        self.client_stats.clear()
        logger.info("rate_limiter_reset_all")


class PerClientRateLimiter:
    """
    Gerenciador de rate limiters para múltiplos clientes WebSocket
    
    Cria um rate limiter independente para cada cliente
    """
    
    def __init__(self, max_alerts_per_minute: int = 100):
        self.max_alerts_per_minute = max_alerts_per_minute
        self.limiters: Dict[str, RateLimiter] = {}
    
    def check(self, client_id: str) -> bool:
        """Verifica se alerta é permitido"""
        if client_id not in self.limiters:
            self.limiters[client_id] = RateLimiter(
                max_alerts_per_minute=self.max_alerts_per_minute
            )
        
        return self.limiters[client_id].is_allowed(client_id)
    
    def remove_client(self, client_id: str) -> None:
        """Remove limiter de um cliente (desconexão)"""
        if client_id in self.limiters:
            self.limiters.pop(client_id)
            logger.info("rate_limiter_cliente_removido", client_id=client_id)
    
    def get_stats(self, client_id: str) -> Dict:
        """Retorna stats de um cliente"""
        if client_id not in self.limiters:
            return {"client_id": client_id, "error": "Cliente não encontrado"}
        
        return self.limiters[client_id].get_stats(client_id)
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Retorna stats de todos os clientes"""
        result = {}
        for client_id, limiter in self.limiters.items():
            result[client_id] = limiter.get_stats(client_id)
        return result


# Instância global
rate_limiter = PerClientRateLimiter(max_alerts_per_minute=100)
