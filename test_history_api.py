#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动获取history数据 - 修复版
正确处理返回的rows字段
"""

import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def fetch_history_fixed(theme_id: str, output_dir: Path):
    """获取并保存history数据（修复版）"""
    
    auth_token = os.getenv("AUTHORIZATION")
    if not auth_token:
        print("❌ 请设置AUTHORIZATION环境变量")
        return False
    
    print(f"\n📊 开始获取题材 {theme_id} 的历史事件...")
    
    # 创建history目录
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    
    all_events = []
    page = 1
    page_size = 20
    
    while True:
        print(f"\n📄 正在获取第{page}页...")
        
        # 构建URL
        url = f"https://app.txcfgl.com/api/app/subject/top-history?subjectId={theme_id}&pageNum={page}&pageSize={page_size}"
        
        # curl命令
        cmd = [
            'curl',
            '-s',
            '-L',
            '-H', f'Authorization: {auth_token}',
            '-H', 'User-Agent: Mozilla/5.0',
            '--cacert', '/etc/ssl/cert.pem',
            url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if result.stdout:
                data = json.loads(result.stdout)
                
                if data.get('code') == 200:
                    # ⚠️ 关键修复：这里用 "rows" 而不是 "data"
                    items = data.get('rows', [])
                    
                    print(f"  返回码: {data.get('code')}")
                    print(f"  消息: {data.get('msg')}")
                    print(f"  本页条数: {len(items)}")
                    
                    if not items:
                        print(f"  ✅ 第{page}页无数据，采集完成")
                        break
                    
                    all_events.extend(items)
                    
                    # 如果返回数量小于page_size，说明是最后一页
                    if len(items) < page_size:
                        print(f"  ✅ 已到最后一页")
                        break
                    
                    page += 1
                    time.sleep(0.5)  # 礼貌延迟
                else:
                    print(f"  ⚠️ API返回错误: {data.get('msg')}")
                    break
            else:
                print("  ⚠️ 空响应")
                break
                
        except Exception as e:
            print(f"  ❌ 请求失败: {e}")
            break
    
    # 保存结果
    if all_events:
        file_path = history_dir / f"{theme_id}_history.jsonl"
        with open(file_path, 'w', encoding='utf-8') as f:
            for event in all_events:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        
        print(f"\n{'='*60}")
        print(f"✅ 成功！")
        print(f"{'='*60}")
        print(f"  题材: {theme_id}")
        print(f"  总页数: {page}")
        print(f"  总记录数: {len(all_events)}")
        print(f"  保存路径: {file_path}")
        
        # 显示前3条作为预览
        print(f"\n📝 前3条记录预览:")
        for i, event in enumerate(all_events[:3], 1):
            print(f"\n--- 记录 {i} ---")
            desc = event.get('description', '')[:150]
            print(f"  {desc}...")
            print(f"  日期: {event.get('rankDate', 'unknown')}")
            print(f"  热度: {event.get('heatName', 'unknown')}")
        
        return True
    else:
        print(f"\n❌ 没有获取到任何数据")
        return False

def check_existing_files(theme_id: str, output_dir: Path):
    """检查是否已有history文件"""
    history_dir = output_dir / "history"
    if not history_dir.exists():
        return
    
    files = list(history_dir.glob(f"{theme_id}_history.jsonl"))
    if files:
        for f in files:
            size = f.stat().st_size
            print(f"📁 已存在文件: {f.name} ({size} 字节)")
            if size > 0:
                with open(f, 'r') as fh:
                    lines = fh.readlines()
                    print(f"   包含 {len(lines)} 条记录")

def main():
    print("\n" + "="*70)
    print("手动获取history数据工具 - 修复版")
    print("="*70)
    
    # 检查认证
    auth_token = os.getenv("AUTHORIZATION")
    if not auth_token:
        print("❌ 请先设置AUTHORIZATION环境变量")
        print("   export AUTHORIZATION='Bearer xxx...'")
        return
    
    print(f"✅ Authorization已设置: {auth_token[:20]}...")
    
    # 输出目录
    output_dir = Path("theme_data_complete")
    output_dir.mkdir(exist_ok=True)
    
    # 获取用户输入的题材ID
    while True:
        print("\n" + "-"*40)
        theme_id = input("🎯 请输入题材ID (输入 q 退出): ").strip()
        
        if theme_id.lower() == 'q':
            break
        
        if theme_id.isdigit():
            # 先检查是否已有文件
            check_existing_files(theme_id, output_dir)
            
            # 询问是否重新获取
            confirm = input(f"\n是否重新获取题材 {theme_id} 的历史数据？(y/n): ").strip().lower()
            if confirm == 'y':
                fetch_history_fixed(theme_id, output_dir)
            else:
                print("已跳过")
        else:
            print("❌ 请输入有效的数字ID")

if __name__ == "__main__":
    main()