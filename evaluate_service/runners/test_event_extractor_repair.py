#!/usr/bin/env python3
"""
event_extractor.py修复验证测试
位置: evaluate_service/scripts/runners/test_event_extractor_repair.py
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock

# 设置项目路径
EVALUATE_DIR = Path(__file__).parent.parent.parent.absolute()
PROJECT_ROOT = EVALUATE_DIR.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

print("="*70)
print("🧪 event_extractor.py 修复验证测试")
print("="*70)
print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"项目根目录: {PROJECT_ROOT}")

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
        
        # 模拟AI响应 - 注意：summary应该是"判断摘要"，不是详细新闻摘要
        mock_response = {
            "event_info": {
                "event_type": "技术突破",
                "summary": "某公司发布突破性AI技术，可能定义新标准",  # 判断摘要，50字左右
                "impact_industries": ["人工智能", "芯片半导体"],
                "direction": "利好",
                "confidence": 0.88
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.85,
                "reason": "突破性技术首次商用，可能定义行业新标准"
            }
        }
        mock_parser.parse_news.return_value = mock_response
        
        # 创建提取器
        extractor = AIEventExtractor(mock_parser)
        
        # 测试数据 - 长内容
        long_content = '''某AI科技公司今日在北京正式发布了新一代人工智能大模型"DeepMind-X"。
该模型在多项国际基准测试中取得了突破性成绩，相比上一代产品性能提升了30%。
核心技术包括创新的注意力机制和高效的训练算法。

公司CEO在发布会上表示："这一突破将推动AI技术在医疗、金融、教育等领域的深度应用。
我们的模型采用了全新的架构设计，在处理复杂任务时表现更加稳定。"

技术细节方面，该模型包含以下创新点：
1. 混合专家架构，包含16个专家网络
2. 动态路由机制，提高推理效率
3. 高效训练算法，减少40%的算力消耗

市场分析师预计，这一技术突破将带动相关产业链的发展：
- 芯片半导体行业：对高性能AI芯片需求增加
- 云计算服务：需要更多算力支持模型推理
- 软件服务：AI应用开发门槛降低

公司计划在未来三个月内开源部分核心技术，供全球研究者和开发者使用。'''
        
        test_news = {
            'news_id': 'test_001',
            'title': 'AI公司发布新一代大模型，性能提升30%',
            'content': long_content
        }
        
        print(f"测试数据:")
        print(f"  标题: {test_news['title']}")
        print(f"  原始内容长度: {len(test_news['content'])} 字符")
        print(f"  AI摘要(判断摘要)长度: {len(mock_response['event_info']['summary'])} 字符")
        
        # 执行提取
        result = await extractor.extract_event(test_news)
        
        if not result:
            print("❌ 提取返回None")
            return False
        
        print(f"\n✅ 提取成功")
        print(f"返回字段: {list(result.keys())}")
        
        # 🎯 关键检查1: 是否有original_data字段
        if 'original_data' not in result:
            print("❌ 缺少original_data字段")
            return False
        
        print("✅ 有original_data字段")
        
        od = result['original_data']
        print(f"  original_data字段: {list(od.keys())}")
        
        # 🎯 关键检查2: 是否保存了完整的原始content
        if 'content' not in od:
            print("❌ original_data中没有content字段")
            return False
        
        saved_content = od['content']
        original_content = test_news['content']
        
        if saved_content == original_content:
            print(f"✅ 完整保存了原始内容 ({len(saved_content)}字符)")
        else:
            print(f"❌ 保存的内容与原始内容不匹配")
            print(f"  原始长度: {len(original_content)}")
            print(f"  保存长度: {len(saved_content)}")
            return False
        
        # 🎯 关键检查3: summary字段应该是AI的判断摘要
        ai_summary = result['summary']
        if ai_summary == mock_response['event_info']['summary']:
            print(f"✅ summary字段是AI的判断摘要 ({len(ai_summary)}字符)")
        else:
            print(f"❌ summary字段不是预期的AI摘要")
            return False
        
        # 🎯 关键检查4: 验证原始内容 ≠ AI摘要
        print(f"\n🎯 关键验证: 原始内容 ≠ AI摘要")
        if original_content != ai_summary:
            print("✅ 成功: 原始内容与AI摘要是不同的")
            print(f"  原始内容开头: {original_content[:50]}...")
            print(f"  AI摘要开头: {ai_summary[:50]}...")
        else:
            print("❌ 失败: 原始内容与AI摘要相同")
            return False
        
        # 🎯 关键检查5: 数据完整性标记
        if 'data_integrity' in result:
            di = result['data_integrity']
            print(f"\n📊 数据完整性标记:")
            print(f"  内容长度: {di.get('content_length')}")
            print(f"  AI摘要长度: {di.get('ai_summary_length')}")
            print(f"  增强比例: {di.get('enhancement_ratio', 0):.2f}x")
            
            if di.get('content_length') == len(original_content):
                print("✅ 正确记录了内容长度")
            else:
                print("❌ 内容长度记录错误")
                return False
        else:
            print("❌ 缺少data_integrity字段")
            return False
        
        # 🎯 关键检查6: 是否有ai_response字段
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

async def test_short_content():
    """测试短内容处理"""
    print("\n🔬 测试 2: 短内容处理")
    print("-"*60)
    
    try:
        from model_service.service.event_extractor import AIEventExtractor
        from unittest.mock import Mock, AsyncMock
        
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock(return_value={
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
        })
        
        extractor = AIEventExtractor(mock_parser)
        
        # 短内容测试
        test_news = {
            'news_id': 'test_short',
            'title': '新产品发布',
            'content': '短内容'
        }
        
        print(f"测试短内容: '{test_news['content']}' ({len(test_news['content'])}字符)")
        
        result = await extractor.extract_event(test_news)
        
        if result and result['data_integrity']['content_length'] == 3:
            print("✅ 短内容处理正确")
            return True
        else:
            print("❌ 短内容处理错误")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

async def test_missing_content():
    """测试缺少内容的情况"""
    print("\n🔬 测试 3: 缺少内容处理")
    print("-"*60)
    
    try:
        from model_service.service.event_extractor import AIEventExtractor
        from unittest.mock import Mock, AsyncMock
        
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock(return_value={
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
        })
        
        extractor = AIEventExtractor(mock_parser)
        
        # 无内容测试
        test_news = {
            'news_id': 'test_no_content',
            'title': '无内容测试',
            'content': ''
        }
        
        print(f"测试无内容: '{test_news['content']}' ({len(test_news['content'])}字符)")
        
        result = await extractor.extract_event(test_news)
        
        if result and result['data_integrity']['has_content'] is False:
            print("✅ 无内容处理正确")
            return True
        else:
            print("❌ 无内容处理错误")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

async def main():
    """主测试函数"""
    print("\n📋 测试计划:")
    print("1. 数据完整性保存测试")
    print("2. 短内容处理测试")
    print("3. 缺少内容处理测试")
    print()
    
    test_results = []
    
    # 运行所有测试
    tests = [
        ("数据完整性保存", test_data_integrity),
        ("短内容处理", test_short_content),
        ("缺少内容处理", test_missing_content),
    ]
    
    for test_name, test_func in tests:
        try:
            passed = await test_func()
            test_results.append((test_name, passed))
        except Exception as e:
            print(f"💥 {test_name} 测试异常: {e}")
            test_results.append((test_name, False))
    
    # 保存测试结果
    results_dir = EVALUATE_DIR / "data" / "test_results"
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
            "failed_tests": sum(1 for _, passed in test_results if not passed),
            "all_passed": all(passed for _, passed in test_results)
        }
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    # 打印汇总
    print("\n" + "="*70)
    print("📊 测试结果汇总:")
    print("-"*70)
    
    all_passed = True
    for test_name, passed in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("🎉 所有测试通过！event_extractor.py 修复正确")
        print(f"📄 详细结果保存到: {result_file}")
        print("\n✅ 可以进入下一步: 修改 deepseek_parser.py")
        return 0
    else:
        print("⚠️  有测试失败，请检查 event_extractor.py 的修改")
        print(f"📄 详细结果保存到: {result_file}")
        print("\n🔧 需要修复 event_extractor.py")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)