"""
AI Theme App - Locust性能测试脚本
用于模拟用户行为，测试系统性能
"""

from locust import HttpUser, task, between, TaskSet, events
import random
import json
import time
from datetime import datetime, timedelta

# 测试数据
TEST_THEMES = [
    "人工智能", "大数据", "云计算", "区块链", "物联网",
    "5G通信", "新能源汽车", "生物医药", "半导体", "金融科技"
]

TEST_STOCKS = [
    {"code": "000001", "name": "平安银行"},
    {"code": "000002", "name": "万科A"},
    {"code": "000858", "name": "五粮液"},
    {"code": "002415", "name": "海康威视"},
    {"code": "300750", "name": "宁德时代"}
]

NEWS_KEYWORDS = [
    "财报", "业绩", "增长", "下跌", "收购",
    "合作", "创新", "政策", "市场", "投资"
]


class ThemeAnalysisTasks(TaskSet):
    """主题分析相关任务"""

    @task(3)
    def get_themes(self):
        """获取主题列表"""
        with self.client.get("/api/themes", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取主题列表失败: {response.status_code}")

    @task(2)
    def analyze_theme(self):
        """分析特定主题"""
        theme = random.choice(TEST_THEMES)
        payload = {
            "theme": theme,
            "time_range": "7d",
            "analysis_depth": "medium"
        }
        with self.client.post("/api/themes/analyze",
                             json=payload,
                             catch_response=True) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"主题分析失败: {response.status_code}")

    @task(1)
    def get_theme_details(self):
        """获取主题详情"""
        theme = random.choice(TEST_THEMES)
        with self.client.get(f"/api/themes/{theme}",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取主题详情失败: {response.status_code}")


class NewsStreamTasks(TaskSet):
    """新闻流处理相关任务"""

    @task(3)
    def get_news_stream(self):
        """获取新闻流"""
        params = {
            "limit": 20,
            "offset": 0,
            "category": random.choice(["all", "financial", "tech", "market"])
        }
        with self.client.get("/api/news/stream",
                            params=params,
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取新闻流失败: {response.status_code}")

    @task(2)
    def search_news(self):
        """搜索新闻"""
        keyword = random.choice(NEWS_KEYWORDS)
        payload = {
            "keyword": keyword,
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": datetime.now().strftime("%Y-%m-%d")
        }
        with self.client.post("/api/news/search",
                             json=payload,
                             catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"搜索新闻失败: {response.status_code}")

    @task(1)
    def analyze_news_sentiment(self):
        """分析新闻情感"""
        news_id = random.randint(1, 1000)
        with self.client.get(f"/api/news/{news_id}/sentiment",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"分析新闻情感失败: {response.status_code}")


class MarketAnalysisTasks(TaskSet):
    """市场分析相关任务"""

    @task(3)
    def get_market_indicators(self):
        """获取市场指标"""
        with self.client.get("/api/market/indicators",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取市场指标失败: {response.status_code}")

    @task(2)
    def get_stock_analysis(self):
        """获取股票分析"""
        stock = random.choice(TEST_STOCKS)
        with self.client.get(f"/api/stocks/{stock['code']}/analysis",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取股票分析失败: {response.status_code}")

    @task(1)
    def get_abnormal_signals(self):
        """获取异常信号"""
        params = {
            "signal_type": random.choice(["price", "volume", "sentiment"]),
            "threshold": 0.8
        }
        with self.client.get("/api/signals/abnormal",
                            params=params,
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取异常信号失败: {response.status_code}")


class AIThemeAppUser(HttpUser):
    """
    AI主题分析应用用户模拟
    模拟真实用户行为模式
    """

    # 用户思考时间：1-3秒
    wait_time = between(1, 3)

    # 任务权重分配
    tasks = {
        ThemeAnalysisTasks: 4,      # 40% 主题分析
        NewsStreamTasks: 3,         # 30% 新闻流处理
        MarketAnalysisTasks: 3      # 30% 市场分析
    }

    def on_start(self):
        """用户登录"""
        self.login()

    def on_stop(self):
        """用户登出"""
        self.logout()

    def login(self):
        """模拟用户登录"""
        payload = {
            "username": f"test_user_{random.randint(1, 1000)}",
            "password": "test_password"
        }
        with self.client.post("/api/auth/login",
                             json=payload,
                             catch_response=True) as response:
            if response.status_code == 200:
                # 保存token
                data = response.json()
                self.client.headers.update({
                    "Authorization": f"Bearer {data.get('token', '')}"
                })
                response.success()
            else:
                response.failure(f"登录失败: {response.status_code}")

    def logout(self):
        """模拟用户登出"""
        with self.client.post("/api/auth/logout",
                             catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"登出失败: {response.status_code}")


# 自定义事件监听器
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """请求事件监听器"""
    if exception:
        print(f"请求失败: {name}, 异常: {exception}")
    else:
        print(f"请求成功: {name}, 响应时间: {response_time}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始事件"""
    print("=" * 50)
    print("性能测试开始")
    print(f"目标主机: {environment.host}")
    print(f"用户数量: {environment.runner.user_count}")
    print("=" * 50)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束事件"""
    print("=" * 50)
    print("性能测试结束")
    print("=" * 50)


# 自定义统计收集器
class CustomStatsCollector:
    """自定义统计收集器"""

    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "failed_requests": 0,
            "total_response_time": 0,
            "endpoint_stats": {}
        }

    def collect_request(self, request_type, name, response_time, success):
        """收集请求统计"""
        self.stats["total_requests"] += 1
        self.stats["total_response_time"] += response_time

        if not success:
            self.stats["failed_requests"] += 1

        if name not in self.stats["endpoint_stats"]:
            self.stats["endpoint_stats"][name] = {
                "count": 0,
                "total_time": 0,
                "failures": 0
            }

        self.stats["endpoint_stats"][name]["count"] += 1
        self.stats["endpoint_stats"][name]["total_time"] += response_time
        if not success:
            self.stats["endpoint_stats"][name]["failures"] += 1

    def get_stats(self):
        """获取统计信息"""
        stats = self.stats.copy()
        if stats["total_requests"] > 0:
            stats["avg_response_time"] = stats["total_response_time"] / stats["total_requests"]
            stats["failure_rate"] = stats["failed_requests"] / stats["total_requests"]

        # 计算每个端点的平均响应时间
        for endpoint, data in stats["endpoint_stats"].items():
            if data["count"] > 0:
                data["avg_response_time"] = data["total_time"] / data["count"]
                data["failure_rate"] = data["failures"] / data["count"]

        return stats


# 全局统计收集器
stats_collector = CustomStatsCollector()


@events.request.add_listener
def collect_stats(request_type, name, response_time, response_length, exception, **kwargs):
    """收集统计信息"""
    success = exception is None
    stats_collector.collect_request(request_type, name, response_time, success)


@events.test_stop.add_listener
def print_final_stats(environment, **kwargs):
    """打印最终统计信息"""
    stats = stats_collector.get_stats()

    print("\n" + "=" * 50)
    print("性能测试统计摘要")
    print("=" * 50)
    print(f"总请求数: {stats['total_requests']}")
    print(f"失败请求数: {stats['failed_requests']}")
    print(f"失败率: {stats.get('failure_rate', 0) * 100:.2f}%")
    print(f"平均响应时间: {stats.get('avg_response_time', 0):.2f}ms")

    print("\n端点性能统计:")
    print("-" * 50)
    for endpoint, data in stats["endpoint_stats"].items():
        print(f"{endpoint}:")
        print(f"  请求数: {data['count']}")
        print(f"  平均响应时间: {data.get('avg_response_time', 0):.2f}ms")
        print(f"  失败率: {data.get('failure_rate', 0) * 100:.2f}%")

    print("=" * 50)


if __name__ == "__main__":
    """
    命令行直接运行测试
    用法: python locustfile.py --host=http://localhost:8000
    """
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--run":
        from locust import runners
        from locust.env import Environment

        # 设置测试环境
        host = "http://localhost:8000"
        if len(sys.argv) > 2:
            host = sys.argv[2]

        env = Environment(user_classes=[AIThemeAppUser], host=host)
        runner = env.create_local_runner()

        # 启动测试
        print(f"开始性能测试，目标: {host}")
        runner.start(100, spawn_rate=10)

        # 运行5分钟
        import time
        time.sleep(300)

        # 停止测试
        runner.stop()

        # 生成报告
        stats = stats_collector.get_stats()
        print(f"测试完成，总请求数: {stats['total_requests']}")