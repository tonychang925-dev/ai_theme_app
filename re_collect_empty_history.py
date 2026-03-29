#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专门重新采集空的历史事件文件
"""

import json
import subprocess
import time
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def get_empty_history_files(data_dir: str = "theme_data_complete") -> list:
    """扫描所有空的历史文件"""
    history_dir = Path(data_dir) / "history"
    if not history_dir.exists():
        return []
    
    empty_files = []
    for f in history_dir.glob("*_history.jsonl"):
        if f.stat().st_size == 0:
            theme_id = f.stem.replace("_history", "")
            empty_files.append(theme_id)
            print(f"  ⚠️ 空文件: {f.name}")
    
    return empty_files

def fetch_history(theme_id: str, auth_token: str, output_dir: Path):
    """重新采集单个历史事件"""
    url = f"https://app.txcfgl.com/api/app/subject/top-history?subjectId={theme_id}&pageNum=1&pageSize=20"
    
    cmd = [
        'curl', '-s', '-L',
        '-H', f'Authorization: {auth_token}',
        '-H', 'User-Agent: Mozilla/5.0',
        '--cacert', '/etc/ssl/cert.pem',
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.stdout:
            data = json.loads(result.stdout)
            if data.get('code') == 200 and 'rows' in data:
                rows = data['rows']
                if rows:
                    file_path = output_dir / "history" / f"{theme_id}_history.jsonl"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        for item in rows:
                            f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    print(f"  ✅ {theme_id}: 成功采集 {len(rows)} 条记录")
                    return True
                else:
                    # 如果返回空数组，也写入一个标记文件，避免重复尝试
                    file_path = output_dir / "history" / f"{theme_id}_history.jsonl"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write('')  # 保持空文件，但可以添加注释
                    print(f"  ℹ️ {theme_id}: 无历史事件数据")
                    return True
            else:
                print(f"  ❌ {theme_id}: API返回错误 {data.get('code')}")
        else:
            print(f"  ❌ {theme_id}: 空响应")
    except Exception as e:
        print(f"  ❌ {theme_id}: 请求异常 {e}")
    
    return False

def main():
    print("\n" + "="*70)
    print("历史事件空文件补采工具")
    print("="*70)
    
    # 检查认证
    auth_token = os.getenv("AUTHORIZATION")
    if not auth_token:
        print("❌ 请设置AUTHORIZATION环境变量")
        return
    
    data_dir = Path("theme_data_complete")
    
    # 获取空文件列表
    print("\n🔍 扫描空的历史文件...")
    empty_list = get_empty_history_files(data_dir)
    
    if not empty_list:
        print("✅ 没有发现空的历史文件")
        return
    
    print(f"\n📊 发现 {len(empty_list)} 个空文件，开始重新采集...")
    
    success = 0
    for i, theme_id in enumerate(empty_list, 1):
        print(f"\n进度 [{i}/{len(empty_list)}] 处理 {theme_id}")
        if fetch_history(theme_id, auth_token, data_dir):
            success += 1
        time.sleep(1)  # 礼貌延迟
    
    print(f"\n✅ 完成！成功重新采集 {success}/{len(empty_list)} 个")

if __name__ == "__main__":
    main()