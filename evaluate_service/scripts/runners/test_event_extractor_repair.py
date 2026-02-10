#!/usr/bin/env python3
"""
event_extractor.py修复验证测试
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock

# 获取当前目录
current_dir = Path(__file__).parent.parent.parent.absolute()
print(f"当前目录: {current_dir}")

# 尝试不同的项目根目录
possible_roots = [
    current_dir,  # 可能在evaluate_service目录
    current_dir.parent,  # 可能在ai_theme_app目录
    Path("/Users/admin/Desktop/ai_theme_app"),  # 绝对路径
]

for root in possible_roots:
    if (root / "model_service" / "service" / "event_extractor.py").exists():
        PROJECT_ROOT = root
        print(f"✅ 找到项目根目录: {PROJECT_ROOT}")
        break
else:
    print("❌ 找不到项目根目录")
    sys.exit(1)

# 添加项目根目录到Python路径
sys.path.insert(0, str(PROJECT_ROOT))

print("="*70)
print("🧪 event_extractor.py 修复验证测试")
print("="*70)

async def test_data_integrity():
    """测试数据完整性保存功能"""
    print("\n🔬 测试 1: 数据完整性保存")
    print("-"*60)
    
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
                "impact_industries": ["人工智能", "芯片半导体"],
                "direction": "利好",
                "confidence": 0.88
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.85,
                "reason": "突破性技术首次商用"
            }
        }
        mock_parser.parse_news.return_value = mock_response
        
        # 创建提取器
        extractor = AIEventExtractor(mock_parser)
        
        # 测试数据
        test_content = "某AI科技公司今日发布了新一代人工智能大模型。该模型性能提升30%，将推动AI技术在多领域应用。"
        test_news = {
            'news_id': 'test_001',
            'title': 'AI公司发布新一代大模型',
            'content': test_content
        }
        
        print(f"测试数据:")
        print(f"  标题: {test_news['title']}")
        print(f"  原始内容长度: {len(test_news['content'])} 字符")
        
        # 执行提取
        result = await extractor.extract_event(test_news)
        
        if not result:
            print("❌ 提取返回None")
            return False
        
        print(f"\n✅ 提取成功")
        print(f"返回字段: {list(result.keys())}")
        
        # 检查是否有original_data字段
        if 'original_data' not in result:
            print("❌ 缺少original_data字段")
            return False
        
        print("✅ 有original_data字段")
        
        od = result['original_data']
        
        # 检查是否保存了完整的原始content
        if 'content' not in od:
            print("❌ original_data中没有content字段")
            return False
        
        saved_content = od['content']
        original_content = test_news['content']
        
        if saved_content == original_content:
            print(f"✅ 完整保存了原始内容 ({len(saved_content)}字符)")
        else:
            print(f"❌ 保存的内容与原始内容不匹配")
            return False
        
        # 检查summary字段
        ai_summary = result['summary']
        if ai_summary:
            print(f"✅ summary字段有内容 ({len(ai_summary)}字符)")
        else:
            print("❌ summary字段为空")
            return False
        
        # 验证原始内容 ≠ AI摘要
        if original_content != ai_summary:
            print("✅ 原始内容与AI摘要是不同的")
        else:
            print("❌ 原始内容与AI摘要相同")
            return False
        
        # 检查数据完整性标记
        if 'data_integrity' in result:
            di = result['data_integrity']
            print(f"✅ 有data_integrity字段")
            
            if di.get('content_length') == len(original_content):
                print("✅ 正确记录了内容长度")
            else:
                print("❌ 内容长度记录错误")
                return False
        else:
            print("❌ 缺少data_integrity字段")
            return False
        
        # 检查是否有ai_response字段
        if 'ai_response' in result:
            print("✅ 保存了完整AI响应")
        else:
            print("❌ 缺少ai_response字段")
            return False
        
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
    """主测试函数"""
    print("\n📋 测试计划:")
    print("1. 数据完整性保存测试")
    print()
    
    test_results = []
    
    # 运行测试
    try:
        passed = await test_data_integrity()
        test_results.append(("数据完整性保存", passed))
    except Exception as e:
        print(f"💥 测试异常: {e}")
        test_results.append(("数据完整性保存", False))
    
    # 保存测试结果
    results_dir = PROJECT_ROOT / "evaluate_service" / "data" / "test_results"
    results_dir.mkdir(exist_ok=True)
    
    result_file = results_dir / f"event_extractor_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    result_data = {
        "component": "event_extractor.py",
        "timestamp": datetime.now().isoformat(),
        "tests": [
            {"name": name, "passed": passed} for name, passed in test_results
        ],
        "summary": {
            "total_tests": len(test_results),
            "passed_tests": sum(1 for _, passed in test_results if passed),
            "all_passed": all(passed for _, passed in test_results)
        }
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    # 打印汇总
    print("\n" + "="*70)
    print("📊 测试结果汇总:")
    
    all_passed = True
    for test_name, passed in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("🎉 测试通过！event_extractor.py 修复正确")
        print(f"📄 详细结果保存到: {result_file}")
        return 0
    else:
        print("⚠️  测试失败，请检查 event_extractor.py 的修改")
        print(f"📄 详细结果保存到: {result_file}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
