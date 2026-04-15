# model_service/services/cached_event_extractor.py
"""
带缓存的AI事件提取器
集成Redis缓存，减少重复AI调用，提升性能
"""

import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio

from .event_extractor import AIEventExtractor

logger = logging.getLogger(__name__)


class CachedAIEventExtractor(AIEventExtractor):
    """带缓存的AI事件提取器"""

    def __init__(self, redis_client=None, cache_ttl: int = 3600, **kwargs):
        """
        初始化带缓存的提取器

        Args:
            redis_client: Redis客户端实例
            cache_ttl: 缓存过期时间（秒），默认1小时
            **kwargs: 传递给父类的参数
        """
        super().__init__(**kwargs)
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
        self.cache_enabled = redis_client is not None

        if self.cache_enabled:
            logger.info(f"✅ 启用Redis缓存，TTL: {cache_ttl}秒")
        else:
            logger.warning("⚠️  Redis客户端未提供，缓存功能禁用")

    def _generate_cache_key(self, news_data: Dict) -> str:
        """生成缓存键"""
        # 基于新闻内容生成哈希键
        title = str(news_data.get('title', ''))
        content = str(news_data.get('content', ''))

        # 使用标题和内容前500字符生成哈希
        content_for_hash = f"{title}:{content[:500]}"
        content_hash = hashlib.md5(content_for_hash.encode()).hexdigest()

        # 包含新闻ID以便调试
        news_id = news_data.get('news_id', 'unknown')

        return f"ai_event:{content_hash}:{news_id}"

    async def extract_event_with_cache(self, news_data: Dict) -> Dict[str, Any]:
        """
        带缓存的AI事件提取

        Args:
            news_data: 新闻数据

        Returns:
            事件提取结果，包含缓存信息
        """
        news_id = news_data.get('news_id', 'unknown')
        cache_key = self._generate_cache_key(news_data)

        # 检查缓存
        cached_result = None
        if self.cache_enabled:
            try:
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    cached_result = json.loads(cached_data)
                    logger.debug(f"📦 缓存命中: {news_id}")

                    # 添加缓存标记
                    cached_result['cached'] = True
                    cached_result['cache_key'] = cache_key
                    cached_result['cache_timestamp'] = datetime.now().isoformat()

                    return cached_result
            except Exception as e:
                logger.warning(f"⚠️  缓存读取失败: {e}")

        # 调用AI分析
        logger.info(f"🧠 AI分析（未缓存）: {news_id}")
        start_time = datetime.now()

        try:
            result = await super().extract_event(news_data)

            if result:
                # 添加处理时间信息
                processing_time = (datetime.now() - start_time).total_seconds()
                result['processing_time'] = processing_time
                result['cached'] = False
                result['cache_key'] = cache_key
                result['analyzed_at'] = datetime.now().isoformat()

                # 缓存成功的结果
                if self.cache_enabled and self._should_cache_result(result):
                    try:
                        await self.redis_client.setex(
                            cache_key,
                            self.cache_ttl,
                            json.dumps(result, ensure_ascii=False)
                        )
                        logger.debug(f"💾 缓存保存: {news_id}")
                    except Exception as e:
                        logger.warning(f"⚠️  缓存保存失败: {e}")

            return result

        except Exception as e:
            logger.error(f"❌ AI分析失败: {news_id} - {e}")
            return {
                "status": "error",
                "error": str(e),
                "news_id": news_id,
                "cached": False,
                "timestamp": datetime.now().isoformat()
            }

    def _should_cache_result(self, result: Dict) -> bool:
        """判断是否应该缓存结果"""
        if not result:
            return False

        # 只缓存成功的分析结果
        if result.get("status") != "success":
            return False

        # 检查置信度
        confidence = result.get("confidence", 0)
        if confidence < 0.3:  # 低置信度结果不缓存
            return False

        # 检查事件类型
        event_type = result.get("event_type", "")
        if not event_type or event_type == "其他":
            return False

        return True

    async def extract_event_batch_with_cache(self, news_items: List[Dict]) -> List[Dict]:
        """
        批量提取事件（带缓存）

        Args:
            news_items: 新闻数据列表

        Returns:
            事件提取结果列表
        """
        if not news_items:
            return []

        logger.info(f"🧠 批量AI分析: {len(news_items)}条新闻")

        results = []
        cached_count = 0
        ai_analysis_count = 0

        # 先检查缓存
        cache_keys = []
        for news_item in news_items:
            cache_key = self._generate_cache_key(news_item)
            cache_keys.append(cache_key)

        cached_results = {}
        if self.cache_enabled:
            try:
                # 批量获取缓存
                cache_values = await self.redis_client.mget(cache_keys)
                for i, cache_value in enumerate(cache_values):
                    if cache_value:
                        news_item = news_items[i]
                        news_id = news_item.get('news_id', f'item_{i}')

                        try:
                            cached_result = json.loads(cache_value)
                            cached_result['cached'] = True
                            cached_result['cache_key'] = cache_keys[i]
                            cached_result['cache_timestamp'] = datetime.now().isoformat()

                            cached_results[i] = cached_result
                            cached_count += 1
                            logger.debug(f"📦 批量缓存命中: {news_id}")
                        except Exception as e:
                            logger.warning(f"⚠️  缓存解析失败: {e}")
            except Exception as e:
                logger.warning(f"⚠️  批量缓存读取失败: {e}")

        # 处理需要AI分析的项目
        ai_tasks = []
        for i, news_item in enumerate(news_items):
            if i in cached_results:
                results.append(cached_results[i])
            else:
                # 创建AI分析任务
                task = asyncio.create_task(
                    self.extract_event_with_cache(news_item)
                )
                ai_tasks.append((i, task))
                ai_analysis_count += 1

        # 等待AI分析完成
        if ai_tasks:
            logger.info(f"🔍 需要AI分析: {ai_analysis_count}条")

            # 并发执行AI分析
            for i, task in ai_tasks:
                try:
                    result = await task
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ AI分析任务失败: {e}")
                    results.append({
                        "status": "error",
                        "error": str(e),
                        "news_id": news_items[i].get('news_id', f'item_{i}'),
                        "cached": False,
                        "timestamp": datetime.now().isoformat()
                    })

        # 确保结果顺序与输入一致
        sorted_results = []
        result_index = 0
        for i in range(len(news_items)):
            if i in cached_results:
                sorted_results.append(cached_results[i])
            else:
                if result_index < len(results):
                    sorted_results.append(results[result_index])
                    result_index += 1
                else:
                    sorted_results.append(None)

        logger.info(
            f"✅ 批量分析完成: 总计{len(news_items)}条, "
            f"缓存{cached_count}条, AI分析{ai_analysis_count}条"
        )

        return sorted_results

    async def clear_cache_for_news(self, news_data: Dict) -> bool:
        """清除指定新闻的缓存"""
        if not self.cache_enabled:
            return False

        cache_key = self._generate_cache_key(news_data)

        try:
            deleted = await self.redis_client.delete(cache_key)
            if deleted:
                logger.info(f"🗑️  清除缓存: {news_data.get('news_id', 'unknown')}")
            return deleted > 0
        except Exception as e:
            logger.error(f"❌ 清除缓存失败: {e}")
            return False

    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.cache_enabled:
            return {"cache_enabled": False}

        try:
            # 统计缓存键模式
            pattern = "ai_event:*"
            cache_keys = await self.redis_client.keys(pattern)

            return {
                "cache_enabled": True,
                "total_cached_items": len(cache_keys),
                "cache_ttl": self.cache_ttl,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ 获取缓存统计失败: {e}")
            return {
                "cache_enabled": True,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查，包含缓存状态"""
        base_health = await super().health_check()

        cache_health = {
            "cache_enabled": self.cache_enabled,
            "redis_connected": False,
            "cache_ttl": self.cache_ttl
        }

        if self.cache_enabled:
            try:
                # 测试Redis连接
                await self.redis_client.ping()
                cache_health["redis_connected"] = True

                # 获取缓存统计
                cache_stats = await self.get_cache_stats()
                cache_health.update(cache_stats)

            except Exception as e:
                cache_health["redis_error"] = str(e)
                logger.warning(f"⚠️  Redis健康检查失败: {e}")

        return {
            "base_health": base_health,
            "cache_health": cache_health,
            "timestamp": datetime.now().isoformat()
        }


# 工厂函数
def create_cached_extractor(redis_client=None, **kwargs) -> CachedAIEventExtractor:
    """创建带缓存的AI事件提取器"""
    return CachedAIEventExtractor(redis_client=redis_client, **kwargs)


# 测试代码
if __name__ == "__main__":
    import asyncio

    async def test_cached_extractor():
        """测试带缓存的提取器"""
        print("🧪 测试带缓存的AI事件提取器")

        try:
            # 创建Redis客户端（测试用）
            import redis.asyncio as redis
            redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)

            # 创建提取器
            extractor = create_cached_extractor(
                redis_client=redis_client,
                cache_ttl=300  # 5分钟测试缓存
            )

            print(f"✅ 创建带缓存提取器，缓存TTL: {extractor.cache_ttl}秒")

            # 健康检查
            health = await extractor.health_check()
            print(f"✅ 健康检查: {health}")

            if health["base_health"]:
                # 测试数据
                test_news = {
                    "news_id": "test_cache_1",
                    "title": "测试缓存功能",
                    "content": "这是一个测试新闻，用于验证缓存功能。"
                }

                print(f"\n📊 测试缓存功能...")

                # 第一次调用（应该调用AI）
                print("1. 第一次调用（应调用AI）...")
                result1 = await extractor.extract_event_with_cache(test_news)
                print(f"   结果: {result1.get('status', 'unknown')}, 缓存: {result1.get('cached', False)}")

                # 第二次调用（应该命中缓存）
                print("2. 第二次调用（应命中缓存）...")
                result2 = await extractor.extract_event_with_cache(test_news)
                print(f"   结果: {result2.get('status', 'unknown')}, 缓存: {result2.get('cached', False)}")

                # 批量测试
                print("\n📊 测试批量缓存功能...")
                batch_news = [
                    {
                        "news_id": "batch_test_1",
                        "title": "批量测试1",
                        "content": "批量测试内容1"
                    },
                    {
                        "news_id": "batch_test_2",
                        "title": "批量测试2",
                        "content": "批量测试内容2"
                    }
                ]

                batch_results = await extractor.extract_event_batch_with_cache(batch_news)
                print(f"   批量结果: {len(batch_results)}条")
                for i, result in enumerate(batch_results):
                    if result:
                        print(f"     新闻{i+1}: {result.get('status', 'unknown')}, 缓存: {result.get('cached', False)}")

                # 获取缓存统计
                cache_stats = await extractor.get_cache_stats()
                print(f"\n📈 缓存统计: {cache_stats}")

                # 清理测试缓存
                print("\n🗑️  清理测试缓存...")
                for news in [test_news] + batch_news:
                    await extractor.clear_cache_for_news(news)

            await redis_client.close()
            print("\n🎉 缓存提取器测试完成")

        except ImportError:
            print("⚠️  Redis客户端不可用，跳过缓存测试")
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(test_cached_extractor())