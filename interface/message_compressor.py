"""Compressão de mensagens WebSocket para reduzir bandwidth."""

import gzip
import json
from typing import Any, Dict, Union
import structlog


logger = structlog.get_logger(__name__)


class MessageCompressor:
    """
    Compressor/Decompressor de mensagens WebSocket.
    
    Usa gzip para comprimir mensagens JSON, reduzindo tamanho em 30-50%.
    
    Benefícios:
    - Reduz tamanho de mensagens em 30-50% (típico)
    - Melhor performance em rede lenta/mobile
    - Transparente para a aplicação
    
    Desvantagem:
    - Adiciona ~2-5ms de overhead de compressão/decompressão
    - Não vale a pena para mensagens muito pequenas (<1KB)
    """
    
    # Limite mínimo para comprimir (em bytes)
    # Não vale a pena comprimir mensagens muito pequenas
    MIN_SIZE_TO_COMPRESS = 1024  # 1KB
    
    # Nível de compressão (1-9, quanto maior mais compressão mas mais CPU)
    COMPRESSION_LEVEL = 6  # Balanço entre compressão e CPU
    
    @staticmethod
    def compress(data: Union[Dict, str], force: bool = False) -> Dict[str, Any]:
        """
        Comprime dados JSON.
        
        Args:
            data: Dados para comprimir (dict ou string JSON)
            force: Se True, comprime mesmo se pequeno
        
        Returns:
            {
                "compressed": True/False (se foi realmente comprimido),
                "original_size": int,
                "compressed_size": int,
                "compression_ratio": float (0.0-1.0),
                "data": str (base64 se comprimido, ou JSON se não)
            }
        """
        try:
            # Converter para JSON string
            if isinstance(data, str):
                json_str = data
            else:
                json_str = json.dumps(data)
            
            json_bytes = json_str.encode('utf-8')
            original_size = len(json_bytes)
            
            # Decidir se vale a pena comprimir
            should_compress = force or original_size >= MessageCompressor.MIN_SIZE_TO_COMPRESS
            
            if not should_compress:
                logger.debug(
                    "message_too_small_to_compress",
                    size=original_size,
                    threshold=MessageCompressor.MIN_SIZE_TO_COMPRESS,
                )
                return {
                    "compressed": False,
                    "original_size": original_size,
                    "compressed_size": original_size,
                    "compression_ratio": 1.0,
                    "data": json_str,
                }
            
            # Comprimir com gzip
            compressed_bytes = gzip.compress(
                json_bytes,
                compresslevel=MessageCompressor.COMPRESSION_LEVEL,
            )
            compressed_size = len(compressed_bytes)
            compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
            
            # Converter para base64 para poder enviar via texto
            import base64
            compressed_b64 = base64.b64encode(compressed_bytes).decode('ascii')
            
            logger.debug(
                "message_compressed",
                original_size=original_size,
                compressed_size=compressed_size,
                ratio=f"{compression_ratio:.2%}",
            )
            
            return {
                "compressed": True,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "compression_ratio": compression_ratio,
                "data": compressed_b64,
            }
        
        except Exception as e:
            logger.error("compression_error", error=str(e))
            # Fallback: retornar sem comprimir
            json_str = json.dumps(data) if not isinstance(data, str) else data
            return {
                "compressed": False,
                "original_size": len(json_str),
                "compressed_size": len(json_str),
                "compression_ratio": 1.0,
                "data": json_str,
                "error": str(e),
            }
    
    @staticmethod
    def decompress(compressed_data: Dict[str, Any]) -> Union[Dict, str]:
        """
        Descomprime dados JSON.
        
        Args:
            compressed_data: Dados comprimidos (saída de compress())
        
        Returns:
            Dict ou string JSON descomprimida
        """
        try:
            if not compressed_data.get("compressed"):
                # Não estava comprimido, apenas retornar
                data = compressed_data.get("data")
                if isinstance(data, str):
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        return data
                return data
            
            # Descomprimir
            import base64
            compressed_b64 = compressed_data.get("data")
            compressed_bytes = base64.b64decode(compressed_b64)
            json_bytes = gzip.decompress(compressed_bytes)
            json_str = json_bytes.decode('utf-8')
            
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return json_str
        
        except Exception as e:
            logger.error("decompression_error", error=str(e))
            raise
    
    @staticmethod
    def calculate_savings(original_size: int, compressed_size: int) -> Dict[str, Any]:
        """
        Calcula economia de bandwidth.
        
        Args:
            original_size: Tamanho original em bytes
            compressed_size: Tamanho comprimido em bytes
        
        Returns:
            {
                "original_kb": float,
                "compressed_kb": float,
                "savings_percent": float,
                "savings_kb": float,
            }
        """
        original_kb = original_size / 1024
        compressed_kb = compressed_size / 1024
        savings_kb = (original_size - compressed_size) / 1024
        savings_percent = (
            ((original_size - compressed_size) / original_size * 100)
            if original_size > 0
            else 0
        )
        
        return {
            "original_kb": round(original_kb, 3),
            "compressed_kb": round(compressed_kb, 3),
            "savings_percent": round(savings_percent, 1),
            "savings_kb": round(savings_kb, 3),
        }


class CompressionStats:
    """Rastreia estatísticas de compressão."""
    
    def __init__(self):
        """Inicializa estatísticas."""
        self.total_messages = 0
        self.total_compressed = 0
        self.total_original_bytes = 0
        self.total_compressed_bytes = 0
        self.compression_errors = 0
        self.decompression_errors = 0
    
    def add_compression(self, original_size: int, compressed_size: int):
        """Adiciona métrica de compressão."""
        self.total_messages += 1
        self.total_compressed += 1
        self.total_original_bytes += original_size
        self.total_compressed_bytes += compressed_size
    
    def add_uncompressed(self, size: int):
        """Adiciona métrica de mensagem não comprimida."""
        self.total_messages += 1
        self.total_original_bytes += size
        self.total_compressed_bytes += size
    
    def record_error(self, error_type: str = "compression"):
        """Registra erro."""
        if error_type == "decompression":
            self.decompression_errors += 1
        else:
            self.compression_errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas."""
        overall_ratio = (
            (self.total_compressed_bytes / self.total_original_bytes * 100)
            if self.total_original_bytes > 0
            else 100
        )
        
        savings_percent = 100 - overall_ratio
        savings_kb = (self.total_original_bytes - self.total_compressed_bytes) / 1024
        
        return {
            "total_messages": self.total_messages,
            "messages_compressed": self.total_compressed,
            "original_kb": round(self.total_original_bytes / 1024, 2),
            "compressed_kb": round(self.total_compressed_bytes / 1024, 2),
            "compression_ratio": round(overall_ratio, 1),
            "savings_percent": round(savings_percent, 1),
            "savings_kb": round(savings_kb, 2),
            "compression_errors": self.compression_errors,
            "decompression_errors": self.decompression_errors,
        }
    
    def __repr__(self):
        stats = self.get_stats()
        return (
            f"CompressionStats("
            f"msgs={stats['total_messages']}, "
            f"compressed={stats['messages_compressed']}, "
            f"savings={stats['savings_percent']}%)"
        )


# Instância global de estatísticas
compression_stats = CompressionStats()
