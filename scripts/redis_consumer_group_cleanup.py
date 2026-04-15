#!/usr/bin/env python3
"""
Redis消费者组自动化清理脚本
增强版 - 提供更安全的清理功能和详细报告
"""

import asyncio
import logging
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# 添加项目路径
sys.path.append('.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnhancedConsumerGroupCleanup:
    """增强版消费者组清理器"""
    
    def __init__(self, redis_client, config: Optional[Dict] = None):
        self.redis = redis_client
        self.config = config or {}
        
        # 默认配置
        self.default_config = {
            "cleanup_enabled": True,
            "max_group_age_hours": 24,
            "cleanup_interval_minutes": 60,
            "min_idle_time_minutes": 120,  # 最小空闲时间（分钟）
            "max_pending_messages": 0,  # 最大pending消息数（0表示不允许有pending）
            "dry_run": False,  # 干跑模式，不实际删除
            "protected_groups": [
                "news_storage_handlers",
                "theme_processors_v1", 
                "major_workers",
                "theme_workers",
                "data_updaters",
                "monitoring",
                "news_business_processors"  # 保护业务处理器
            ],
            "test_group_patterns": [
                r"test_.*",
                r"temp_.*",
                r"p2_.*",
                r"business_\d{8}_\d{6}",  # business_20260410_224431 模式
                r"database_service_group:.*",  # database_service_group:stats, :cache, :themes, :relations
                r".*test.*",  # sse_testers
                r".*update.*",  # update_subscribers
                r".*cluster.*"  # clustering_workers
            ],
            "report_file": "consumer_group_cleanup_report.json"
        }
        
        # 更新配置
        self.default_config.update(self.config)
        self.config = self.default_config
        
        # 清理统计
        self.stats = {
            "start_time": datetime.now().isoformat(),
            "total_streams": 0,
            "total_groups": 0,
            "groups_cleaned": 0,
            "groups_protected": 0,
            "groups_skipped": 0,
            "errors": [],
            "details": []
        }
        
        logger.info(f"🧹 初始化增强版消费者组清理器")
        logger.info(f"   干跑模式: {'✅ 启用' if self.config['dry_run'] else '❌ 禁用'}")
        logger.info(f"   保护组: {len(self.config['protected_groups'])}个")
        logger.info(f"   测试组模式: {len(self.config['test_group_patterns'])}个")
    
    async def run_cleanup(self) -> Dict[str, Any]:
        """执行清理任务"""
        if not self.config["cleanup_enabled"]:
            logger.warning("清理功能已禁用")
            return {"enabled": False}
        
        logger.info("🚀 开始执行消费者组清理任务")
        
        try:
            # 1. 获取所有Stream
            streams = await self._get_all_streams()
            self.stats["total_streams"] = len(streams)
            logger.info(f"📊 找到 {len(streams)} 个Streams")
            
            # 2. 分析每个Stream的消费者组
            for stream in streams:
                await self._analyze_stream_groups(stream)
            
            # 3. 执行清理（如果不是干跑模式）
            if not self.config["dry_run"]:
                await self._execute_cleanup()
            
            # 4. 生成报告
            report = await self._generate_report()
            
            logger.info(f"✅ 清理任务完成")
            logger.info(f"   总计组数: {self.stats['total_groups']}")
            logger.info(f"   清理组数: {self.stats['groups_cleaned']}")
            logger.info(f"   保护组数: {self.stats['groups_protected']}")
            logger.info(f"   跳过组数: {self.stats['groups_skipped']}")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ 清理任务失败: {e}")
            self.stats["errors"].append({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            return {"error": str(e)}
    
    async def _get_all_streams(self, pattern: str = "stream:*") -> List[str]:
        """获取所有Stream名称"""
        try:
            streams = await self.redis.keys(pattern)
            return [s.decode('utf-8') if isinstance(s, bytes) else s for s in streams]
        except Exception as e:
            logger.warning(f"获取Stream列表失败: {e}")
            return []
    
    async def _analyze_stream_groups(self, stream: str):
        """分析Stream的消费者组"""
        try:
            groups_info = await self.redis.xinfo_groups(stream)
            
            for group_info in groups_info:
                self.stats["total_groups"] += 1
                group_name = group_info["name"]
                
                # 分析组状态
                analysis = await self._analyze_group_status(stream, group_name, group_info)
                
                # 记录详情
                self.stats["details"].append({
                    "stream": stream,
                    "group": group_name,
                    "analysis": analysis,
                    "timestamp": datetime.now().isoformat()
                })
                
                # 更新统计
                if analysis["action"] == "clean":
                    logger.debug(f"标记清理: {stream}/{group_name}")
                elif analysis["action"] == "protect":
                    self.stats["groups_protected"] += 1
                    logger.debug(f"标记保护: {stream}/{group_name}")
                else:
                    self.stats["groups_skipped"] += 1
                    
        except Exception as e:
            logger.warning(f"分析Stream失败 {stream}: {e}")
    
    async def _analyze_group_status(self, stream: str, group: str, group_info: Dict) -> Dict[str, Any]:
        """分析消费者组状态，决定处理动作"""
        import re
        
        consumers = group_info.get("consumers", 0)
        pending = group_info.get("pending", 0)
        last_delivered = group_info.get("last-delivered-id", "0-0")
        
        analysis = {
            "group": group,
            "stream": stream,
            "consumers": consumers,
            "pending": pending,
            "last_delivered": last_delivered,
            "action": "skip",  # skip, protect, clean
            "reason": "",
            "risk_level": "low"
        }
        
        # 1. 检查是否为保护组
        if group in self.config["protected_groups"]:
            analysis["action"] = "protect"
            analysis["reason"] = "protected_group"
            analysis["risk_level"] = "none"
            return analysis
        
        # 2. 检查是否有活跃消费者
        if consumers > 0:
            analysis["action"] = "protect"
            analysis["reason"] = "active_consumers"
            analysis["risk_level"] = "none"
            return analysis
        
        # 3. 检查是否有pending消息
        if pending > self.config["max_pending_messages"]:
            analysis["action"] = "protect"
            analysis["reason"] = f"has_pending_messages_{pending}"
            analysis["risk_level"] = "medium"
            return analysis
        
        # 4. 检查是否匹配测试组模式
        is_test_group = False
        for pattern in self.config["test_group_patterns"]:
            if re.match(pattern, group):
                is_test_group = True
                break
        
        if not is_test_group:
            analysis["action"] = "protect"
            analysis["reason"] = "not_test_group"
            analysis["risk_level"] = "high"  # 非测试组需要谨慎
            return analysis
        
        # 5. 检查最后活动时间（简化版）
        if last_delivered == "0-0":
            # 从未消费过消息，可能是测试创建的
            analysis["action"] = "clean"
            analysis["reason"] = "never_consumed"
            analysis["risk_level"] = "low"
        else:
            # 尝试估算空闲时间
            try:
                # 获取Stream信息
                stream_info = await self.redis.xinfo_stream(stream)
                if stream_info.get("length", 0) == 0:
                    # 空Stream，可清理
                    analysis["action"] = "clean"
                    analysis["reason"] = "empty_stream"
                    analysis["risk_level"] = "low"
                else:
                    # 需要更复杂的时间判断，暂时保护
                    analysis["action"] = "protect"
                    analysis["reason"] = "has_consumption_history"
                    analysis["risk_level"] = "medium"
            except:
                # 获取信息失败，保护
                analysis["action"] = "protect"
                analysis["reason"] = "info_check_failed"
                analysis["risk_level"] = "medium"
        
        return analysis
    
    async def _execute_cleanup(self):
        """执行清理操作"""
        logger.info("执行实际清理操作...")
        
        cleaned_count = 0
        for detail in self.stats["details"]:
            if detail["analysis"]["action"] == "clean":
                stream = detail["stream"]
                group = detail["group"]
                
                try:
                    await self.redis.xgroup_destroy(stream, group)
                    cleaned_count += 1
                    logger.info(f"🧹 清理消费者组: {stream}/{group}")
                    
                    # 更新详情
                    detail["cleaned"] = True
                    detail["cleaned_at"] = datetime.now().isoformat()
                    
                except Exception as e:
                    if "NOGROUP" in str(e):
                        logger.debug(f"组已不存在: {stream}/{group}")
                        detail["cleaned"] = True
                        detail["note"] = "already_deleted"
                    else:
                        logger.error(f"清理失败 {stream}/{group}: {e}")
                        detail["cleaned"] = False
                        detail["error"] = str(e)
        
        self.stats["groups_cleaned"] = cleaned_count
    
    async def _generate_report(self) -> Dict[str, Any]:
        """生成清理报告"""
        report = {
            "metadata": {
                "script_version": "1.1.0",
                "run_time": self.stats["start_time"],
                "end_time": datetime.now().isoformat(),
                "config": self.config,
                "dry_run": self.config["dry_run"]
            },
            "statistics": {
                "total_streams": self.stats["total_streams"],
                "total_groups": self.stats["total_groups"],
                "groups_cleaned": self.stats["groups_cleaned"],
                "groups_protected": self.stats["groups_protected"],
                "groups_skipped": self.stats["groups_skipped"],
                "error_count": len(self.stats["errors"])
            },
            "details": self.stats["details"],
            "errors": self.stats["errors"],
            "recommendations": []
        }
        
        # 生成建议
        if self.stats["groups_cleaned"] > 0:
            report["recommendations"].append({
                "type": "success",
                "message": f"成功清理 {self.stats['groups_cleaned']} 个非活跃测试组",
                "action": "监控系统内存使用变化"
            })
        
        if any(d["analysis"]["risk_level"] == "high" for d in self.stats["details"]):
            report["recommendations"].append({
                "type": "warning",
                "message": "发现高风险组（非测试模式但有清理标记）",
                "action": "手动审查这些组: " + ", ".join(
                    f"{d['stream']}/{d['group']}" 
                    for d in self.stats["details"] 
                    if d["analysis"]["risk_level"] == "high"
                )[:100] + "..."
            })
        
        # 保存报告到文件
        if self.config["report_file"]:
            try:
                with open(self.config["report_file"], 'w') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                logger.info(f"📄 报告已保存: {self.config['report_file']}")
            except Exception as e:
                logger.error(f"保存报告失败: {e}")
        
        return report
    
    def print_summary(self):
        """打印清理摘要"""
        print("\n" + "=" * 70)
        print("🧹 Redis消费者组清理摘要")
        print("=" * 70)
        
        print(f"📊 统计信息:")
        print(f"   总Streams数: {self.stats['total_streams']}")
        print(f"   总消费者组数: {self.stats['total_groups']}")
        print(f"   清理组数: {self.stats['groups_cleaned']}")
        print(f"   保护组数: {self.stats['groups_protected']}")
        print(f"   跳过组数: {self.stats['groups_skipped']}")
        print(f"   错误数: {len(self.stats['errors'])}")
        
        print(f"\n⚙️  配置信息:")
        print(f"   干跑模式: {'✅ 是' if self.config['dry_run'] else '❌ 否'}")
        print(f"   保护组: {len(self.config['protected_groups'])}个")
        print(f"   最大组年龄: {self.config['max_group_age_hours']}小时")
        
        print(f"\n📋 清理详情 (前5个):")
        for i, detail in enumerate(self.stats["details"][:5]):
            action = detail["analysis"]["action"]
            reason = detail["analysis"]["reason"]
            print(f"   {i+1}. {detail['stream']}/{detail['group']}")
            print(f"      动作: {action}, 原因: {reason}")
        
        if self.stats["errors"]:
            print(f"\n❌ 错误列表:")
            for error in self.stats["errors"][:3]:
                print(f"   - {error.get('error', '未知错误')}")
        
        print("=" * 70)


async def main():
    """主函数"""
    import redis.asyncio as redis
    
    print("🚀 Redis消费者组自动化清理脚本")
    print("=" * 60)
    
    # 配置选项
    config = {
        "dry_run": True,  # 第一次运行使用干跑模式
        "max_group_age_hours": 24,
        "min_idle_time_minutes": 120,
        "max_pending_messages": 0,
        "report_file": "consumer_group_cleanup_report_20260414.json",
        "protected_groups": [
            "news_storage_handlers",
            "theme_processors_v1",
            "major_workers", 
            "theme_workers",
            "data_updaters",
            "monitoring",
            "news_business_processors",
            "realtime_push_service",
            "sse_pushers",
            "event_review_writers"
        ]
    }
    
    print("⚙️  配置:")
    print(f"   模式: {'🧪 干跑模式 (不实际删除)' if config['dry_run'] else '🔧 实际清理模式'}")
    print(f"   保护组: {len(config['protected_groups'])}个关键业务组")
    print(f"   报告文件: {config['report_file']}")
    print()
    
    try:
        # 连接Redis
        redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)
        
        # 创建清理器
        cleanup = EnhancedConsumerGroupCleanup(redis_client, config)
        
        # 执行清理
        report = await cleanup.run_cleanup()
        
        # 打印摘要
        cleanup.print_summary()
        
        # 关闭连接
        await redis_client.close()
        
        if config["dry_run"]:
            print("\n💡 建议:")
            print("1. 检查干跑模式报告，确认标记为清理的组确实可以删除")
            print("2. 修改配置 dry_run=False 后再次运行以实际清理")
            print("3. 将清理脚本加入定时任务 (cron)")
        
        return report
        
    except Exception as e:
        print(f"❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    # 运行清理脚本
    report = asyncio.run(main())
    
    # 退出码
    if "error" in report:
        sys.exit(1)
    else:
        sys.exit(0)

