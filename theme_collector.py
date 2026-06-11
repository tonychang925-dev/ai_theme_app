#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整版题材数据采集器
采集所有数据类型：历史事件、详情、日线数据、实时股票、子主题树
"""

import subprocess
import json
from pathlib import Path
import os
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# ==================== 配置 ====================
class Config:
    """系统配置"""
    BASE_URL = "https://app.txcfgl.com/api/app"
    AUTH_TOKEN = os.getenv("AUTHORIZATION", "")
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    COLLECT_DAILY = True      # 是否采集日线数据
    COLLECT_STOCKS = True     # 是否采集股票数据
    COLLECT_RECURSIVE = True  # 是否递归采集子题材
    MAX_DEPTH = 3             # 最大递归深度
    
    # 输出目录结构
    OUTPUT_DIR = Path("theme_data_complete")
    HISTORY_DIR = OUTPUT_DIR / "history"      # top-history 数据
    DETAILS_DIR = OUTPUT_DIR / "details"      # query/{id} 数据
    DAILY_DIR = OUTPUT_DIR / "daily"          # daily/{id}/{days} 数据
    STOCKS_DIR = OUTPUT_DIR / "stocks"        # realtime-by-subject/v2 数据
    CHILDREN_DIR = OUTPUT_DIR / "children"    # child-tree/v2/{id} 数据
    LISTS_DIR = OUTPUT_DIR / "lists"          # 题材列表数据
    
    # 采集控制
    REQUEST_DELAY = 0.5      # 请求延迟（秒）
    DAILY_DAYS = 365         # 日线数据天数
    STOCK_DATES = 5          # 采集最近几个交易日的股票数据
    
    @classmethod
    def init_dirs(cls):
        """初始化所有输出目录"""
        for dir_path in [
            cls.HISTORY_DIR, cls.DETAILS_DIR, cls.DAILY_DIR,
            cls.STOCKS_DIR, cls.CHILDREN_DIR, cls.LISTS_DIR
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

# ==================== API客户端 ====================
class APIClient:
    """使用curl的API客户端"""
    
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.stats = {
            'total_requests': 0,
            'success': 0,
            'failed': 0,
            'by_type': {}
        }
    
    def _build_curl_cmd(self, endpoint: str, params: Optional[Dict] = None) -> List[str]:
        """构建curl命令"""
        url = f"{Config.BASE_URL}/{endpoint.lstrip('/')}"
        
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        
        cmd = [
            'curl',
            '-s',  # 静默模式
            '-L',  # 跟随重定向
            '--compressed',
            '--connect-timeout', '8',
            '--max-time', '20',
            '-H', f'User-Agent: {Config.HEADERS["User-Agent"]}',
            '-H', f'Accept: {Config.HEADERS["Accept"]}',
            '-H', f'Accept-Language: {Config.HEADERS["Accept-Language"]}',
            '-H', 'Connection: keep-alive',
            '-H', 'Referer: https://app.txcfgl.com/',
            '-H', 'Origin: https://app.txcfgl.com',
            '-H', f'Authorization: {self.auth_token}',
            '--cacert', '/etc/ssl/cert.pem',
            url
        ]
        
        return cmd
    
    def request(self, endpoint: str, params: Optional[Dict] = None, 
                data_type: str = "unknown") -> Optional[Dict]:
        """发送请求"""
        cmd = self._build_curl_cmd(endpoint, params)
        
        # 限流
        time.sleep(Config.REQUEST_DELAY)
        
        # 更新统计
        self.stats['total_requests'] += 1
        self.stats['by_type'][data_type] = self.stats['by_type'].get(data_type, 0) + 1
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    
                    # 检查响应状态
                    if isinstance(data, dict):
                        code = data.get('code')
                        if code == 200:
                            self.stats['success'] += 1
                            return data
                        elif code == 401:
                            print(f"⚠️ 认证失败: {data.get('msg', '')}")
                            self.stats['failed'] += 1
                            return None
                        else:
                            print(f"⚠️ 返回码 {code}: {data.get('msg', '')}")
                            self.stats['failed'] += 1
                            return data  # 仍然返回数据，可能包含有用信息
                    
                    self.stats['success'] += 1
                    return data
                    
                except json.JSONDecodeError:
                    print(f"❌ 响应不是有效的JSON: {result.stdout[:100]}")
                    self.stats['failed'] += 1
                    return None
            else:
                print("❌ 空响应")
                self.stats['failed'] += 1
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Curl错误: {e}")
            self.stats['failed'] += 1
            return None

# ==================== 数据采集器 ====================
class DataCollector:
    """各类数据采集器"""
    
    def __init__(self, client: APIClient):
        self.client = client
        Config.init_dirs()
    
    def save_jsonl(self, data: Any, file_path: Path, data_type: str):
        """保存为JSONL格式"""
        if data is None:
            print(f"⚠️ 没有{data_type}数据可保存")
            return False

        try:
            items = self.extract_items(data)

            if not items:
                print(f"⚠️ {data_type}数据为空")
                return False

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            print(f"✅ 已保存 {len(items)} 条{data_type}记录到 {file_path}")
            return True

        except Exception as e:
            print(f"❌ 保存{data_type}数据失败: {e}")
            return False

    @staticmethod
    def extract_items(data: Any) -> List[Any]:
        """统一提取响应里的记录列表，兼容 data / rows 两种结构。"""
        if data is None:
            return []
        if isinstance(data, dict):
            if 'data' in data:
                data_field = data['data']
                if isinstance(data_field, list):
                    return data_field
                if data_field is not None:
                    return [data_field]
            if 'rows' in data:
                rows = data['rows']
                if isinstance(rows, list):
                    return rows
                if rows is not None:
                    return [rows]
            return [data]
        if isinstance(data, list):
            return data
        return []
    
    # ========== 1. 题材详情 ==========
    def collect_details(self, theme_id: int) -> Optional[Dict]:
        """采集题材详情 /query/{id}"""
        print(f"\n📊 采集题材 {theme_id} 详情...")
        data = self.client.request(f"subject/query/{theme_id}", data_type="details")
        
        if data:
            file_path = Config.DETAILS_DIR / f"{theme_id}_details.jsonl"
            self.save_jsonl(data, file_path, "详情")
        
        return data
    
    # ========== 2. 历史事件 ==========
    def collect_history(self, theme_id: int, pages: int = 3) -> Optional[Dict]:
        """采集历史事件 /top-history"""
        print(f"\n📜 采集题材 {theme_id} 历史事件...")

        all_data = []
        for page in range(1, pages + 1):
            params = {
                "subjectId": theme_id,
                "pageNum": page,
                "pageSize": 20
            }
            data = self.client.request("subject/top-history", params, f"history_p{page}")

            rows = self.extract_items(data)
            if rows:
                all_data.extend(rows)
                print(f"  第{page}页: {len(rows)} 条")
            else:
                break

        if all_data:
            file_path = Config.HISTORY_DIR / f"{theme_id}_history.jsonl"
            self.save_jsonl({"data": all_data}, file_path, "历史事件")
        
        return {"data": all_data} if all_data else None
    
    # ========== 3. 日线数据 ==========
    def collect_daily(self, theme_id: int, days: int = 365) -> Optional[Dict]:
        """采集日线数据 /daily/{id}/{days}"""
        print(f"\n📈 采集题材 {theme_id} 日线数据 ({days}天)...")
        data = self.client.request(f"subject/daily/{theme_id}/{days}", data_type="daily")
        
        if data and 'data' in data and data['data']:
            file_path = Config.DAILY_DIR / f"{theme_id}_daily.jsonl"
            self.save_jsonl(data, file_path, "日线")
            print(f"  共 {len(data['data'])} 个交易日")
        
        return data
    
    # ========== 4. 实时股票 ==========
    def collect_stocks(self, theme_id: int, date: str = None) -> Optional[Dict]:
        """采集实时股票数据 /realtime-by-subject/v2"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"\n📊 采集题材 {theme_id} {date} 股票数据...")
        
        params = {
            "sort": "pctChg",
            "sortType": "desc",
            "date": date,
            "subjectId": theme_id,
            "start": 0,
            "end": 1200
        }
        
        data = self.client.request("stock/realtime-by-subject/v2", params, f"stocks_{date}")
        
        if data and 'rows' in data and data['rows']:
            # 按月分片存储
            month = date[:7]
            file_path = Config.STOCKS_DIR / f"{theme_id}_{month}_stocks.jsonl"
            self.save_jsonl(data, file_path, f"股票{date}")
            print(f"  共 {len(data['rows'])} 只股票")
        
        return data
    
    # ========== 5. 子主题树 ==========
    def collect_children(self, theme_id: int) -> Optional[Dict]:
        """采集子主题树 /child-tree/v2/{id}"""
        print(f"\n🌳 采集题材 {theme_id} 子主题树...")
        
        params = {
            "sort": "pctChg",
            "sortType": "desc"
        }
        
        data = self.client.request(f"subject/child-tree/v2/{theme_id}", params, "children")
        if data is None:
            return None

        file_path = Config.CHILDREN_DIR / f"{theme_id}_children.jsonl"

        # 兼容两种返回：
        # 1) 标准 JSON 对象，包含 data/rows
        # 2) 直接返回字符串 payload（当前 child-tree 接口就是这种）
        if isinstance(data, str):
            self.save_jsonl({"data": [{"raw": data, "subject_id": theme_id}]}, file_path, "子主题")
            print(f"  child-tree 返回字符串 payload，已原样落盘")
            return {"data": data}

        if isinstance(data, dict) and data.get('data'):
            self.save_jsonl(data, file_path, "子主题")
            print(f"  共 {len(data['data'])} 个子主题")

        return data
    
    # ========== 6. 批量采集一个题材 ==========
    def collect_all_for_theme(self, theme_id: int, recursive: bool = True, max_depth: int = 3):
        """
        全面采集题材数据，可选择是否递归采集子题材
        
        Args:
            theme_id: 题材ID
            recursive: 是否递归采集子题材
            max_depth: 最大递归深度
        """
        self._collect_single_theme(theme_id, depth=1, max_depth=max_depth if recursive else 1)

    def _collect_single_theme(self, theme_id: int, depth: int, max_depth: int):
        """
        递归采集单个题材的内部方法
        """
        indent = "  " * (depth - 1)
        print(f"\n{indent}{'='*50}")
        print(f"{indent}[深度{depth}] 开始采集题材 {theme_id}")
        print(f"{indent}{'='*50}")
        
        # 1. 详情（必须）
        details_data = self.collect_details(theme_id)
        
        # 2. 历史事件（必须）
        history_data = self.collect_history(theme_id)
        
        # 3. 日线数据（可选）
        if hasattr(Config, 'COLLECT_DAILY') and Config.COLLECT_DAILY:
            self.collect_daily(theme_id, Config.DAILY_DAYS)
        
        # 4. 实时股票（可选）
        if hasattr(Config, 'COLLECT_STOCKS') and Config.COLLECT_STOCKS:
            for i in range(Config.STOCK_DATES):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                self.collect_stocks(theme_id, date)
        
        # 5. 子主题树 - 用于获取子题材列表
        children_data = self.collect_children(theme_id)
        
        # 6. 递归采集子题材
        if depth < max_depth and children_data and 'data' in children_data:
            child_items = children_data['data']
            print(f"{indent}发现 {len(child_items)} 个子题材，开始递归采集...")
            
            for child_item in child_items:
                if isinstance(child_item, list) and len(child_item) > 0:
                    child_id = child_item[0]
                    child_name = child_item[1] if len(child_item) > 1 else "未知"
                    print(f"{indent}  ↳ 子题材: {child_name} ({child_id})")
                    
                    # 递归采集子题材
                    self._collect_single_theme(child_id, depth + 1, max_depth)
                    
                    # 子题材间延迟
                    time.sleep(Config.REQUEST_DELAY)
        
        print(f"{indent}✅ 题材 {theme_id} 采集完成")

# ==================== 题材发现 ====================
class ThemeDiscovery:
    """发现需要采集的题材"""
    
    def __init__(self, client: APIClient):
        self.client = client
    
    def discover_from_history(self) -> List[int]:
        """从已采集的历史数据中发现题材ID"""
        theme_ids = set()
        
        # 从已有文件中发现题材ID
        history_files = list(Config.HISTORY_DIR.glob("*_history.jsonl"))
        for f in history_files:
            try:
                theme_id = int(f.stem.split('_')[0])
                theme_ids.add(theme_id)
            except:
                pass
        
        return sorted(list(theme_ids))
    
    def discover_from_api(self) -> List[int]:
        """从 /subject/list API 发现所有题材ID（只需请求一次）"""
        print("\n正在从 /subject/list 获取题材列表...")
        
        # 请求一次就够了，不需要分页
        params = {
            "pageNum": 1,
            "pageSize": 1000  # 设置大一点确保获取全部
        }
        
        data = self.client.request("subject/list", params, "discover")
        
        all_ids = set()
        
        if data and data.get('code') == 200:
            items = data.get('data', [])
            print(f"  获取到 {len(items)} 个题材")
            
            # 提取题材ID
            for item in items:
                if isinstance(item, dict):
                    # 尝试不同的ID字段名
                    theme_id = item.get('id') or item.get('subjectId')
                    if theme_id:
                        all_ids.add(theme_id)
            
            print(f"\n✅ 共发现 {len(all_ids)} 个唯一题材ID")
            return sorted(list(all_ids))
        else:
            print("❌ 获取题材列表失败")
            return []
    
    def get_priority_themes(self) -> List[int]:
        """获取优先采集的题材（数据丰富的）"""
        # 从之前采集结果中找出数据量大的题材
        rich_themes = []
        
        for f in Config.DETAILS_DIR.glob("*_details.jsonl"):
            size = f.stat().st_size
            if size > 1000:  # 大于1KB
                try:
                    theme_id = int(f.stem.split('_')[0])
                    rich_themes.append((theme_id, size))
                except:
                    pass
        
        # 按数据量排序
        rich_themes.sort(key=lambda x: x[1], reverse=True)
        return [tid for tid, _ in rich_themes[:20]]  # 返回前20个

# ==================== 分批次采集功能 ====================

def batch_collect_with_progress(collector, theme_ids, batch_size=100, pause_time=30):
    """
    分批次采集题材，每批完成后暂停
    
    Args:
        collector: 数据采集器实例
        theme_ids: 所有题材ID列表
        batch_size: 每批采集数量
        pause_time: 批次间暂停时间（秒）
    """
    total = len(theme_ids)
    batches = [theme_ids[i:i+batch_size] for i in range(0, total, batch_size)]
    
    print(f"\n📊 将分 {len(batches)} 批采集 {total} 个题材，每批 {batch_size} 个")
    print(f"⏱️  预计总时间: {total * 6 / 60:.1f} 分钟")
    print(f"⏸️  批次间暂停: {pause_time} 秒\n")
    
    start_time = time.time()
    total_processed = 0
    
    for batch_idx, batch in enumerate(batches, 1):
        print(f"\n{'='*70}")
        print(f"📦 开始第 {batch_idx}/{len(batches)} 批采集，本批 {len(batch)} 个题材")
        print(f"{'='*70}")
        
        batch_start = time.time()
        
        # 采集本批题材
        for i, theme_id in enumerate(batch, 1):
            print(f"\n进度: 本批 [{i}/{len(batch)}] 总体 [{total_processed + i}/{total}]")
            collector.collect_all_for_theme(theme_id)
            
            # 每10个题材显示一次统计
            if i % 10 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / (total_processed + i)
                remaining = avg_time * (total - (total_processed + i))
                print(f"\n📊 统计: 已用{elapsed:.1f}秒, 平均{avg_time:.1f}秒/题材, 预计剩余{remaining:.1f}秒")
        
        batch_time = time.time() - batch_start
        total_processed += len(batch)
        
        print(f"\n✅ 第 {batch_idx} 批完成，用时 {batch_time:.1f} 秒")
        print(f"📈 累计完成: {total_processed}/{total} 个题材")
        
        # 如果不是最后一批，暂停
        if batch_idx < len(batches):
            print(f"\n⏸️  暂停 {pause_time} 秒，准备下一批...")
            
            # 倒计时显示
            for i in range(pause_time, 0, -1):
                print(f"\r    {i} 秒后继续...", end='', flush=True)
                time.sleep(1)
            print("\r   继续采集！" + " " * 20)
    
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"🎉 全部 {total} 个题材采集完成！")
    print(f"⏱️  总用时: {total_time/60:.1f} 分钟")
    print(f"{'='*70}")
    
    return total_time

# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("完整版题材数据采集系统启动")
    print("="*70)
    
    # 检查认证
    if not Config.AUTH_TOKEN:
        print("❌ 请设置环境变量 AUTHORIZATION")
        print("   在.env文件中添加: AUTHORIZATION=\"Bearer xxx...\"")
        print("\n或者手动输入:")
        auth_token = input("请输入 Authorization: ").strip()
        if auth_token:
            Config.AUTH_TOKEN = auth_token
        else:
            return
    
    # 初始化
    client = APIClient(Config.AUTH_TOKEN)
    collector = DataCollector(client)
    discovery = ThemeDiscovery(client)
    
    # 选择采集模式
    print("\n请选择采集模式:")
    print("1. 采集所有已知题材（从API发现）")
    print("2. 采集优先题材（数据量大的）")
    print("3. 手动指定题材ID")
    print("4. 采集单个题材测试")
    print("5. 从文件恢复采集（读取已保存的进度）")
    
    mode = input("\n请输入模式 (1-5): ").strip()
    
    theme_ids = []
    
    if mode == "1":
        print("\n正在从API发现题材...")
        theme_ids = discovery.discover_from_api()
        if not theme_ids:
            print("⚠️ API发现失败，尝试从本地文件发现...")
            theme_ids = discovery.discover_from_files()
        
    elif mode == "2":
        theme_ids = discovery.get_priority_themes()
        print(f"优先采集 {len(theme_ids)} 个题材")
        
    elif mode == "3":
        ids_input = input("请输入题材ID（用逗号或空格分隔）: ")
        theme_ids = [int(x) for x in ids_input.replace(',', ' ').split()]
        
    elif mode == "4":
        tid = int(input("请输入测试题材ID: "))
        theme_ids = [tid]
        
    elif mode == "5":
        # 从进度文件恢复
        progress_file = Config.OUTPUT_DIR / "progress.json"
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress = json.load(f)
                    completed = set(progress.get('completed', []))
                    all_themes = set(progress.get('all_themes', []))
                    
                    remaining = list(all_themes - completed)
                    if remaining:
                        print(f"📊 发现进度: 已完成 {len(completed)} 个，剩余 {len(remaining)} 个")
                        theme_ids = remaining
                    else:
                        print("✅ 所有题材都已采集完成！")
                        return
            except Exception as e:
                print(f"❌ 读取进度文件失败: {e}")
                return
        else:
            print("❌ 未找到进度文件")
            return
    
    else:
        print("❌ 无效选择")
        return
    
    if not theme_ids:
        print("❌ 没有题材可采集")
        return
    
    # 显示题材列表预览
    preview = theme_ids[:10]
    print(f"\n📋 共发现 {len(theme_ids)} 个题材")
    print(f"预览: {preview}{'...' if len(theme_ids) > 10 else ''}")
    
    # 保存所有题材列表供进度恢复用
    all_themes_file = Config.OUTPUT_DIR / "all_themes.json"
    with open(all_themes_file, 'w') as f:
        json.dump(theme_ids, f)
    
    # 询问采集方式
    print("\n请选择采集方式:")
    print("1. 一次性采集全部（可能耗时较长）")
    print("2. 分批次采集（推荐，可中途休息）")
    print("3. 自定义批次参数")
    print("4. 仅采集前N个测试")
    
    collect_mode = input("\n请输入 (1-4): ").strip()
    
    if collect_mode == "1":
        # 一次性采集
        confirm = input(f"\n将一次性采集全部 {len(theme_ids)} 个题材，是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        print("\n" + "="*70)
        print("开始一次性批量采集")
        print("="*70)
        
        start_time = time.time()
        completed = []
        
        try:
            for i, theme_id in enumerate(theme_ids, 1):
                print(f"\n进度: [{i}/{len(theme_ids)}]")
                collector.collect_all_for_theme(theme_id)
                completed.append(theme_id)
                
                # 每10个题材保存一次进度
                if i % 10 == 0:
                    # 保存进度
                    progress = {
                        'completed': completed,
                        'all_themes': theme_ids,
                        'last_update': datetime.now().isoformat()
                    }
                    with open(Config.OUTPUT_DIR / "progress.json", 'w') as f:
                        json.dump(progress, f, indent=2)
                    
                    # 显示统计
                    elapsed = time.time() - start_time
                    avg_time = elapsed / i
                    remaining = avg_time * (len(theme_ids) - i)
                    print(f"\n📊 统计: 已用{elapsed:.1f}秒, 平均{avg_time:.1f}秒/题材, 预计剩余{remaining:.1f}秒")
                    
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断采集")
            print(f"已采集 {len(completed)} 个题材，进度已保存")
            
            # 保存进度
            progress = {
                'completed': completed,
                'all_themes': theme_ids,
                'last_update': datetime.now().isoformat(),
                'interrupted': True
            }
            with open(Config.OUTPUT_DIR / "progress.json", 'w') as f:
                json.dump(progress, f, indent=2)
            print("✅ 进度已保存，下次可选择模式5恢复采集")
            return
        
        total_time = time.time() - start_time
        
    elif collect_mode == "2":
        # 分批次采集（默认参数）
        print(f"\n将使用默认参数分批次采集 {len(theme_ids)} 个题材")
        batch_collect_with_progress(collector, theme_ids, batch_size=100, pause_time=30)
        
    elif collect_mode == "3":
        # 自定义批次
        try:
            batch_size = int(input("请输入每批采集数量 (推荐50-100): ").strip() or "100")
            pause_time = int(input("请输入批次间暂停秒数 (推荐30-60): ").strip() or "30")
            batch_collect_with_progress(collector, theme_ids, batch_size, pause_time)
        except ValueError:
            print("❌ 输入无效，使用默认值")
            batch_collect_with_progress(collector, theme_ids, batch_size=100, pause_time=30)
    
    elif collect_mode == "4":
        # 仅采集前N个
        try:
            n = int(input("请输入要采集的数量: ").strip())
            if n > len(theme_ids):
                n = len(theme_ids)
            theme_ids = theme_ids[:n]
            print(f"\n将采集前 {n} 个题材进行测试")
            
            # 直接调用一次性采集的逻辑
            start_time = time.time()
            for i, theme_id in enumerate(theme_ids, 1):
                print(f"\n进度: [{i}/{n}]")
                collector.collect_all_for_theme(theme_id)
            
            total_time = time.time() - start_time
            print(f"\n✅ 测试采集完成，用时 {total_time:.1f} 秒")
            return
            
        except ValueError:
            print("❌ 输入无效")
            return
    
    else:
        print("❌ 无效选择")
        return
    
    # 最终统计
    print("\n" + "="*70)
    print("采集完成！")
    print("="*70)
    
    # 显示统计信息
    if 'total_time' in locals():
        print(f"⏱️  总用时: {total_time:.1f} 秒 ({total_time/60:.1f} 分钟)")
    
    print(f"📊 题材数: {len(theme_ids)}")
    print(f"📈 请求总数: {client.stats['total_requests']}")
    print(f"✅ 成功: {client.stats['success']}")
    print(f"❌ 失败: {client.stats['failed']}")
    
    if client.stats['total_requests'] > 0:
        success_rate = client.stats['success'] / client.stats['total_requests'] * 100
        print(f"📊 成功率: {success_rate:.1f}%")
    
    print("\n📁 数据类型统计:")
    for data_type, count in sorted(client.stats['by_type'].items()):
        print(f"  {data_type}: {count}")
    
    print(f"\n💾 数据保存位置: {Config.OUTPUT_DIR.absolute()}")
    
    print("\n📂 目录结构:")
    for dir_path in sorted(Config.OUTPUT_DIR.glob("*")):
        if dir_path.is_dir():
            file_count = len(list(dir_path.glob("*.jsonl")))
            total_size = sum(f.stat().st_size for f in dir_path.glob("*.jsonl")) / 1024
            print(f"  📁 {dir_path.name}/: {file_count} 个文件 ({total_size:.1f} KB)")
    
    # 保存最终进度
    final_progress = {
        'completed': theme_ids,
        'all_themes': theme_ids,
        'last_update': datetime.now().isoformat(),
        'stats': client.stats,
        'completed_all': True
    }
    with open(Config.OUTPUT_DIR / "progress.json", 'w') as f:
        json.dump(final_progress, f, indent=2)
    
    print("\n✅ 进度已保存到 progress.json")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
        print("部分数据可能已保存，可以下次使用模式5恢复采集")
    except Exception as e:
        print(f"\n❌ 程序出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
