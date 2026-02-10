#!/usr/bin/env python3
"""
event_extractor.py 修复测试 - 直接测试
位置: evaluate_service/scripts/test_event_extractor_now.py
"""
import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# 获取项目根目录
current_dir = Path(__file__).parent.parent.absolute()  # evaluate_service
PROJECT_ROOT = current_dir.parent.absolute()  # ai_theme_app

print(f"当前目录: {current_dir}")
print(f"项目根目录: {PROJECT_ROOT}")

# 检查文件是否存在
extractor_file = PROJECT_ROOT / "model_service" / "service" / "event_extractor.py"
print(f"检查文件: {extractor_file}")

if not extractor_file.exists():
    print("❌ 文件不存在！")
    sys.exit(1)

print("✅ 文件存在")

# 添加项目根目录到Python路径
sys.path.insert(0, str(PROJECT_ROOT))

async def test_event_extractor():
    """测试event_extractor.py的修复"""
    print("\n" + "="*60)
    print("🧪 测试 event_extractor.py 数据完整性修复")
    print("="*60)
    
    try:
        from model_service.service.event_extractor import AIEventExtractor
        
        # 创建模拟解析器
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock()
        mock_parser.health_check = AsyncMock(return_value=True)
        
        # 模拟AI响应
        mock_response = {
            "event_info": {
                "event_type": "技术突破",
                "summary": "某公司发布突破性AI技术",
                "impact_industries": ["人工智能"],
                "direction": "利好",
                "confidence": 0.9
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.85,
                "reason": "重大技术突破"
            }
        }
        mock_parser.parse_news.return_value = mock_response
        
        # 创建提取器
        extractor = AIEventExtractor(mock_parser)
        
        # 测试数据
        test_content = "这是完整的测试新闻内容，应该被完整保存。"
        test_news = {
            'news_id': 'test_001',
            'title': '测试标题',
            'content': test_content
        }
        
        print(f"测试数据:")
        print(f"  标题: {test_news['title']}")
        print(f"  原始内容: {test_news['content']}")
        print(f"  内容长度: {len(test_news['content'])}字符")
        
        # 执行提取
        result = await extractor.extract_event(test_news)
        
        if not result:
            print("❌ 提取返回None")
            return False
        
        print(f"\n✅ 提取成功")
        print(f"返回字段: {list(result.keys())}")
        
        # 检查关键修复字段
        required_fields = ['original_data', 'data_integrity', 'ai_response']
        missing_fields = []
        
        for field in required_fields:
            if field in result:
                print(f"  ✅ 有{field}字段")
            else:
                print(f"  ❌ 缺少{field}字段")
                missing_fields.append(field)
        
        if missing_fields:
            print(f"❌ 缺少字段: {missing_fields}")
            return False
        
        # 检查是否保存了完整原始内容
        if 'original_data' in result:
            od = result['original_data']
            if 'content' in od:
                saved_content = od['content']
                if saved_content == test_content:
                    print(f"  ✅ 完整保存了原始内容 ({len(saved_content)}字符)")
                else:
                    print(f"  ❌ 保存的内容不匹配")
                    print(f"    原始: {test_content}")
                    print(f"    保存: {saved_content}")
                    return False
            else:
                print("  ❌ original_data中没有content字段")
                return False
        
        # 检查数据完整性标记
        if 'data_integrity' in result:
            di = result['data_integrity']
            if di.get('content_length') == len(test_content):
                print(f"  ✅ 正确记录了内容长度: {di['content_length']}")
            else:
                print(f"  ❌ 内容长度记录错误")
                return False
            
            if di.get('has_content'):
                print("  ✅ 标记为有内容")
            else:
                print("  ❌ 标记为无内容")
                return False
        
        # 检查AI响应保存
        if 'ai_response' in result:
            ai_resp = result['ai_response']
            if ai_resp == mock_response:
                print("  ✅ 正确保存了AI响应")
            else:
                print("  ❌ AI响应保存错误")
                return False
        
        # 验证原始内容 ≠ AI摘要
        original_content = test_content
        ai_summary = result.get('summary', '')
        
        print(f"\n🔍 验证: 原始内容 ≠ AI摘要")
        print(f"  原始内容: {original_content}")
        print(f"  AI摘要: {ai_summary}")
        
        if original_content != ai_summary:
            print("  ✅ 原始内容与AI摘要不同")
        else:
            print("  ❌ 原始内容与AI摘要相同")
            return False
        
        print("\n🎉 所有检查通过！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    success = await test_event_extractor()
    
    print("\n" + "="*60)
    if success:
        print("🎉 event_extractor.py 修复验证通过！")
        print("✅ 原始数据完整保存功能正常")
        print("✅ 数据完整性标记正确")
        print("✅ AI响应保存正确")
        return 0
    else:
        print("⚠️  event_extractor.py 修复验证失败")
        print("🔧 请检查修改是否正确")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
