#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据管理工具 - 修复股票采集逻辑
"""

import json
import subprocess
import time
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class VersionManager:
    """版本管理器 - 追踪数据更新"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.version_file = data_dir / "version_control.json"
        self.versions = self._load_versions()
    
    def _load_versions(self) -> Dict:
        """加载版本信息"""
        if self.version_file.exists():
            try:
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'stocks': {}, 'themes': {}, 'last_check': None}
        return {'stocks': {}, 'themes': {}, 'last_check': None}
    
    def _save_versions(self):
        """保存版本信息"""
        with open(self.version_file, 'w', encoding='utf-8') as f:
            json.dump(self.versions, f, indent=2, ensure_ascii=False)
    
    def get_stock_version(self, stock_code: str) -> Optional[str]:
        """获取股票数据版本"""
        return self.versions['stocks'].get(stock_code, {}).get('version')
    
    def update_stock_version(self, stock_code: str, data: dict, file_path: Path):
        """更新股票版本信息"""
        stock_data = data.get('data', {})
        update_time = stock_data.get('updateTime')
        
        content_hash = self._generate_hash(stock_data)
        
        self.versions['stocks'][stock_code] = {
            'version': content_hash,
            'update_time': update_time,
            'last_fetch': datetime.now().isoformat(),
            'name': stock_data.get('name'),
            'file_size': file_path.stat().st_size if file_path.exists() else 0
        }
        self._save_versions()
    
    def _generate_hash(self, data: dict) -> str:
        """生成数据哈希"""
        stable_data = {k: v for k, v in data.items() 
                      if k not in ['updateTime', 'vol', 'amount', 'pctChg']}
        content = json.dumps(stable_data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:8]
    
    def needs_update(self, stock_code: str, new_data: dict) -> bool:
        """检查是否需要更新"""
        old_version = self.get_stock_version(stock_code)
        if not old_version:
            return True
        
        new_hash = self._generate_hash(new_data.get('data', {}))
        return old_version != new_hash
    
    def mark_check(self):
        """标记检查时间"""
        self.versions['last_check'] = datetime.now().isoformat()
        self._save_versions()


class UnifiedDataManager:
    """统一数据管理器"""
    
    def __init__(self, data_dir: str = "theme_data_complete"):
        self.data_dir = Path(data_dir)
        self.auth_token = os.getenv("AUTHORIZATION")
        
        if not self.auth_token:
            print("❌ 请设置环境变量 AUTHORIZATION")
            print("   可以在.env文件中设置: AUTHORIZATION=\"Bearer xxx...\"")
            exit(1)
        
        print(f"✅ 使用Token: {self.auth_token[:20]}...")
        
        # 版本管理器
        self.version_mgr = VersionManager(self.data_dir)
        
        # 目录配置
        self.stock_details_dir = self.data_dir / "stock_details"
        self.stock_details_dir.mkdir(parents=True, exist_ok=True)
        
        # 进度文件
        self.stock_progress_file = self.data_dir / "stock_progress.json"
        self.stock_progress = self._load_stock_progress()
        
        # 统计信息
        self.stock_stats = {
            'total_requests': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # 定义需要检查的数据类型（题材相关）
        self.theme_data_types = {
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
            }
        }
        
        # 题材统计
        self.theme_stats = self._init_theme_stats()
    
    def _init_theme_stats(self):
        """初始化题材统计"""
        stats = {
            "total_themes": 0,
            "complete_themes": 0,
            "missing_data": {},
            "empty_files": {},
            "data_type_stats": {}
        }
        
        for data_type, config in self.theme_data_types.items():
            stats["missing_data"][data_type] = []
            stats["empty_files"][data_type] = []
            stats["data_type_stats"][data_type] = {
                "total": 0,
                "missing": 0,
                "empty": 0,
                "valid": 0
            }
        
        return stats
    
    def _load_stock_progress(self) -> Dict:
        """加载股票采集进度"""
        if self.stock_progress_file.exists():
            try:
                with open(self.stock_progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        'completed': set(data.get('completed', [])),
                        'failed': set(data.get('failed', []))
                    }
            except:
                return {'completed': set(), 'failed': set()}
        return {'completed': set(), 'failed': set()}
    
    def _save_stock_progress(self):
        """保存股票采集进度"""
        data = {
            'completed': list(self.stock_progress['completed']),
            'failed': list(self.stock_progress['failed'])
        }
        with open(self.stock_progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    # ==================== 股票相关功能 ====================
    
    def scan_stock_sources(self) -> Set[str]:
        """从children文件扫描所有股票代码"""
        children_dir = self.data_dir / "children"
        if not children_dir.exists():
            print(f"❌ children目录不存在: {children_dir}")
            return set()
        
        stock_codes = set()
        files = list(children_dir.glob("*_children.jsonl"))
        
        print(f"\n📊 扫描 {len(files)} 个children文件获取股票列表...")
        
        for i, file_path in enumerate(files, 1):
            if i % 100 == 0:
                print(f"  进度: {i}/{len(files)} 个文件, 已发现 {len(stock_codes)} 只股票")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if isinstance(data, list) and len(data) > 11:
                                    code = data[11]
                                    if code and code not in stock_codes:
                                        stock_codes.add(code)
                            except:
                                continue
            except Exception as e:
                continue
        
        print(f"✅ 共发现 {len(stock_codes)} 只股票")
        return stock_codes
    
    def test_auth_token(self):
        """测试认证token是否有效"""
        test_url = "https://app.txcfgl.com/api/app/stock/query/000001"
        
        cmd = [
            'curl', '-s', '-L',
            '-H', 'User-Agent: Mozilla/5.0',
            '-H', 'Accept: application/json',
            '-H', f'Authorization: {self.auth_token}',
            '--cacert', '/etc/ssl/cert.pem',
            test_url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.stdout:
                data = json.loads(result.stdout)
                if data.get('code') == 200:
                    return True
                else:
                    print(f"⚠️ 认证测试失败: {data.get('msg')}")
                    return False
            return False
        except Exception as e:
            print(f"⚠️ 认证测试异常: {e}")
            return False
    
    def fetch_stock_detail(self, stock_code: str) -> Optional[Dict]:
        """获取股票详情"""
        url = f"https://app.txcfgl.com/api/app/stock/query/{stock_code}"
        
        cmd = [
            'curl', '-s', '-L',
            '-H', 'User-Agent: Mozilla/5.0',
            '-H', 'Accept: application/json',
            '-H', f'Authorization: {self.auth_token}',
            '--cacert', '/etc/ssl/cert.pem',
            url
        ]
        
        self.stock_stats['total_requests'] += 1
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                data = json.loads(result.stdout)
                if data.get('code') == 200:
                    return data
                else:
                    print(f"      API错误: {data.get('msg')}")
            return None
        except subprocess.TimeoutExpired:
            print(f"      请求超时")
            return None
        except Exception as e:
            print(f"      错误: {e}")
            return None
    
    def collect_stock(self, stock_code: str) -> str:
        """
        采集单只股票
        返回: 'success', 'failed', 'skipped'
        """
        file_path = self.stock_details_dir / f"{stock_code}_detail.json"
        
        # 检查是否已存在
        if file_path.exists():
            self.stock_stats['skipped'] += 1
            return 'skipped'
        
        data = self.fetch_stock_detail(stock_code)
        if not data:
            self.stock_stats['failed'] += 1
            self.stock_progress['failed'].add(stock_code)
            return 'failed'
        
        # 保存新数据
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 更新版本信息
        self.version_mgr.update_stock_version(stock_code, data, file_path)
        
        # 更新进度
        self.stock_progress['completed'].add(stock_code)
        if stock_code in self.stock_progress['failed']:
            self.stock_progress['failed'].remove(stock_code)
        
        self.stock_stats['success'] += 1
        return 'success'
    
    def collect_missing_stocks(self, limit: int = None, batch_size: int = 50, pause: int = 2):
        """只采集缺失的股票（已存在的跳过）"""
        print("\n" + "="*80)
        print("📈 开始采集缺失的股票")
        print("="*80)
        
        # 先测试认证
        if not self.test_auth_token():
            print("\n❌ 认证失败，请检查token是否有效")
            print("   可以重新运行: export AUTHORIZATION=\"Bearer 新的token\"")
            return
        
        # 获取所有股票
        all_stocks = self.scan_stock_sources()
        
        # 找出缺失的（未采集的）
        completed = self.stock_progress['completed']
        missing_stocks = [s for s in all_stocks if s not in completed]
        missing_stocks.sort()
        
        if limit:
            missing_stocks = missing_stocks[:limit]
        
        print(f"\n📊 统计:")
        print(f"  总股票数: {len(all_stocks)}")
        print(f"  已采集: {len(completed)}")
        print(f"  缺失: {len(missing_stocks)}")
        
        if not missing_stocks:
            print("\n✅ 所有股票都已采集完成！")
            return
        
        # 确认
        print(f"\n📦 将采集 {len(missing_stocks)} 只缺失的股票")
        confirm = input("是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # 开始采集
        start_time = time.time()
        
        for i in range(0, len(missing_stocks), batch_size):
            batch = missing_stocks[i:i+batch_size]
            print(f"\n{'='*60}")
            print(f"📦 批次 {i//batch_size + 1}/{(len(missing_stocks)-1)//batch_size + 1}")
            print(f"{'='*60}")
            
            for j, stock_code in enumerate(batch, 1):
                global_idx = i + j
                progress = (global_idx / len(missing_stocks)) * 100
                
                print(f"\n[{global_idx}/{len(missing_stocks)}] {progress:.1f}% {stock_code}")
                
                status = self.collect_stock(stock_code)
                
                status_icons = {
                    'success': '✅ 成功',
                    'failed': '❌ 失败',
                    'skipped': '⏭️ 已存在'
                }
                print(f"  {status_icons.get(status, '❓')}")
                
                if j % 10 == 0:
                    self._print_stock_stats()
            
            # 保存进度
            self._save_stock_progress()
            
            if i + batch_size < len(missing_stocks):
                print(f"\n⏸️ 批次完成，暂停 {pause} 秒...")
                time.sleep(pause)
        
        elapsed = time.time() - start_time
        print(f"\n{'='*80}")
        print("✅ 股票采集完成！")
        print("="*80)
        self._print_stock_stats()
        print(f"⏱️  总耗时: {elapsed:.1f} 秒")
        if len(missing_stocks) > 0:
            print(f"⚡ 平均速度: {len(missing_stocks)/elapsed:.1f} 只/秒")
        
        self.version_mgr.mark_check()
    
    def retry_failed_stocks(self, batch_size: int = 20):
        """重试失败的股票"""
        failed = self.stock_progress['failed']
        if not failed:
            print("✅ 没有失败的股票")
            return
        
        print(f"\n📦 重试 {len(failed)} 只失败的股票")
        
        failed_list = sorted(list(failed))
        success_count = 0
        
        for i, stock_code in enumerate(failed_list[:batch_size], 1):
            print(f"\n[{i}/{min(batch_size, len(failed_list))}] 重试 {stock_code}")
            
            # 删除旧文件（如果有）
            file_path = self.stock_details_dir / f"{stock_code}_detail.json"
            if file_path.exists():
                file_path.unlink()
            
            status = self.collect_stock(stock_code)
            if status == 'success':
                success_count += 1
            
            time.sleep(1)
        
        print(f"\n✅ 重试完成: 成功 {success_count} 只")
    
    def _print_stock_stats(self):
        """打印股票统计"""
        print(f"\n📊 股票实时统计:")
        print(f"  请求数: {self.stock_stats['total_requests']}")
        print(f"  成功: {self.stock_stats['success']}")
        print(f"  失败: {self.stock_stats['failed']}")
        print(f"  跳过(已存在): {self.stock_stats['skipped']}")
        print(f"  累计成功: {len(self.stock_progress['completed'])}")
    
    # ==================== 题材相关功能 ====================
    
    def get_all_theme_ids(self) -> List[str]:
        """从lists目录获取所有题材ID"""
        theme_ids = set()
        
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
        
        return sorted(list(theme_ids))
    
    def scan_all_themes(self):
        """扫描所有题材，检查完整性"""
        print("\n" + "="*80)
        print("🔍 开始题材数据完整性检查")
        print("="*80)
        
        all_themes = self.get_all_theme_ids()
        self.theme_stats["total_themes"] = len(all_themes)
        
        print(f"\n📊 待检查题材总数: {len(all_themes)}")
        
        for i, theme_id in enumerate(sorted(all_themes), 1):
            if i % 50 == 0:
                print(f"  进度: {i}/{len(all_themes)}")
            
            self._check_single_theme(theme_id)
        
        self._print_theme_report()
    
    def _check_single_theme(self, theme_id: str):
        """检查单个题材"""
        for data_type, config in self.theme_data_types.items():
            file_path = self.data_dir / config["dir"] / f"{theme_id}{config['suffix']}"
            
            self.theme_stats["data_type_stats"][data_type]["total"] += 1
            
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if len(lines) == 0:
                            self.theme_stats["empty_files"][data_type].append(theme_id)
                            self.theme_stats["data_type_stats"][data_type]["empty"] += 1
                        else:
                            self.theme_stats["data_type_stats"][data_type]["valid"] += 1
                except:
                    self.theme_stats["data_type_stats"][data_type]["missing"] += 1
            else:
                self.theme_stats["data_type_stats"][data_type]["missing"] += 1
                if config["required"]:
                    self.theme_stats["missing_data"][data_type].append(theme_id)
    
    def _print_theme_report(self):
        """打印题材检查报告"""
        total = self.theme_stats["total_themes"]
        
        print("\n" + "="*80)
        print("📋 题材完整性检查报告")
        print("="*80)
        
        print(f"\n📊 总体统计:")
        print(f"  总题材数: {total}")
        
        print(f"\n📁 数据类型统计:")
        for data_type, config in self.theme_data_types.items():
            stats = self.theme_stats["data_type_stats"][data_type]
            print(f"\n  {config['description']}:")
            print(f"    应有: {stats['total']}")
            print(f"    存在: {stats['valid']}")
            print(f"    空文件: {stats['empty']}")
            print(f"    缺失: {stats['missing']}")
            
            if stats['missing'] > 0:
                print(f"    缺失示例: {self.theme_stats['missing_data'][data_type][:5]}")
    
    # ==================== 通用功能 ====================
    
    def show_summary(self):
        """显示汇总信息"""
        print("\n" + "="*80)
        print("📊 数据汇总")
        print("="*80)
        
        # 题材统计
        total_themes = len(self.get_all_theme_ids())
        print(f"\n📁 题材数据:")
        print(f"  总题材数: {total_themes}")
        
        # 股票统计
        stock_files = list(self.stock_details_dir.glob("*_detail.json"))
        stock_count = len(stock_files)
        stock_size = sum(f.stat().st_size for f in stock_files) / (1024*1024)
        
        all_stocks = self.scan_stock_sources()
        
        print(f"\n📈 股票数据:")
        print(f"  已采集: {stock_count} 只")
        print(f"  数据量: {stock_size:.2f} MB")
        print(f"  待采集: {len(all_stocks) - stock_count} 只")
        print(f"  失败: {len(self.stock_progress['failed'])} 只")
        
        # 版本信息
        print(f"\n🔄 版本信息:")
        print(f"  最后检查: {self.version_mgr.versions.get('last_check', '从未')}")


def main():
    """主函数"""
    manager = UnifiedDataManager()
    
    while True:
        print("\n" + "="*80)
        print("📊 统一数据管理工具")
        print("="*80)
        print("\n请选择功能:")
        
        print("\n📁 题材数据管理:")
        print("  1. 检查题材完整性")
        
        print("\n📈 股票数据管理:")
        print("  2. 采集缺失的股票（推荐）")
        print("  3. 测试采集前10只股票")
        print("  4. 重试失败的股票")
        
        print("\n🔍 通用功能:")
        print("  5. 显示数据汇总")
        print("  0. 退出")
        
        choice = input("\n请输入选择 (0-5): ").strip()
        
        if choice == "1":
            manager.scan_all_themes()
        
        elif choice == "2":
            manager.collect_missing_stocks()
        
        elif choice == "3":
            manager.collect_missing_stocks(limit=10)
        
        elif choice == "4":
            manager.retry_failed_stocks()
        
        elif choice == "5":
            manager.show_summary()
        
        elif choice == "0":
            print("\n👋 再见！")
            break
        
        else:
            print("❌ 无效选择")


if __name__ == "__main__":
    main()