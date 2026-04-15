"""
错误编码系统单元测试
测试标准化错误处理功能
"""

import pytest
from datetime import datetime

from database_service.utils.error_codes import (
    ErrorDomain,
    ErrorSeverity,
    ErrorCode,
    AppError,
    get_error_message,
    format_error_code
)


class TestErrorDomain:
    """测试错误域枚举"""
    
    def test_error_domain_values(self):
        """测试错误域值"""
        assert ErrorDomain.REDIS.value == "REDIS"
        assert ErrorDomain.DATABASE.value == "DATABASE"
        assert ErrorDomain.STREAM.value == "STREAM"
        assert ErrorDomain.AI_SERVICE.value == "AI_SERVICE"
        assert ErrorDomain.NETWORK.value == "NETWORK"
        assert ErrorDomain.VALIDATION.value == "VALIDATION"
        assert ErrorDomain.UNKNOWN.value == "UNKNOWN"
    
    def test_error_domain_from_string(self):
        """测试从字符串获取错误域"""
        assert ErrorDomain("REDIS") == ErrorDomain.REDIS
        assert ErrorDomain("DATABASE") == ErrorDomain.DATABASE
        assert ErrorDomain("STREAM") == ErrorDomain.STREAM
    
    def test_error_domain_invalid(self):
        """测试无效错误域"""
        with pytest.raises(ValueError):
            ErrorDomain("INVALID_DOMAIN")


class TestErrorSeverity:
    """测试错误严重级别"""
    
    def test_error_severity_values(self):
        """测试严重级别值"""
        assert ErrorSeverity.DEBUG.value == "DEBUG"
        assert ErrorSeverity.INFO.value == "INFO"
        assert ErrorSeverity.WARNING.value == "WARNING"
        assert ErrorSeverity.ERROR.value == "ERROR"
        assert ErrorSeverity.CRITICAL.value == "CRITICAL"
    
    def test_error_severity_ordering(self):
        """测试严重级别排序"""
        levels = list(ErrorSeverity)
        assert levels[0] == ErrorSeverity.DEBUG
        assert levels[-1] == ErrorSeverity.CRITICAL
    
    def test_is_more_severe_than(self):
        """测试严重级别比较"""
        assert ErrorSeverity.ERROR.is_more_severe_than(ErrorSeverity.WARNING)
        assert ErrorSeverity.CRITICAL.is_more_severe_than(ErrorSeverity.ERROR)
        assert not ErrorSeverity.INFO.is_more_severe_than(ErrorSeverity.WARNING)
        assert not ErrorSeverity.DEBUG.is_more_severe_than(ErrorSeverity.DEBUG)


class TestErrorCode:
    """测试错误编码类"""
    
    def test_error_code_creation(self):
        """测试错误编码创建"""
        error_code = ErrorCode(
            domain=ErrorDomain.REDIS,
            severity=ErrorSeverity.ERROR,
            code=1,
            message="Redis连接失败",
            suggestion="检查Redis服务状态",
            recovery="重启Redis服务"
        )
        
        assert error_code.domain == ErrorDomain.REDIS
        assert error_code.severity == ErrorSeverity.ERROR
        assert error_code.code == 1
        assert error_code.message == "Redis连接失败"
        assert error_code.suggestion == "检查Redis服务状态"
        assert error_code.recovery == "重启Redis服务"
    
    def test_error_code_format(self):
        """测试错误编码格式"""
        error_code = ErrorCode(
            domain=ErrorDomain.DATABASE,
            severity=ErrorSeverity.WARNING,
            code=2
        )
        
        formatted = error_code.format()
        assert formatted == "DATABASE-WARNING-002"
    
    def test_error_code_from_string(self):
        """测试从字符串解析错误编码"""
        # 有效格式
        error_code = ErrorCode.from_string("REDIS-ERROR-001")
        assert error_code.domain == ErrorDomain.REDIS
        assert error_code.severity == ErrorSeverity.ERROR
        assert error_code.code == 1
        
        # 无效格式
        with pytest.raises(ValueError):
            ErrorCode.from_string("INVALID-FORMAT")
        
        # 无效域
        with pytest.raises(ValueError):
            ErrorCode.from_string("INVALID-ERROR-001")
        
        # 无效严重级别
        with pytest.raises(ValueError):
            ErrorCode.from_string("REDIS-INVALID-001")
    
    def test_error_code_equality(self):
        """测试错误编码相等性"""
        code1 = ErrorCode(ErrorDomain.REDIS, ErrorSeverity.ERROR, 1)
        code2 = ErrorCode(ErrorDomain.REDIS, ErrorSeverity.ERROR, 1)
        code3 = ErrorCode(ErrorDomain.DATABASE, ErrorSeverity.ERROR, 1)
        
        assert code1 == code2
        assert code1 != code3
        assert hash(code1) == hash(code2)
    
    def test_predefined_error_codes(self):
        """测试预定义错误编码"""
        # 测试一些预定义编码存在
        from database_service.utils.error_codes import (
            REDIS_CONNECTION_ERROR,
            DATABASE_QUERY_TIMEOUT,
            STREAM_PROCESSING_ERROR
        )
        
        assert REDIS_CONNECTION_ERROR.domain == ErrorDomain.REDIS
        assert REDIS_CONNECTION_ERROR.severity == ErrorSeverity.ERROR
        assert REDIS_CONNECTION_ERROR.format() == "REDIS-ERROR-001"
        
        assert DATABASE_QUERY_TIMEOUT.domain == ErrorDomain.DATABASE
        assert DATABASE_QUERY_TIMEOUT.severity == ErrorSeverity.WARNING
        assert DATABASE_QUERY_TIMEOUT.format() == "DATABASE-WARNING-002"
        
        assert STREAM_PROCESSING_ERROR.domain == ErrorDomain.STREAM
        assert STREAM_PROCESSING_ERROR.severity == ErrorSeverity.ERROR
        assert STREAM_PROCESSING_ERROR.format() == "STREAM-ERROR-003"


class TestAppError:
    """测试应用异常类"""
    
    def test_app_error_creation(self):
        """测试AppError创建"""
        error = AppError(
            error_code=ErrorCode(
                domain=ErrorDomain.REDIS,
                severity=ErrorSeverity.ERROR,
                code=1
            ),
            message="Redis连接失败",
            details={"host": "localhost", "port": 6379},
            original_exception=ConnectionError("连接被拒绝")
        )
        
        assert error.error_code.domain == ErrorDomain.REDIS
        assert error.message == "Redis连接失败"
        assert error.details == {"host": "localhost", "port": 6379}
        assert isinstance(error.original_exception, ConnectionError)
        assert error.timestamp is not None
        assert isinstance(error.timestamp, datetime)
    
    def test_app_error_str_representation(self):
        """测试AppError字符串表示"""
        error = AppError(
            error_code=ErrorCode(
                domain=ErrorDomain.DATABASE,
                severity=ErrorSeverity.WARNING,
                code=2
            ),
            message="查询超时"
        )
        
        str_repr = str(error)
        assert "DATABASE-WARNING-002" in str_repr
        assert "查询超时" in str_repr
    
    def test_app_error_to_dict(self):
        """测试AppError转换为字典"""
        error = AppError(
            error_code=ErrorCode(
                domain=ErrorDomain.STREAM,
                severity=ErrorSeverity.ERROR,
                code=3
            ),
            message="流处理失败",
            details={"stream": "news_stream", "message_id": "123"}
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error_code"] == "STREAM-ERROR-003"
        assert error_dict["message"] == "流处理失败"
        assert error_dict["severity"] == "ERROR"
        assert error_dict["domain"] == "STREAM"
        assert error_dict["details"] == {"stream": "news_stream", "message_id": "123"}
        assert "timestamp" in error_dict
    
    def test_app_error_from_dict(self):
        """测试从字典创建AppError"""
        error_dict = {
            "error_code": "AI_SERVICE-ERROR-004",
            "message": "模型调用失败",
            "details": {"model": "gpt-4", "attempt": 3},
            "timestamp": "2026-04-14T10:00:00Z"
        }
        
        error = AppError.from_dict(error_dict)
        
        assert error.error_code.format() == "AI_SERVICE-ERROR-004"
        assert error.message == "模型调用失败"
        assert error.details == {"model": "gpt-4", "attempt": 3}
    
    def test_app_error_raise_and_catch(self):
        """测试抛出和捕获AppError"""
        try:
            raise AppError(
                error_code=ErrorCode(
                    domain=ErrorDomain.NETWORK,
                    severity=ErrorSeverity.WARNING,
                    code=5
                ),
                message="网络超时"
            )
        except AppError as e:
            assert e.error_code.domain == ErrorDomain.NETWORK
            assert e.error_code.severity == ErrorSeverity.WARNING
            assert e.message == "网络超时"
    
    def test_app_error_with_original_exception(self):
        """测试包含原始异常的AppError"""
        original = ValueError("无效参数")
        
        try:
            raise original
        except ValueError as e:
            app_error = AppError(
                error_code=ErrorCode(
                    domain=ErrorDomain.VALIDATION,
                    severity=ErrorSeverity.ERROR,
                    code=6
                ),
                message="参数验证失败",
                original_exception=e
            )
            
            assert app_error.original_exception == e
            assert isinstance(app_error.original_exception, ValueError)


class TestUtilityFunctions:
    """测试工具函数"""
    
    def test_format_error_code(self):
        """测试格式化错误编码"""
        code = ErrorCode(ErrorDomain.REDIS, ErrorSeverity.ERROR, 1)
        formatted = format_error_code(code)
        assert formatted == "REDIS-ERROR-001"
        
        # 测试直接使用参数
        formatted = format_error_code(ErrorDomain.DATABASE, ErrorSeverity.WARNING, 2)
        assert formatted == "DATABASE-WARNING-002"
    
    def test_get_error_message(self):
        """测试获取错误消息"""
        # 测试预定义错误
        message = get_error_message("REDIS-ERROR-001")
        assert "Redis连接失败" in message
        
        # 测试未知错误
        message = get_error_message("UNKNOWN-ERROR-999")
        assert "未知错误" in message
        
        # 测试无效格式
        with pytest.raises(ValueError):
            get_error_message("INVALID-FORMAT")
    
    def test_error_code_registry(self):
        """测试错误编码注册表"""
        from database_service.utils.error_codes import ERROR_CODE_REGISTRY
        
        # 测试注册表包含预定义编码
        assert "REDIS-ERROR-001" in ERROR_CODE_REGISTRY
        assert "DATABASE-WARNING-002" in ERROR_CODE_REGISTRY
        assert "STREAM-ERROR-003" in ERROR_CODE_REGISTRY
        
        # 测试注册表值
        redis_error = ERROR_CODE_REGISTRY["REDIS-ERROR-001"]
        assert redis_error.domain == ErrorDomain.REDIS
        assert redis_error.severity == ErrorSeverity.ERROR
        assert redis_error.code == 1


class TestIntegration:
    """集成测试"""
    
    def test_complete_error_flow(self):
        """测试完整错误处理流程"""
        # 1. 创建错误编码
        error_code = ErrorCode(
            domain=ErrorDomain.AI_SERVICE,
            severity=ErrorSeverity.CRITICAL,
            code=7,
            message="AI服务不可用",
            suggestion="检查AI服务状态",
            recovery="重启AI服务"
        )
        
        # 2. 创建异常
        try:
            raise ConnectionError("无法连接到AI服务")
        except ConnectionError as e:
            app_error = AppError(
                error_code=error_code,
                message="AI服务调用失败",
                details={"service": "model_service", "endpoint": "/predict"},
                original_exception=e
            )
        
        # 3. 转换为字典（用于日志/API响应）
        error_dict = app_error.to_dict()
        
        # 4. 验证结果
        assert error_dict["error_code"] == "AI_SERVICE-CRITICAL-007"
        assert error_dict["message"] == "AI服务调用失败"
        assert error_dict["severity"] == "CRITICAL"
        assert error_dict["domain"] == "AI_SERVICE"
        assert error_dict["details"] == {"service": "model_service", "endpoint": "/predict"}
        
        # 5. 从字典恢复
        restored_error = AppError.from_dict(error_dict)
        assert restored_error.error_code.format() == "AI_SERVICE-CRITICAL-007"
        assert restored_error.message == "AI服务调用失败"
    
    def test_error_severity_filtering(self):
        """测试错误严重级别过滤"""
        errors = [
            AppError(ErrorCode(ErrorDomain.REDIS, ErrorSeverity.DEBUG, 1), "调试信息"),
            AppError(ErrorCode(ErrorDomain.DATABASE, ErrorSeverity.INFO, 2), "信息日志"),
            AppError(ErrorCode(ErrorDomain.STREAM, ErrorSeverity.WARNING, 3), "警告"),
            AppError(ErrorCode(ErrorDomain.AI_SERVICE, ErrorSeverity.ERROR, 4), "错误"),
            AppError(ErrorCode(ErrorDomain.NETWORK, ErrorSeverity.CRITICAL, 5), "严重错误"),
        ]
        
        # 过滤出ERROR及以上级别的错误
        severe_errors = [
            e for e in errors 
            if e.error_code.severity.is_more_severe_than(ErrorSeverity.WARNING)
            or e.error_code.severity == ErrorSeverity.ERROR
        ]
        
        assert len(severe_errors) == 2  # ERROR和CRITICAL
        assert severe_errors[0].error_code.severity == ErrorSeverity.ERROR
        assert severe_errors[1].error_code.severity == ErrorSeverity.CRITICAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
