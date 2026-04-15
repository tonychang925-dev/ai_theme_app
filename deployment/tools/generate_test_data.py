#!/usr/bin/env python3
"""
AI主题分析应用 - 测试数据生成工具
用于生成性能测试所需的数据
"""

import json
import random
import time
from datetime import datetime, timedelta
from faker import Faker
import asyncio
import aiohttp
import argparse
import sys

fake = Faker(locale='zh_CN')


class TestDataGenerator:
    """测试数据生成器"""

    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.theme_ids = []
        self.stock_codes = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_themes(self, count=50):
        """生成测试主题数据"""
        print(f"生成 {count} 个测试主题...")

        themes = []
        categories = ['科技', '消费', '医药', '新能源', '金融', '制造', '环保', '人工智能']

        for i in range(count):
            theme = {
                'id': f'theme_test_{i:03d}',
                'name': f'{random.choice(categories)}主题测试{i}',
                'description': fake.text(max_nb_chars=200),
                'category': random.choice(categories),
                'heat_score': random.randint(50, 100),
                'created_at': fake.date_time_this_year().isoformat(),
                'updated_at': fake.date_time_this_month().isoformat(),
                'metadata': {
                    'test_data': True,
                    'generated_at': datetime.now().isoformat()
                }
            }
            themes.append(theme)

        # 保存到文件
        with open('test_themes.json', 'w', encoding='utf-8') as f:
            json.dump(themes, f, ensure_ascii=False, indent=2)

        self.theme_ids = [theme['id'] for theme in themes]
        print(f"主题数据已保存到 test_themes.json")
        return themes

    async def generate_stocks(self, count=100):
        """生成测试股票数据"""
        print(f"生成 {count} 个测试股票...")

        stocks = []
        industries = ['银行', '证券', '保险', '科技', '医药', '消费', '能源', '制造']

        for i in range(count):
            stock_code = f'{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}'
            stock = {
                'code': stock_code,
                'name': f'{fake.company()}股份',
                'industry': random.choice(industries),
                'market_value': random.randint(1000000000, 100000000000),
                'current_price': round(random.uniform(10, 200), 2),
                'change_percent': round(random.uniform(-5, 5), 2),
                'volume': random.randint(1000000, 100000000),
                'turnover': random.randint(100000000, 10000000000),
                'pe_ratio': round(random.uniform(10, 50), 2),
                'pb_ratio': round(random.uniform(1, 5), 2),
                'metadata': {
                    'test_data': True,
                    'generated_at': datetime.now().isoformat()
                }
            }
            stocks.append(stock)

        # 保存到文件
        with open('test_stocks.json', 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)

        self.stock_codes = [stock['code'] for stock in stocks]
        print(f"股票数据已保存到 test_stocks.json")
        return stocks

    async def generate_news_events(self, count=200):
        """生成测试新闻事件数据"""
        print(f"生成 {count} 个测试新闻事件...")

        events = []
        event_types = ['policy', 'financial', 'industry', 'company', 'market']
        impact_levels = ['high', 'medium', 'low']

        for i in range(count):
            event_date = fake.date_time_between(start_date='-30d', end_date='now')
            event = {
                'event_id': f'evt_test_{i:04d}',
                'title': fake.sentence(),
                'content': fake.text(max_nb_chars=500),
                'summary': fake.text(max_nb_chars=100),
                'event_type': random.choice(event_types),
                'impact_level': random.choice(impact_levels),
                'source': random.choice(['news_site', 'government', 'company', 'research']),
                'published_at': event_date.isoformat(),
                'created_at': datetime.now().isoformat(),
                'related_themes': random.sample(self.theme_ids, min(3, len(self.theme_ids))) if self.theme_ids else [],
                'related_stocks': random.sample(self.stock_codes, min(5, len(self.stock_codes))) if self.stock_codes else [],
                'metadata': {
                    'test_data': True,
                    'generated_at': datetime.now().isoformat()
                }
            }
            events.append(event)

        # 保存到文件
        with open('test_events.json', 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

        print(f"新闻事件数据已保存到 test_events.json")
        return events

    async def generate_intel_feed(self, count=300):
        """生成测试情报流数据"""
        print(f"生成 {count} 个测试情报流项目...")

        feed_items = []
        item_types = ['news', 'event', 'theme_update', 'stock_alert', 'market_trend']

        for i in range(count):
            item_date = fake.date_time_between(start_date='-7d', end_date='now')
            item = {
                'id': f'feed_test_{i:05d}',
                'type': random.choice(item_types),
                'title': fake.sentence(),
                'content': fake.text(max_nb_chars=200),
                'priority': random.randint(1, 5),
                'published_at': item_date.isoformat(),
                'source_channel': random.choice(['realtime_news', 'jyhf_manual', 'ai_analysis']),
                'related_themes': random.sample(self.theme_ids, min(2, len(self.theme_ids))) if self.theme_ids else [],
                'related_stocks': random.sample(self.stock_codes, min(3, len(self.stock_codes))) if self.stock_codes else [],
                'metadata': {
                    'test_data': True,
                    'generated_at': datetime.now().isoformat()
                }
            }
            feed_items.append(item)

        # 保存到文件
        with open('test_feed.json', 'w', encoding='utf-8') as f:
            json.dump(feed_items, f, ensure_ascii=False, indent=2)

        print(f"情报流数据已保存到 test_feed.json")
        return feed_items

    async def generate_recap_data(self, days=30):
        """生成测试复盘数据"""
        print(f"生成 {days} 天的测试复盘数据...")

        recap_data = []
        for day in range(days):
            date = datetime.now() - timedelta(days=day)
            recap = {
                'date': date.strftime('%Y-%m-%d'),
                'market_summary': fake.text(max_nb_chars=300),
                'top_themes': [
                    {
                        'theme_id': theme_id,
                        'heat_score': random.randint(60, 100),
                        'change': random.randint(-20, 20)
                    }
                    for theme_id in random.sample(self.theme_ids, min(5, len(self.theme_ids)))
                ] if self.theme_ids else [],
                'top_stocks': [
                    {
                        'code': stock_code,
                        'name': f'股票{stock_code}',
                        'change_percent': round(random.uniform(-10, 10), 2),
                        'volume': random.randint(1000000, 50000000)
                    }
                    for stock_code in random.sample(self.stock_codes, min(10, len(self.stock_codes)))
                ] if self.stock_codes else [],
                'key_events': [
                    {
                        'event_id': f'evt_recap_{day}_{j}',
                        'title': fake.sentence(),
                        'impact': random.choice(['high', 'medium', 'low'])
                    }
                    for j in range(random.randint(3, 8))
                ],
                'metadata': {
                    'test_data': True,
                    'generated_at': datetime.now().isoformat()
                }
            }
            recap_data.append(recap)

        # 保存到文件
        with open('test_recap.json', 'w', encoding='utf-8') as f:
            json.dump(recap_data, f, ensure_ascii=False, indent=2)

        print(f"复盘数据已保存到 test_recap.json")
        return recap_data

    async def load_data_to_api(self, endpoint, data):
        """将测试数据加载到API"""
        print(f"加载数据到 {endpoint}...")

        success_count = 0
        error_count = 0

        for item in data:
            try:
                async with self.session.post(
                    f"{self.base_url}{endpoint}",
                    json=item,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in [200, 201]:
                        success_count += 1
                    else:
                        error_count += 1
                        print(f"错误: {response.status} - {await response.text()}")
            except Exception as e:
                error_count += 1
                print(f"异常: {str(e)}")

            # 避免请求过快
            await asyncio.sleep(0.1)

        print(f"加载完成: 成功 {success_count}, 失败 {error_count}")
        return success_count, error_count

    async def generate_all(self, counts=None):
        """生成所有测试数据"""
        if counts is None:
            counts = {
                'themes': 50,
                'stocks': 100,
                'events': 200,
                'feed': 300,
                'recap_days': 30
            }

        print("开始生成测试数据...")
        print("=" * 60)

        # 生成主题数据
        await self.generate_themes(counts['themes'])

        # 生成股票数据
        await self.generate_stocks(counts['stocks'])

        # 生成新闻事件数据
        await self.generate_news_events(counts['events'])

        # 生成情报流数据
        await self.generate_intel_feed(counts['feed'])

        # 生成复盘数据
        await self.generate_recap_data(counts['recap_days'])

        print("=" * 60)
        print("所有测试数据生成完成！")
        print(f"生成的文件:")
        print(f"  - test_themes.json: {counts['themes']} 个主题")
        print(f"  - test_stocks.json: {counts['stocks']} 个股票")
        print(f"  - test_events.json: {counts['events']} 个事件")
        print(f"  - test_feed.json: {counts['feed']} 个情报项")
        print(f"  - test_recap.json: {counts['recap_days']} 天复盘")

    def create_load_test_scenario(self, user_count=100, duration_minutes=10):
        """创建负载测试场景配置"""
        scenario = {
            'name': 'AI Theme App Load Test',
            'description': '性能压力测试场景',
            'configuration': {
                'user_count': user_count,
                'duration_minutes': duration_minutes,
                'ramp_up_time_minutes': 2,
                'ramp_down_time_minutes': 2,
                'think_time_ms': {
                    'min': 1000,
                    'max': 3000
                }
            },
            'apis': {
                'themes': {
                    'endpoint': '/api/themes',
                    'method': 'GET',
                    'weight': 30,
                    'expected_response_time_ms': 500
                },
                'intel_feed': {
                    'endpoint': '/api/intel/feed',
                    'method': 'GET',
                    'weight': 25,
                    'expected_response_time_ms': 600
                },
                'stock_info': {
                    'endpoint': '/api/stocks/{code}',
                    'method': 'GET',
                    'weight': 20,
                    'expected_response_time_ms': 400
                },
                'recap': {
                    'endpoint': '/api/recap/daily',
                    'method': 'GET',
                    'weight': 15,
                    'expected_response_time_ms': 800
                },
                'ai_process': {
                    'endpoint': '/api/events/process',
                    'method': 'POST',
                    'weight': 10,
                    'expected_response_time_ms': 2000
                }
            },
            'test_data': {
                'theme_ids': self.theme_ids,
                'stock_codes': self.stock_codes,
                'search_terms': ['科技', '消费', '医药', '新能源', '人工智能']
            },
            'success_criteria': {
                'response_time_p95_ms': 500,
                'error_rate_percent': 1,
                'throughput_rps': 50,
                'concurrent_users': user_count
            }
        }

        # 保存场景配置
        with open('load_test_scenario.json', 'w', encoding='utf-8') as f:
            json.dump(scenario, f, ensure_ascii=False, indent=2)

        print(f"负载测试场景已保存到 load_test_scenario.json")
        return scenario


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AI主题分析应用测试数据生成工具')
    parser.add_argument('--base-url', default='http://localhost:8000', help='API基础URL')
    parser.add_argument('--themes', type=int, default=50, help='生成主题数量')
    parser.add_argument('--stocks', type=int, default=100, help='生成股票数量')
    parser.add_argument('--events', type=int, default=200, help='生成事件数量')
    parser.add_argument('--feed', type=int, default=300, help='生成情报流数量')
    parser.add_argument('--recap-days', type=int, default=30, help='生成复盘天数')
    parser.add_argument('--load-scenario', action='store_true', help='创建负载测试场景')
    parser.add_argument('--load-to-api', action='store_true', help='将数据加载到API')

    args = parser.parse_args()

    async with TestDataGenerator(args.base_url) as generator:
        counts = {
            'themes': args.themes,
            'stocks': args.stocks,
            'events': args.events,
            'feed': args.feed,
            'recap_days': args.recap_days
        }

        # 生成测试数据
        await generator.generate_all(counts)

        # 创建负载测试场景
        if args.load_scenario:
            generator.create_load_test_scenario()

        # 加载数据到API
        if args.load_to_api:
            print("\n开始加载数据到API...")
            print("=" * 60)

            # 这里可以添加实际的数据加载逻辑
            # 例如: await generator.load_data_to_api('/api/themes', themes_data)
            print("注意: 数据加载功能需要根据实际API接口实现")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)