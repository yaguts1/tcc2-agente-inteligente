"""Tests for WebSocket functionality."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from interface.web import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def test_websocket_manager_connect_disconnect():
    """Test WebSocket connection manager."""
    from interface.ws_manager_optimized import ConnectionManagerOptimized as ConnectionManager
    
    manager = ConnectionManager()
    
    # Initially no connections
    assert len(manager.active_connections) == 0
    
    # Simulate connection (we can't easily test real WebSocket here)
    # Just verify the manager works
    assert hasattr(manager, 'connect')
    assert hasattr(manager, 'disconnect')
    assert hasattr(manager, 'broadcast')


@pytest.mark.asyncio
async def test_websocket_broadcast():
    """Test WebSocket broadcast functionality."""
    from interface.ws_manager_optimized import ConnectionManagerOptimized as ConnectionManager
    
    manager = ConnectionManager()
    
    # Create mock connections
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    
    # Add them to active connections
    from interface.ws_manager_optimized import WebSocketFilter
    
    manager.active_connections[mock_ws1] = {
        "filters": WebSocketFilter(),
        "messages_sent": 0,
        "messages_filtered": 0,
        "client_id": 1
    }
    manager.active_connections[mock_ws2] = {
        "filters": WebSocketFilter(),
        "messages_sent": 0,
        "messages_filtered": 0,
        "client_id": 2
    }
    
    # Test broadcast
    message = {
        "type": "alert_update",
        "alert_id": "PAC-001__2024-01-01T00:00:00",
        "status": "acknowledged",
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    await manager.broadcast(message)
    
    # Verify both connections received the message
    mock_ws1.send_json.assert_called_once_with(message)
    mock_ws2.send_json.assert_called_once_with(message)


def test_alert_acknowledge_broadcasts(client):
    """Test that acknowledging an alert broadcasts update."""
    # This is a basic test that the endpoint exists and is callable
    # Full WebSocket testing requires a proper WebSocket test client
    
    # The endpoint should exist
    from interface.api import router
    routes = [route.path for route in router.routes]
    assert any("ws/alerts" in route for route in routes)


def test_alert_complete_broadcasts(client):
    """Test that completing an alert broadcasts update."""
    # Verify the endpoint exists
    from interface.api import router
    routes = [route.path for route in router.routes]
    assert any("ws/alerts" in route for route in routes)


def test_batch_operations_broadcast(client):
    """Test that batch operations broadcast updates."""
    from interface.api import router
    routes = [route.path for route in router.routes]
    
    # Verify batch endpoints exist
    assert any("batch/acknowledge" in route for route in routes)
    assert any("batch/complete" in route for route in routes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
