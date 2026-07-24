"""
Testes para Rate Limiter do WebSocket
"""
import pytest
import time
from interface.rate_limiter import RateLimiter, PerClientRateLimiter


class TestRateLimiter:
    """Testes unitários do RateLimiter"""
    
    def test_permitir_alertas_dentro_do_limite(self):
        """Deve permitir alertas enquanto dentro do limite"""
        limiter = RateLimiter(max_alerts_per_minute=10)
        
        # Primeiro 10 devem ser permitidos
        for i in range(10):
            assert limiter.is_allowed("client1") is True
    
    def test_bloquear_alertas_alem_do_limite(self):
        """Deve bloquear alertas acima do limite"""
        limiter = RateLimiter(max_alerts_per_minute=5)
        client_id = "client1"
        
        # Enviar 5 (permitidos)
        for i in range(5):
            assert limiter.is_allowed(client_id) is True
        
        # 6º deve ser bloqueado
        assert limiter.is_allowed(client_id) is False
    
    def test_respeitar_limite_por_cliente(self):
        """Limite deve ser independente por cliente"""
        limiter = RateLimiter(max_alerts_per_minute=3)
        
        # Cliente 1: 3 alertas (ok)
        for i in range(3):
            assert limiter.is_allowed("client1") is True
        
        # Cliente 1: 4º bloqueado
        assert limiter.is_allowed("client1") is False
        
        # Cliente 2: deveria permitir (limite independente)
        assert limiter.is_allowed("client2") is True
    
    def test_sliding_window_limpa_alertas_antigos(self):
        """Janela deslizante deve limpar alertas fora do intervalo"""
        limiter = RateLimiter(max_alerts_per_minute=2, window_seconds=1)
        client_id = "client1"
        
        # Enviar 2 alertas
        assert limiter.is_allowed(client_id) is True
        assert limiter.is_allowed(client_id) is True
        
        # 3º bloqueado (limite atingido)
        assert limiter.is_allowed(client_id) is False
        
        # Aguardar 1.5 segundos (alertas antigos saem da janela)
        time.sleep(1.5)
        
        # Agora deveria permitir (window foi limpa)
        assert limiter.is_allowed(client_id) is True
    
    def test_stats_registram_permitidos(self):
        """Stats devem registrar alertas permitidos"""
        limiter = RateLimiter(max_alerts_per_minute=100)
        client_id = "client1"
        
        # Enviar 5 alertas
        for i in range(5):
            limiter.is_allowed(client_id)
        
        stats = limiter.get_stats(client_id)
        assert stats["allowed"] == 5
        assert stats["blocked"] == 0
        assert stats["total"] == 5
    
    def test_stats_registram_bloqueados(self):
        """Stats devem registrar alertas bloqueados"""
        limiter = RateLimiter(max_alerts_per_minute=3)
        client_id = "client1"
        
        # Enviar 3 (permitidos)
        for i in range(3):
            limiter.is_allowed(client_id)
        
        # Enviar 3 (bloqueados)
        for i in range(3):
            limiter.is_allowed(client_id)
        
        stats = limiter.get_stats(client_id)
        assert stats["allowed"] == 3
        assert stats["blocked"] == 3
        assert stats["total"] == 6
        assert stats["block_rate"] == 50.0
    
    def test_reset_cliente(self):
        """Deve reseta limiter de um cliente"""
        limiter = RateLimiter(max_alerts_per_minute=2)
        client_id = "client1"
        
        # Enviar 2 (limite atingido)
        limiter.is_allowed(client_id)
        limiter.is_allowed(client_id)
        
        # 3º bloqueado
        assert limiter.is_allowed(client_id) is False
        
        # Resetar cliente
        limiter.reset_client(client_id)
        
        # Agora deveria permitir novamente
        assert limiter.is_allowed(client_id) is True
    
    def test_reset_all(self):
        """Deve reseta todos os clientes"""
        limiter = RateLimiter(max_alerts_per_minute=2)
        
        # Cliente 1 e 2 no limite
        for i in range(2):
            limiter.is_allowed("client1")
            limiter.is_allowed("client2")
        
        # Ambos bloqueados
        assert limiter.is_allowed("client1") is False
        assert limiter.is_allowed("client2") is False
        
        # Reset all
        limiter.reset_all()
        
        # Ambos devem permitir
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client2") is True
    
    def test_get_all_stats(self):
        """Deve retorna stats de todos os clientes"""
        limiter = RateLimiter(max_alerts_per_minute=100)
        
        # Enviar alertas de 3 clientes
        for i in range(5):
            limiter.is_allowed("client1")
        for i in range(3):
            limiter.is_allowed("client2")
        for i in range(7):
            limiter.is_allowed("client3")
        
        all_stats = limiter.get_all_stats()
        
        assert len(all_stats) == 3
        assert all_stats["client1"]["allowed"] == 5
        assert all_stats["client2"]["allowed"] == 3
        assert all_stats["client3"]["allowed"] == 7


class TestPerClientRateLimiter:
    """Testes para gerenciador de múltiplos clientes"""
    
    def test_criar_limiter_por_cliente(self):
        """Deve criar limiter automático por cliente"""
        manager = PerClientRateLimiter(max_alerts_per_minute=5)
        
        # Primeira chamada cria limiter
        assert manager.check("client1") is True
        assert "client1" in manager.limiters
    
    def test_limites_independentes_por_cliente(self):
        """Cada cliente deve ter limite independente"""
        manager = PerClientRateLimiter(max_alerts_per_minute=2)
        
        # Cliente 1: 2 permitidos, 3º bloqueado
        assert manager.check("client1") is True
        assert manager.check("client1") is True
        assert manager.check("client1") is False
        
        # Cliente 2: deveria permitir
        assert manager.check("client2") is True
    
    def test_remover_cliente(self):
        """Deve remover cliente do gerenciador"""
        manager = PerClientRateLimiter(max_alerts_per_minute=2)
        
        # Adicionar cliente
        manager.check("client1")
        assert "client1" in manager.limiters
        
        # Remover cliente
        manager.remove_client("client1")
        assert "client1" not in manager.limiters
    
    def test_get_stats_cliente(self):
        """Deve retorna stats de um cliente"""
        manager = PerClientRateLimiter(max_alerts_per_minute=100)
        
        # Enviar 5 alertas
        for i in range(5):
            manager.check("client1")
        
        stats = manager.get_stats("client1")
        assert stats["allowed"] == 5
        assert stats["blocked"] == 0
    
    def test_get_stats_cliente_nao_encontrado(self):
        """Deve retorna erro se cliente não existe"""
        manager = PerClientRateLimiter()
        
        stats = manager.get_stats("unknown")
        assert "error" in stats
    
    def test_get_all_stats(self):
        """Deve retorna stats de todos os clientes"""
        manager = PerClientRateLimiter(max_alerts_per_minute=100)
        
        # Enviar de 3 clientes
        for i in range(5):
            manager.check("client1")
        for i in range(3):
            manager.check("client2")
        
        all_stats = manager.get_all_stats()
        assert len(all_stats) == 2
        assert all_stats["client1"]["allowed"] == 5
        assert all_stats["client2"]["allowed"] == 3


class TestRateLimiterIntegration:
    """Testes de integração"""
    
    def test_100_alertas_por_minuto_limite_padrao(self):
        """Padrão deve permitir até 100 alertas/minuto"""
        limiter = RateLimiter(max_alerts_per_minute=100)
        
        # Enviar 100
        for i in range(100):
            assert limiter.is_allowed("client1") is True
        
        # 101º bloqueado
        assert limiter.is_allowed("client1") is False
    
    def test_pausa_e_retoma(self):
        """Deve permitir retomar após pausa"""
        limiter = RateLimiter(max_alerts_per_minute=3, window_seconds=2)
        client_id = "client1"
        
        # 3 alertas
        for i in range(3):
            limiter.is_allowed(client_id)
        
        assert limiter.is_allowed(client_id) is False
        
        # Aguardar window completa
        time.sleep(2.5)
        
        # Deveria permitir novamente
        assert limiter.is_allowed(client_id) is True
    
    def test_carga_multiplos_clientes(self):
        """Deve suportar múltiplos clientes simultaneamente"""
        manager = PerClientRateLimiter(max_alerts_per_minute=10)
        
        # 5 clientes enviando 5 alertas cada
        for client_num in range(5):
            client_id = f"client{client_num}"
            for i in range(5):
                assert manager.check(client_id) is True
        
        # Todos devem ter 5 permitidos
        all_stats = manager.get_all_stats()
        assert len(all_stats) == 5
        for stats in all_stats.values():
            assert stats["allowed"] == 5
            assert stats["blocked"] == 0
    
    def test_simulacao_ataque_spam(self):
        """Simula ataque de spam"""
        limiter = RateLimiter(max_alerts_per_minute=100)
        client_id = "attacker"
        
        # Tentar enviar 500 alertas
        blocked_count = 0
        for i in range(500):
            if not limiter.is_allowed(client_id):
                blocked_count += 1
        
        # Deveria bloquear 400 (permitir 100, bloquear resto)
        assert blocked_count == 400
        
        stats = limiter.get_stats(client_id)
        assert stats["allowed"] == 100
        assert stats["blocked"] == 400
        assert stats["block_rate"] == 80.0
