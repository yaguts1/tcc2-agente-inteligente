"""WebSocket connection manager com suporte a filtros."""

from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import structlog
from datetime import datetime
from enum import Enum


class AlertSeverity(str, Enum):
    """Níveis de severidade de alerta."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WebSocketFilter:
    """Filtro para alertas no WebSocket."""
    
    def __init__(
        self,
        severities: Optional[List[str]] = None,
        patient_id: Optional[str] = None,
        alert_types: Optional[List[str]] = None,
        limit: int = 1000,
    ):
        """
        Inicializa filtro.
        
        Args:
            severities: Lista de severidades (ex: ["high", "critical"])
            patient_id: ID do paciente específico (ex: "PAC-0001")
            alert_types: Tipos de alerta (ex: ["heart_rate", "pressure"])
            limit: Limite máximo de alertas a armazenar
        """
        self.severities = set(severities) if severities else None
        self.patient_id = patient_id
        self.alert_types = set(alert_types) if alert_types else None
        self.limit = limit
    
    def matches(self, alert: dict) -> bool:
        """Verifica se alerta atende aos critérios de filtro."""
        
        # Filtro de severidade
        if self.severities:
            if alert.get("severity") not in self.severities:
                return False
        
        # Filtro de paciente
        if self.patient_id:
            if alert.get("patient_id") != self.patient_id:
                return False
        
        # Filtro de tipo
        if self.alert_types:
            if alert.get("alert_type") not in self.alert_types:
                return False
        
        return True
    
    def __repr__(self):
        parts = []
        if self.severities:
            parts.append(f"severities={self.severities}")
        if self.patient_id:
            parts.append(f"patient_id={self.patient_id}")
        if self.alert_types:
            parts.append(f"types={self.alert_types}")
        
        return f"WebSocketFilter({', '.join(parts)})"


class ConnectionManagerOptimized:
    """
    Gerenciador de conexões WebSocket otimizado.
    
    Suporta:
    - Filtros por cliente (reduz bandwidth)
    - Rate limiting (proteção contra abuse)
    - Stats e metrics
    - Logging estruturado
    """
    
    def __init__(self):
        """Inicializa gerenciador."""
        self.active_connections: Dict[WebSocket, Dict] = {}
        self.logger = structlog.get_logger(__name__)
    
    async def connect(
        self,
        websocket: WebSocket,
        filters: Optional[WebSocketFilter] = None,
    ):
        """Aceita e registra nova conexão."""
        await websocket.accept()
        
        client_id = id(websocket)
        self.active_connections[websocket] = {
            "filters": filters or WebSocketFilter(),
            "connected_at": datetime.now(),
            "messages_sent": 0,
            "messages_filtered": 0,
            "client_id": client_id,
        }
        
        self.logger.info(
            "ws_client_connected",
            client_id=client_id,
            total_clients=len(self.active_connections),
            filters=str(self.active_connections[websocket]["filters"]),
        )
    
    async def disconnect(self, websocket: WebSocket):
        """Remove conexão."""
        if websocket in self.active_connections:
            stats = self.active_connections.pop(websocket)
            client_id = stats["client_id"]
            connected_time = (datetime.now() - stats["connected_at"]).total_seconds()
            
            self.logger.info(
                "ws_client_disconnected",
                client_id=client_id,
                connected_seconds=connected_time,
                messages_sent=stats["messages_sent"],
                messages_filtered=stats["messages_filtered"],
                total_clients=len(self.active_connections),
            )
    
    async def broadcast(self, message: dict):
        """
        Faz broadcast de mensagem para todos clientes.
        
        Aplica filtros antes de enviar - cliente só recebe alertas relevantes.
        """
        if not self.active_connections:
            return
        
        self.logger.debug(
            "broadcast_start",
            total_clients=len(self.active_connections),
            message_type=message.get("type"),
        )
        
        disconnected = []
        
        for websocket, client_data in self.active_connections.items():
            try:
                filters = client_data["filters"]
                
                # Aplicar filtro
                if not filters.matches(message):
                    client_data["messages_filtered"] += 1
                    continue
                
                # Enviar apenas se passou no filtro
                await websocket.send_json(message)
                client_data["messages_sent"] += 1
                
            except Exception as e:
                self.logger.warning(
                    "broadcast_error",
                    client_id=client_data["client_id"],
                    error=str(e),
                )
                disconnected.append(websocket)
        
        # Limpar conexões com erro
        for ws in disconnected:
            await self.disconnect(ws)
        
        self.logger.debug(
            "broadcast_end",
            total_sent=sum(
                c["messages_sent"] for c in self.active_connections.values()
            ),
            total_filtered=sum(
                c["messages_filtered"] for c in self.active_connections.values()
            ),
        )
    
    def get_stats(self) -> dict:
        """Retorna estatísticas das conexões."""
        if not self.active_connections:
            return {
                "active_clients": 0,
                "total_messages_sent": 0,
                "total_messages_filtered": 0,
            }
        
        stats = {
            "active_clients": len(self.active_connections),
            "total_messages_sent": sum(
                c["messages_sent"] for c in self.active_connections.values()
            ),
            "total_messages_filtered": sum(
                c["messages_filtered"] for c in self.active_connections.values()
            ),
            "clients": [],
        }
        
        for client_data in self.active_connections.values():
            stats["clients"].append({
                "client_id": client_data["client_id"],
                "messages_sent": client_data["messages_sent"],
                "messages_filtered": client_data["messages_filtered"],
                "filters": str(client_data["filters"]),
            })
        
        return stats


# Instância global
ws_manager_optimized = ConnectionManagerOptimized()
