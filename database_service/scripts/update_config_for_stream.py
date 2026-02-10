#!/usr/bin/env python3
"""
更新现有配置文件以支持Redis Stream
"""
import sys
from pathlib import Path
import yaml

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database_service.config import DatabaseConfig
from database_service.streams.stream_config import EnhancedDatabaseConfig, STREAM_CONFIG_EXAMPLE


def update_existing_config(existing_config_path: str):
    """更新现有配置文件"""
    
    print(f"📄 读取现有配置文件: {existing_config_path}")
    
    try:
        # 读取现有配置
        with open(existing_config_path, 'r', encoding='utf-8') as f:
            existing_config = yaml.safe_load(f)
        
        # 读取示例配置
        example_config = yaml.safe_load(STREAM_CONFIG_EXAMPLE)
        
        # 合并配置
        merged_config = deep_merge(existing_config, example_config)
        
        # 备份原始文件
        backup_path = existing_config_path + '.bak'
        with open(backup_path, 'w', encoding='utf-8') as f:
            yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True)
        print(f"📦 原始配置已备份到: {backup_path}")
        
        # 写入新配置
        with open(existing_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(merged_config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"✅ 配置文件已更新: {existing_config_path}")
        
    except Exception as e:
        print(f"❌ 更新配置文件失败: {e}")
        return False
    
    return True


def deep_merge(source: dict, destination: dict) -> dict:
    """深度合并两个字典"""
    for key, value in source.items():
        if isinstance(value, dict):
            # 获取节点或设置默认值
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value
    
    return destination


def create_stream_config_file():
    """创建独立的Stream配置文件"""
    
    config_content = """# Redis Stream 配置
# 将此文件包含到主配置文件中

# Stream 定义
streams:
  news_raw:
    name: "news:raw"
    description: "原始新闻流"
    priority: "high"
    max_length: 10000
    auto_trim: true
    alert_on_backlog: true
    backlog_threshold: 2000
  
  events_major:
    name: "events:major"
    description: "重大事件流"
    priority: "high"
    max_length: 5000
    alert_on_stuck: true
    stuck_threshold_ms: 60000
  
  events_normal:
    name: "events:normal"
    description: "普通事件流"
    priority: "medium"
    max_length: 20000
    alert_on_backlog: true
    backlog_threshold: 5000
  
  themes_updates:
    name: "themes:updates"
    description: "主题更新流"
    priority: "medium"
    max_length: 2000
  
  dead_letter:
    name: "dead:letter"
    description: "死信队列"
    priority: "low"
    max_length: 1000
    auto_trim: false

# 消费者组配置
consumer_groups:
  news_processors:
    name: "news_processors"
    stream: "news:raw"
    strategy: "worker_pool"
    workers: 3
    batch_size: 10
    block_time_ms: 5000
    max_retries: 3
    enable_dlq: true
  
  major_workers:
    name: "major_workers"
    stream: "events:major"
    strategy: "single"
    workers: 2
    batch_size: 5
    block_time_ms: 10000
    max_retries: 5
    enable_dlq: true
  
  theme_workers:
    name: "theme_workers"
    stream: "events:normal"
    strategy: "worker_pool"
    workers: 4
    batch_size: 20
    block_time_ms: 5000
    max_retries: 3
    enable_batch_processing: true
    batch_timeout_seconds: 60

# 外部服务配置
external_services:
  model_service:
    url: "http://localhost:8001"
    timeout: 30
    retry_count: 3
    retry_delay: 1.0
  
  theme_service:
    url: "http://localhost:8002"
    timeout: 30
    retry_count: 3
    retry_delay: 1.0
  
  crawler_service:
    url: "http://localhost:8003"
    timeout: 60
    retry_count: 5
    retry_delay: 2.0

# 功能开关
features:
  enable_stream_processing: true
  enable_legacy_event_bus: false
  dual_write_mode: true

# 性能配置
performance:
  max_connections: 50
  connection_timeout: 5
  read_timeout: 10
  write_timeout: 10
  max_processing_threads: 10
  thread_pool_size: 5
  queue_max_size: 1000

# 监控配置
monitoring:
  enable_monitoring: true
  metrics_interval: 30
  health_check_interval: 60
  max_error_rate: 0.01
  circuit_breaker_enabled: true
  circuit_breaker_threshold: 10
  circuit_breaker_timeout: 60
"""
    
    stream_config_path = Path("config") / "stream_config.yaml"
    stream_config_path.parent.mkdir(exist_ok=True)
    
    with open(stream_config_path, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print(f"✅ 创建了Stream配置文件: {stream_config_path}")
    print("📝 使用方式:")
    print("1. 在主配置文件中使用 !include 指令:")
    print("   redis_stream: !include config/stream_config.yaml")
    print("2. 或者在主配置文件中直接包含以上内容")


def generate_env_file():
    """生成环境变量示例文件"""
    
    env_content = """# Redis Stream 环境变量配置
# 复制到 .env 文件中使用

# Redis Stream 配置
REDIS_STREAM_ENABLED=true

# 外部服务配置
MODEL_SERVICE_URL=http://localhost:8001
MODEL_SERVICE_TIMEOUT=30
MODEL_SERVICE_RETRY_COUNT=3
MODEL_SERVICE_RETRY_DELAY=1.0

THEME_SERVICE_URL=http://localhost:8002
THEME_SERVICE_TIMEOUT=30
THEME_SERVICE_RETRY_COUNT=3
THEME_SERVICE_RETRY_DELAY=1.0

CRAWLER_SERVICE_URL=http://localhost:8003
CRAWLER_SERVICE_TIMEOUT=60
CRAWLER_SERVICE_RETRY_COUNT=5
CRAWLER_SERVICE_RETRY_DELAY=2.0

# 功能开关
ENABLE_STREAM_PROCESSING=true
ENABLE_LEGACY_EVENT_BUS=false
DUAL_WRITE_MODE=true

# 性能配置
MAX_PROCESSING_THREADS=10
THREAD_POOL_SIZE=5
QUEUE_MAX_SIZE=1000

# 监控配置
ENABLE_MONITORING=true
METRICS_INTERVAL=30
HEALTH_CHECK_INTERVAL=60
MAX_ERROR_RATE=0.01
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_THRESHOLD=10
CIRCUIT_BREAKER_TIMEOUT=60
"""
    
    env_path = Path(".env.stream.example")
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print(f"✅ 创建了环境变量示例文件: {env_path}")
    print("📝 使用方式:")
    print("1. 复制到 .env 文件中")
    print("2. 或者添加到现有的 .env 文件末尾")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="更新配置以支持Redis Stream")
    parser.add_argument("--action", choices=["update", "create", "env"], 
                       default="create", help="执行的操作")
    parser.add_argument("--config-file", help="现有配置文件路径")
    
    args = parser.parse_args()
    
    print("🚀 Redis Stream 配置更新工具")
    print("=" * 60)
    
    if args.action == "update" and args.config_file:
        success = update_existing_config(args.config_file)
        if success:
            print("\n✅ 配置更新完成！")
            print("📋 下一步:")
            print("1. 验证配置文件格式")
            print("2. 重启服务加载新配置")
            print("3. 测试Stream功能")
        else:
            print("\n❌ 配置更新失败")
    
    elif args.action == "create":
        create_stream_config_file()
        
        print("\n📋 配置创建完成！")
        print("🎯 建议的集成方式:")
        print("1. 创建单独的 stream_config.yaml 文件")
        print("2. 在主配置文件中引用该文件")
        print("3. 或者直接扩展现有的 config.py")
    
    elif args.action == "env":
        generate_env_file()
        
        print("\n📋 环境变量文件创建完成！")
        print("🎯 使用方法:")
        print("1. 将变量添加到部署环境的 .env 文件中")
        print("2. 或者在 Docker 容器中设置环境变量")
        print("3. 或者在 Kubernetes ConfigMap 中配置")
    
    print("=" * 60)


if __name__ == "__main__":
    main()