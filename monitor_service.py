#!/usr/bin/env python3
"""
监控服务日志
"""
import time
import subprocess
import sys
import os

def monitor_service_logs(seconds=30):
    """监控服务日志"""
    print("👀 监控AI服务日志")
    print("=" * 60)
    print(f"监控 {seconds} 秒内的日志...\n")
    
    # 尝试获取服务进程ID
    try:
        # 查找model_service进程
        result = subprocess.run(
            ["pgrep", "-f", "model_service"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"📊 找到服务进程: {', '.join(pids)}")
        else:
            print("⚠️  未找到运行中的model_service进程")
    except:
        pass
    
    # 直接查看可能的日志输出
    print("\n📋 最后50行可能的日志:")
    print("-" * 60)
    
    # 尝试查看标准输出
    try:
        # 使用lsof查找服务打开的文件
        result = subprocess.run(
            ["lsof", "-p", pids[0] if 'pids' in locals() and pids else "999999"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'PIPE' in line and 'FD=1' in line:  # 标准输出
                    print("服务输出到标准输出")
    except:
        pass
    
    # 简单的方法：直接向服务发送请求并观察
    print("\n🔍 发送测试请求并观察...")
    print("-" * 60)
    
    test_data = {
        "news_list": [{
            "news_id": "test_monitor_001",
            "title": "监控测试新闻",
            "content": "这是一条用于监控服务日志的测试新闻",
            "source": "monitor",
            "publish_date": "2024-01-15"
        }]
    }
    
    import json
    import http.client
    
    try:
        conn = http.client.HTTPConnection("localhost", 8001, timeout=10)
        conn.request("POST", "/api/process-news", 
                    json.dumps(test_data),
                    {"Content-Type": "application/json"})
        
        response = conn.getresponse()
        print(f"请求状态: {response.status}")
        print(f"响应: {response.read().decode()[:200]}")
        conn.close()
    except Exception as e:
        print(f"请求失败: {e}")
    
    print("\n💡 提示: 查看启动服务的终端窗口可以看到详细日志")

if __name__ == "__main__":
    monitor_service_logs(30)
