#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API调试工具 - 先查看列表接口的真实返回格式
"""

import subprocess
import json
import os
from dotenv import load_dotenv

load_dotenv()

def debug_api_endpoint(endpoint: str, params: dict = None):
    """调试API端点，查看真实返回格式"""
    
    auth_token = os.getenv("AUTHORIZATION")
    if not auth_token:
        print("❌ 请设置AUTHORIZATION环境变量")
        return
    
    url = f"https://app.txcfgl.com/api/app/{endpoint}"
    
    # 构建curl命令
    cmd = [
        'curl',
        '-s',
        '-L',
        '--compressed',
        '-H', f'Authorization: {auth_token}',
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        '-H', 'Accept: application/json',
        '--cacert', '/etc/ssl/cert.pem',
    ]
    
    if params:
        query = '&'.join([f"{k}={v}" for k, v in params.items()])
        url = f"{url}?{query}"
    
    cmd.append(url)
    
    print(f"\n🔍 调试端点: {url}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                print(f"\n✅ 响应状态码: {data.get('code', 'unknown')}")
                print(f"✅ 响应消息: {data.get('msg', 'unknown')}")
                
                # 打印数据结构
                print("\n📊 数据结构:")
                if 'data' in data:
                    data_field = data['data']
                    print(f"  data类型: {type(data_field)}")
                    
                    if isinstance(data_field, list):
                        print(f"  列表长度: {len(data_field)}")
                        if len(data_field) > 0:
                            print(f"  第一个元素类型: {type(data_field[0])}")
                            print(f"  第一个元素预览: {json.dumps(data_field[0], ensure_ascii=False)[:200]}")
                    elif isinstance(data_field, dict):
                        print(f"  字典keys: {list(data_field.keys())}")
                else:
                    print(f"  完整响应: {json.dumps(data, ensure_ascii=False)[:500]}")
                
                return data
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析错误: {e}")
                print(f"原始响应: {result.stdout[:500]}")
        else:
            print("❌ 空响应")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Curl错误: {e}")
        if e.stderr:
            print(f"错误详情: {e.stderr}")

def debug_all_endpoints():
    """调试所有可能的列表接口"""
    
    endpoints = [
        # 带分页参数
        ("subject/list", {"pageNum": 1, "pageSize": 10}),
        ("subject/all", {"pageNum": 1, "pageSize": 10}),
        ("theme/list", {"pageNum": 1, "pageSize": 10}),
        ("subject/category/list", {"pageNum": 1, "pageSize": 10}),
        
        # 不带参数
        ("subject/list", None),
        ("subject/all", None),
        ("theme/list", None),
        ("subject/category/list", None),
        
        # 其他可能的端点
        ("subject/tree", None),
        ("subject/catalog", None),
        ("subject/query/all", None),
    ]
    
    for endpoint, params in endpoints:
        print(f"\n{'='*60}")
        debug_api_endpoint(endpoint, params)

if __name__ == "__main__":
    print("🔧 API调试工具启动")
    print("="*60)
    debug_all_endpoints()