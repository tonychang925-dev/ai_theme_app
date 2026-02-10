#!/usr/bin/env python3
"""
event_extractor.py 修复后的单元测试
测试数据完整性保存功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, AsyncMock

class TestAIEventExtractorFixed:
    """测试修复后的AIEventExtractor"""
    
    def setup_method(self):
        """测试准备"""
        # 创建模拟的LLM解析器
        self.mock_llm_parser = Mock()
        self.mock_llm_parser.parse_news = AsyncMock()
        self.mock_llm_parser.health_check = AsyncMock(return_value=True)
        
        # 导入并创建提取器
        from model_service.service.event_extractor import AIEventExtractor
        self.extractor = AIEventExtractor(self.mock_llm_parser)
    
    @pytest.mark.asyncio
    async def test_extract_event_saves_original_data(self):
        """测试是否保存了原始数据"""
        # 模拟AI响应
        self.mock_llm_parser.parse_news.return_value = {
            "event_info": {
                "event_type": "技术突破",
                "summary": "某公司发布了新一代AI模型，性能提升30%",
                "impact_industries": ["人工智能", "软件"],
                "direction": "利好",
                "confidence": 0.85
            },
            "theme_discovery_directive": {
                "action": "CLUSTER",
                "confidence": 0.8,
                "reason": "重要技术突破"
            }
        }
        
        # 测试数据
        test_news = {
            'news_id': 'test_001',
            'title': '某公司发布新一代AI模型',
            'content': '详细新闻内容，包含技术细节和市场影响分析...' * 20  # 长内容
        }
        
        # 执行提取
        result = await self.extractor.extract_event(test_news)
        
        # 断言：必须保存原始数据
        assert result is not None
        assert 'original_data' in result
        assert result['original_data']['title'] == test_news['title']
        assert 'content' in result['original_data']
        assert len(result['original_data']['content']) > 0
        
        # 断言：必须有数据完整性标记
        assert 'data_integrity' in result
        assert result['data_integrity']['has_content'] is True
        assert result['data_integrity']['content_length'] == len(test_news['content'])
    
    @pytest.mark.asyncio
    async def test_extract_event_handles_short_content(self):
        """测试处理短内容的情况"""
        self.mock_llm_parser.parse_news.return_value = {
            "event_info": {
                "event_type": "产品发布",
                "summary": "新产品发布",
                "impact_industries": ["消费电子"],
                "direction": "中性",
                "confidence": 0.7
            },
            "theme_discovery_directive": {
                "action": "CLUSTER",
                "confidence": 0.6,
                "reason": "常规产品更新"
            }
        }
        
        # 短内容测试
        test_news = {
            'news_id': 'test_002',
            'title': '新产品发布',
            'content': '短内容'
        }
        
        result = await self.extractor.extract_event(test_news)
        
        assert result is not None
        assert result['data_integrity']['content_length'] == 3  # "短内容"3个字符
        assert result['data_integrity']['has_content'] is True
    
    @pytest.mark.asyncio
    async def test_extract_event_preserves_ai_response(self):
        """测试是否保存了完整的AI响应"""
        mock_ai_response = {
            "event_info": {
                "event_type": "政策发布",
                "summary": "详细政策摘要...",
                "impact_industries": ["新能源汽车"],
                "direction": "利好",
                "confidence": 0.9
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.85,
                "reason": "重大产业政策"
            },
            "raw_response": {"some": "raw_data"}
        }
        
        self.mock_llm_parser.parse_news.return_value = mock_ai_response
        
        test_news = {
            'news_id': 'test_003',
            'title': '新能源汽车政策',
            'content': '政策详细内容...'
        }
        
        result = await self.extractor.extract_event(test_news)
        
        # 断言：保存了AI响应
        assert 'ai_response' in result
        assert result['ai_response'] == mock_ai_response
        assert 'raw_ai_response' in result
    
    @pytest.mark.asyncio
    async def test_extract_event_handles_missing_content(self):
        """测试处理缺少内容的情况"""
        self.mock_llm_parser.parse_news.return_value = {
            "event_info": {
                "event_type": "unknown",
                "summary": "",
                "impact_industries": [],
                "direction": "中性",
                "confidence": 0.5
            },
            "theme_discovery_directive": {
                "action": "CLUSTER",
                "confidence": 0.5,
                "reason": ""
            }
        }
        
        # 无内容测试
        test_news = {
            'news_id': 'test_004',
            'title': '无内容测试',
            'content': ''
        }
        
        result = await self.extractor.extract_event(test_news)
        
        assert result is not None
        assert result['data_integrity']['has_content'] is False
        assert result['data_integrity']['content_length'] == 0

if __name__ == "__main__":
    # 直接运行测试
    import asyncio
    
    async def run_tests():
        tester = TestAIEventExtractorFixed()
        tester.setup_method()
        
        print("🧪 运行 event_extractor 单元测试")
        print("="*60)
        
        tests = [
            ("测试保存原始数据", tester.test_extract_event_saves_original_data),
            ("测试处理短内容", tester.test_extract_event_handles_short_content),
            ("测试保存AI响应", tester.test_extract_event_preserves_ai_response),
            ("测试处理缺少内容", tester.test_extract_event_handles_missing_content),
        ]
        
        all_passed = True
        for test_name, test_func in tests:
            try:
                await test_func()
                print(f"✅ {test_name}")
            except AssertionError as e:
                print(f"❌ {test_name}: {e}")
                all_passed = False
            except Exception as e:
                print(f"💥 {test_name}: {e}")
                all_passed = False
        
        print("="*60)
        if all_passed:
            print("🎉 所有单元测试通过！")
        else:
            print("⚠️  有测试失败")
        
        return all_passed
    
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
