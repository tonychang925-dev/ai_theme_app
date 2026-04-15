#!/usr/bin/env python3
"""
环境变量工具函数
用于从.env.theme等文件读取配置
"""

import os
import re
from typing import Dict, Optional


def load_env_file(file_path: str = ".env.theme") -> Dict[str, str]:
    # 如果文件路径是相对路径，尝试从项目根目录查找
    if not os.path.isabs(file_path):
        # 尝试从当前目录向上查找项目根目录
        import sys
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包后的情况
            current_dir = sys._MEIPASS
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))

        project_root = current_dir
        for i in range(4):  # 最多向上查找4级
            test_path = os.path.join(project_root, file_path)
            if os.path.exists(test_path):
                file_path = test_path
                break
            parent = os.path.dirname(project_root)
            if parent == project_root:  # 到达根目录
                break
            project_root = parent
    """
    加载环境变量文件
    
    Args:
        file_path: 环境变量文件路径
    
    Returns:
        包含环境变量的字典
    """
    env_vars = {}
    
    if not os.path.exists(file_path):
        print(f"警告: 环境变量文件不存在: {file_path}")
        return env_vars
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除值中的引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    env_vars[key] = value
    
    except Exception as e:
        print(f"加载环境变量文件失败: {str(e)}")
    
    return env_vars


def get_deepseek_api_key(env_file: str = ".env.theme") -> Optional[str]:
    """
    从环境变量文件获取DeepSeek API密钥
    
    Args:
        env_file: 环境变量文件路径
    
    Returns:
        DeepSeek API密钥，如果不存在则返回None
    """
    env_vars = load_env_file(env_file)
    
    # 尝试不同的键名
    possible_keys = ['DEEPSEEK_API_KEY', 'deepseek_API_key', 'DEEPSEEK_API', 'deepseek_api_key']
    
    for key in possible_keys:
        if key in env_vars:
            return env_vars[key]
    
    # 如果没有找到，尝试从环境变量中获取
    return os.environ.get('DEEPSEEK_API_KEY')


def get_openai_api_key(env_file: str = ".env.theme") -> Optional[str]:
    """
    从环境变量文件获取OpenAI API密钥
    
    Args:
        env_file: 环境变量文件路径
    
    Returns:
        OpenAI API密钥，如果不存在则返回None
    """
    env_vars = load_env_file(env_file)
    
    # 尝试不同的键名
    possible_keys = ['OPENAI_API_KEY', 'openai_API_key', 'OPENAI_API', 'openai_api_key']
    
    for key in possible_keys:
        if key in env_vars:
            return env_vars[key]
    
    # 如果没有找到，尝试从环境变量中获取
    return os.environ.get('OPENAI_API_KEY')


def get_database_url(env_file: str = ".env.theme") -> Optional[str]:
    """
    从环境变量文件获取数据库URL
    
    Args:
        env_file: 环境变量文件路径
    
    Returns:
        数据库URL，如果不存在则返回None
    """
    env_vars = load_env_file(env_file)
    
    # 尝试不同的键名
    possible_keys = ['DATABASE_URL', 'database_url', 'DB_URL', 'db_url']
    
    for key in possible_keys:
        if key in env_vars:
            return env_vars[key]
    
    # 如果没有找到，尝试从环境变量中获取
    return os.environ.get('DATABASE_URL')


def get_tushare_token(env_file: str = ".env.theme") -> Optional[str]:
    """
    从环境变量文件获取Tushare令牌
    
    Args:
        env_file: 环境变量文件路径
    
    Returns:
        Tushare令牌，如果不存在则返回None
    """
    env_vars = load_env_file(env_file)
    
    # 尝试不同的键名
    possible_keys = ['TUSHARE_TOKEN', 'tushare_token', 'TUSHARE_TOKEN', 'tushare_token']
    
    for key in possible_keys:
        if key in env_vars:
            return env_vars[key]
    
    # 如果没有找到，尝试从环境变量中获取
    return os.environ.get('TUSHARE_TOKEN')


def get_all_config(env_file: str = ".env.theme") -> Dict[str, str]:
    """
    获取所有配置
    
    Args:
        env_file: 环境变量文件路径
    
    Returns:
        包含所有配置的字典
    """
    config = {}
    
    # 从文件加载
    file_config = load_env_file(env_file)
    config.update(file_config)
    
    # 从环境变量加载（覆盖文件配置）
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'DATABASE_URL', 'TUSHARE_TOKEN']:
        env_value = os.environ.get(key)
        if env_value:
            config[key] = env_value
    
    return config


def print_config_summary(env_file: str = ".env.theme"):
    """打印配置摘要"""
    config = get_all_config(env_file)
    
    print("配置摘要:")
    print(f"配置文件: {env_file}")
    
    # 安全地显示配置（隐藏敏感信息）
    for key, value in config.items():
        if 'KEY' in key or 'TOKEN' in key or 'PASSWORD' in key or 'SECRET' in key:
            if value:
                masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
                print(f"  {key}: {masked_value}")
            else:
                print(f"  {key}: (未设置)")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    # 测试功能
    print_config_summary()
    
    deepseek_key = get_deepseek_api_key()
    if deepseek_key:
        print(f"\nDeepSeek API密钥: {deepseek_key[:8]}...{deepseek_key[-4:]}")
    else:
        print("\nDeepSeek API密钥: 未找到")
