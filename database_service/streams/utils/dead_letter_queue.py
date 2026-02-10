"""
死信队列管理器
"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class DeadLetterReason(Enum):
    """死信原因"""
    PROCESSING_ERROR = "processing_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT_ERROR = "timeout_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    UNKNOWN_ERROR = "unknown_error"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    INVALID_FORMAT = "invalid_format"

class DeadLetterQueue:
    """死信队列管理器"""
    
    def __init__(self, stream_manager, retention_days: int = 7, max_retries: int = 3):
        self.stream_manager = stream_manager
        self.retention_days = retention_days
        self.max_retries = max_retries
        
        # 统计信息
        self.stats = {
            "total_messages": 0,
            "by_reason": {},
            "retry_success": 0,
            "retry_failed": 0,
            "archived": 0
        }
    
    async def send_to_dlq(self, original_message: Dict[str, Any],
                         original_stream: str,
                         original_id: str,
                         error: str,
                         reason: DeadLetterReason = DeadLetterReason.UNKNOWN_ERROR,
                         metadata: Dict[str, Any] = None) -> Optional[str]:
        """
        发送到死信队列
        
        Args:
            original_message: 原始消息
            original_stream: 原始Stream
            original_id: 原始消息ID
            error: 错误信息
            reason: 死信原因
            metadata: 附加元数据
            
        Returns:
            死信队列消息ID，失败返回None
        """
        try:
            dlq_message = {
                "original_message": original_message,
                "original_stream": original_stream,
                "original_id": original_id,
                "error": error,
                "reason": reason.value,
                "metadata": metadata or {},
                "failed_at": datetime.now().isoformat(),
                "retry_count": 0,
                "last_retry_at": None
            }
            
            message_id = await self.stream_manager.publish(
                "stream:dead:letter",
                dlq_message,
                max_len=1000
            )
            
            # 更新统计
            self.stats["total_messages"] += 1
            reason_str = reason.value
            self.stats["by_reason"][reason_str] = self.stats["by_reason"].get(reason_str, 0) + 1
            
            logger.warning(f"📤 发送到死信队列: {original_id} from {original_stream} ({reason.value})")
            
            return message_id
            
        except Exception as e:
            logger.error(f"❌ 发送到死信队列失败: {e}")
            return None
    
    async def retry_message(self, dlq_message_id: str, dlq_data: Dict[str, Any]) -> bool:
        """
        重试死信队列中的消息
        
        Args:
            dlq_message_id: 死信队列消息ID
            dlq_data: 死信队列消息数据
            
        Returns:
            是否重试成功
        """
        retry_count = dlq_data.get("retry_count", 0) + 1
        
        # 检查是否超过最大重试次数
        if retry_count > self.max_retries:
            logger.warning(f"消息 {dlq_data['original_id']} 已达最大重试次数")
            await self._archive_message(dlq_message_id, dlq_data)
            self.stats["retry_failed"] += 1
            return False
        
        # 更新重试信息
        dlq_data["retry_count"] = retry_count
        dlq_data["last_retry_at"] = datetime.now().isoformat()
        
        try:
            # 重新发布到原始Stream
            await self.stream_manager.publish(
                dlq_data["original_stream"],
                dlq_data["original_message"]
            )
            
            logger.info(f"🔄 重试消息 {dlq_data['original_id']} (尝试 {retry_count})")
            self.stats["retry_success"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"重试消息失败: {e}")
            return False
    
    async def _archive_message(self, message_id: str, message_data: Dict[str, Any]):
        """
        归档消息
        
        Args:
            message_id: 消息ID
            message_data: 消息数据
        """
        # 这里可以实现归档逻辑，例如保存到数据库或文件
        archive_data = {
            **message_data,
            "archived_at": datetime.now().isoformat(),
            "archived_by": "dead_letter_queue"
        }
        
        logger.info(f"📦 归档消息 {message_data['original_id']}")
        self.stats["archived"] += 1
        
        # 实际归档逻辑需要根据具体存储实现
        # 例如：保存到数据库表或写入文件
    
    async def analyze_dlq(self) -> Dict[str, Any]:
        """
        分析死信队列
        
        Returns:
            分析结果
        """
        try:
            # 获取死信队列信息
            info = await self.stream_manager.get_stream_info("stream:dead:letter")
            
            analysis = {
                "total_messages": info.get("length", 0),
                "reasons": self.stats["by_reason"],
                "retry_stats": {
                    "success": self.stats["retry_success"],
                    "failed": self.stats["retry_failed"],
                    "success_rate": self.stats["retry_success"] / max(self.stats["retry_success"] + self.stats["retry_failed"], 1)
                },
                "stats": self.stats,
                "analyzed_at": datetime.now().isoformat()
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析死信队列失败: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_messages(self, max_age_days: int = None):
        """
        清理旧消息
        
        Args:
            max_age_days: 最大保留天数，None使用配置的retention_days
        """
        retention_days = max_age_days or self.retention_days
        logger.info(f"🧹 清理 {retention_days} 天前的死信消息")
        
        # 注意：Redis Stream没有按时间的自动清理功能
        # 这里需要手动实现，或者依赖maxlen自动清理
        # 实际实现取决于具体需求
    
    def should_retry(self, error_type: str) -> bool:
        """
        检查错误类型是否应该重试
        
        Args:
            error_type: 错误类型
            
        Returns:
            是否应该重试
        """
        non_retryable_errors = [
            "validation_error",
            "invalid_format",
            "permission_denied"
        ]
        
        return error_type not in non_retryable_errors
    
    def get_reason_for_error(self, error: str) -> DeadLetterReason:
        """根据错误信息获取死信原因"""
        error_lower = error.lower()
        
        if "timeout" in error_lower:
            return DeadLetterReason.TIMEOUT_ERROR
        elif "validation" in error_lower or "invalid" in error_lower:
            return DeadLetterReason.VALIDATION_ERROR
        elif "max retry" in error_lower or "max_retry" in error_lower:
            return DeadLetterReason.MAX_RETRIES_EXCEEDED
        elif any(service in error_lower for service in ["service", "api", "http"]):
            return DeadLetterReason.EXTERNAL_SERVICE_ERROR
        else:
            return DeadLetterReason.PROCESSING_ERROR
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_messages": 0,
            "by_reason": {},
            "retry_success": 0,
            "retry_failed": 0,
            "archived": 0
        }
