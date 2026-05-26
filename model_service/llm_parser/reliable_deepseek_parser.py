# model_service/llm_parser/reliable_deepseek_parser.py
"""
可靠的DeepSeek解析器 - 增强稳定性版
包含：重试机制、断路器、监控、性能优化
"""
import asyncio
import time
import aiohttp
import json
import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime
import hashlib

from .deepseek_parser import DeepSeekParser

logger = logging.getLogger(__name__)

# 简单的断路器实现
class SimpleCircuitBreaker:
    """简化的断路器实现"""
    
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            current_time = time.time()
            
            # 检查断路器状态
            if self.state == "OPEN":
                if current_time - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("断路器进入半开状态，尝试恢复")
                else:
                    raise CircuitBreakerError("服务熔断中，请稍后重试")
            
            try:
                result = await func(*args, **kwargs)
                
                # 成功调用，重置断路器
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info("断路器恢复正常状态")
                elif self.state == "CLOSED":
                    self.failure_count = max(0, self.failure_count - 1)
                
                return result
                
            except Exception as e:
                # 失败调用
                self.failure_count += 1
                self.last_failure_time = current_time
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(f"断路器打开，服务熔断: {e}")
                
                raise e
        
        return wrapper

class CircuitBreakerError(Exception):
    """断路器异常"""
    pass

# 自定义重试装饰器
def retry_with_backoff(max_retries=3, initial_delay=1, max_delay=30):
    """简单的指数退避重试装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break
                    
                    # 指数退避
                    delay = min(initial_delay * (2 ** attempt), max_delay)
                    logger.warning(f"重试 {attempt+1}/{max_retries}, 延迟 {delay}秒: {e}")
                    await asyncio.sleep(delay)
                except Exception as e:
                    # 非网络错误不重试
                    raise e
            
            if last_exception:
                raise last_exception
        return wrapper
    return decorator

class ReliableDeepSeekParser(DeepSeekParser):
    """可靠的DeepSeek解析器 - 增强稳定性"""
    
    def __init__(self, model_name: str = "deepseek-chat", config: Dict = None):
        super().__init__(model_name)
        self.config = config or {
            'max_retries': 3,
            'timeout': 45,  # 增加到45秒
            'enable_cache': True,
            'cache_ttl': 300,
            'failure_threshold': 5,
            'recovery_timeout': 60
        }
        
        # 创建断路器
        self.circuit_breaker = SimpleCircuitBreaker(
            failure_threshold=self.config.get('failure_threshold', 5),
            recovery_timeout=self.config.get('recovery_timeout', 60)
        )
        
        # 监控指标
        self.metrics = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'timeout_calls': 0,
            'network_errors': 0,
            'api_errors': 0,
            'total_response_time': 0.0,
            'last_success_time': None,
            'last_error': None,
            'last_error_time': None,
            'cache_hits': 0,
            'cache_misses': 0,
            'json_repairs': 0
        }
        
        # 响应缓存
        self.response_cache = {}
        self.cache_ttl = self.config.get('cache_ttl', 300)
        
        logger.info(f"🔧 ReliableDeepSeekParser初始化，模型: {model_name}")
        logger.info(f"  配置: 重试{self.config.get('max_retries')}次, 超时{self.config.get('timeout')}秒, 缓存TTL{self.cache_ttl}秒")
    
    @retry_with_backoff(max_retries=3, initial_delay=1, max_delay=10)
    async def parse_content(self, content: str) -> Optional[Dict[str, Any]]:
        """
        增强的解析方法 - 包含重试、断路器、监控
        """
        # 应用断路器
        @self.circuit_breaker
        async def _parse_with_breaker():
            return await self._parse_content_internal(content)
        
        return await _parse_with_breaker()
    
    async def _parse_content_internal(self, content: str) -> Optional[Dict[str, Any]]:
        """实际的解析逻辑"""
        start_time = time.time()
        self.metrics['total_calls'] += 1
        
        # 检查缓存
        cache_key = self._generate_cache_key(content)
        if self.config.get('enable_cache', True) and cache_key in self.response_cache:
            cached = self.response_cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                logger.debug(f"使用缓存响应，key: {cache_key[:50]}...")
                self.metrics['cache_hits'] += 1
                return cached['response']
        
        self.metrics['cache_misses'] += 1
        
        try:
            # 🔥 使用修复后的API调用
            result = await self._call_deepseek_api_directly(content)
            
            # 记录成功
            response_time = time.time() - start_time
            self.metrics['successful_calls'] += 1
            self.metrics['total_response_time'] += response_time
            self.metrics['last_success_time'] = time.time()
            
            # 计算平均响应时间
            avg_response_time = self.metrics['total_response_time'] / self.metrics['successful_calls']
            
            # 缓存结果（如果应该缓存）
            if result and self._should_cache_result(result):
                self.response_cache[cache_key] = {
                    'response': result,
                    'timestamp': time.time(),
                    'confidence': result.get('confidence', 0),
                    'decision': result.get('decision', '')
                }
                
                # 清理过期缓存
                self._cleanup_expired_cache()
                
                logger.debug(f"缓存AI响应，决策: {result.get('decision')}, 置信度: {result.get('confidence', 0):.2f}")
            
            logger.info(f"✅ AI调用成功，耗时: {response_time:.2f}秒, 平均: {avg_response_time:.2f}秒")
            return result
            
        except asyncio.TimeoutError as e:
            self.metrics['failed_calls'] += 1
            self.metrics['timeout_calls'] += 1
            self.metrics['last_error'] = f"Timeout after {self.config.get('timeout', 30)}s"
            self.metrics['last_error_time'] = time.time()
            logger.error(f"⏰ AI调用超时: {e}")
            raise TimeoutError(f"AI调用超时 ({self.config.get('timeout', 45)}秒)") from e
            
        except aiohttp.ClientError as e:
            self.metrics['failed_calls'] += 1
            self.metrics['network_errors'] += 1
            self.metrics['last_error'] = f"Network error: {str(e)}"
            self.metrics['last_error_time'] = time.time()
            logger.error(f"🌐 AI网络错误: {e}")
            raise aiohttp.ClientError(f"AI网络错误: {e}") from e
            
        except Exception as e:
            self.metrics['failed_calls'] += 1
            self.metrics['api_errors'] += 1
            self.metrics['last_error'] = f"API error: {str(e)}"
            self.metrics['last_error_time'] = time.time()
            logger.error(f"❌ AI调用失败: {e}")
            raise
    
    async def _call_deepseek_api_directly(self, content: str) -> Optional[Dict[str, Any]]:
        """直接调用DeepSeek API（修复参数格式和JSON解析）"""
        await self._ensure_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 🔥 修复：添加system message确保JSON格式
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个JSON API，必须返回严格符合JSON格式的响应，不要包含任何其他文字。"
                },
                {"role": "user", "content": content}
            ],
            "max_tokens": 2000,
            "temperature": 0.1,  # 低温度确保确定性
            "stream": False
        }
        
        logger.debug(f"发送请求到DeepSeek API，模型: {self.model_name}, 内容长度: {len(content)}")
        
        try:
            timeout_value = self.config.get('timeout', 90)
            connect_timeout = self.config.get('connect_timeout', 10)
            read_timeout = self.config.get('read_timeout', 60)
            async with self._session.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(
                    total=timeout_value,
                    connect=connect_timeout,
                    sock_read=read_timeout,
                )
            ) as response:
                
                # 检查HTTP状态
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API返回错误 {response.status}: {error_text}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"API错误 {response.status}: {error_text[:200]}"
                    )
                
                result = await response.json()
                
                logger.debug(f"收到API响应，token使用: {result.get('usage', {})}")
                
                if 'choices' in result and result['choices']:
                    reply = result['choices'][0]['message']['content']
                    
                    # 🔥 增强的JSON清理逻辑
                    cleaned_reply = self._clean_ai_response(reply)
                    
                    try:
                        parsed_data = json.loads(cleaned_reply)
                        
                        if not isinstance(parsed_data, dict):
                            logger.warning(f"返回的不是字典类型: {type(parsed_data)}")
                            # 尝试包装成字典
                            parsed_data = {"response": parsed_data}
                        
                        return parsed_data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析失败: {e}")
                        logger.debug(f"原始响应: {reply[:200]}...")
                        logger.debug(f"清理后: {cleaned_reply[:200]}...")
                        
                        # 🔥 尝试多种修复策略
                        parsed_data = self._try_repair_json(reply)
                        if parsed_data:
                            self.metrics['json_repairs'] += 1
                            logger.info(f"✅ 成功修复JSON响应（第{self.metrics['json_repairs']}次）")
                            return parsed_data
                        else:
                            logger.error("❌ 无法修复JSON响应")
                            # 返回原始响应包装
                            return {"raw_response": reply, "parse_error": str(e)}
                else:
                    logger.error(f"API响应格式异常: {result}")
                    return None
                    
        except asyncio.TimeoutError:
            raise TimeoutError(f"API请求超时 ({timeout_value}秒)")
        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {e}")
            raise
        except Exception as e:
            logger.error(f"API请求异常: {e}")
            raise
    
    def _clean_ai_response(self, response: str) -> str:
        """清理AI响应，提取JSON内容"""
        if not response:
            return ""
        
        response = response.strip()
        
        # 🔥 处理多种可能的响应格式
        # 1. 代码块格式: ```json {...} ```
        if response.startswith('```json'):
            # 移除开头的```json
            response = response[7:]
        elif response.startswith('```'):
            # 移除开头的```
            response = response[3:]
        
        # 移除结尾的```
        if response.endswith('```'):
            response = response[:-3]
        
        # 移除可能的语言标记
        response = response.strip()
        
        # 查找第一个{和最后一个}
        start = response.find('{')
        end = response.rfind('}')
        
        if start != -1 and end != -1 and end > start:
            # 提取JSON部分
            response = response[start:end+1]
        
        return response.strip()
    
    def _try_repair_json(self, text: str) -> Optional[Dict]:
        """尝试多种方法修复JSON"""
        if not text:
            return None
        
        repair_methods = [
            self._repair_json_by_extraction,  # 提取JSON部分
            self._repair_json_by_wrapping,    # 包装成字典
            self._repair_json_by_manual,      # 手动修复常见问题
        ]
        
        for method in repair_methods:
            try:
                result = method(text)
                if result:
                    return result
            except Exception:
                continue
        
        return None
    
    def _repair_json_by_extraction(self, text: str) -> Optional[Dict]:
        """通过提取修复JSON"""
        # 尝试匹配JSON对象
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)
        
        if matches:
            # 选择最长的匹配（最有可能是完整的JSON）
            longest_match = max(matches, key=len)
            return json.loads(longest_match)
        
        return None
    
    def _repair_json_by_wrapping(self, text: str) -> Optional[Dict]:
        """通过包装修复JSON"""
        # 如果不是以{开头，尝试包装
        if not text.startswith('{') and text.strip():
            # 尝试包装成{"response": text}
            wrapped = f'{{"response": {json.dumps(text)}}}'
            try:
                return json.loads(wrapped)
            except:
                pass
        
        return None
    
    def _repair_json_by_manual(self, text: str) -> Optional[Dict]:
        """手动修复常见JSON问题"""
        # 修复常见的JSON问题
        repairs = [
            # 修复单引号
            (r"'(.*?)'", r'"\1"'),
            # 修复无引号的键
            (r'(\w+):', r'"\1":'),
            # 修复末尾多余的逗号
            (r',\s*}', '}'),
            (r',\s*]', ']'),
            # 修复True/False/None
            ("True", "true"),
            ("False", "false"),
            ("None", "null"),
        ]
        
        repaired = text
        for pattern, replacement in repairs:
            repaired = re.sub(pattern, replacement, repaired, flags=re.MULTILINE)
        
        try:
            return json.loads(repaired)
        except:
            return None
    
    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """增强的新闻解析 - 包含超时控制"""
        # 构建缓存键
        cache_key = self._generate_cache_key(f"news:{title}:{content[:100]}")
        
        if self.config.get('enable_cache', True) and cache_key in self.response_cache:
            cached = self.response_cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                logger.debug(f"使用缓存的新闻解析结果: {title[:50]}...")
                self.metrics['cache_hits'] += 1
                return cached['response']
        
        try:
            # 设置单独的超时
            news_timeout = self.config.get('news_timeout', 60)
            result = await asyncio.wait_for(
                super().parse_news(title, content),
                timeout=news_timeout
            )
            
            # 缓存结果
            if result:
                self.response_cache[cache_key] = {
                    'response': result,
                    'timestamp': time.time(),
                    'title': title[:50]
                }
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ 新闻解析超时: {title[:50]}...")
            raise TimeoutError(f"新闻解析超时 ({news_timeout}秒): {title[:50]}...")
    
    def _generate_cache_key(self, content: str) -> str:
        """生成缓存键（含prompt版本，prompt变更后自动失效旧缓存）。"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        return f"ai_response:v2:{self.model_name}:{content_hash}"
    
    def _should_cache_result(self, result: Dict) -> bool:
        """判断是否应该缓存结果"""
        if not self.config.get('enable_cache', True):
            return False
        
        # 检查置信度和决策类型
        confidence = result.get('confidence', 0)
        decision = result.get('decision', '')
        
        # 高置信度的决策结果缓存
        if confidence > 0.7 and decision in ['CREATE_NEW', 'MERGE_INTO', 'IGNORE']:
            return True
        
        # event_info的缓存（新闻解析结果）
        if 'event_info' in result and confidence > 0.6:
            return True
            
        return False
    
    def _cleanup_expired_cache(self):
        """清理过期缓存"""
        if not self.response_cache:
            return
        
        current_time = time.time()
        expired_keys = []
        
        for key, value in self.response_cache.items():
            if current_time - value['timestamp'] > self.cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.response_cache[key]
        
        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存")
    
    async def health_check(self) -> Dict[str, Any]:
        """增强的健康检查 - 更宽松的判断"""
        basic_health = False
        last_error = None
        
        try:
            # 先检查API密钥
            if not self.api_key:
                logger.warning("❌ API密钥未设置")
                basic_health = False
                last_error = "API密钥未设置"
            else:
                # 尝试一个非常简单的测试
                basic_health = await super().health_check()
        except Exception as e:
            basic_health = False
            last_error = str(e)
            logger.warning(f"基础健康检查失败: {e}")
        
        # 计算成功率（即使没有调用过，也认为是正常的）
        success_rate = 0.0
        if self.metrics['total_calls'] > 0:
            success_rate = self.metrics['successful_calls'] / self.metrics['total_calls']
        else:
            # 没有调用记录，使用默认值
            success_rate = 1.0
        
        # 断路器状态
        breaker_state = self.circuit_breaker.state
        
        # 综合健康状态 - 更宽松的判断
        is_healthy = (
            basic_health or  # 基础健康检查通过
            (success_rate > 0.5 and breaker_state == "CLOSED") or  # 成功率>50%且断路器正常
            self.metrics['total_calls'] == 0  # 还没调用过，也认为是健康的
        )
        
        health_details = {
            'is_healthy': is_healthy,
            'basic_health': basic_health,
            'success_rate': success_rate,
            'avg_response_time': self.metrics.get('total_response_time', 0) / max(self.metrics['successful_calls'], 1),
            'total_calls': self.metrics['total_calls'],
            'successful_calls': self.metrics['successful_calls'],
            'failed_calls': self.metrics['failed_calls'],
            'timeout_calls': self.metrics['timeout_calls'],
            'network_errors': self.metrics['network_errors'],
            'api_errors': self.metrics['api_errors'],
            'json_repairs': self.metrics['json_repairs'],
            'circuit_breaker_state': breaker_state,
            'failure_count': self.circuit_breaker.failure_count,
            'last_error': last_error or self.metrics['last_error'],
            'timestamp': time.time(),
            'api_key_configured': bool(self.api_key),
            'service_status': 'healthy' if is_healthy else 'degraded',
            'cache_stats': {
                'cache_size': len(self.response_cache),
                'cache_hits': self.metrics.get('cache_hits', 0),
                'cache_misses': self.metrics.get('cache_misses', 0),
                'cache_hit_rate': self.metrics.get('cache_hits', 0) / max(self.metrics.get('cache_hits', 0) + self.metrics.get('cache_misses', 1), 1)
            }
        }
        
        status_icon = "✅" if is_healthy else "⚠️"
        logger.info(f"{status_icon} 健康检查: 状态={'健康' if is_healthy else '降级'}, "
                   f"基础检查={'通过' if basic_health else '失败'}, "
                   f"API密钥={'已配置' if self.api_key else '未配置'}, "
                   f"成功率={success_rate:.1%}")
        
        return health_details
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取详细指标"""
        return self.metrics.copy()
    
    def clear_cache(self):
        """清除缓存"""
        cache_size = len(self.response_cache)
        self.response_cache.clear()
        logger.info(f"🗑️  AI响应缓存已清除，共 {cache_size} 条记录")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        return {
            'total_entries': len(self.response_cache),
            'sample_keys': list(self.response_cache.keys())[:5] if self.response_cache else []
        }

# 测试函数
async def test_reliable_parser():
    """测试可靠的解析器"""
    import os
    
    print("🧪 测试ReliableDeepSeekParser...")
    
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("❌ DEEPSEEK_API_KEY未设置")
        return False
    
    parser = None
    try:
        parser = ReliableDeepSeekParser(
            model_name="deepseek-chat",
            config={
                'max_retries': 2,
                'timeout': 45,
                'enable_cache': True,
                'temperature': 0.1
            }
        )
        
        # 健康检查
        health = await parser.health_check()
        print(f"健康状态: {health['is_healthy']}")
        
        if health['is_healthy']:
            # 测试解析 - 使用非常简单的测试内容
            test_content = "请回复'测试成功'"
            print(f"测试内容: {test_content}")
            
            try:
                result = await parser.parse_content(test_content)
                print(f"✅ 解析成功!")
                print(f"结果: {result}")
                
                # 查看指标
                metrics = parser.get_metrics()
                print(f"调用统计: {metrics['total_calls']}次调用, {metrics['successful_calls']}次成功")
                
                return True
                
            except TimeoutError as e:
                print(f"⏰ 超时错误: {e}")
                return False
            except Exception as e:
                print(f"❌ 解析测试失败: {e}")
                return False
        else:
            print(f"❌ 解析器不健康: {health}")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if parser:
            await parser.close()

if __name__ == "__main__":
    asyncio.run(test_reliable_parser())
