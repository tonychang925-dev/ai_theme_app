"""
消息序列化器
"""
import json
import zlib
from typing import Dict, Any

class MessageSerializer:
    """消息序列化器"""
    
    def __init__(self, compress_threshold: int = 1024, enable_compression: bool = True):
        self.compress_threshold = compress_threshold
        self.enable_compression = enable_compression
    
    def serialize(self, data: Dict[str, Any]) -> bytes:
        """序列化消息"""
        json_str = json.dumps(data, ensure_ascii=False)
        
        if self.enable_compression and len(json_str.encode('utf-8')) > self.compress_threshold:
            compressed = zlib.compress(json_str.encode('utf-8'))
            return b'C' + compressed
        
        return b'J' + json_str.encode('utf-8')
    
    def deserialize(self, data: bytes) -> Dict[str, Any]:
        """反序列化消息"""
        if data[0] == 67:  # 'C'
            decompressed = zlib.decompress(data[1:])
            json_str = decompressed.decode('utf-8')
        elif data[0] == 74:  # 'J'
            json_str = data[1:].decode('utf-8')
        else:
            json_str = data.decode('utf-8')
        
        return json.loads(json_str)
