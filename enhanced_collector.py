#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票详情采集器 - 完整版
功能：
- 统计总股票数
- 实时显示进度
- 断点续传
- 跳过已下载
"""

import subprocess
import json
import os
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from collections import OrderedDict

load_dotenv()

class StockCollector:
    def __init__(self):
        self.token = os.getenv("AUTHORIZATION")
        if not self.token:
            print("❌ 请设置环境变量 AUTHORIZATION")
            exit(1)
        
        # 目录配置
        self.base_dir = Path("theme_data_complete")
        self.stock_dir = self.base_dir / "stock_details"
        self.stock_dir.mkdir(parents=True, exist_ok=True)
        
        # 进度文件
        self.progress_file = self.base_dir / "stock_progress.json"
        
        # 加载进度
        self.progress = self._load_progress()
        self.collected = self._scan_downloaded()
        
        # 统计信息
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'total_requests': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        self._print_status()
    
    def _print_status(self):
        """打印状态"""
        print("\n" + "="*70)
        print("📊 股票采集器状态")
        print("="*70)
        print(f"📁 基础目录: {self.base_dir.absolute()}")
        print(f"📁 股票目录: {self.stock_dir.absolute()}")
        print(f"📊 已采集: {len(self.collected)} 只")
        print(f"📊 进度文件: {self.progress_file}")
        print("="*70)
    
    def _load_progress(self):
        """加载进度文件"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'completed': [], 'failed': [], 'last_update': None}
        return {'completed': [], 'failed': [], 'last_update': None}
    
    def _save_progress(self):
        """保存进度"""
        self.progress['last_update'] = datetime.now().isoformat()
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)
    
    def _scan_downloaded(self):
        """扫描已下载的股票"""
        collected = set()
        for f in self.stock_dir.glob("*_detail.json"):
            stock_code = f.stem.replace("_detail", "")
            collected.add(stock_code)
        return collected
    
    def _update_progress(self, stock_code: str, status: str):
        """更新进度"""
        if status == 'success':
            if stock_code not in self.progress['completed']:
                self.progress['completed'].append(stock_code)
            if stock_code in self.progress['failed']:
                self.progress['failed'].remove(stock_code)
            self.stats['success'] += 1
        elif status == 'failed':
            if stock_code not in self.progress['failed']:
                self.progress['failed'].append(stock_code)
            self.stats['failed'] += 1
        elif status == 'skipped':
            self.stats['skipped'] += 1
        
        self._save_progress()
    
    def extract_from_children(self, sample_size: int = None):
        """从children文件提取股票代码"""
        children_dir = self.base_dir / "children"
        if not children_dir.exists():
            print(f"❌ children目录不存在: {children_dir}")
            return []
        
        files = sorted(children_dir.glob("*_children.jsonl"))
        total_files = len(files)
        print(f"\n📊 扫描 {total_files} 个children文件...")
        
        stock_codes = OrderedDict()
        processed_files = 0
        
        for file_path in files:
            processed_files += 1
            if processed_files % 100 == 0:
                print(f"  进度: 已扫描 {processed_files}/{total_files} 个文件，发现 {len(stock_codes)} 只股票")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if isinstance(data, list) and len(data) > 11:
                                    stock_code = data[11]
                                    if stock_code and stock_code not in stock_codes:
                                        stock_codes[stock_code] = True
                            except:
                                continue
            except Exception as e:
                print(f"  警告: 读取文件 {file_path.name} 失败: {e}")
                continue
        
        print(f"✅ 扫描完成! 共发现 {len(stock_codes)} 只股票")
        return list(stock_codes.keys())
    
    def fetch_stock(self, stock_code: str):
        """获取股票详情"""
        url = f"https://app.txcfgl.com/api/app/stock/query/{stock_code}"
        
        cmd = [
            'curl', '-s', '-L',
            '-H', 'User-Agent: Mozilla/5.0',
            '-H', 'Accept: application/json',
            '-H', f'Authorization: {self.token}',
            '--cacert', '/etc/ssl/cert.pem',
            url
        ]
        
        self.stats['total_requests'] += 1
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                data = json.loads(result.stdout)
                if data.get('code') == 200:
                    return data
            return None
        except Exception as e:
            print(f"    错误: {e}")
            return None
    
    def collect(self, limit: int = None, batch_size: int = 50, pause: int = 2):
        """批量采集"""
        print("\n" + "="*70)
        print("🚀 开始批量采集股票详情")
        print("="*70)
        
        # 1. 提取所有股票代码
        all_stocks = self.extract_from_children()
        total_stocks = len(all_stocks)
        
        # 2. 过滤已采集的
        to_collect = [s for s in all_stocks if s not in self.collected]
        if limit:
            to_collect = to_collect[:limit]
        
        # 3. 统计信息
        print(f"\n📊 统计信息:")
        print(f"  总股票数: {total_stocks}")
        print(f"  已采集: {len(self.collected)}")
        print(f"  待采集: {len(to_collect)}")
        print(f"  成功率: {self._calc_success_rate():.1f}%")
        
        if not to_collect:
            print("\n🎉 全部股票已采集完成！")
            return
        
        # 4. 确认开始
        print(f"\n📦 本次将采集 {len(to_collect)} 只股票")
        confirm = input("是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # 5. 分批采集
        total_batches = (len(to_collect) + batch_size - 1) // batch_size
        start_time = time.time()
        
        for batch_idx in range(0, len(to_collect), batch_size):
            batch = to_collect[batch_idx:batch_idx + batch_size]
            current_batch = batch_idx // batch_size + 1
            
            print(f"\n{'='*60}")
            print(f"📦 批次 {current_batch}/{total_batches} (本批 {len(batch)} 只)")
            print(f"{'='*60}")
            
            for i, stock_code in enumerate(batch, 1):
                global_idx = batch_idx + i
                progress_pct = (global_idx / len(to_collect)) * 100
                
                print(f"\n[{global_idx}/{len(to_collect)}] {progress_pct:.1f}% 采集 {stock_code}...")
                
                # 检查是否已存在
                file_path = self.stock_dir / f"{stock_code}_detail.json"
                if file_path.exists():
                    print(f"  ⏭️ 已存在，跳过")
                    self._update_progress(stock_code, 'skipped')
                    continue
                
                # 采集
                data = self.fetch_stock(stock_code)
                if data:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"  ✅ 成功保存: {file_path.name}")
                    self._update_progress(stock_code, 'success')
                    self.collected.add(stock_code)
                else:
                    print(f"  ❌ 失败")
                    self._update_progress(stock_code, 'failed')
                
                # 显示当前统计
                if (i) % 10 == 0:
                    self._show_stats()
            
            # 批次间暂停
            if current_batch < total_batches:
                print(f"\n⏸️ 批次完成，暂停 {pause} 秒...")
                for i in range(pause, 0, -1):
                    print(f"\r   {i} 秒后继续...", end='', flush=True)
                    time.sleep(1)
                print()
        
        # 6. 最终统计
        elapsed = time.time() - start_time
        print(f"\n{'='*70}")
        print("✅ 采集完成！")
        print("="*70)
        self._show_stats()
        print(f"⏱️  总耗时: {elapsed:.1f} 秒")
        print(f"⚡ 平均速度: {len(to_collect)/elapsed:.1f} 只/秒")
    
    def _calc_success_rate(self):
        """计算成功率"""
        total = len(self.progress['completed']) + len(self.progress['failed'])
        if total == 0:
            return 0
        return (len(self.progress['completed']) / total) * 100
    
    def _show_stats(self):
        """显示统计信息"""
        print(f"\n📊 实时统计:")
        print(f"  请求总数: {self.stats['total_requests']}")
        print(f"  成功: {self.stats['success']}")
        print(f"  失败: {self.stats['failed']}")
        print(f"  跳过: {self.stats['skipped']}")
        print(f"  累计成功: {len(self.progress['completed'])}")
        print(f"  累计失败: {len(self.progress['failed'])}")
        print(f"  成功率: {self._calc_success_rate():.1f}%")
    
    def retry_failed(self, batch_size: int = 20):
        """重试失败的股票"""
        failed = self.progress.get('failed', [])
        if not failed:
            print("✅ 没有失败的股票")
            return
        
        print(f"\n📦 重试 {len(failed)} 只失败的股票")
        
        for i, stock_code in enumerate(failed[:batch_size], 1):
            print(f"\n[{i}/{min(batch_size, len(failed))}] 重试 {stock_code}...")
            
            data = self.fetch_stock(stock_code)
            if data:
                file_path = self.stock_dir / f"{stock_code}_detail.json"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  ✅ 成功")
                self._update_progress(stock_code, 'success')
            else:
                print(f"  ❌ 仍然失败")
            
            time.sleep(1)
    
    def show_summary(self):
        """显示汇总信息"""
        print("\n" + "="*70)
        print("📊 采集汇总")
        print("="*70)
        
        # 统计股票总数
        all_stocks = self.extract_from_children()
        
        print(f"\n📈 统计:")
        print(f"  总股票数: {len(all_stocks)}")
        print(f"  已成功: {len(self.progress['completed'])}")
        print(f"  已失败: {len(self.progress['failed'])}")
        print(f"  剩余: {len(all_stocks) - len(self.progress['completed'])}")
        print(f"  成功率: {self._calc_success_rate():.1f}%")
        
        # 文件大小统计
        total_size = sum(f.stat().st_size for f in self.stock_dir.glob("*.json")) / (1024*1024)
        print(f"  数据总量: {total_size:.2f} MB")
        
        if self.progress['failed']:
            print(f"\n⚠️ 失败的股票 (前10): {self.progress['failed'][:10]}")

def main():
    collector = StockCollector()
    
    while True:
        print("\n" + "="*70)
        print("请选择操作:")
        print("1. 采集所有股票（自动跳过已下载）")
        print("2. 测试采集前10只")
        print("3. 显示统计信息")
        print("4. 重试失败的股票")
        print("5. 退出")
        
        choice = input("\n请输入 (1-5): ").strip()
        
        if choice == "1":
            collector.collect()
        elif choice == "2":
            collector.collect(limit=10)
        elif choice == "3":
            collector.show_summary()
        elif choice == "4":
            collector.retry_failed()
        elif choice == "5":
            print("👋 再见！")
            break
        else:
            print("❌ 无效选择")

if __name__ == "__main__":
    main()