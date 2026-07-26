"""Testes para WebSocket otimizado com filtros e rate limiting."""

import pytest
from unittest.mock import AsyncMock

from interface.ws_manager_optimized import (
    WebSocketFilter,
    ConnectionManagerOptimized,
)


class TestWebSocketFilter:
    """Testes para classe WebSocketFilter."""
    
    def test_filter_severity_single(self):
        """Testa filtro de severidade simples."""
        f = WebSocketFilter(severities=["high"])
        
        assert f.matches({"severity": "high"})
        assert not f.matches({"severity": "low"})
    
    def test_filter_severity_multiple(self):
        """Testa filtro de múltiplas severidades."""
        f = WebSocketFilter(severities=["high", "critical"])
        
        assert f.matches({"severity": "high"})
        assert f.matches({"severity": "critical"})
        assert not f.matches({"severity": "low"})
    
    def test_filter_patient_id(self):
        """Testa filtro de paciente."""
        f = WebSocketFilter(patient_id="PAC-0001")
        
        assert f.matches({"patient_id": "PAC-0001"})
        assert not f.matches({"patient_id": "PAC-0002"})
    
    def test_filter_alert_types(self):
        """Testa filtro de tipos de alerta."""
        f = WebSocketFilter(alert_types=["heart_rate", "pressure"])
        
        assert f.matches({"alert_type": "heart_rate"})
        assert f.matches({"alert_type": "pressure"})
        assert not f.matches({"alert_type": "temperature"})
    
    def test_filter_combined(self):
        """Testa filtro combinado."""
        f = WebSocketFilter(
            severities=["high", "critical"],
            patient_id="PAC-0001",
            alert_types=["heart_rate"],
        )
        
        # Passa em todos filtros
        assert f.matches({
            "severity": "high",
            "patient_id": "PAC-0001",
            "alert_type": "heart_rate",
        })
        
        # Falha em severidade
        assert not f.matches({
            "severity": "low",
            "patient_id": "PAC-0001",
            "alert_type": "heart_rate",
        })
        
        # Falha em patient_id
        assert not f.matches({
            "severity": "high",
            "patient_id": "PAC-0002",
            "alert_type": "heart_rate",
        })
        
        # Falha em alert_type
        assert not f.matches({
            "severity": "high",
            "patient_id": "PAC-0001",
            "alert_type": "temperature",
        })
    
    def test_filter_no_filters(self):
        """Testa que sem filtros, tudo passa."""
        f = WebSocketFilter()
        
        assert f.matches({"severity": "low", "patient_id": "PAC-999"})
        assert f.matches({"alert_type": "any_type"})
        assert f.matches({})


class TestConnectionManagerOptimized:
    """Testes para ConnectionManagerOptimized."""
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Testa conectar e desconectar."""
        manager = ConnectionManagerOptimized()
        
        # Mock websocket
        ws = AsyncMock()
        ws.accept = AsyncMock()
        
        # Conectar
        await manager.connect(ws)
        assert ws in manager.active_connections
        assert len(manager.active_connections) == 1
        
        # Desconectar
        await manager.disconnect(ws)
        assert ws not in manager.active_connections
        assert len(manager.active_connections) == 0
    
    @pytest.mark.asyncio
    async def test_connect_with_filters(self):
        """Testa conectar com filtros."""
        manager = ConnectionManagerOptimized()
        
        ws = AsyncMock()
        ws.accept = AsyncMock()
        
        filters = WebSocketFilter(severities=["high", "critical"])
        await manager.connect(ws, filters=filters)
        
        assert manager.active_connections[ws]["filters"] == filters
    
    @pytest.mark.asyncio
    async def test_broadcast_no_filters(self):
        """Testa broadcast sem filtros (todos recebem)."""
        manager = ConnectionManagerOptimized()
        
        # Setup 2 clientes
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        
        await manager.connect(ws1)
        await manager.connect(ws2)
        
        # Broadcast
        message = {"type": "alert", "severity": "high"}
        await manager.broadcast(message)
        
        # Ambos devem ter recebido
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
    
    @pytest.mark.asyncio
    async def test_broadcast_with_filters(self):
        """Testa broadcast com filtros (apenas relevantes recebem)."""
        manager = ConnectionManagerOptimized()
        
        # ws1: só recebe high/critical
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        
        filters1 = WebSocketFilter(severities=["high", "critical"])
        await manager.connect(ws1, filters=filters1)
        
        # ws2: recebe tudo
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        
        await manager.connect(ws2)
        
        # Broadcast low severity
        message = {"type": "alert", "severity": "low"}
        await manager.broadcast(message)
        
        # ws1 NÃO recebe (filtrado)
        ws1.send_json.assert_not_called()
        
        # ws2 recebe (sem filtro)
        ws2.send_json.assert_called_once_with(message)
    
    @pytest.mark.asyncio
    async def test_stats(self):
        """Testa obter estatísticas."""
        manager = ConnectionManagerOptimized()
        
        # Sem clientes
        stats = manager.get_stats()
        assert stats["active_clients"] == 0
        
        # Com cliente
        ws = AsyncMock()
        ws.accept = AsyncMock()
        await manager.connect(ws)
        
        stats = manager.get_stats()
        assert stats["active_clients"] == 1
        assert stats["total_messages_sent"] == 0
        
        # Simular envio de mensagem
        manager.active_connections[ws]["messages_sent"] += 5
        stats = manager.get_stats()
        assert stats["total_messages_sent"] == 5


class TestWebSocketEndpoint:
    """Testes para endpoint WebSocket."""
    
    def test_websocket_endpoint_exists(self):
        """Verifica se endpoint existe."""
        from interface.api import router
        
        # Procura por endpoint websocket
        found = False
        for route in router.routes:
            if hasattr(route, 'path') and '/ws/alerts' in route.path:
                found = True
                break
        
        assert found, "Endpoint /ws/alerts não encontrado"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
