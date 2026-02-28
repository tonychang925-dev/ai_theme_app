#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题材数据完整性检查工具 - 修复JSON序列化问题
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Any
import subprocess
import time
import os
from dotenv import load_dotenv

load_dotenv()

class DataIntegrityChecker:
    """数据完整性检查器"""
    
    def __init__(self, data_dir: str = "theme_data_complete"):
        self.data_dir = Path(data_dir)
        self.auth_token = os.getenv("AUTHORIZATION")
        
        # 定义需要检查的数据类型
        self.data_types = {
            "history": {
                "dir": "history",
                "suffix": "_history.jsonl",
                "description": "历史事件",
                "required": True
            },
            "details": {
                "dir": "details",
                "suffix": "_details.jsonl",
                "description": "题材详情",
                "required": True
            },
            "daily": {
                "dir": "daily",
                "suffix": "_daily.jsonl",
                "description": "日线数据",
                "required": False
            },
            "stocks": {
                "dir": "stocks",
                "suffix": "_stocks.jsonl",
                "description": "股票数据",
                "required": False
            },
            "children": {
                "dir": "children",
                "suffix": "_children.jsonl",
                "description": "子主题树",
                "required": False
            }
        }
        
        # 统计信息（使用list代替set，确保JSON可序列化）
        self.stats = {
            "total_themes": 0,
            "complete_themes": 0,
            "missing_data": {},
            "empty_files": {},
            "small_files": {},
            "failed_themes": []  # set → list
        }
        
        # 初始化缺失数据字典
        for data_type in self.data_types:
            self.stats["missing_data"][data_type] = []
            self.stats["empty_files"][data_type] = []
            self.stats["small_files"][data_type] = []
    
    def get_all_theme_ids(self) -> List[str]:
        """从lists目录获取所有题材ID"""
        theme_ids = set()
        
        # 1. 从lists目录读取
        list_file = self.data_dir / "lists" / "full_theme_list.jsonl"
        if list_file.exists():
            with open(list_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        tid = str(item.get('id') or item.get('subjectId'))
                        if tid:
                            theme_ids.add(tid)
                    except:
                        continue
        
        # 2. 如果lists没有，从现有文件推断
        if not theme_ids:
            for data_type, config in self.data_types.items():
                type_dir = self.data_dir / config["dir"]
                if type_dir.exists():
                    for f in type_dir.glob(f"*{config['suffix']}"):
                        tid = f.stem.replace(config['suffix'].replace('_', ''), '')
                        theme_ids.add(tid)
        
        return sorted(list(theme_ids))  # set → sorted list
    
    def check_file_integrity(self, theme_id: str) -> Dict[str, Any]:
        """检查单个题材的数据完整性"""
        result = {
            "theme_id": theme_id,
            "has_data": {},
            "file_size": {},
            "record_count": {},
            "is_complete": True
        }
        
        for data_type, config in self.data_types.items():
            file_path = self.data_dir / config["dir"] / f"{theme_id}{config['suffix']}"
            
            if file_path.exists():
                size = file_path.stat().st_size
                result["has_data"][data_type] = True
                result["file_size"][data_type] = size
                
                # 统计记录数
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        result["record_count"][data_type] = len(lines)
                        
                        # 检查空文件
                        if len(lines) == 0:
                            self.stats["empty_files"][data_type].append(theme_id)
                            result["is_complete"] = False
                        
                        # 检查文件过小（可能数据不完整）
                        if 0 < size < 100:
                            self.stats["small_files"][data_type].append(theme_id)
                            
                except Exception as e:
                    result["record_count"][data_type] = 0
                    self.stats["failed_themes"].append(theme_id)
            else:
                result["has_data"][data_type] = False
                if config["required"]:
                    result["is_complete"] = False
                    self.stats["missing_data"][data_type].append(theme_id)
        
        if result["is_complete"]:
            self.stats["complete_themes"] += 1
        
        return result
    
    def scan_all_themes(self) -> List[Dict[str, Any]]:
        """扫描所有题材，检查完整性"""
        print("\n" + "="*80)
        print("🔍 开始数据完整性检查")
        print("="*80)
        
        # 获取所有题材ID
        all_themes = self.get_all_theme_ids()
        self.stats["total_themes"] = len(all_themes)
        
        print(f"\n📊 待检查题材总数: {len(all_themes)}")
        
        # 检查每个题材
        results = []
        for i, theme_id in enumerate(sorted(all_themes), 1):
            if i % 50 == 0:
                print(f"  进度: {i}/{len(all_themes)}")
            
            result = self.check_file_integrity(theme_id)
            results.append(result)
        
        return results
    
    def generate_report(self) -> Dict[str, Any]:
        """生成检查报告（确保所有数据都是JSON可序列化的）"""
        report = {
            "检查时间": datetime.now().isoformat(),
            "统计": {
                "总题材数": self.stats["total_themes"],
                "完整题材": self.stats["complete_themes"],
                "完成率": f"{self.stats['complete_themes']/max(self.stats['total_themes'],1)*100:.2f}%",
                "缺失数据统计": {},
                "空文件统计": {},
                "小文件统计": {}
            },
            "缺失数据详情": {},
            "建议操作": []
        }
        
        # 计算各类型缺失数量
        for data_type, config in self.data_types.items():
            missing_count = len(self.stats["missing_data"][data_type])
            empty_count = len(self.stats["empty_files"][data_type])
            small_count = len(self.stats["small_files"][data_type])
            
            report["统计"]["缺失数据统计"][config["description"]] = missing_count
            report["统计"]["空文件统计"][config["description"]] = empty_count
            report["统计"]["小文件统计"][config["description"]] = small_count
            
            # 记录详情（只记录前20个，避免报告太大）
            if missing_count > 0:
                report["缺失数据详情"][f"{config['description']}_缺失"] = {
                    "数量": missing_count,
                    "题材ID示例": self.stats["missing_data"][data_type][:20]
                }
                report["建议操作"].append(f"重新采集缺失的{config['description']}：共{missing_count}个题材")
            
            if empty_count > 0:
                report["缺失数据详情"][f"{config['description']}_空文件"] = {
                    "数量": empty_count,
                    "题材ID示例": self.stats["empty_files"][data_type][:20]
                }
            
            if small_count > 0:
                report["缺失数据详情"][f"{config['description']}_小文件"] = {
                    "数量": small_count,
                    "题材ID示例": self.stats["small_files"][data_type][:20]
                }
        
        return report
    
    def print_report(self, report: Dict[str, Any]):
        """打印报告"""
        print("\n" + "="*80)
        print("📋 数据完整性检查报告")
        print("="*80)
        
        stats = report["统计"]
        print(f"\n📊 总体统计:")
        print(f"  总题材数: {stats['总题材数']}")
        print(f"  完整题材: {stats['完整题材']}")
        print(f"  完成率: {stats['完成率']}")
        
        print(f"\n❌ 缺失数据统计:")
        for desc, count in stats["缺失数据统计"].items():
            if count > 0:
                print(f"  {desc}: {count} 个缺失")
        
        print(f"\n⚠️ 空文件统计:")
        for desc, count in stats["空文件统计"].items():
            if count > 0:
                print(f"  {desc}: {count} 个空文件")
        
        print(f"\n📉 小文件统计 (<100字节):")
        for desc, count in stats["小文件统计"].items():
            if count > 0:
                print(f"  {desc}: {count} 个")
        
        if report["建议操作"]:
            print(f"\n🔧 建议操作:")
            for i, action in enumerate(report["建议操作"], 1):
                print(f"  {i}. {action}")
    
    def re_collect_missing(self, report: Dict[str, Any], data_type: str = None):
        """重新采集缺失的数据"""
        print("\n" + "="*80)
        print("🔄 开始重新采集缺失数据")
        print("="*80)
        
        if not self.auth_token:
            print("❌ 未设置AUTHORIZATION环境变量")
            return
        
        # 确定要重新采集的数据类型
        types_to_collect = []
        if data_type:
            if data_type in self.data_types:
                types_to_collect = [data_type]
        else:
            # 默认重新采集所有required类型
            types_to_collect = [t for t, c in self.data_types.items() if c["required"]]
        
        for dt in types_to_collect:
            missing_list = self.stats["missing_data"].get(dt, [])
            empty_list = self.stats["empty_files"].get(dt, [])
            
            to_collect = set(missing_list + empty_list)
            
            if not to_collect:
                print(f"\n✅ {self.data_types[dt]['description']} 没有缺失数据")
                continue
            
            print(f"\n📦 重新采集 {self.data_types[dt]['description']} ({len(to_collect)} 个题材)")
            
            # 分批重新采集
            batch_size = 20
            batches = [list(to_collect)[i:i+batch_size] for i in range(0, len(to_collect), batch_size)]
            
            for i, batch in enumerate(batches, 1):
                print(f"\n  批次 {i}/{len(batches)}")
                
                for theme_id in batch:
                    print(f"    采集 {theme_id}...")
                    
                    if dt == "history":
                        self._fetch_history(theme_id)
                    elif dt == "details":
                        self._fetch_details(theme_id)
                    
                    time.sleep(1)
                
                if i < len(batches):
                    print(f"    批次完成，等待5秒...")
                    time.sleep(5)
    
    def _fetch_history(self, theme_id: str):
        """重新采集history数据"""
        cmd = [
            'curl', '-s', '-L',
            '-H', f'Authorization: {self.auth_token}',
            '--cacert', '/etc/ssl/cert.pem',
            f'https://app.txcfgl.com/api/app/subject/top-history?subjectId={theme_id}&pageNum=1&pageSize=20'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.stdout:
                data = json.loads(result.stdout)
                if data.get('code') == 200 and 'rows' in data:
                    file_path = self.data_dir / "history" / f"{theme_id}_history.jsonl"
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        for item in data['rows']:
                            f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    print(f"      ✅ 成功")
        except Exception as e:
            print(f"      ❌ 失败: {e}")
    
    def _fetch_details(self, theme_id: str):
        """重新采集details数据"""
        cmd = [
            'curl', '-s', '-L',
            '-H', f'Authorization: {self.auth_token}',
            '--cacert', '/etc/ssl/cert.pem',
            f'https://app.txcfgl.com/api/app/subject/query/{theme_id}'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.stdout:
                data = json.loads(result.stdout)
                if data.get('code') == 200:
                    file_path = self.data_dir / "details" / f"{theme_id}_details.jsonl"
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(data, ensure_ascii=False) + '\n')
                    print(f"      ✅ 成功")
        except Exception as e:
            print(f"      ❌ 失败: {e}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="题材数据完整性检查工具")
    parser.add_argument("--data-dir", default="theme_data_complete", help="数据目录")
    parser.add_argument("--check-only", action="store_true", help="只检查，不重新采集")
    parser.add_argument("--re-collect", choices=["history", "details", "daily", "stocks", "children"], 
                       help="重新采集指定的数据类型")
    
    args = parser.parse_args()
    
    # 初始化检查器
    checker = DataIntegrityChecker(args.data_dir)
    
    # 执行检查
    results = checker.scan_all_themes()
    report = checker.generate_report()
    checker.print_report(report)
    
    # 保存报告
    report_file = Path(args.data_dir) / f"integrity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📁 详细报告已保存: {report_file}")
    
    # 重新采集缺失数据
    if not args.check_only and report["建议操作"]:
        print("\n" + "="*80)
        response = input("是否开始重新采集缺失数据？(y/n): ").strip().lower()
        if response == 'y':
            # 询问要重新采集的数据类型
            print("\n请选择要重新采集的数据类型:")
            print("1. 只重新采集历史事件 (history)")
            print("2. 只重新采集题材详情 (details)")
            print("3. 全部重新采集")
            choice = input("请输入选择 (1/2/3): ").strip()
            
            if choice == '1':
                checker.re_collect_missing(report, "history")
            elif choice == '2':
                checker.re_collect_missing(report, "details")
            elif choice == '3':
                checker.re_collect_missing(report, "history")
                checker.re_collect_missing(report, "details")
            else:
                print("无效选择，跳过重新采集")

if __name__ == "__main__":
    main()