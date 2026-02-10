#!/usr/bin/env python3
"""
event_extractor.py 最终测试 - 修复路径问题
"""
import asyncio
import sys
import os
from pathlib import Path

# 关键：正确设置项目根目录
current_dir = Path(__file__).parent.absolute()
project_root = current_dir  # 假设脚本在项目根目录运行

print(f"当前目录: {current_dir}")
print(f"项目根目录: {project_root}")

# 添加项目根目录到Python路径
sys.path.insert(0, str(project_root))

# 检查是否可以导入
try:
    # 尝试导入
    from model_service.service.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("尝试其他路径...")
    
    # 尝试添加父目录
    parent_dir = current_dir.parent
    sys.path.insert(0, str(parent_dir))
    
    try:
        from model_service.service.event_extractor import AIEventExtractor
        print("✅ 从父目录成功导入 AIEventExtractor")
        project_root = parent_dir
    except ImportError as e2:
        print(f"❌ 仍然失败: {e2}")
        print("当前Python路径:")
        for p in sys.path:
            print(f"  {p}")
        sys.exit(1)

from unittest.mock import Mock, AsyncMock

async def test_event_extractor_fixed():
    """测试修复后的event_extractor"""
    print("\n🧪 测试 event_extractor 数据完整性保存")
    print("="*60)
    
    # 创建模拟的LLM解析器
    mock_llm_parser = Mock()
    mock_llm_parser.parse_news = AsyncMock()
    mock_llm_parser.health_check = AsyncMock(return_value=True)
    
    # 模拟AI响应
    mock_ai_response = {
        "event_info": {
            "event_type": "技术突破",
            "summary": "某公司发布了新一代AI模型，性能提升30%，在多项基准测试中表现优异",
            "impact_industries": ["人工智能", "软件", "云计算"],
            "direction": "利好",
            "confidence": 0.85
        },
        "theme_discovery_directive": {
            "action": "CLUSTER",
            "confidence": 0.8,
            "reason": "重要技术突破，可能影响多个行业"
        }
    }
    
    mock_llm_parser.parse_news.return_value = mock_ai_response
    
    # 创建提取器
    extractor = AIEventExtractor(mock_llm_parser)
    
    # 测试数据 - 长内容
    test_news = {
        'news_id': 'test_001',
        'title': '某AI公司发布新一代大模型，性能提升30%',
        'content': '''某AI科技公司今日在北京正式发布了新一代人工智能大模型"DeepMind-X"。
该模型在多项国际基准测试中取得了突破性成绩，相比上一代产品性能提升了30%。
核心技术包括创新的注意力机制和高效的训练算法。
公司CEO表示，这一突破将推动AI技术在医疗、金融、教育等领域的应用。
市场分析师预计，该技术将带动相关产业链的发展，包括芯片、云计算、软件服务等。'''
    }
    
    print("测试用例: 长内容新闻")
    print(f"  标题: {test_news['title']}")
    print(f"  内容长度: {len(test_news['content'])}字符")
    print(f"  内容预览: {test_news['content'][:100]}...")
    
    # 执行提取
    print("\n执行提取...")
    result = await extractor.extract_event(test_news)
    
    # 验证结果
    tests_passed = []
    tests_failed = []
    
    if result is None:
        tests_failed.append("提取结果为空")
        print("❌ 提取返回了None")
    else:
        print(f"✅ 提取成功，结果类型: {type(result)}")
        print(f"结果字段: {list(result.keys())}")
    
    # 1. 检查基础字段
    required_fields = ['news_id', 'event_type', 'summary', 'theme_directive']
    for field in required_fields:
        if field in result:
            tests_passed.append(f"有{field}字段")
        else:
            tests_failed.append(f"缺少{field}字段")
    
    # 2. 检查新增字段 - 原始数据保存
    new_fields = ['original_data', 'ai_response', 'data_integrity']
    for field in new_fields:
        if field in result:
            tests_passed.append(f"有{field}字段（新增修复）")
            print(f"  ✅ 检查到新增字段: {field}")
        else:
            tests_failed.append(f"缺少{field}字段（修复未生效）")
            print(f"  ❌ 未找到新增字段: {field}")
    
    # 3. 详细检查original_data
    if 'original_data' in result:
        od = result['original_data']
        print(f"\n🔍 original_data字段: {list(od.keys())}")
        
        if 'content' in od:
            content_len = len(od['content'])
            expected_len = len(test_news['content'])
            
            if content_len == expected_len:
                tests_passed.append("正确保存了完整内容")
                print(f"  内容保存: {content_len}字符 (正确)")
            else:
                tests_failed.append(f"内容长度不匹配: {content_len} vs {expected_len}")
                print(f"  内容保存: {content_len}字符 (期望: {expected_len})")
        else:
            tests_failed.append("original_data中没有content字段")
    
    # 4. 检查data_integrity
    if 'data_integrity' in result:
        di = result['data_integrity']
        print(f"\n🔍 data_integrity字段: {list(di.keys())}")
        
        if 'content_length' in di:
            tests_passed.append("记录了内容长度")
            print(f"  记录的内容长度: {di['content_length']}")
    
    # 5. 检查是否调用了AI
    if mock_llm_parser.parse_news.called:
        tests_passed.append("正确调用了AI解析器")
        call_args = mock_llm_parser.parse_news.call_args
        print(f"\n🔍 AI调用参数:")
        print(f"  标题: {call_args[0][0][:50]}...")
        print(f"  内容长度: {len(call_args[0][1])}字符")
    else:
        tests_failed.append("未调用AI解析器")
    
    # 打印测试结果
    print(f"\n📊 测试结果: 通过 {len(tests_passed)}/{len(tests_passed)+len(tests_failed)}")
    
    if tests_passed:
        print("\n✅ 通过的测试:")
        for test in tests_passed:
            print(f"  ✓ {test}")
    
    if tests_failed:
        print("\n❌ 失败的测试:")
        for test in tests_failed:
            print(f"  ✗ {test}")
    
    print("\n" + "="*60)
    
    if len(tests_failed) == 0:
        print("🎉 event_extractor 数据完整性测试通过！")
        return True
    else:
        print("⚠️  event_extractor 测试失败")
        
        # 输出当前event_extractor.py的关键部分帮助调试
        print("\n🔧 调试信息:")
        extractor_file = project_root / "model_service" / "service" / "event_extractor.py"
        if extractor_file.exists():
            print(f"检查文件: {extractor_file}")
            with open(extractor_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 查找extract_event方法的返回部分
            in_extract_method = False
            return_found = False
            
            for i, line in enumerate(lines):
                if 'async def extract_event' in line:
                    in_extract_method = True
                    print(f"\n找到extract_event方法 (第{i+1}行):")
                
                if in_extract_method and 'return' in line and not line.strip().startswith('#'):
                    return_found = True
                    print(f"返回语句 (第{i+1}行): {line.strip()}")
                    
                    # 显示附近几行
                    start = max(0, i-3)
                    end = min(len(lines), i+4)
                    print("上下文:")
                    for j in range(start, end):
                        prefix = ">>>" if j == i else "   "
                        print(f"{prefix} {j+1:3d}: {lines[j].rstrip()}")
                    
                    # 检查关键字段
                    return_line = line
                    if "'original_data'" not in return_line:
                        print("❌ 返回语句中缺少'original_data'")
                    if "'data_integrity'" not in return_line:
                        print("❌ 返回语句中缺少'data_integrity'")
                    
                    break
        
        return False

async def test_short_content():
    """测试短内容处理"""
    print("\n🧪 测试短内容处理")
    print("="*60)
    
    from unittest.mock import Mock, AsyncMock
    
    mock_llm_parser = Mock()
    mock_llm_parser.parse_news = AsyncMock(return_value={
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
    
    extractor = AIEventExtractor(mock_llm_parser)
    
    # 短内容测试
    test_news = {
        'news_id': 'test_short',
        'title': '新产品发布',
        'content': '短内容'
    }
    
    print(f"测试短内容: '{test_news['content']}' ({len(test_news['content'])}字符)")
    
    result = await extractor.extract_event(test_news)
    
    if result:
        print(f"✅ 提取成功")
        
        if 'original_data' in result:
            print(f"  保存了原始数据")
            
        if 'data_integrity' in result:
            di = result['data_integrity']
            if di.get('content_length') == 3:
                print(f"  正确记录内容长度: {di['content_length']}")
                return True
            else:
                print(f"❌ 内容长度错误: {di.get('content_length')} (期望: 3)")
                return False
        else:
            print("❌ 没有data_integrity字段")
            return False
    else:
        print("❌ 提取失败")
        return False

async def main():
    """主测试函数"""
    print("🚀 event_extractor 修复验证测试")
    print("测试目标: 验证数据完整性保存修复")
    print("="*60)
    
    test_results = []
    
    # 运行测试
    try:
        result1 = await test_event_extractor_fixed()
        test_results.append(("数据完整性保存测试", result1))
    except Exception as e:
        print(f"💥 测试异常: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("数据完整性保存测试", False))
    
    try:
        result2 = await test_short_content()
        test_results.append(("短内容处理测试", result2))
    except Exception as e:
        print(f"💥 短内容测试异常: {e}")
        test_results.append(("短内容处理测试", False))
    
    # 汇总结果
    print("\n" + "="*60)
    print("📋 测试汇总:")
    
    all_passed = True
    for test_name, passed in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 所有测试通过！")
        print("\n下一步: 修改 deepseek_parser.py 的提示词")
        return 0
    else:
        print("⚠️  有测试失败")
        print("\n建议:")
        print("1. 检查 event_extractor.py 的修改是否正确")
        print("2. 确保在 extract_event 方法中保存了 original_data")
        print("3. 重新运行测试")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
