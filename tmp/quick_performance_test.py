#!/usr/bin/env python3
"""
快速全链路性能测试
简化版本，用于快速验证
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

async def quick_test():
    """快速测试"""
    print("=== 快速全链路性能测试 ===")
    print("1. 检查环境变量...")
    
    # 检查关键环境变量
    required_vars = ["DEEPSEEK_API_KEY", "POSTGRES_DATABASE"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"缺少环境变量: {missing_vars}")
        
        # 尝试从.env.theme读取
        env_file = PROJECT_ROOT / ".env.theme"
        if env_file.exists():
            print("尝试从.env.theme文件读取...")
            content = env_file.read_text()
            env_vars = {}
            for line in content.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
            
            for var in missing_vars:
                if var in env_vars:
                    os.environ[var] = env_vars[var]
                    print(f"  已设置 {var}")
                else:
                    print(f"  错误: {var} 未在.env.theme中找到")
                    return False
        else:
            print("错误: 未找到.env.theme文件")
            return False
    
    print("2. 环境变量检查通过")
    
    # 检查关键文件
    print("3. 检查关键文件...")
    required_files = [
        "evaluate_service/data/raw/test_cases.txt",
        "tmp/full_chain_performance_test.py",
        "database_service/streams/handlers/theme_processor.py"
    ]
    
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} 不存在")
            return False
    
    print("4. 关键文件检查通过")
    
    # 测试配置
    print("5. 测试配置:")
    print(f"   项目根目录: {PROJECT_ROOT}")
    print(f"   Python路径: {sys.path[0]}")
    
    # 检查Python模块
    print("6. 检查Python模块导入...")
    try:
        import redis.asyncio as redis
        print("  ✓ redis.asyncio")
    except ImportError as e:
        print(f"  ✗ redis.asyncio: {e}")
        return False
    
    try:
        import asyncpg
        print("  ✓ asyncpg")
    except ImportError as e:
        print(f"  ✗ asyncpg: {e}")
        return False
    
    print("7. Python模块检查通过")
    
    # 输出测试建议
    print("\n=== 测试建议 ===")
    print("1. 运行完整性能测试:")
    print("   ./tmp/run_performance_test.sh")
    print("\n2. 运行简化测试 (10条消息):")
    print("   cd /Users/admin/Desktop/ai_theme_app")
    print("   export DEEPSEEK_API_KEY=$(grep DEEPSEEK_API_KEY .env.theme | cut -d= -f2)")
    print("   export PYTHONPATH=/Users/admin/Desktop/ai_theme_app")
    print("   export POSTGRES_DATABASE=stock_data_test")
    print("   python -u tmp/full_chain_performance_test.py")
    print("\n3. 检查测试数据:")
    print("   wc -l evaluate_service/data/raw/test_cases.txt")
    print("   head -5 evaluate_service/data/raw/test_cases.txt")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(quick_test())
    if success:
        print("\n✅ 快速检查完成，可以开始性能测试")
        sys.exit(0)
    else:
        print("\n❌ 快速检查失败，请解决问题后再运行测试")
        sys.exit(1)
