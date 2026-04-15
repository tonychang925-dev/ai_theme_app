"""
ConsumerGroupManager单元测试
测试Redis消费者组管理功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta
import json

from database_service.streams.utils.consumer_group_manager import ConsumerGroupManager


class TestConsumerGroupManager:
    """消费者组管理器测试类"""
    
    @pytest.fixture
    def mock_redis(self):
        """创建模拟Redis客户端"""
        redis_mock = AsyncMock()
        
        # 模拟xinfo_groups返回
        redis_mock.xinfo_groups = AsyncMock()
        
        # 模拟xgroup_destroy
        redis_mock.xgroup_destroy = AsyncMock()
        
        # 模拟keys
        redis_mock.keys = AsyncMock()
        
        # 模拟xinfo_stream
        redis_mock.xinfo_stream = AsyncMock()
        
        # 模拟xpending
        redis_mock.xpending = AsyncMock()
        
        return redis_mock
    
    @pytest.fixture
    def consumer_group_manager(self, mock_redis):
        """创建ConsumerGroupManager实例"""
        config = {
            "protected_groups": ["business_group_1", "business_group_2"],
            "test_group_patterns": [r"test_.*", r"temp_.*"],
            "max_group_age_hours": 24,
            "min_idle_time_minutes": 120,
            "max_pending_messages": 1000,
            "dry_run": False
        }
        return ConsumerGroupManager(mock_redis, config)
    
    @pytest.mark.asyncio
    async def test_cleanup_old_groups_success(self, consumer_group_manager, mock_redis):
        """测试成功清理旧消费者组"""
        # 模拟Stream列表
        mock_redis.keys.return_value = ["stream:test_1", "stream:test_2"]
        
        # 模拟消费者组信息
        mock_redis.xinfo_groups.side_effect = [
            [  # stream:test_1的组
                {
                    "name": "test_group_1",
                    "consumers": 0,
                    "pending": 0,
                    "last-delivered-id": "0-0"
                },
                {
                    "name": "business_group_1",
                    "consumers": 2,
                    "pending": 10,
                    "last-delivered-id": "1000-0"
                }
            ],
            [  # stream:test_2的组
                {
                    "name": "temp_group_1",
                    "consumers": 0,
                    "pending": 0,
                    "last-delivered-id": "0-0"
                }
            ]
        ]
        
        # 模拟Stream信息
        mock_redis.xinfo_stream.return_value = {"length": 0}
        
        # 执行清理
        result = await consumer_group_manager.cleanup_old_groups()
        
        # 验证结果
        assert result["total_streams"] == 2
        assert result["total_groups"] == 3
        assert result["groups_cleaned"] == 2  # test_group_1和temp_group_1
        assert result["groups_protected"] == 1  # business_group_1
        
        # 验证xgroup_destroy被调用
        assert mock_redis.xgroup_destroy.call_count == 2
        
        # 验证调用参数
        calls = mock_redis.xgroup_destroy.call_args_list
        assert calls[0][0] == ("stream:test_1", "test_group_1")
        assert calls[1][0] == ("stream:test_2", "temp_group_1")
    
    @pytest.mark.asyncio
    async def test_cleanup_protected_groups(self, consumer_group_manager, mock_redis):
        """测试保护关键业务组不被清理"""
        # 模拟Stream列表
        mock_redis.keys.return_value = ["stream:business"]
        
        # 模拟业务组信息（有活跃消费者）
        mock_redis.xinfo_groups.return_value = [
            {
                "name": "business_group_1",
                "consumers": 3,
                "pending": 50,
                "last-delivered-id": "2000-0"
            }
        ]
        
        # 执行清理
        result = await consumer_group_manager.cleanup_old_groups()
        
        # 验证业务组被保护
        assert result["groups_cleaned"] == 0
        assert result["groups_protected"] == 1
        
        # 验证xgroup_destroy没有被调用
        mock_redis.xgroup_destroy.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cleanup_dry_run_mode(self, mock_redis):
        """测试干跑模式不实际删除"""
        # 创建干跑模式的manager
        config = {
            "protected_groups": [],
            "test_group_patterns": [r"test_.*"],
            "dry_run": True
        }
        manager = ConsumerGroupManager(mock_redis, config)
        
        # 模拟测试组
        mock_redis.keys.return_value = ["stream:test"]
        mock_redis.xinfo_groups.return_value = [
            {
                "name": "test_group_1",
                "consumers": 0,
                "pending": 0,
                "last-delivered-id": "0-0"
            }
        ]
        mock_redis.xinfo_stream.return_value = {"length": 0}
        
        # 执行清理
        result = await manager.cleanup_old_groups()
        
        # 验证干跑模式下不删除
        assert result["groups_cleaned"] == 0  # 干跑模式下不计入清理
        mock_redis.xgroup_destroy.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_high_pending_messages(self, consumer_group_manager, mock_redis):
        """测试高pending消息检测"""
        # 模拟高pending消息组
        mock_redis.keys.return_value = ["stream:high_pending"]
        mock_redis.xinfo_groups.return_value = [
            {
                "name": "high_pending_group",
                "consumers": 1,
                "pending": 1500,  # 超过阈值
                "last-delivered-id": "1000-0"
            }
        ]
        
        # 模拟pending消息详情
        mock_redis.xpending.return_value = {
            "min": "1000-0",
            "max": "2500-0",
            "count": 1500,
            "consumers": [
                {"name": "consumer_1", "pending": 1500}
            ]
        }
        
        # 执行监控
        result = await consumer_group_manager.monitor_consumer_groups()
        
        # 验证高pending检测
        assert len(result["high_pending_alerts"]) > 0
        alert = result["high_pending_alerts"][0]
        assert alert["group"] == "high_pending_group"
        assert alert["pending_count"] == 1500
        assert alert["stream"] == "stream:high_pending"
    
    @pytest.mark.asyncio
    async def test_monitor_empty_streams(self, consumer_group_manager, mock_redis):
        """测试空Stream监控"""
        mock_redis.keys.return_value = []
        
        result = await consumer_group_manager.monitor_consumer_groups()
        
        assert result["total_streams"] == 0
        assert result["total_groups"] == 0
        assert len(result["group_details"]) == 0
    
    @pytest.mark.asyncio
    async def test_error_handling_redis_failure(self, consumer_group_manager, mock_redis):
        """测试Redis操作失败处理"""
        # 模拟Redis操作失败
        mock_redis.keys.side_effect = Exception("Redis connection failed")
        
        # 执行清理，应该捕获异常
        result = await consumer_group_manager.cleanup_old_groups()
        
        # 验证错误处理
        assert "error" in result
        assert result["error"] == "Redis connection failed"
        assert result["total_streams"] == 0
    
    def test_config_validation(self):
        """测试配置验证"""
        # 测试无效配置
        with pytest.raises(ValueError):
            ConsumerGroupManager(None, {"max_group_age_hours": -1})
        
        # 测试有效配置
        config = {
            "protected_groups": ["group1"],
            "test_group_patterns": [r"test.*"],
            "max_group_age_hours": 24,
            "dry_run": True
        }
        manager = ConsumerGroupManager(Mock(), config)
        
        assert manager.config["protected_groups"] == ["group1"]
        assert manager.config["dry_run"] is True
    
    @pytest.mark.asyncio
    async def test_group_analysis_logic(self, consumer_group_manager):
        """测试组分析逻辑"""
        # 测试数据
        group_info = {
            "name": "test_group_1",
            "consumers": 0,
            "pending": 0,
            "last-delivered-id": "0-0"
        }
        
        # 调用内部分析方法
        analysis = await consumer_group_manager._analyze_group_status(
            "stream:test",
            "test_group_1",
            group_info
        )
        
        # 验证分析结果
        assert analysis["group"] == "test_group_1"
        assert analysis["stream"] == "stream:test"
        assert analysis["consumers"] == 0
        assert analysis["pending"] == 0
        assert analysis["action"] in ["clean", "protect", "skip"]
    
    @pytest.mark.asyncio
    async def test_report_generation(self, consumer_group_manager, mock_redis):
        """测试报告生成"""
        # 模拟一些数据
        mock_redis.keys.return_value = ["stream:test"]
        mock_redis.xinfo_groups.return_value = [
            {
                "name": "test_group",
                "consumers": 0,
                "pending": 0,
                "last-delivered-id": "0-0"
            }
        ]
        mock_redis.xinfo_stream.return_value = {"length": 0}
        
        # 执行清理
        await consumer_group_manager.cleanup_old_groups()
        
        # 生成报告
        report = consumer_group_manager.generate_report()
        
        # 验证报告结构
        assert "summary" in report
        assert "details" in report
        assert "timestamp" in report
        assert "config" in report
        
        # 验证报告内容
        assert report["summary"]["total_streams"] == 1
        assert report["summary"]["total_groups"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
