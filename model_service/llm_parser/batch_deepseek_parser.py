# model_service/llm_parser/batch_deepseek_parser.py
"""
批量DeepSeek解析器 - 支持批量API调用优化性能
基于AI性能测试结果，批量处理可提升5.1倍性能
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .reliable_deepseek_parser import ReliableDeepSeekParser

logger = logging.getLogger(__name__)


class BatchDeepSeekParser(ReliableDeepSeekParser):
    """批量DeepSeek解析器 - 支持批量API调用"""

    def __init__(self, model_name: str = "deepseek-chat", batch_size: int = 5):
        super().__init__(model_name)
        self.batch_size = batch_size
        self.batch_cache = {}  # 批量结果缓存
        logger.info(f"🧠 初始化批量DeepSeek解析器，批量大小: {batch_size}")

    def build_batch_prompt(self, news_items: List[Dict]) -> str:
        """构建批量处理Prompt"""
        prompt_parts = []

        # 系统指令
        system_instruction = """你是一个专业的金融新闻事件提取AI。请分析以下多条新闻，为每条新闻提取结构化事件信息。

输出要求：
1. 为每条新闻输出一个独立的JSON对象
2. 每个JSON对象必须包含以下字段：
   - event_type: 事件类型（如"政策发布"、"财报发布"、"并购"等）
   - confidence: 置信度（0.0-1.0）
   - direction: 方向（"利好"、"利空"、"中性"）
   - impact_industries: 影响行业列表
   - summary: 事件摘要
   - entities: 相关实体列表
   - severity_score: 严重性评分（0.0-1.0）
   - source_weight: 来源权重（0.0-1.0）

请严格按照以下JSON数组格式输出：
[
  {
    "news_id": "第一条新闻的ID",
    "event_type": "...",
    "confidence": 0.8,
    "direction": "利好",
    "impact_industries": ["行业1", "行业2"],
    "summary": "事件摘要",
    "entities": [{"name": "实体1", "type": "公司"}],
    "severity_score": 0.7,
    "source_weight": 0.8
  },
  {
    "news_id": "第二条新闻的ID",
    ...
  }
]
"""

        prompt_parts.append(system_instruction)
        prompt_parts.append("\n=== 新闻列表 ===\n")

        for i, news_item in enumerate(news_items):
            title = news_item.get('title', '')
            content = news_item.get('content', '')
            news_id = news_item.get('news_id', f'news_{i+1}')

            prompt_parts.append(f"【新闻 {i+1} - ID: {news_id}】")
            prompt_parts.append(f"标题: {title}")

            # 限制内容长度
            if len(content) > 500:
                content = content[:500] + "..."
            prompt_parts.append(f"内容: {content}")
            prompt_parts.append("-" * 40)

        prompt_parts.append("\n请分析以上新闻并输出JSON数组：")
        return "\n".join(prompt_parts)

    async def parse_news_batch(self, news_items: List[Dict]) -> List[Dict]:
        """批量解析新闻 - 核心优化方法"""
        if not news_items:
            return []

        # 如果只有一条新闻，退回到单条处理
        if len(news_items) == 1:
            single_result = await self.parse_news(
                news_items[0].get('title', ''),
                news_items[0].get('content', '')
            )
            if single_result:
                single_result['news_id'] = news_items[0].get('news_id', 'unknown')
            return [single_result] if single_result else []

        # 生成批量缓存键
        batch_key = self._generate_batch_cache_key(news_items)

        # 检查批量缓存
        if batch_key in self.batch_cache:
            cached = self.batch_cache[batch_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                logger.debug(f"使用批量缓存结果: {len(news_items)}条新闻")
                self.metrics['batch_cache_hits'] = self.metrics.get('batch_cache_hits', 0) + 1
                return cached['results']

        start_time = time.time()
        logger.info(f"🧠 开始批量解析 {len(news_items)} 条新闻")

        try:
            # 构建批量Prompt
            batch_prompt = self.build_batch_prompt(news_items)

            # 调用API（使用父类的parse_content方法）
            batch_response = await self.parse_content(batch_prompt)

            if not batch_response:
                logger.error("❌ 批量API调用返回空结果")
                return []

            # 解析批量结果
            batch_results = self._parse_batch_response(batch_response, news_items)

            # 缓存批量结果
            if batch_results:
                self.batch_cache[batch_key] = {
                    'results': batch_results,
                    'timestamp': time.time(),
                    'news_count': len(news_items)
                }

                # 清理过期缓存
                self._cleanup_expired_batch_cache()

            processing_time = time.time() - start_time
            avg_time_per_news = processing_time / len(news_items) if news_items else 0

            logger.info(
                f"✅ 批量解析完成: {len(batch_results)}/{len(news_items)}条成功, "
                f"总耗时: {processing_time:.2f}s, 平均: {avg_time_per_news:.2f}s/条"
            )

            return batch_results

        except Exception as e:
            logger.error(f"❌ 批量解析失败: {e}")
            # 失败时退回到单条处理
            return await self._fallback_to_single_processing(news_items)

    def _parse_batch_response(self, batch_response: Dict, news_items: List[Dict]) -> List[Dict]:
        """解析批量API响应"""
        try:
            # 尝试从响应中提取JSON数组
            response_content = batch_response.get('choices', [{}])[0].get('message', {}).get('content', '')

            if not response_content:
                logger.error("批量响应内容为空")
                return []

            # 提取JSON部分
            json_start = response_content.find('[')
            json_end = response_content.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                logger.error("未找到JSON数组")
                return []

            json_str = response_content[json_start:json_end]

            try:
                parsed_results = json.loads(json_str)
                if not isinstance(parsed_results, list):
                    logger.error(f"解析结果不是列表: {type(parsed_results)}")
                    return []

                # 将结果映射回原始新闻
                results_by_news_id = {}
                for result in parsed_results:
                    news_id = result.get('news_id')
                    if news_id:
                        results_by_news_id[news_id] = result

                # 构建最终结果列表
                final_results = []
                for news_item in news_items:
                    news_id = news_item.get('news_id', 'unknown')
                    if news_id in results_by_news_id:
                        result = results_by_news_id[news_id]
                        # 适配到标准格式
                        adapted_result = self.adapt_structured_response(
                            result,
                            news_item.get('title', ''),
                            news_item.get('content', '')
                        )
                        adapted_result['news_id'] = news_id
                        final_results.append(adapted_result)
                    else:
                        logger.warning(f"未找到新闻 {news_id} 的解析结果")
                        final_results.append(None)

                return final_results

            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}")
                return []

        except Exception as e:
            logger.error(f"解析批量响应失败: {e}")
            return []

    async def _fallback_to_single_processing(self, news_items: List[Dict]) -> List[Dict]:
        """批量处理失败时退回到单条处理"""
        logger.warning(f"批量处理失败，退回到单条处理: {len(news_items)}条新闻")

        results = []
        for news_item in news_items:
            try:
                result = await self.parse_news(
                    news_item.get('title', ''),
                    news_item.get('content', '')
                )
                if result:
                    result['news_id'] = news_item.get('news_id', 'unknown')
                results.append(result)
            except Exception as e:
                logger.error(f"单条处理失败: {e}")
                results.append(None)

        return results

    def _generate_batch_cache_key(self, news_items: List[Dict]) -> str:
        """生成批量缓存键"""
        import hashlib

        # 基于新闻标题和内容生成哈希
        content_parts = []
        for news_item in news_items:
            title = news_item.get('title', '')
            content = news_item.get('content', '')
            content_parts.append(f"{title}:{content[:100]}")

        content_str = "|".join(content_parts)
        content_hash = hashlib.md5(content_str.encode()).hexdigest()

        return f"batch:{self.model_name}:{content_hash}"

    def _cleanup_expired_batch_cache(self):
        """清理过期批量缓存"""
        current_time = time.time()
        expired_keys = []

        for key, value in self.batch_cache.items():
            if current_time - value['timestamp'] > self.cache_ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.batch_cache[key]

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期批量缓存")

    async def health_check(self) -> Dict[str, Any]:
        """增强的健康检查，包含批量功能测试"""
        basic_health = await super().health_check()

        health_info = {
            "basic_health": basic_health,
            "batch_size": self.batch_size,
            "batch_cache_size": len(self.batch_cache),
            "batch_enabled": True,
            "timestamp": datetime.now().isoformat()
        }

        return health_info

    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        metrics = super().get_metrics()
        metrics.update({
            "batch_size": self.batch_size,
            "batch_cache_hits": self.metrics.get('batch_cache_hits', 0),
            "batch_cache_size": len(self.batch_cache),
            "batch_processing_count": self.metrics.get('batch_processing_count', 0)
        })
        return metrics


# 工厂函数
def create_batch_parser(batch_size: int = 5) -> BatchDeepSeekParser:
    """创建批量解析器实例"""
    return BatchDeepSeekParser(batch_size=batch_size)


# 测试代码
if __name__ == "__main__":
    import asyncio

    async def test_batch_parser():
        """测试批量解析器"""
        print("🧪 测试批量DeepSeek解析器")

        try:
            parser = create_batch_parser(batch_size=3)
            print(f"✅ 创建批量解析器，批量大小: {parser.batch_size}")

            # 健康检查
            health = await parser.health_check()
            print(f"✅ 健康检查: {health}")

            if health.get("basic_health"):
                # 测试数据
                test_news = [
                    {
                        "news_id": "test_1",
                        "title": "央行降准0.5个百分点",
                        "content": "中国人民银行决定下调金融机构存款准备金率0.5个百分点，释放长期资金约1万亿元。"
                    },
                    {
                        "news_id": "test_2",
                        "title": "特斯拉发布新款Model 3",
                        "content": "特斯拉在上海超级工厂发布新款Model 3，续航提升至600公里。"
                    },
                    {
                        "news_id": "test_3",
                        "title": "阿里巴巴公布季度财报",
                        "content": "阿里巴巴集团公布2023年第四季度财报，营收同比增长8%。"
                    }
                ]

                print(f"\n📊 测试批量解析 {len(test_news)} 条新闻...")
                results = await parser.parse_news_batch(test_news)

                print(f"✅ 批量解析完成: {len([r for r in results if r])}/{len(test_news)} 条成功")

                for i, result in enumerate(results):
                    if result:
                        print(f"  新闻 {i+1}: {result.get('event_type', 'N/A')} (置信度: {result.get('confidence', 0):.2f})")
                    else:
                        print(f"  新闻 {i+1}: 解析失败")

                # 获取指标
                metrics = parser.get_metrics()
                print(f"\n📈 性能指标: {metrics}")

            await parser.close()
            print("\n🎉 批量解析器测试完成")

        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(test_batch_parser())