#!/usr/bin/env python3
"""
错误编码系统
为AI主题应用提供标准化的错误分类和编码
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
import json


class ErrorDomain(Enum):
    """错误域 - 标识错误发生的系统模块"""
    REDIS = "REDIS"
    DATABASE = "DB"
    STREAM = "STREAM"
    AI_SERVICE = "AI"
    MODEL_SERVICE = "MODEL"
    FRONTEND = "FE"
    BACKEND_API = "API"
    VALIDATION = "VALID"
    AUTH = "AUTH"
    NETWORK = "NET"
    UNKNOWN = "UNKNOWN"


class ErrorSeverity(Enum):
    """错误严重程度"""
    DEBUG = "DEBUG"      # 调试信息，不影响功能
    INFO = "INFO"        # 信息性消息
    WARNING = "WARN"     # 警告，可能有问题但不影响核心功能
    ERROR = "ERROR"      # 错误，影响部分功能
    CRITICAL = "CRITICAL"  # 严重错误，系统不可用或数据丢失风险


class ErrorCode:
    """错误编码类"""
    
    # 错误编码格式: DOMAIN-SEVERITY-CODE
    # 例如: REDIS-ERROR-001, AI-CRITICAL-101
    
    # Redis相关错误
    REDIS_CONNECTION_FAILED = "REDIS-ERROR-001"
    REDIS_TIMEOUT = "REDIS-ERROR-002"
    REDIS_STREAM_NOT_FOUND = "REDIS-WARN-003"
    REDIS_CONSUMER_GROUP_EXISTS = "REDIS-INFO-004"
    REDIS_CONSUMER_GROUP_NOT_FOUND = "REDIS-ERROR-005"
    REDIS_MESSAGE_FORMAT_ERROR = "REDIS-ERROR-006"
    REDIS_MEMORY_LEAK_DETECTED = "REDIS-CRITICAL-007"
    
    # 数据库相关错误
    DB_CONNECTION_FAILED = "DB-ERROR-101"
    DB_QUERY_FAILED = "DB-ERROR-102"
    DB_TRANSACTION_FAILED = "DB-ERROR-103"
    DB_DATA_NOT_FOUND = "DB-WARN-104"
    DB_CONSTRAINT_VIOLATION = "DB-ERROR-105"
    
    # Stream处理错误
    STREAM_PROCESSING_FAILED = "STREAM-ERROR-201"
    STREAM_HANDLER_NOT_FOUND = "STREAM-ERROR-202"
    STREAM_MESSAGE_VALIDATION_FAILED = "STREAM-ERROR-203"
    STREAM_DEAD_LETTER_QUEUE_FULL = "STREAM-WARN-204"
    
    # AI服务错误
    AI_SERVICE_UNAVAILABLE = "AI-ERROR-301"
    AI_MODEL_LOAD_FAILED = "AI-ERROR-302"
    AI_INFERENCE_TIMEOUT = "AI-ERROR-303"
    AI_BATCH_PROCESSING_FAILED = "AI-ERROR-304"
    AI_RESULT_VALIDATION_FAILED = "AI-WARN-305"
    AI_PERFORMANCE_DEGRADED = "AI-WARN-306"
    
    # 模型服务错误
    MODEL_EXTRACTION_FAILED = "MODEL-ERROR-401"
    MODEL_CLASSIFICATION_FAILED = "MODEL-ERROR-402"
    MODEL_SIMILARITY_CALCULATION_FAILED = "MODEL-ERROR-403"
    MODEL_CACHE_MISS = "MODEL-INFO-404"
    
    # API错误
    API_VALIDATION_ERROR = "API-ERROR-501"
    API_AUTHENTICATION_FAILED = "API-ERROR-502"
    API_RATE_LIMIT_EXCEEDED = "API-WARN-503"
    API_RESOURCE_NOT_FOUND = "API-ERROR-504"
    API_INTERNAL_SERVER_ERROR = "API-ERROR-505"
    
    # 验证错误
    VALIDATION_INPUT_INVALID = "VALID-ERROR-601"
    VALIDATION_REQUIRED_FIELD_MISSING = "VALID-ERROR-602"
    VALIDATION_DATA_TYPE_MISMATCH = "VALID-ERROR-603"
    
    # 网络错误
    NETWORK_CONNECTION_FAILED = "NET-ERROR-701"
    NETWORK_TIMEOUT = "NET-ERROR-702"
    NETWORK_DNS_RESOLUTION_FAILED = "NET-ERROR-703"
    
    @classmethod
    def get_error_info(cls, error_code: str) -> Dict[str, Any]:
        """获取错误码的详细信息"""
        error_info_map = {
            # Redis错误
            cls.REDIS_CONNECTION_FAILED: {
                "message": "Redis连接失败",
                "description": "无法连接到Redis服务器",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.REDIS,
                "suggested_action": "检查Redis服务状态和网络连接",
                "recovery_strategy": "retry_with_backoff"
            },
            cls.REDIS_TIMEOUT: {
                "message": "Redis操作超时",
                "description": "Redis操作在规定时间内未完成",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.REDIS,
                "suggested_action": "检查Redis服务器负载或增加超时时间",
                "recovery_strategy": "retry_with_backoff"
            },
            cls.REDIS_MEMORY_LEAK_DETECTED: {
                "message": "检测到Redis内存泄漏",
                "description": "Redis内存使用持续增长，可能存在内存泄漏",
                "severity": ErrorSeverity.CRITICAL,
                "domain": ErrorDomain.REDIS,
                "suggested_action": "立即检查消费者组状态和清理非活跃组",
                "recovery_strategy": "immediate_intervention"
            },
            
            # AI服务错误
            cls.AI_SERVICE_UNAVAILABLE: {
                "message": "AI服务不可用",
                "description": "无法连接到AI推理服务",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.AI_SERVICE,
                "suggested_action": "检查AI服务状态和网络连接",
                "recovery_strategy": "retry_with_circuit_breaker"
            },
            cls.AI_INFERENCE_TIMEOUT: {
                "message": "AI推理超时",
                "description": "AI模型推理在规定时间内未完成",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.AI_SERVICE,
                "suggested_action": "优化模型或增加超时时间",
                "recovery_strategy": "retry_with_backoff"
            },
            cls.AI_PERFORMANCE_DEGRADED: {
                "message": "AI性能下降",
                "description": "AI处理时间超过预期阈值",
                "severity": ErrorSeverity.WARNING,
                "domain": ErrorDomain.AI_SERVICE,
                "suggested_action": "检查模型性能或考虑批量处理优化",
                "recovery_strategy": "monitor_and_optimize"
            },
            
            # 数据库错误
            cls.DB_CONNECTION_FAILED: {
                "message": "数据库连接失败",
                "description": "无法连接到数据库服务器",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.DATABASE,
                "suggested_action": "检查数据库服务状态和网络连接",
                "recovery_strategy": "retry_with_backoff"
            },
            
            # API错误
            cls.API_VALIDATION_ERROR: {
                "message": "API请求验证失败",
                "description": "请求数据不符合验证规则",
                "severity": ErrorSeverity.ERROR,
                "domain": ErrorDomain.BACKEND_API,
                "suggested_action": "检查请求数据格式和必填字段",
                "recovery_strategy": "client_side_fix"
            },
            cls.API_RATE_LIMIT_EXCEEDED: {
                "message": "API速率限制超出",
                "description": "请求频率超过允许的限制",
                "severity": ErrorSeverity.WARNING,
                "domain": ErrorDomain.BACKEND_API,
                "suggested_action": "降低请求频率或联系管理员调整限制",
                "recovery_strategy": "wait_and_retry"
            }
        }
        
        return error_info_map.get(error_code, {
            "message": "未知错误",
            "description": "未定义的错误代码",
            "severity": ErrorSeverity.ERROR,
            "domain": ErrorDomain.UNKNOWN,
            "suggested_action": "联系系统管理员",
            "recovery_strategy": "manual_intervention"
        })
    
    @classmethod
    def parse_error_code(cls, error_code: str) -> Dict[str, str]:
        """解析错误编码"""
        try:
            parts = error_code.split('-')
            if len(parts) != 3:
                return {
                    "domain": "UNKNOWN",
                    "severity": "ERROR",
                    "code": "000",
                    "valid": False
                }
            
            return {
                "domain": parts[0],
                "severity": parts[1],
                "code": parts[2],
                "valid": True
            }
        except:
            return {
                "domain": "UNKNOWN",
                "severity": "ERROR",
                "code": "000",
                "valid": False
            }


class AppError(Exception):
    """应用错误基类"""
    
    def __init__(self, 
                 error_code: str,
                 message: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None,
                 cause: Optional[Exception] = None):
        """
        初始化应用错误
        
        Args:
            error_code: 错误编码
            message: 错误消息（可选，默认使用错误编码对应的消息）
            details: 错误详情（可选）
            cause: 原始异常（可选）
        """
        self.error_code = error_code
        self.error_info = ErrorCode.get_error_info(error_code)
        
        # 使用提供的消息或默认消息
        self.message = message or self.error_info.get("message", "未知错误")
        self.details = details or {}
        self.cause = cause
        
        # 解析错误编码
        self.parsed_code = ErrorCode.parse_error_code(error_code)
        
        # 时间戳
        self.timestamp = datetime.now().isoformat()
        
        # 构建完整消息
        full_message = f"[{error_code}] {self.message}"
        if cause:
            full_message += f" (原因: {str(cause)})"
        
        super().__init__(full_message)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "domain": self.parsed_code["domain"],
            "severity": self.parsed_code["severity"],
            "numeric_code": self.parsed_code["code"],
            "details": self.details,
            "timestamp": self.timestamp,
            "suggested_action": self.error_info.get("suggested_action"),
            "recovery_strategy": self.error_info.get("recovery_strategy")
        }
    
    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @property
    def severity(self) -> ErrorSeverity:
        """获取错误严重程度"""
        return self.error_info.get("severity", ErrorSeverity.ERROR)
    
    @property
    def domain(self) -> ErrorDomain:
        """获取错误域"""
        return self.error_info.get("domain", ErrorDomain.UNKNOWN)


class ErrorResponse:
    """错误响应类 - 用于API响应"""
    
    def __init__(self, error: AppError, request_id: Optional[str] = None):
        self.error = error
        self.request_id = request_id
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        response = {
            "success": False,
            "error": self.error.to_dict(),
            "timestamp": self.timestamp
        }
        
        if self.request_id:
            response["request_id"] = self.request_id
        
        return response
    
    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


# 便捷错误创建函数
def create_error(error_code: str, 
                 message: Optional[str] = None,
                 details: Optional[Dict] = None,
                 cause: Optional[Exception] = None) -> AppError:
    """创建应用错误"""
    return AppError(error_code, message, details, cause)


def create_redis_connection_error(cause: Optional[Exception] = None) -> AppError:
    """创建Redis连接错误"""
    return create_error(ErrorCode.REDIS_CONNECTION_FAILED, cause=cause)


def create_ai_service_error(cause: Optional[Exception] = None) -> AppError:
    """创建AI服务错误"""
    return create_error(ErrorCode.AI_SERVICE_UNAVAILABLE, cause=cause)


def create_validation_error(field: str, reason: str) -> AppError:
    """创建验证错误"""
    details = {"field": field, "reason": reason}
    return create_error(ErrorCode.VALIDATION_INPUT_INVALID, details=details)


def create_api_error(error_code: str, 
                     message: Optional[str] = None,
                     details: Optional[Dict] = None) -> AppError:
    """创建API错误"""
    return create_error(error_code, message, details)


# 测试函数
def test_error_codes():
    """测试错误编码系统"""
    print("🧪 测试错误编码系统...")
    print("=" * 60)
    
    # 测试错误创建
    try:
        raise create_redis_connection_error(
            cause=Exception("Connection refused")
        )
    except AppError as e:
        print(f"1. Redis连接错误:")
        print(f"   错误码: {e.error_code}")
        print(f"   消息: {e.message}")
        print(f"   严重程度: {e.severity.value}")
        print(f"   建议操作: {e.error_info.get('suggested_action')}")
        print()
    
    # 测试验证错误
    try:
        raise create_validation_error("email", "无效的邮箱格式")
    except AppError as e:
        print(f"2. 验证错误:")
        print(f"   错误码: {e.error_code}")
        print(f"   详情: {e.details}")
        print()
    
    # 测试错误响应
    error = create_ai_service_error(
        cause=Exception("AI服务超时")
    )
    response = ErrorResponse(error, request_id="req_123456")
    
    print(f"3. 错误响应:")
    print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
    print()
    
    # 测试错误码解析
    test_codes = [
        ErrorCode.REDIS_CONNECTION_FAILED,
        ErrorCode.AI_PERFORMANCE_DEGRADED,
        ErrorCode.API_RATE_LIMIT_EXCEEDED,
        "INVALID-CODE-FORMAT"
    ]
    
    print(f"4. 错误码解析:")
    for code in test_codes:
        parsed = ErrorCode.parse_error_code(code)
        print(f"   {code} -> 域: {parsed['domain']}, 严重程度: {parsed['severity']}, 有效: {parsed['valid']}")
    
    print("=" * 60)
    print("✅ 错误编码系统测试完成")


if __name__ == "__main__":
    test_error_codes()
