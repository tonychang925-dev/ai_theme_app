#!/usr/bin/env python3
"""
AI主题分析应用 - 压力测试脚本
使用Locust进行性能压力测试
"""

import time
import random
from locust import HttpUser, task, between, events
from faker import Faker

fake = Faker(locale='zh_CN')


class AIThemeUser(HttpUser):
    """AI主题分析应用用户模拟"""

    wait_time = between(1, 3)  # 用户等待时间1-3秒

    def on_start(self):
        """用户启动时执行"""
        self.theme_ids = []
        self.stock_codes = ['000001', '000002', '000858', '600519', '300750']
        self.user_id = fake.uuid4()

        # 获取主题列表
        response = self.client.get("/api/themes?limit=10")
        if response.status_code == 200:
            data = response.json()
            if 'themes' in data:
                self.theme_ids = [theme['id'] for theme in data['themes'][:5]]

    @task(3)
    def get_themes(self):
        """获取主题列表"""
        params = {
            'limit': random.randint(5, 20),
            'page': random.randint(1, 5),
            'sort_by': random.choice(['heat', 'created_at', 'updated_at'])
        }

        with self.client.get("/api/themes", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取主题失败: {response.status_code}")

    @task(2)
    def get_theme_detail(self):
        """获取主题详情"""
        if not self.theme_ids:
            return

        theme_id = random.choice(self.theme_ids)
        with self.client.get(f"/api/themes/{theme_id}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取主题详情失败: {response.status_code}")

    @task(2)
    def get_intel_feed(self):
        """获取情报流"""
        params = {
            'limit': random.randint(10, 30),
            'type': random.choice(['all', 'news', 'event', 'theme_update']),
            'source': random.choice(['all', 'realtime', 'jyhf'])
        }

        with self.client.get("/api/intel/feed", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取情报流失败: {response.status_code}")

    @task(2)
    def get_stock_info(self):
        """获取股票信息"""
        stock_code = random.choice(self.stock_codes)
        with self.client.get(f"/api/stocks/{stock_code}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取股票信息失败: {response.status_code}")

    @task(1)
    def get_recap_daily(self):
        """获取每日复盘"""
        params = {
            'date': fake.date_between(start_date='-7d', end_date='today').strftime('%Y-%m-%d')
        }

        with self.client.get("/api/recap/daily", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取每日复盘失败: {response.status_code}")

    @task(1)
    def search_themes(self):
        """搜索主题"""
        search_terms = ['科技', '消费', '医药', '新能源', '金融', '人工智能']
        params = {
            'q': random.choice(search_terms),
            'limit': 10
        }

        with self.client.get("/api/themes/search", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"搜索主题失败: {response.status_code}")

    @task(1)
    def get_theme_heat(self):
        """获取主题热度"""
        if not self.theme_ids:
            return

        theme_id = random.choice(self.theme_ids)
        params = {
            'days': random.choice([1, 3, 7, 30])
        }

        with self.client.get(f"/api/themes/{theme_id}/heat", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取主题热度失败: {response.status_code}")


class AIEventUser(HttpUser):
    """AI事件处理用户模拟（高负载）"""

    wait_time = between(0.5, 1.5)

    def on_start(self):
        """用户启动时执行"""
        self.event_templates = [
            "公司发布新产品，预计将带动相关产业链发展",
            "政策出台支持产业发展，相关企业受益",
            "行业龙头业绩超预期，板块整体上涨",
            "技术创新突破，推动产业升级",
            "市场需求增长，供应紧张价格上涨"
        ]

    @task(5)
    def process_event(self):
        """处理AI事件（模拟高负载）"""
        event_content = random.choice(self.event_templates)

        payload = {
            'content': event_content,
            'source': 'test',
            'timestamp': int(time.time()),
            'metadata': {
                'test_user': True,
                'load_test': True
            }
        }

        with self.client.post("/api/events/process", json=payload, catch_response=True) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"处理事件失败: {response.status_code}")


class StreamingUser(HttpUser):
    """流式数据用户模拟（SSE连接）"""

    wait_time = between(5, 10)

    @task(3)
    def connect_sse(self):
        """连接SSE流"""
        # 模拟SSE连接，持续30秒
        params = {
            'channel': random.choice(['intel', 'theme_updates', 'market_alerts'])
        }

        start_time = time.time()
        try:
            with self.client.get("/api/stream/sse", params=params, stream=True, timeout=30, catch_response=True) as response:
                if response.status_code == 200:
                    # 读取一些数据
                    for _ in range(10):
                        if time.time() - start_time > 30:
                            break
                        time.sleep(1)
                    response.success()
                else:
                    response.failure(f"SSE连接失败: {response.status_code}")
        except Exception as e:
            response.failure(f"SSE连接异常: {str(e)}")


# 自定义事件监听器
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Locust初始化时执行"""
    print("=" * 60)
    print("AI主题分析应用 - 压力测试开始")
    print(f"目标主机: {environment.host}")
    print(f"用户类: {[user.__name__ for user in environment.user_classes]}")
    print("=" * 60)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时执行"""
    print(f"测试开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时执行"""
    print(f"测试结束: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    # 直接运行时的配置
    import sys
    print("请使用 locust 命令运行此脚本:")
    print("  locust -f ai_theme_test.py --host=http://localhost:8000")
    print("或指定用户类和数量:")
    print("  locust -f ai_theme_test.py --host=http://localhost:8000 --users=100 --spawn-rate=10 -t 10m")