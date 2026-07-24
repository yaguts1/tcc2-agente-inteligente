"""Testes para compressão de mensagens WebSocket."""

import pytest
import json
import base64
import gzip

from interface.message_compressor import (
    MessageCompressor,
    CompressionStats,
)


class TestMessageCompressor:
    """Testes para MessageCompressor."""
    
    def test_compress_small_message(self):
        """Testa que mensagens pequenas não são comprimidas."""
        small_data = {"id": 1, "name": "test"}
        
        result = MessageCompressor.compress(small_data)
        
        assert result["compressed"] is False
        assert result["original_size"] > 0
        assert result["compression_ratio"] == 1.0
    
    def test_compress_large_message(self):
        """Testa compressão de mensagem grande."""
        # Criar mensagem grande (>1KB)
        large_data_list = [
            {
                "id": i,
                "name": f"alert_{i}",
                "description": "x" * 100,
                "tags": ["tag1", "tag2", "tag3"] * 10,
            }
            for i in range(50)
        ]
        
        result = MessageCompressor.compress(large_data_list)
        
        assert result["compressed"] is True
        assert result["compressed_size"] < result["original_size"]
        assert result["compression_ratio"] < 1.0
    
    def test_compress_decompress_roundtrip(self):
        """Testa que compress/decompress é lossless."""
        original_data = {
            "alert_type": "heart_rate",
            "severity": "high",
            "patient_id": "PAC-0001",
            "timestamp": "2025-10-27T14:30:00Z",
            "value": 120,
            "unit": "bpm",
        }
        
        # Forçar compressão mesmo se pequeno
        compressed = MessageCompressor.compress(original_data, force=True)
        assert compressed["compressed"] is True
        
        # Descomprimir
        decompressed = MessageCompressor.decompress(compressed)
        
        assert decompressed == original_data
    
    def test_compress_json_string(self):
        """Testa compressão de string JSON."""
        json_str = json.dumps({"x": "y" * 500})
        
        result = MessageCompressor.compress(json_str, force=True)
        
        assert result["compressed"] is True
        assert result["compressed_size"] < result["original_size"]
    
    def test_decompress_uncompressed(self):
        """Testa descompressão de dados não comprimidos."""
        data = {"message": "test"}
        json_str = json.dumps(data)
        
        wrapped = {
            "compressed": False,
            "data": json_str,
        }
        
        result = MessageCompressor.decompress(wrapped)
        
        assert result == data
    
    def test_calculate_savings(self):
        """Testa cálculo de economia."""
        original = 10000  # 10KB
        compressed = 3000  # 3KB
        
        savings = MessageCompressor.calculate_savings(original, compressed)
        
        assert round(savings["original_kb"], 1) == 9.8
        assert round(savings["compressed_kb"], 1) == 2.9
        assert savings["savings_percent"] == 70.0
        assert round(savings["savings_kb"], 2) == 6.84
    
    def test_compress_empty_data(self):
        """Testa compressão de dados vazio."""
        result = MessageCompressor.compress({})
        
        # Deve não comprimir (muito pequeno)
        assert result["compressed"] is False
    
    def test_compress_null_handling(self):
        """Testa lidagem com valores nulos."""
        data = {
            "alert": None,
            "description": None,
            "timestamp": "2025-10-27T14:30:00Z",
        }
        
        result = MessageCompressor.compress(data, force=True)
        decompressed = MessageCompressor.decompress(result)
        
        assert decompressed == data
    
    def test_compress_nested_structures(self):
        """Testa compressão de estruturas aninhadas."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": ["a", "b", "c"] * 100,
                    }
                }
            }
        }
        
        result = MessageCompressor.compress(data, force=True)
        decompressed = MessageCompressor.decompress(result)
        
        assert decompressed == data


class TestCompressionStats:
    """Testes para CompressionStats."""
    
    def test_add_compression(self):
        """Testa adicionar métrica de compressão."""
        stats = CompressionStats()
        
        stats.add_compression(1000, 300)
        
        assert stats.total_messages == 1
        assert stats.total_compressed == 1
        assert stats.total_original_bytes == 1000
        assert stats.total_compressed_bytes == 300
    
    def test_add_uncompressed(self):
        """Testa adicionar métrica de não comprimido."""
        stats = CompressionStats()
        
        stats.add_uncompressed(500)
        
        assert stats.total_messages == 1
        assert stats.total_compressed == 0
        assert stats.total_original_bytes == 500
        assert stats.total_compressed_bytes == 500
    
    def test_get_stats(self):
        """Testa obter estatísticas."""
        stats = CompressionStats()
        
        # Adicionar 1 mensagem comprimida (1000 -> 300)
        stats.add_compression(1000, 300)
        
        # Adicionar 1 mensagem não comprimida (500)
        stats.add_uncompressed(500)
        
        result = stats.get_stats()
        
        assert result["total_messages"] == 2
        assert result["messages_compressed"] == 1
        assert round(result["original_kb"], 2) == 1.46
        assert result["compression_ratio"] < 100
        assert result["savings_percent"] > 0
    
    def test_record_error(self):
        """Testa registrar erro."""
        stats = CompressionStats()
        
        stats.record_error("compression")
        stats.record_error("compression")
        stats.record_error("decompression")
        
        result = stats.get_stats()
        
        assert result["compression_errors"] == 2
        assert result["decompression_errors"] == 1
    
    def test_empty_stats(self):
        """Testa estatísticas vazio."""
        stats = CompressionStats()
        
        result = stats.get_stats()
        
        assert result["total_messages"] == 0
        assert result["savings_percent"] == 0.0


class TestCompressionIntegration:
    """Testes de integração."""
    
    def test_real_alert_compression(self):
        """Testa compressão com alerta real."""
        alert = {
            "id": "ALT-12345",
            "type": "alert_update",
            "alert_type": "heart_rate_abnormal",
            "severity": "high",
            "patient_id": "PAC-0001",
            "patient_name": "João da Silva",
            "value": 125,
            "unit": "bpm",
            "normal_range": "60-100",
            "status": "pending",
            "created_at": "2025-10-27T14:30:00Z",
            "description": "Frequência cardíaca elevada detectada no paciente",
            "actions": [
                {"action": "check", "status": "pending"},
                {"action": "notify", "status": "done"},
            ],
        }
        
        # Simular 100 alertas
        alerts = [alert for _ in range(100)]
        
        result = MessageCompressor.compress(alerts, force=True)
        
        assert result["compressed"] is True
        savings = MessageCompressor.calculate_savings(
            result["original_size"],
            result["compressed_size"],
        )
        
        # Deve ter boa compressão
        assert savings["savings_percent"] > 30
        
        # Descomprimir e validar
        decompressed = MessageCompressor.decompress(result)
        assert len(decompressed) == 100
        assert decompressed[0]["patient_id"] == "PAC-0001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
