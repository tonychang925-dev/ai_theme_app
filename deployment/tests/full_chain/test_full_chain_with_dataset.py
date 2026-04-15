#!/usr/bin/env python3
"""
AI主题分析应用 - 全链路测试脚本（测试数据集）
使用test_cases.txt中的测试数据验证业务逻辑
"""

import json
import time
import asyncio
import aiohttp
from datetime import datetime
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def load_test_cases():
    """加载测试数据"""
    test_cases_path = "../../../evaluate_service/data/raw/test_cases.txt"
    try:
        with open(test_cases_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析测试数据
        test_cases = {}
        current_theme = None

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 检查是否是主题行
            if line.startswith("测试集") and "题材名称:" in line:
                # 提取主题名称
                parts = line.split("题材名称:")
                if len(parts) > 1:
                    current_theme = parts[1].strip()
                    test_cases[current_theme] = []
            elif line.startswith("- ") and current_theme:
                # 提取新闻内容
                news_content = line[2:].strip()
                test_cases[current_theme].append(news_content)

        return test_cases

    except Exception as e:
        print(f"加载测试数据失败: {str(e)}")
        return {}

# 导入环境变量工具
try:
    from env_utils import get_deepseek_api_key, get_all_config
except ImportError:
    # 如果env_utils不存在，创建简单的替代函数
    def get_deepseek_api_key(env_file=".env.theme"):
        """从环境变量文件获取DeepSeek API密钥"""
        import re
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = re.match(r'DEEPSEEK_API_KEY\s*=\s*(.+)', line.strip())
                        if match:
                            value = match.group(1).strip()
                            # 移除引号
                            if (value.startswith('"') and value.endswith('"')) or \
                               (value.startswith("'") and value.endswith("'")):
                                value = value[1:-1]
                            return value
            except Exception as e:
                print(f"读取环境变量文件失败: {str(e)}")
        return os.environ.get('DEEPSEEK_API_KEY')
    
    def get_all_config(env_file=".env.theme"):
        """获取所有配置"""
        config = {}
        # 这里可以添加更多逻辑，但为了简单起见返回空字典
        return config


class FullChainTester:
    """全链路测试器"""
    
    def __init__(self, base_url="http://localhost:8002", api_key=None, env_file=".env.theme"):
        self.base_url = base_url
        
        # 优先使用传入的api_key，否则从环境文件读取
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = get_deepseek_api_key(env_file)
        
        self.session = None
        self.test_results = []
        self.theme_ids = []
        self.stock_codes = []
        
        # 打印API密钥状态（安全地）
        if self.api_key:
            masked_key = self.api_key[:4] + '*' * (len(self.api_key) - 8) + self.api_key[-4:] if len(self.api_key) > 8 else '****'
            print(f"使用API密钥: {masked_key}")
        else:
            print("警告: 未设置API密钥，某些功能可能受限")
    
    async def __aenter__(self):
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        self.session = aiohttp.ClientSession(headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_api_health(self):
        """测试API健康状态"""
        print("1. 测试API健康状态...")
        
        endpoints = [
            "/api/health",
            "/api/themes",
            "/api/intel/feed",
            "/api/recap/daily"
        ]
        
        results = []
        for endpoint in endpoints:
            try:
                async with self.session.get(f"{self.base_url}{endpoint}", timeout=10) as response:
                    status = response.status
                    if status == 200:
                        results.append({"endpoint": endpoint, "status": "healthy", "response_time": response.elapsed.total_seconds()})
                    else:
                        results.append({"endpoint": endpoint, "status": f"error: {status}", "response_time": response.elapsed.total_seconds()})
            except Exception as e:
                results.append({"endpoint": endpoint, "status": f"exception: {str(e)}", "response_time": None})
        
        healthy_count = sum(1 for r in results if r["status"] == "healthy")
        print(f"  API健康检查: {healthy_count}/{len(endpoints)} 个端点正常")
        return results
    
    async def load_test_data(self):
        """加载测试数据"""
        print("2. 加载测试数据集...")
        
        try:
            test_cases = load_test_cases()
            print(f"  加载了 {len(test_cases)} 个测试主题")
            
            # 提取新闻数据
            news_items = []
            for theme_name, news_list in test_cases.items():
                for news in news_list:
                    news_items.append({
                        "content": news,
                        "theme_name": theme_name,
                        "timestamp": datetime.now().isoformat()
                    })
            
            print(f"  提取了 {len(news_items)} 条新闻数据")
            return news_items
            
        except Exception as e:
            print(f"  加载测试数据失败: {str(e)}")
            return []
    
    async def simulate_news_processing(self, news_items, batch_size=10):
        """模拟新闻处理流程"""
        print(f"3. 模拟新闻处理流程 (批量大小: {batch_size})...")
        
        processed_count = 0
        errors = []
        
        # 分批处理新闻
        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i+batch_size]
            print(f"  处理批次 {i//batch_size + 1}: {len(batch)} 条新闻")
            
            for news in batch:
                try:
                    # 模拟事件处理API调用
                    payload = {
                        "content": news["content"],
                        "source": "test_dataset",
                        "timestamp": news["timestamp"],
                        "metadata": {
                            "theme_name": news["theme_name"],
                            "test_id": f"test_{processed_count}"
                        }
                    }
                    
                    async with self.session.post(
                        f"{self.base_url}/api/events/process",
                        json=payload,
                        timeout=30
                    ) as response:
                        if response.status in [200, 202]:
                            result = await response.json()
                            processed_count += 1
                            
                            # 记录处理结果
                            self.test_results.append({
                                "step": "news_processing",
                                "news_id": f"news_{processed_count}",
                                "theme_name": news["theme_name"],
                                "status": "success",
                                "response_time": response.elapsed.total_seconds(),
                                "result": result.get("event_id", "unknown")
                            })
                        else:
                            errors.append({
                                "news": news["content"][:50],
                                "status": response.status,
                                "error": await response.text()
                            })
                            
                except Exception as e:
                    errors.append({
                        "news": news["content"][:50],
                        "status": "exception",
                        "error": str(e)
                    })
            
            # 批次间延迟
            await asyncio.sleep(1)
        
        print(f"  新闻处理完成: {processed_count}/{len(news_items)} 条成功")
        if errors:
            print(f"  处理错误: {len(errors)} 条")
        
        return processed_count, errors
    
    async def verify_theme_updates(self):
        """验证主题更新"""
        print("4. 验证主题更新...")
        
        try:
            # 获取主题列表
            async with self.session.get(f"{self.base_url}/api/themes?limit=50") as response:
                if response.status == 200:
                    data = await response.json()
                    themes = data.get("themes", [])
                    
                    # 记录主题信息
                    self.theme_ids = [theme["id"] for theme in themes]
                    print(f"  获取到 {len(themes)} 个主题")
                    
                    # 检查主题热度
                    heat_scores = []
                    for theme in themes[:10]:  # 检查前10个主题
                        heat_scores.append({
                            "theme_id": theme["id"],
                            "name": theme.get("name", "unknown"),
                            "heat_score": theme.get("heat_score", 0)
                        })
                    
                    return themes, heat_scores
                else:
                    print(f"  获取主题列表失败: {response.status}")
                    return [], []
                    
        except Exception as e:
            print(f"  验证主题更新异常: {str(e)}")
            return [], []
    
    async def verify_intel_feed(self):
        """验证情报流"""
        print("5. 验证情报流...")
        
        try:
            async with self.session.get(f"{self.base_url}/api/intel/feed?limit=20") as response:
                if response.status == 200:
                    data = await response.json()
                    feed_items = data.get("items", [])
                    
                    print(f"  获取到 {len(feed_items)} 条情报流项目")
                    
                    # 分析情报流类型分布
                    type_dist = {}
                    for item in feed_items:
                        item_type = item.get("type", "unknown")
                        type_dist[item_type] = type_dist.get(item_type, 0) + 1
                    
                    return feed_items, type_dist
                else:
                    print(f"  获取情报流失败: {response.status}")
                    return [], {}
                    
        except Exception as e:
            print(f"  验证情报流异常: {str(e)}")
            return [], {}
    
    async def verify_recap_data(self):
        """验证复盘数据"""
        print("6. 验证复盘数据...")
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            async with self.session.get(f"{self.base_url}/api/recap/daily?date={today}") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    has_market_summary = "market_summary" in data
                    has_top_themes = "top_themes" in data and len(data["top_themes"]) > 0
                    has_top_stocks = "top_stocks" in data and len(data["top_stocks"]) > 0
                    
                    print(f"  复盘数据检查:")
                    print(f"    - 市场总结: {'有' if has_market_summary else '无'}")
                    print(f"    - 热门主题: {len(data.get('top_themes', []))} 个" if has_top_themes else "    - 热门主题: 无")
                    print(f"    - 热门股票: {len(data.get('top_stocks', []))} 个" if has_top_stocks else "    - 热门股票: 无")
                    
                    return data
                else:
                    print(f"  获取复盘数据失败: {response.status}")
                    return {}
                    
        except Exception as e:
            print(f"  验证复盘数据异常: {str(e)}")
            return {}
    
    async def run_full_test(self):
        """运行完整测试"""
        print("=" * 60)
        print("AI主题分析应用 - 全链路测试（测试数据集）")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        start_time = time.time()
        
        # 1. 测试API健康状态
        api_results = await self.test_api_health()
        
        # 2. 加载测试数据
        news_items = await self.load_test_data()
        if not news_items:
            print("错误: 没有加载到测试数据，测试终止")
            return False
        
        # 3. 模拟新闻处理
        processed_count, errors = await self.simulate_news_processing(news_items)
        
        # 等待系统处理
        print("等待系统处理数据...")
        await asyncio.sleep(10)
        
        # 4. 验证主题更新
        themes, heat_scores = await self.verify_theme_updates()
        
        # 5. 验证情报流
        feed_items, type_dist = await self.verify_intel_feed()
        
        # 6. 验证复盘数据
        recap_data = await self.verify_recap_data()
        
        # 生成测试报告
        end_time = time.time()
        duration = end_time - start_time
        
        print("=" * 60)
        print("测试完成报告:")
        print(f"总耗时: {duration:.2f} 秒")
        print(f"测试数据: {len(news_items)} 条新闻")
        print(f"成功处理: {processed_count} 条")
        print(f"处理错误: {len(errors)} 条")
        print(f"发现主题: {len(themes)} 个")
        print(f"情报流项目: {len(feed_items)} 条")
        print("=" * 60)
        
        # 保存测试结果
        report = {
            "test_name": "full_chain_with_dataset",
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": duration,
            "api_config": {
                "base_url": self.base_url,
                "api_key_configured": bool(self.api_key)
            },
            "api_health": api_results,
            "test_data": {
                "news_count": len(news_items),
                "processed_count": processed_count,
                "error_count": len(errors)
            },
            "system_state": {
                "theme_count": len(themes),
                "feed_item_count": len(feed_items),
                "has_recap_data": bool(recap_data)
            },
            "errors": errors,
            "success": processed_count > len(news_items) * 0.8  # 80%成功率
        }
        
        # 保存报告
        report_file = f"full_chain_dataset_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"测试报告已保存到: {report_file}")
        
        return report["success"]


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI主题分析应用全链路测试（测试数据集）')
    parser.add_argument('--base-url', default='http://localhost:8000', help='API基础URL')
    parser.add_argument('--api-key', help='API密钥（如果不提供，将从.env.theme读取）')
    parser.add_argument('--env-file', default='.env.theme', help='环境变量文件路径')
    parser.add_argument('--batch-size', type=int, default=10, help='批量处理大小')
    
    args = parser.parse_args()
    
    async with FullChainTester(args.base_url, args.api_key, args.env_file) as tester:
        success = await tester.run_full_test()
        
        if success:
            print("\n✅ 全链路测试通过！业务逻辑正常工作。")
            return 0
        else:
            print("\n❌ 全链路测试失败！请检查系统状态。")
            return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n用户中断测试")
        sys.exit(130)
    except Exception as e:
        print(f"测试异常: {str(e)}")
        sys.exit(1)
