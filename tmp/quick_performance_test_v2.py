#!/usr/bin/env python3
"""
快速全链路性能测试 v2
从DATABASE_URL提取数据库名
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

def extract_db_from_url(url: str) -> str:
    """从DATABASE_URL提取数据库名"""
    # 格式: postgresql://user:password@host:port/database
    match = re.search(r'/([^/?]+)(?:\?|$)', url)
    if match:
        return match.group(1)
    return ""

async def quick_test():
    """快速测试"""
    print("=== 快速全链路性能测试 v2 ===")
    print("1. 检查环境变量...")
    
    # 从.env.theme读取所有环境变量
    env_file = PROJECT_ROOT / ".env.theme"
    if env_file.exists():
        print("从.env.theme文件读取环境变量...")
        content = env_file.read_text()
        for line in content.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ[key] = value
                    print(f"  已设置 {key}")
    
    # 检查关键环境变量
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("错误: DEEPSEEK_API_KEY 未设置")
        return False
    
    # 从DATABASE_URL提取POSTGRES_DATABASE
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        db_name = extract_db_from_url(db_url)
        if db_name:
            os.environ["POSTGRES_DATABASE"] = db_name
            print(f"  从DATABASE_URL提取数据库名: {db_name}")
        else:
            print("警告: 无法从DATABASE_URL提取数据库名")
            # 设置默认值
            os.environ["POSTGRES_DATABASE"] = "stock_data_test"
            print(f"  使用默认数据库名: stock_data_test")
    else:
        print("警告: DATABASE_URL 未设置")
        os.environ["POSTGRES_DATABASE"] = "stock_data_test"
        print(f"  使用默认数据库名: stock_data_test")
    
    print("2. 环境变量检查通过")
    
    # 检查关键文件
    print("3. 检查关键文件...")
    required_files = [
        "evaluate_service/data/raw/test_cases.txt",
        "tmp/full_chain_performance_test.py",
        "database_service/streams/handlers/theme_processor.py"
    ]
    
    all_files_exist = True
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} 不存在")
            all_files_exist = False
    
    if not all_files_exist:
        return False
    
    print("4. 关键文件检查通过")
    
    # 测试数据统计
    test_cases_path = PROJECT_ROOT / "evaluate_service/data/raw/test_cases.txt"
    if test_cases_path.exists():
        with open(test_cases_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.count('\n') + 1
            print(f"5. 测试数据统计:")
            print(f"   测试用例文件行数: {lines}")
            
            # 粗略统计测试用例数量
            test_sets = content.count("测试集")
            print(f"   测试集数量: {test_sets}")
    
    # 检查Python模块
    print("6. 检查Python模块导入...")
    try:
        import redis.asyncio as redis
        print("  ✓ redis.asyncio")
    except ImportError as e:
        print(f"  ✗ redis.asyncio: {e}")
        print("  请安装: pip install redis")
        return False
    
    try:
        import asyncpg
        print("  ✓ asyncpg")
    except ImportError as e:
        print(f"  ✗ asyncpg: {e}")
        print("  请安装: pip install asyncpg")
        return False
    
    print("7. Python模块检查通过")
    
    # 输出当前环境变量
    print("\n=== 当前环境变量 ===")
    print(f"DEEPSEEK_API_KEY: {os.getenv('DEEPSEEK_API_KEY', '未设置')[:10]}...")
    print(f"POSTGRES_DATABASE: {os.getenv('POSTGRES_DATABASE', '未设置')}")
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL', '未设置')[:50]}...")
    
    # 输出测试命令
    print("\n=== 测试命令 ===")
    print("运行完整性能测试:")
    print("  cd /Users/admin/Desktop/ai_theme_app")
    print("  ./tmp/run_performance_test.sh")
    print("\n或直接运行:")
    print("  cd /Users/admin/Desktop/ai_theme_app")
    print(f"  export DEEPSEEK_API_KEY={os.getenv('DEEPSEEK_API_KEY')}")
    print(f"  export POSTGRES_DATABASE={os.getenv('POSTGRES_DATABASE')}")
    print("  export PYTHONPATH=/Users/admin/Desktop/ai_theme_app")
    print("  python -u tmp/full_chain_performance_test.py")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(quick_test())
    if success:
        print("\n✅ 环境检查完成，可以开始性能测试")
        sys.exit(0)
    else:
        print("\n❌ 环境检查失败，请解决问题后再运行测试")
        sys.exit(1)
