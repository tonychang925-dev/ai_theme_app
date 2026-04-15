#!/usr/bin/env python3
"""
Redis消费者组实际清理脚本
基于增强版清理器，执行实际清理操作
"""

import asyncio
import logging
import sys
import json
from datetime import datetime

# 添加项目路径
sys.path.append('.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """主函数 - 执行实际清理"""
    import redis.asyncio as redis
    
    print("🚀 Redis消费者组实际清理脚本")
    print("=" * 60)
    print("⚠️  警告: 此脚本将实际删除标记为清理的消费者组")
    print("=" * 60)
    
    # 配置选项 - 实际清理模式
    config = {
        "dry_run": False,  # 实际清理模式
        "max_group_age_hours": 24,
        "min_idle_time_minutes": 120,
        "max_pending_messages": 0,
        "report_file": "consumer_group_cleanup_actual_report_20260414.json",
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
        ]
    }
    
    print("⚙️  配置:")
    print(f"   模式: 🔧 实际清理模式 (将删除标记为清理的组)")
    print(f"   保护组: {len(config['protected_groups'])}个关键业务组")
    print(f"   报告文件: {config['report_file']}")
    print()
    
    # 确认执行
    print("❓ 确认执行实际清理? (输入 'yes' 继续): ", end='')
    confirmation = input().strip().lower()
    
    if confirmation != 'yes':
        print("❌ 操作取消")
        return {"status": "cancelled"}
    
    try:
        # 连接Redis
        redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)
        
        # 导入清理器
        from scripts.redis_consumer_group_cleanup import EnhancedConsumerGroupCleanup
        
        # 创建清理器
        cleanup = EnhancedConsumerGroupCleanup(redis_client, config)
        
        # 执行清理
        print("\n🔄 开始执行实际清理...")
        report = await cleanup.run_cleanup()
        
        # 打印摘要
        cleanup.print_summary()
        
        # 关闭连接
        await redis_client.aclose()
        
        print("\n✅ 实际清理完成")
        print(f"   清理了 {report['statistics']['groups_cleaned']} 个非活跃消费者组")
        
        return report
        
    except Exception as e:
        print(f"❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    # 运行实际清理脚本
    report = asyncio.run(main())
    
    # 退出码
    if "error" in report:
        sys.exit(1)
    else:
        sys.exit(0)
