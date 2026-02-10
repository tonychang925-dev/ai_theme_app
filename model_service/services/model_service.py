"""
Model Service - 独立服务，提供AI事件提取功能
仿照NewsCrawlerService的设计模式
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback

logger = logging.getLogger(__name__)


class ModelService:
    """Model Service - 提供AI事件提取功能"""
    
    def __init__(self):
        """
        初始化Model Service
        """
        self.event_extractor = None
        self.mock_extractor = None
        self.initialized = False
        
        try:
            # 1. 初始化真实AI事件提取器
            self._init_real_extractor()
            
            # 2. 初始化模拟事件提取器（用于测试/备选）
            self._init_mock_extractor()
            
            self.initialized = True
            logger.info("🧠 ModelService初始化成功")
            
        except Exception as e:
            logger.error(f"❌ ModelService初始化失败: {e}")
            self.initialized = False
        
        # 服务元数据
        self.service_metadata = {
            "service": "ModelService",
            "version": "1.0.0",
            "description": "基于DeepSeek的AI事件提取服务",
            "features": ["ai_event_extraction", "mock_extraction", "batch_processing"],
            "initialized_at": datetime.now().isoformat(),
            "initialized": self.initialized,
            "has_real_extractor": self.event_extractor is not None,
            "has_mock_extractor": self.mock_extractor is not None
        }
    
    def _init_real_extractor(self):
        """初始化真实AI事件提取器"""
        try:
            from model_service.services.event_extractor import AIEventExtractor
            
            self.event_extractor = AIEventExtractor()
            logger.info("✅ AI事件提取器初始化成功")
            
        except ImportError as e:
            logger.warning(f"⚠️  无法导入AI事件提取器: {e}")
            logger.info("💡 将使用模拟提取模式运行")
            self.event_extractor = None
        except Exception as e:
            logger.error(f"❌ AI事件提取器初始化失败: {e}")
            self.event_extractor = None
    
    def _init_mock_extractor(self):
        """初始化模拟事件提取器"""
        try:
            from model_service.services.event_extractor import MockEventExtractor
            self.mock_extractor = MockEventExtractor()
            logger.info("✅ 模拟事件提取器初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️  无法导入模拟事件提取器: {e}")
            self.mock_extractor = None
    
    async def extract_event(self, news_data: Dict) -> Dict[str, Any]:
        """
        提取事件 - 主接口
        
        Args:
            news_data: 新闻数据，包含title、content、news_id等
            
        Returns:
            事件提取结果
        """
        operation = "extract_event"
        
        try:
            news_id = news_data.get('news_id', 'unknown')
            logger.info(f"🧠 开始AI事件提取: {news_id}")
            
            if not self.event_extractor:
                return self._create_error_response(
                    "AI事件提取器未初始化", 
                    operation,
                    "请检查DeepSeek API配置"
                )
            
            # 执行事件提取
            event_result = await self.event_extractor.extract_event(news_data)
            
            if not event_result:
                return self._create_error_response(
                    "AI返回空结果", 
                    operation,
                    "请检查新闻内容是否有效"
                )
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "ModelService",
                "request": {
                    "news_id": news_id,
                    "title_length": len(news_data.get('title', '')),
                    "content_length": len(news_data.get('content', ''))
                },
                "response": event_result,
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat()
            }
            
            # 记录事件信息
            event_info = event_result.get('event_info', {})
            directive = event_result.get('theme_discovery_directive', {})
            
            logger.info(f"✅ 事件提取成功: {news_id}, "
                       f"事件类型: {event_info.get('event_type', 'unknown')}, "
                       f"主题决策: {directive.get('action', 'unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 事件提取失败: {e}")
            traceback.print_exc()
            return self._create_error_response(str(e), operation)
    
    async def batch_extract_events(self, news_list: List[Dict]) -> Dict[str, Any]:
        """
        批量提取事件
        
        Args:
            news_list: 新闻数据列表
            
        Returns:
            批量提取结果
        """
        operation = "batch_extract_events"
        
        try:
            logger.info(f"📦 批量事件提取: {len(news_list)}条新闻")
            
            if not self.event_extractor:
                return self._create_error_response(
                    "AI事件提取器未初始化", 
                    operation,
                    "请检查DeepSeek API配置"
                )
            
            # 并行处理新闻
            results = []
            successful = 0
            failed = 0
            
            for news_data in news_list:
                try:
                    event_result = await self.extract_event(news_data)
                    
                    if event_result["status"] == "success":
                        successful += 1
                        results.append(event_result["response"])
                    else:
                        failed += 1
                        results.append({
                            "news_id": news_data.get('news_id'),
                            "status": "error",
                            "error": event_result.get("error")
                        })
                except Exception as e:
                    failed += 1
                    results.append({
                        "news_id": news_data.get('news_id'),
                        "status": "error",
                        "error": str(e)
                    })
            
            # 构建响应
            result = {
                "operation": operation,
                "status": "success",
                "service": "ModelService",
                "request": {
                    "batch_size": len(news_list)
                },
                "response": {
                    "total_processed": len(news_list),
                    "successful": successful,
                    "failed": failed,
                    "success_rate": successful / max(len(news_list), 1),
                    "results": results,
                    "processed_at": datetime.now().isoformat()
                },
                "metadata": self.service_metadata,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ 批量事件提取完成: {successful}成功, {failed}失败")
            return result
            
        except Exception as e:
            logger.error(f"❌ 批量事件提取失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def extract_event_auto(self, news_data: Dict, prefer_real: bool = True) -> Dict[str, Any]:
        """
        智能事件提取 - 自动选择真实或模拟
        
        Args:
            news_data: 新闻数据
            prefer_real: 是否优先使用真实AI
            
        Returns:
            事件提取结果
        """
        operation = "extract_event_auto"
        
        try:
            news_id = news_data.get('news_id', 'unknown')
            logger.info(f"🤖 智能事件提取: {news_id}, prefer_real={prefer_real}")
            
            # 检查真实提取器可用性
            real_available = False
            if prefer_real and self.event_extractor:
                try:
                    real_available = await self.event_extractor.health_check()
                    logger.info(f"AI提取器健康检查: {real_available}")
                except:
                    real_available = False
            
            # 根据可用性选择模式
            if real_available:
                result = await self.extract_event(news_data)
                result["operation"] = operation
                result["mode"] = "real"
            elif self.mock_extractor:
                # 使用模拟提取器
                event_result = await self.mock_extractor.extract_event(news_data)
                
                result = {
                    "operation": operation,
                    "status": "success",
                    "service": "ModelService",
                    "mode": "mock",
                    "request": {
                        "news_id": news_id
                    },
                    "response": event_result,
                    "metadata": self.service_metadata,
                    "timestamp": datetime.now().isoformat(),
                    "note": "这是模拟数据，真实AI提取请确保DEEPSEEK_API_KEY已配置"
                }
            else:
                return self._create_error_response(
                    "没有可用的提取器", 
                    operation,
                    "真实AI提取器和模拟提取器都不可用"
                )
            
            result["prefer_real"] = prefer_real
            result["real_available"] = real_available
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 智能事件提取失败: {e}")
            return self._create_error_response(str(e), operation)
    
    async def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        real_healthy = False
        mock_healthy = False
        
        # 检查真实提取器
        if self.event_extractor:
            try:
                real_healthy = await self.event_extractor.health_check()
            except:
                real_healthy = False
        
        # 检查模拟提取器
        if self.mock_extractor:
            try:
                mock_healthy = await self.mock_extractor.health_check()
            except:
                mock_healthy = False
        
        return {
            "operation": "get_service_status",
            "status": "healthy" if self.initialized else "unhealthy",
            "service": "ModelService",
            "initialized": self.initialized,
            "components": {
                "real_extractor": {
                    "available": self.event_extractor is not None,
                    "healthy": real_healthy,
                    "source": "DeepSeek API" if self.event_extractor else "未初始化"
                },
                "mock_extractor": {
                    "available": self.mock_extractor is not None,
                    "healthy": mock_healthy,
                    "source": "模拟数据提取器" if self.mock_extractor else "未初始化"
                }
            },
            "metadata": self.service_metadata,
            "timestamp": datetime.now().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查（兼容旧接口）"""
        status = await self.get_service_status()
        status["operation"] = "health_check"
        return status
    
    def _create_error_response(
        self, 
        error_message: str, 
        operation: str = "unknown",
        details: str = None
    ) -> Dict[str, Any]:
        """创建错误响应"""
        response = {
            "operation": operation,
            "status": "error",
            "error": error_message,
            "service": "ModelService",
            "metadata": self.service_metadata,
            "timestamp": datetime.now().isoformat()
        }
        
        if details:
            response["details"] = details
        
        return response

    async def analyze_news(self, news_data: Dict) -> Dict[str, Any]:
        """分析新闻 - 兼容旧接口名"""
        return await self.extract_event(news_data)


# 全局单例实例
_model_service_instance = None

def get_model_service() -> ModelService:
    """获取Model Service实例（单例模式）"""
    global _model_service_instance
    if _model_service_instance is None:
        _model_service_instance = ModelService()
        logger.info("✅ 创建ModelService单例实例")
    return _model_service_instance


# 快速测试函数
async def test_model_service():
    """测试Model Service"""
    try:
        service = get_model_service()
        
        print("\n" + "="*60)
        print("🧠 Model Service测试")
        print("="*60)
        
        # 1. 检查服务状态
        status = await service.get_service_status()
        print(f"1. 服务状态: {status.get('status')}")
        print(f"   AI提取器: {status['components']['real_extractor']['available']}")
        print(f"   模拟提取器: {'✅ 可用' if status['components']['mock_extractor']['available'] else '❌ 不可用'}")
        
        # 2. 创建测试新闻数据
        test_news = {
            "news_id": "test_001",
            "title": "央行宣布降准0.5个百分点，释放长期资金约1万亿元",
            "content": "中国人民银行决定，自2024年1月1日起，下调金融机构存款准备金率0.5个百分点。此次降准将释放长期资金约1万亿元，有助于降低社会综合融资成本，支持实体经济发展。分析人士认为，此次降准超出市场预期，对股市和债市均构成利好。",
            "source": "test",
            "publish_date": "2024-01-01"
        }
        
        # 3. 测试事件提取（根据可用性选择）
        if status['components']['real_extractor']['available']:
            print("\n2. 测试真实AI事件提取...")
            result = await service.extract_event(test_news)
        else:
            print("\n2. AI提取器不可用，测试模拟事件提取...")
            result = await service.extract_event_auto(test_news, prefer_real=False)
        
        print(f"   操作: {result.get('operation')}")
        print(f"   状态: {result.get('status')}")
        print(f"   模式: {result.get('mode', 'real')}")
        
        if result.get('status') == 'success':
            response = result.get('response', {})
            event_info = response.get('event_info', {})
            directive = response.get('theme_discovery_directive', {})
            
            print(f"\n   事件信息:")
            print(f"     事件类型: {event_info.get('event_type', 'unknown')}")
            print(f"     影响行业: {event_info.get('impact_industries', [])}")
            print(f"     市场方向: {event_info.get('direction', 'unknown')}")
            print(f"     置信度: {event_info.get('event_confidence', 0):.2f}")
            
            print(f"\n   主题决策:")
            print(f"     决策: {directive.get('action', 'unknown')}")
            print(f"     置信度: {directive.get('decision_confidence', 0):.2f}")
            print(f"     理由: {directive.get('reason', '')[:50]}...")
        
        # 4. 测试批量提取
        print("\n3. 测试批量事件提取...")
        batch_news = [test_news.copy()]
        batch_news[0]['news_id'] = 'test_batch_001'
        
        batch_result = await service.batch_extract_events(batch_news)
        print(f"   批量处理: {batch_result.get('response', {}).get('total_processed', 0)}条")
        print(f"   成功: {batch_result.get('response', {}).get('successful', 0)}")
        
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_model_service())