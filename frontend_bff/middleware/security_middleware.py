"""
API安全中间件
提供基础认证、输入验证、安全头设置等功能
"""

import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 添加安全头
        for header, value in self.security_headers.items():
            response.headers[header] = value

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    def __init__(self, app: ASGIApp, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_log: Dict[str, List[float]] = {}
        # 选股页会高频拉取这些只读接口，避免误触发限流影响核心操作。
        self.readonly_exempt_prefixes = (
            "/api/stock-screener/strategies",
            "/api/stock-screener/favorites",
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "GET" and any(path.startswith(prefix) for prefix in self.readonly_exempt_prefixes):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # 清理过期记录
        current_time = time.time()
        if client_ip in self.request_log:
            self.request_log[client_ip] = [
                timestamp for timestamp in self.request_log[client_ip]
                if current_time - timestamp < self.window_seconds
            ]

        # 检查速率限制
        if len(self.request_log.get(client_ip, [])) >= self.max_requests:
            logger.warning(f"速率限制触发: IP={client_ip}, 路径={request.url.path}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"请求过于频繁，请稍后再试。限制: {self.max_requests}次/{self.window_seconds}秒"
                },
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(current_time + self.window_seconds)),
                },
            )

        # 记录请求
        if client_ip not in self.request_log:
            self.request_log[client_ip] = []
        self.request_log[client_ip].append(current_time)

        # 添加速率限制头
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            self.max_requests - len(self.request_log[client_ip])
        )
        response.headers["X-RateLimit-Reset"] = str(
            int(current_time + self.window_seconds)
        )

        return response


class InputValidationMiddleware(BaseHTTPMiddleware):
    """输入验证中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sql_injection_patterns = [
            r"(?i)(union\s+select)",
            r"(?i)(select\s+\*\s+from)",
            r"(?i)(insert\s+into)",
            r"(?i)(update\s+\w+\s+set)",
            r"(?i)(delete\s+from)",
            r"(?i)(drop\s+table)",
            r"(?i)(--\s+)",
            r"(?i)(/\*.*\*/)",
            r"(?i)(;\s*--)",
        ]

        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"data:text/html",
            r"vbscript:",
        ]

        self.path_traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"%2e%2e%5c",
        ]

    async def dispatch(self, request: Request, call_next):
        # 检查查询参数
        for param_name, param_value in request.query_params.items():
            if isinstance(param_value, str):
                self._validate_input(param_name, param_value, "query_param")

        # 检查路径参数
        for param_name, param_value in request.path_params.items():
            if isinstance(param_value, str):
                self._validate_input(param_name, param_value, "path_param")

        # 对于POST/PUT请求，检查请求体
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.json()
                self._validate_json_body(body)
            except:
                # 如果不是JSON，跳过
                pass

        return await call_next(request)

    def _validate_input(self, param_name: str, value: str, input_type: str):
        """验证单个输入值"""
        if not value:
            return

        # SQL注入检查
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"SQL注入尝试: {input_type}={param_name}, value={value[:50]}")
                raise HTTPException(
                    status_code=400,
                    detail=f"输入包含可疑内容: {param_name}"
                )

        # XSS检查
        for pattern in self.xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"XSS尝试: {input_type}={param_name}, value={value[:50]}")
                raise HTTPException(
                    status_code=400,
                    detail=f"输入包含可疑内容: {param_name}"
                )

        # 路径遍历检查
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"路径遍历尝试: {input_type}={param_name}, value={value[:50]}")
                raise HTTPException(
                    status_code=400,
                    detail=f"输入包含可疑内容: {param_name}"
                )

        # 长度检查
        if len(value) > 10000:
            logger.warning(f"输入过长: {input_type}={param_name}, length={len(value)}")
            raise HTTPException(
                status_code=400,
                detail=f"输入过长: {param_name}"
            )

    def _validate_json_body(self, body: Dict):
        """验证JSON请求体"""
        if not isinstance(body, dict):
            return

        def _validate_dict(data: Dict, path: str = ""):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                if isinstance(value, str):
                    self._validate_input(current_path, value, "json_body")
                elif isinstance(value, dict):
                    _validate_dict(value, current_path)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            self._validate_input(f"{current_path}[{i}]", item, "json_body")
                        elif isinstance(item, dict):
                            _validate_dict(item, f"{current_path}[{i}]")

        _validate_dict(body)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """基础认证中间件"""

    def __init__(self, app: ASGIApp, api_key: Optional[str] = None):
        super().__init__(app)
        self.api_key = api_key or os.getenv("API_KEY")
        self.public_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/metrics",
        ]

    async def dispatch(self, request: Request, call_next):
        # 检查是否为公开路径
        if any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)

        # 检查API密钥
        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get("X-API-Key")

        if self.api_key:
            # 支持Bearer token和X-API-Key两种方式
            valid_auth = False

            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                if token == self.api_key:
                    valid_auth = True

            if api_key and api_key == self.api_key:
                valid_auth = True

            if not valid_auth:
                logger.warning(f"认证失败: 路径={request.url.path}, IP={request.client.host}")
                raise HTTPException(
                    status_code=401,
                    detail="无效的API密钥",
                    headers={"WWW-Authenticate": "Bearer"}
                )

        # 记录认证请求
        logger.info(f"认证请求: 路径={request.url.path}, IP={request.client.host}")

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 记录请求信息
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")

        logger.info(f"请求开始: {request.method} {request.url.path} from {client_ip}")

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # 记录响应信息
            logger.info(
                f"请求完成: {request.method} {request.url.path} "
                f"status={response.status_code} "
                f"time={process_time:.3f}s "
                f"from {client_ip}"
            )

            # 添加处理时间头
            response.headers["X-Process-Time"] = str(process_time)

            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"请求异常: {request.method} {request.url.path} "
                f"error={str(e)} "
                f"time={process_time:.3f}s "
                f"from {client_ip}"
            )
            raise


def setup_security_middleware(app: FastAPI):
    """设置安全中间件"""

    # 添加CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # 添加请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)

    # 添加输入验证中间件
    app.add_middleware(InputValidationMiddleware)

    # 添加速率限制中间件
    app.add_middleware(RateLimitMiddleware, max_requests=300, window_seconds=60)

    # 添加安全头中间件
    app.add_middleware(SecurityHeadersMiddleware)

    # 添加认证中间件（如果配置了API密钥）
    api_key = os.getenv("API_KEY")
    if api_key:
        app.add_middleware(AuthenticationMiddleware, api_key=api_key)

    logger.info("✅ 安全中间件配置完成")


# 安全工具函数
def sanitize_input(input_str: str, max_length: int = 1000) -> str:
    """清理输入字符串"""
    if not input_str:
        return ""

    # 限制长度
    if len(input_str) > max_length:
        input_str = input_str[:max_length]

    # 移除危险字符
    dangerous_patterns = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"vbscript:",
        r"expression\s*\(",
        r"url\s*\(",
    ]

    for pattern in dangerous_patterns:
        input_str = re.sub(pattern, "", input_str, flags=re.IGNORECASE)

    # 移除SQL注入关键词
    sql_keywords = [
        r"union\s+select",
        r"select\s+\*\s+from",
        r"insert\s+into",
        r"update\s+\w+\s+set",
        r"delete\s+from",
        r"drop\s+table",
        r"truncate\s+table",
        r"--\s+",
        r"/\*.*\*/",
    ]

    for keyword in sql_keywords:
        input_str = re.sub(keyword, "", input_str, flags=re.IGNORECASE)

    # 移除路径遍历
    input_str = re.sub(r"\.\./|\.\.\\", "", input_str)

    return input_str.strip()


def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """验证手机号格式（中国）"""
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def generate_api_key(length: int = 32) -> str:
    """生成API密钥"""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
