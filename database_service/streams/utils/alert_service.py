"""
告警服务抽象层
支持多种告警渠道：控制台、Slack、邮件、Webhook等
与StreamDefinition配置集成，支持stream-specific告警阈值
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Union

# 尝试导入StreamDefinition（可选依赖）
try:
    from ..stream_config import StreamDefinition, RedisStreamConfig
    STREAM_CONFIG_AVAILABLE = True
except ImportError:
    STREAM_CONFIG_AVAILABLE = False
    StreamDefinition = Any
    RedisStreamConfig = Any

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"      # 信息级别
    WARNING = "warning"  # 警告级别
    ERROR = "error"    # 错误级别
    CRITICAL = "critical"  # 严重级别


class AlertType(Enum):
    """告警类型"""
    BACKLOG = "backlog"           # 消息积压
    STUCK_MESSAGE = "stuck_message"  # 消息卡住
    LOW_SUCCESS_RATE = "low_success_rate"  # 低成功率
    AGING_STREAM = "aging_stream"  # Stream老化
    LARGE_STREAM = "large_stream"  # 大型Stream
    INACTIVE_GROUP = "inactive_group"  # 非活跃消费者组
    HIGH_PENDING = "high_pending"  # 高pending消息
    ERROR_RATE = "error_rate"     # 高错误率
    CONNECTION = "connection"     # 连接问题
    GENERAL = "general"           # 通用告警


@dataclass
class AlertContext:
    """告警上下文"""
    stream_name: Optional[str] = None              # Stream名称
    stream_config: Optional[StreamDefinition] = None  # Stream配置
    metric_value: Optional[Any] = None             # 指标值
    threshold: Optional[Any] = None                # 阈值
    timestamp: datetime = None                     # 时间戳
    additional_info: Dict[str, Any] = None         # 附加信息

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.additional_info is None:
            self.additional_info = {}


@dataclass
class Alert:
    """告警"""
    type: AlertType                  # 告警类型
    severity: AlertSeverity          # 告警级别
    message: str                     # 告警消息
    context: AlertContext            # 告警上下文
    timestamp: datetime = None       # 时间戳

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": {
                "stream_name": self.context.stream_name,
                "metric_value": self.context.metric_value,
                "threshold": self.context.threshold,
                "additional_info": self.context.additional_info
            }
        }


class AlertService(ABC):
    """告警服务抽象基类"""

    def __init__(self, name: str = "default", enabled: bool = True):
        """
        初始化告警服务

        Args:
            name: 服务名称
            enabled: 是否启用
        """
        self.name = name
        self.enabled = enabled
        self.stats = {
            "total_alerts": 0,
            "alerts_by_type": {},
            "alerts_by_severity": {},
            "last_alert_time": None
        }
        logger.info(f"✅ 初始化告警服务: {name} (启用: {enabled})")

    @abstractmethod
    async def send_alert(self, alert: Alert) -> bool:
        """
        发送告警（抽象方法）

        Args:
            alert: 告警对象

        Returns:
            bool: 是否发送成功
        """
        pass

    async def send_batch_alerts(self, alerts: List[Alert]) -> List[bool]:
        """
        批量发送告警

        Args:
            alerts: 告警列表

        Returns:
            List[bool]: 每个告警的发送结果
        """
        results = []
        for alert in alerts:
            try:
                result = await self.send_alert(alert)
                results.append(result)
            except Exception as e:
                logger.error(f"发送告警失败: {e}")
                results.append(False)
        return results

    def check_backlog_alert(self, stream_name: str, stream_config: Optional[StreamDefinition],
                           backlog_count: int) -> Optional[Alert]:
        """
        检查积压告警

        Args:
            stream_name: Stream名称
            stream_config: Stream配置
            backlog_count: 积压消息数

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if not stream_config or not stream_config.alert_on_backlog:
            return None

        threshold = stream_config.backlog_threshold
        if backlog_count > threshold:
            context = AlertContext(
                stream_name=stream_name,
                stream_config=stream_config,
                metric_value=backlog_count,
                threshold=threshold,
                additional_info={"threshold_exceeded_by": backlog_count - threshold}
            )

            return Alert(
                type=AlertType.BACKLOG,
                severity=AlertSeverity.WARNING if backlog_count < threshold * 2 else AlertSeverity.ERROR,
                message=f"Stream '{stream_name}' 积压消息 {backlog_count} 条，超过阈值 {threshold}",
                context=context
            )
        return None

    def check_stuck_message_alert(self, stream_name: str, stream_config: Optional[StreamDefinition],
                                oldest_message_age_ms: int) -> Optional[Alert]:
        """
        检查卡住消息告警

        Args:
            stream_name: Stream名称
            stream_config: Stream配置
            oldest_message_age_ms: 最旧消息年龄（毫秒）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if not stream_config or not stream_config.alert_on_stuck:
            return None

        threshold = stream_config.stuck_threshold_ms
        if oldest_message_age_ms > threshold:
            age_seconds = oldest_message_age_ms / 1000
            threshold_seconds = threshold / 1000

            context = AlertContext(
                stream_name=stream_name,
                stream_config=stream_config,
                metric_value=age_seconds,
                threshold=threshold_seconds,
                additional_info={"age_ms": oldest_message_age_ms}
            )

            return Alert(
                type=AlertType.STUCK_MESSAGE,
                severity=AlertSeverity.WARNING if oldest_message_age_ms < threshold * 2 else AlertSeverity.ERROR,
                message=f"Stream '{stream_name}' 最旧消息已卡住 {age_seconds:.1f} 秒，超过阈值 {threshold_seconds:.1f} 秒",
                context=context
            )
        return None

    def check_success_rate_alert(self, operation_type: str, success_rate: float,
                               threshold: float = 0.9) -> Optional[Alert]:
        """
        检查成功率告警

        Args:
            operation_type: 操作类型（publish, consume, ack）
            success_rate: 成功率（0-1）
            threshold: 阈值（默认0.9）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if success_rate < threshold:
            context = AlertContext(
                metric_value=success_rate,
                threshold=threshold,
                additional_info={"operation": operation_type}
            )

            severity = AlertSeverity.WARNING if success_rate > threshold * 0.8 else AlertSeverity.ERROR

            return Alert(
                type=AlertType.LOW_SUCCESS_RATE,
                severity=severity,
                message=f"{operation_type} 成功率较低: {success_rate:.1%}，低于阈值 {threshold:.1%}",
                context=context
            )
        return None

    def check_aging_stream_alert(self, stream_name: str, age_days: float,
                               threshold_days: float = 30) -> Optional[Alert]:
        """
        检查Stream老化告警

        Args:
            stream_name: Stream名称
            age_days: Stream年龄（天）
            threshold_days: 阈值天数（默认30）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if age_days > threshold_days:
            context = AlertContext(
                stream_name=stream_name,
                metric_value=age_days,
                threshold=threshold_days,
                additional_info={"age_days": age_days}
            )

            return Alert(
                type=AlertType.AGING_STREAM,
                severity=AlertSeverity.WARNING if age_days < threshold_days * 2 else AlertSeverity.ERROR,
                message=f"Stream '{stream_name}' 已老化 {age_days:.1f} 天，超过阈值 {threshold_days} 天",
                context=context
            )
        return None

    def check_large_stream_alert(self, stream_name: str, message_count: int,
                               threshold: int = 5000) -> Optional[Alert]:
        """
        检查大型Stream告警

        Args:
            stream_name: Stream名称
            message_count: 消息数量
            threshold: 阈值（默认5000）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if message_count > threshold:
            context = AlertContext(
                stream_name=stream_name,
                metric_value=message_count,
                threshold=threshold,
                additional_info={"exceeded_by": message_count - threshold}
            )

            return Alert(
                type=AlertType.LARGE_STREAM,
                severity=AlertSeverity.WARNING if message_count < threshold * 2 else AlertSeverity.ERROR,
                message=f"Stream '{stream_name}' 消息数 {message_count} 条，超过阈值 {threshold}",
                context=context
            )
        return None

    def check_inactive_group_alert(self, stream_name: str, group_name: str,
                                 inactive_days: float = 7) -> Optional[Alert]:
        """
        检查非活跃消费者组告警

        Args:
            stream_name: Stream名称
            group_name: 消费者组名称
            inactive_days: 非活跃天数阈值（默认7天）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if inactive_days > 7:
            context = AlertContext(
                stream_name=stream_name,
                additional_info={
                    "group_name": group_name,
                    "inactive_days": inactive_days
                }
            )

            return Alert(
                type=AlertType.INACTIVE_GROUP,
                severity=AlertSeverity.WARNING,
                message=f"消费者组 '{group_name}' 在Stream '{stream_name}' 中已非活跃 {inactive_days:.1f} 天",
                context=context
            )
        return None

    def check_high_pending_alert(self, stream_name: str, group_name: str,
                               pending_count: int, threshold: int = 100) -> Optional[Alert]:
        """
        检查高pending消息告警

        Args:
            stream_name: Stream名称
            group_name: 消费者组名称
            pending_count: pending消息数
            threshold: 阈值（默认100）

        Returns:
            Optional[Alert]: 告警对象（如果触发）
        """
        if pending_count > threshold:
            context = AlertContext(
                stream_name=stream_name,
                metric_value=pending_count,
                threshold=threshold,
                additional_info={
                    "group_name": group_name,
                    "exceeded_by": pending_count - threshold
                }
            )

            severity = AlertSeverity.WARNING if pending_count < threshold * 2 else AlertSeverity.ERROR

            return Alert(
                type=AlertType.HIGH_PENDING,
                severity=severity,
                message=f"消费者组 '{group_name}' 在Stream '{stream_name}' 中有 {pending_count} 条pending消息，超过阈值 {threshold}",
                context=context
            )
        return None

    def _update_stats(self, alert: Alert):
        """更新统计信息"""
        self.stats["total_alerts"] += 1
        self.stats["last_alert_time"] = datetime.now()

        # 按类型统计
        alert_type = alert.type.value
        self.stats["alerts_by_type"][alert_type] = self.stats["alerts_by_type"].get(alert_type, 0) + 1

        # 按级别统计
        severity = alert.severity.value
        self.stats["alerts_by_severity"][severity] = self.stats["alerts_by_severity"].get(severity, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "service_name": self.name,
            "enabled": self.enabled,
            **self.stats,
            "alerts_by_type": self.stats["alerts_by_type"].copy(),
            "alerts_by_severity": self.stats["alerts_by_severity"].copy()
        }


class ConsoleAlertService(AlertService):
    """控制台告警服务（打印到控制台）"""

    def __init__(self, name: str = "console", enabled: bool = True,
                 format_template: str = None):
        """
        初始化控制台告警服务

        Args:
            name: 服务名称
            enabled: 是否启用
            format_template: 格式化模板（支持 {type}, {severity}, {message}, {timestamp}）
        """
        super().__init__(name, enabled)
        self.format_template = format_template or "⚠️ [{severity}] {type}: {message}"

    async def send_alert(self, alert: Alert) -> bool:
        """发送告警到控制台"""
        if not self.enabled:
            return False

        try:
            # 格式化消息
            formatted_message = self.format_template.format(
                type=alert.type.value,
                severity=alert.severity.value,
                message=alert.message,
                timestamp=alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                stream=alert.context.stream_name or "global"
            )

            # 根据级别选择日志级别
            if alert.severity == AlertSeverity.CRITICAL:
                logger.critical(formatted_message)
            elif alert.severity == AlertSeverity.ERROR:
                logger.error(formatted_message)
            elif alert.severity == AlertSeverity.WARNING:
                logger.warning(formatted_message)
            else:
                logger.info(formatted_message)

            # 更新统计
            self._update_stats(alert)

            return True

        except Exception as e:
            logger.error(f"发送控制台告警失败: {e}")
            return False


class AlertManager:
    """告警管理器（管理多个告警服务）"""

    def __init__(self, alert_services: List[AlertService] = None):
        """
        初始化告警管理器

        Args:
            alert_services: 告警服务列表
        """
        self.alert_services = alert_services or [ConsoleAlertService()]
        self.stats = {
            "total_alerts_sent": 0,
            "services_count": len(self.alert_services),
            "last_alert_time": None
        }
        logger.info(f"✅ 初始化告警管理器，包含 {len(self.alert_services)} 个告警服务")

    def add_service(self, service: AlertService):
        """添加告警服务"""
        self.alert_services.append(service)
        self.stats["services_count"] += 1
        logger.info(f"✅ 添加告警服务: {service.name}")

    def remove_service(self, service_name: str) -> bool:
        """移除告警服务"""
        for i, service in enumerate(self.alert_services):
            if service.name == service_name:
                self.alert_services.pop(i)
                self.stats["services_count"] -= 1
                logger.info(f"✅ 移除告警服务: {service_name}")
                return True
        return False

    def get_service(self, service_name: str) -> Optional[AlertService]:
        """获取告警服务"""
        for service in self.alert_services:
            if service.name == service_name:
                return service
        return None

    async def send_alert(self, alert: Alert) -> List[Dict[str, Any]]:
        """
        发送告警到所有服务

        Args:
            alert: 告警对象

        Returns:
            各服务的发送结果
        """
        results = []
        for service in self.alert_services:
            try:
                success = await service.send_alert(alert)
                results.append({
                    "service": service.name,
                    "success": success,
                    "timestamp": datetime.now().isoformat()
                })
                if success:
                    self.stats["total_alerts_sent"] += 1
                    self.stats["last_alert_time"] = datetime.now()
            except Exception as e:
                logger.error(f"通过服务 {service.name} 发送告警失败: {e}")
                results.append({
                    "service": service.name,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })

        return results

    async def send_batch_alerts(self, alerts: List[Alert]) -> List[List[Dict[str, Any]]]:
        """
        批量发送告警

        Args:
            alerts: 告警列表

        Returns:
            每个告警的发送结果列表
        """
        results = []
        for alert in alerts:
            alert_results = await self.send_alert(alert)
            results.append(alert_results)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        service_stats = []
        for service in self.alert_services:
            service_stats.append(service.get_stats())

        return {
            **self.stats,
            "services": service_stats,
            "active_services": [s.name for s in self.alert_services]
        }


# 默认告警管理器实例（单例模式）
_default_alert_manager: Optional[AlertManager] = None


def get_default_alert_manager() -> AlertManager:
    """获取默认告警管理器"""
    global _default_alert_manager
    if _default_alert_manager is None:
        _default_alert_manager = AlertManager()
    return _default_alert_manager


def init_alert_manager(services: List[AlertService] = None):
    """初始化告警管理器"""
    global _default_alert_manager
    _default_alert_manager = AlertManager(services)


# 便捷函数
async def send_alert(alert: Alert, manager: AlertManager = None) -> List[Dict[str, Any]]:
    """发送告警（便捷函数）"""
    if manager is None:
        manager = get_default_alert_manager()
    return await manager.send_alert(alert)


async def check_and_send_backlog_alert(stream_name: str, stream_config: Optional[StreamDefinition],
                                      backlog_count: int, manager: AlertManager = None) -> bool:
    """检查并发送积压告警（便捷函数）"""
    if manager is None:
        manager = get_default_alert_manager()

    # 查找支持check_backlog_alert的服务
    for service in manager.alert_services:
        alert = service.check_backlog_alert(stream_name, stream_config, backlog_count)
        if alert:
            results = await manager.send_alert(alert)
            return any(r.get("success", False) for r in results)

    return False


class SlackAlertService(AlertService):
    """Slack告警服务"""

    def __init__(self, name: str = "slack", enabled: bool = True,
                 webhook_url: Optional[str] = None, channel: str = "#alerts",
                 username: str = "Redis Stream Alert", icon_emoji: str = ":warning:"):
        """
        初始化Slack告警服务

        Args:
            name: 服务名称
            enabled: 是否启用
            webhook_url: Slack Webhook URL（环境变量SLACK_WEBHOOK_URL）
            channel: Slack频道
            username: 发送者用户名
            icon_emoji: 图标emoji
        """
        super().__init__(name, enabled)
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self.session = None

        if self.enabled and not self.webhook_url:
            logger.warning(f"⚠️ Slack告警服务 '{name}' 未配置webhook_url，将保持禁用状态")
            self.enabled = False

    async def send_alert(self, alert: Alert) -> bool:
        """发送告警到Slack"""
        if not self.enabled or not self.webhook_url:
            return False

        try:
            import aiohttp

            # 创建aiohttp会话（如果不存在）
            if self.session is None:
                self.session = aiohttp.ClientSession()

            # 构建Slack消息
            color_map = {
                AlertSeverity.INFO: "#36a64f",      # 绿色
                AlertSeverity.WARNING: "#ffcc00",   # 黄色
                AlertSeverity.ERROR: "#ff0000",     # 红色
                AlertSeverity.CRITICAL: "#8b0000"   # 深红色
            }

            color = color_map.get(alert.severity, "#ffcc00")

            # Slack附件格式
            attachments = [{
                "fallback": alert.message,
                "color": color,
                "title": f"{alert.severity.value.upper()}: {alert.type.value}",
                "text": alert.message,
                "fields": [
                    {
                        "title": "Stream",
                        "value": alert.context.stream_name or "global",
                        "short": True
                    },
                    {
                        "title": "时间",
                        "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "short": True
                    }
                ],
                "footer": f"Redis Stream Alert",
                "ts": int(alert.timestamp.timestamp())
            }]

            # 如果有指标值，添加字段
            if alert.context.metric_value is not None:
                attachments[0]["fields"].append({
                    "title": "指标值",
                    "value": str(alert.context.metric_value),
                    "short": True
                })

            if alert.context.threshold is not None:
                attachments[0]["fields"].append({
                    "title": "阈值",
                    "value": str(alert.context.threshold),
                    "short": True
                })

            payload = {
                "channel": self.channel,
                "username": self.username,
                "icon_emoji": self.icon_emoji,
                "attachments": attachments
            }

            # 发送请求
            async with self.session.post(self.webhook_url, json=payload) as response:
                success = response.status == 200
                if success:
                    logger.info(f"✅ Slack告警发送成功: {alert.message[:50]}...")
                else:
                    logger.warning(f"⚠️ Slack告警发送失败: {response.status}")

                # 更新统计
                if success:
                    self._update_stats(alert)

                return success

        except ImportError:
            logger.error("❌ 发送Slack告警需要安装aiohttp: pip install aiohttp")
            self.enabled = False
            return False
        except Exception as e:
            logger.error(f"❌ 发送Slack告警失败: {e}")
            return False

    async def close(self):
        """关闭资源"""
        if self.session:
            await self.session.close()
            self.session = None


class EmailAlertService(AlertService):
    """邮件告警服务（基础实现）"""

    def __init__(self, name: str = "email", enabled: bool = True,
                 smtp_server: Optional[str] = None, smtp_port: int = 587,
                 sender_email: Optional[str] = None, sender_password: Optional[str] = None,
                 recipient_emails: List[str] = None, use_tls: bool = True):
        """
        初始化邮件告警服务

        Args:
            name: 服务名称
            enabled: 是否启用
            smtp_server: SMTP服务器（环境变量SMTP_SERVER）
            smtp_port: SMTP端口
            sender_email: 发件人邮箱（环境变量SMTP_SENDER_EMAIL）
            sender_password: 发件人密码（环境变量SMTP_SENDER_PASSWORD）
            recipient_emails: 收件人邮箱列表
            use_tls: 是否使用TLS
        """
        super().__init__(name, enabled)
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER")
        self.smtp_port = smtp_port
        self.sender_email = sender_email or os.getenv("SMTP_SENDER_EMAIL")
        self.sender_password = sender_password or os.getenv("SMTP_SENDER_PASSWORD")
        self.recipient_emails = recipient_emails or []
        self.use_tls = use_tls

        # 验证配置
        if self.enabled:
            missing_configs = []
            if not self.smtp_server:
                missing_configs.append("SMTP服务器")
            if not self.sender_email:
                missing_configs.append("发件人邮箱")
            if not self.sender_password:
                missing_configs.append("发件人密码")
            if not self.recipient_emails:
                missing_configs.append("收件人邮箱")

            if missing_configs:
                logger.warning(f"⚠️ 邮件告警服务 '{name}' 缺少配置: {', '.join(missing_configs)}，将保持禁用状态")
                self.enabled = False

    async def send_alert(self, alert: Alert) -> bool:
        """发送邮件告警"""
        if not self.enabled or not self.recipient_emails:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # 构建邮件内容
            subject = f"[{alert.severity.value.upper()}] Redis Stream Alert: {alert.type.value}"

            # HTML邮件内容
            html = f"""
            <html>
            <body>
                <h2>Redis Stream 告警</h2>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr><th>类型</th><td>{alert.type.value}</td></tr>
                    <tr><th>级别</th><td>{alert.severity.value}</td></tr>
                    <tr><th>消息</th><td>{alert.message}</td></tr>
                    <tr><th>时间</th><td>{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                    <tr><th>Stream</th><td>{alert.context.stream_name or 'global'}</td></tr>
            """

            if alert.context.metric_value is not None:
                html += f'<tr><th>指标值</th><td>{alert.context.metric_value}</td></tr>'

            if alert.context.threshold is not None:
                html += f'<tr><th>阈值</th><td>{alert.context.threshold}</td></tr>'

            html += """
                </table>
                <p><small>此邮件由 Redis Stream 监控系统自动发送</small></p>
            </body>
            </html>
            """

            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipient_emails)

            # 添加HTML内容
            msg.attach(MIMEText(html, 'html'))

            # 发送邮件（同步操作，在异步环境中可以使用线程池）
            # 这里使用同步发送简化实现
            import asyncio
            loop = asyncio.get_event_loop()

            def sync_send():
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)
                    return True

            success = await loop.run_in_executor(None, sync_send)

            if success:
                logger.info(f"✅ 邮件告警发送成功: {alert.message[:50]}...")
                self._update_stats(alert)

            return success

        except ImportError:
            logger.error("❌ 发送邮件告警需要标准库smtplib和email")
            return False
        except Exception as e:
            logger.error(f"❌ 发送邮件告警失败: {e}")
            return False


class WebhookAlertService(AlertService):
    """Webhook告警服务"""

    def __init__(self, name: str = "webhook", enabled: bool = True,
                 webhook_url: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None,
                 timeout: int = 10):
        """
        初始化Webhook告警服务

        Args:
            name: 服务名称
            enabled: 是否启用
            webhook_url: Webhook URL（环境变量WEBHOOK_URL）
            headers: 自定义HTTP头
            timeout: 请求超时时间（秒）
        """
        super().__init__(name, enabled)
        self.webhook_url = webhook_url or os.getenv("WEBHOOK_URL")
        self.headers = headers or {"Content-Type": "application/json"}
        self.timeout = timeout
        self.session = None

        if self.enabled and not self.webhook_url:
            logger.warning(f"⚠️ Webhook告警服务 '{name}' 未配置webhook_url，将保持禁用状态")
            self.enabled = False

    async def send_alert(self, alert: Alert) -> bool:
        """发送告警到Webhook"""
        if not self.enabled or not self.webhook_url:
            return False

        try:
            import aiohttp

            # 创建aiohttp会话（如果不存在）
            if self.session is None:
                self.session = aiohttp.ClientSession()

            # 构建请求数据
            payload = alert.to_dict()

            # 发送请求
            async with self.session.post(
                self.webhook_url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout
            ) as response:
                success = response.status in (200, 201, 204)
                if success:
                    logger.info(f"✅ Webhook告警发送成功: {alert.message[:50]}...")
                    self._update_stats(alert)
                else:
                    logger.warning(f"⚠️ Webhook告警发送失败: {response.status}")

                return success

        except ImportError:
            logger.error("❌ 发送Webhook告警需要安装aiohttp: pip install aiohttp")
            self.enabled = False
            return False
        except Exception as e:
            logger.error(f"❌ 发送Webhook告警失败: {e}")
            return False

    async def close(self):
        """关闭资源"""
        if self.session:
            await self.session.close()
            self.session = None