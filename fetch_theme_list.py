#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补救脚本：专门采集题材列表数据
"""

import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def fetch_theme_list(output_dir: Path, page_size: int = 1000):
    """获取完整的题材列表"""
    
    auth_token = os.getenv("AUTHORIZATION")
    if not auth_token:
        print("❌ 请设置AUTHORIZATION环境变量")
        return False
    
    print("\n" + "="*70)
    print("开始采集题材列表数据")
    print("="*70)
    
    # 创建lists目录
    lists_dir = output_dir / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    
    # 请求题材列表（一次获取全部）
    url = f"https://app.txcfgl.com/api/app/subject/list?pageNum=1&pageSize={page_size}"
    
    cmd = [
        'curl',
        '-s',
        '-L',
        '-H', f'Authorization: {auth_token}',
        '-H', 'User-Agent: Mozilla/5.0',
        '--cacert', '/etc/ssl/cert.pem',
        url
    ]
    
    print(f"\n📡 请求URL: {url}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if result.stdout:
            data = json.loads(result.stdout)
            
            if data.get('code') == 200:
                items = data.get('data', [])
                
                print(f"\n✅ 成功获取 {len(items)} 个题材")
                
                # 保存完整列表
                list_file = lists_dir / "full_theme_list.jsonl"
                with open(list_file, 'w', encoding='utf-8') as f:
                    for item in items:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
                
                print(f"📁 已保存到: {list_file}")
                
                # 同时保存一个便于阅读的CSV版本
                csv_file = lists_dir / "theme_list.csv"
                with open(csv_file, 'w', encoding='utf-8') as f:
                    f.write("id,name,level,parent_id,type\n")
                    for item in items:
                        tid = item.get('id', '')
                        name = item.get('name', '')
                        level = item.get('level', '')
                        parent = item.get('parentId', '')
                        f.write(f"{tid},{name},{level},{parent}\n")
                
                print(f"📁 CSV版本: {csv_file}")
                
                # 统计信息
                print(f"\n📊 统计信息:")
                level1 = sum(1 for i in items if i.get('level') == 1)
                level2 = sum(1 for i in items if i.get('level') == 2)
                level3 = sum(1 for i in items if i.get('level') == 3)
                print(f"  一级题材: {level1} 个")
                print(f"  二级题材: {level2} 个")
                print(f"  三级题材: {level3} 个")
                
                # 显示前20个
                print(f"\n📋 前20个题材:")
                for i, item in enumerate(items[:20], 1):
                    name = item.get('name', '未知')
                    level = item.get('level', '')
                    print(f"  {i:2d}. [{level}] {name}")
                
                return True
            else:
                print(f"❌ API返回错误: {data.get('msg')}")
        else:
            print("❌ 空响应")
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    
    return False

def fetch_theme_hierarchy(output_dir: Path):
    """获取题材层级关系（从children文件汇总）"""
    print("\n" + "="*70)
    print("分析题材层级关系")
    print("="*70)
    
    children_dir = output_dir / "children"
    if not children_dir.exists():
        print("❌ children目录不存在")
        return
    
    # 收集所有父子关系
    relationships = []
    
    for child_file in children_dir.glob("*_children.jsonl"):
        theme_id = child_file.stem.replace("_children", "")
        
        with open(child_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        # children文件格式：[child_id, name, full_name, ...]
                        if isinstance(data, list) and len(data) >= 2:
                            child_id = data[0]
                            child_name = data[1]
                            relationships.append({
                                "parent_id": theme_id,
                                "child_id": child_id,
                                "child_name": child_name
                            })
                    except:
                        continue
    
    if relationships:
        hier_file = output_dir / "lists" / "theme_hierarchy.jsonl"
        with open(hier_file, 'w', encoding='utf-8') as f:
            for rel in relationships:
                f.write(json.dumps(rel, ensure_ascii=False) + '\n')
        
        print(f"\n✅ 发现 {len(relationships)} 条父子关系")
        print(f"📁 已保存到: {hier_file}")

def main():
    """主函数"""
    output_dir = Path("theme_data_complete")
    
    # 1. 采集题材列表
    success = fetch_theme_list(output_dir)
    
    if success:
        # 2. 分析层级关系
        fetch_theme_hierarchy(output_dir)
        
        print("\n" + "="*70)
        print("✅ 所有补救操作完成！")
        print("="*70)
        print(f"\n现在您的目录结构应该包含:")
        print(f"  📁 {output_dir}/lists/")
        print(f"     - full_theme_list.jsonl (完整题材列表)")
        print(f"     - theme_list.csv (CSV格式)")
        print(f"     - theme_hierarchy.jsonl (父子关系)")
    else:
        print("\n❌ 补救失败，请检查网络和认证")

if __name__ == "__main__":
    main()