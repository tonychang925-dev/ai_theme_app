#!/usr/bin/env python3
"""
极简event_extractor测试
"""
import asyncio
import sys
from unittest.mock import Mock, AsyncMock

# 添加当前目录到Python路径
sys.path.insert(0, '.')

async def test():
    print("🧪 极简event_extractor测试")
    print("="*60)
    
    try:
        # 尝试导入
        from model_service.service.event_extractor import AIEventExtractor
        print("✅ 成功导入AIEventExtractor")
        
        # 创建模拟解析器
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock()
        
        # 模拟响应
        mock_response = {
            "event_info": {
                "event_type": "测试",
                "summary": "测试摘要",
                "impact_industries": ["测试行业"],
                "direction": "中性",
                "confidence": 0.5
            },
            "theme_discovery_directive": {
                "action": "CLUSTER",
                "confidence": 0.5,
                "reason": "测试"
            }
        }
        mock_parser.parse_news.return_value = mock_response
        
        # 创建提取器
        extractor = AIEventExtractor(mock_parser)
        print("✅ 成功创建提取器实例")
        
        # 测试数据
        test_news = {
            'news_id': 'test_simple',
            'title': '测试标题',
            'content': '测试内容123'
        }
        
        print(f"📝 测试数据: {test_news['title']}")
        
        # 执行提取
        result = await extractor.extract_event(test_news)
        
        if result:
            print("✅ 提取成功")
            
            # 检查关键字段
            checks = [
                ("original_data", "保存原始数据"),
                ("data_integrity", "数据完整性标记"),
                ("ai_response", "保存AI响应"),
            ]
            
            all_ok = True
            for field, desc in checks:
                if field in result:
                    print(f"  ✅ {desc}")
                else:
                    print(f"  ❌ 缺少{desc}")
                    all_ok = False
            
            if all_ok:
                print("\n🎉 event_extractor.py 修复正确！")
                return True
            else:
                print("\n⚠️  缺少关键字段")
                return False
        else:
            print("❌ 提取返回None")
            return False
            
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
