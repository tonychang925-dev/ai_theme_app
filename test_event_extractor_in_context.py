#!/usr/bin/env python3
"""
在正确的项目结构中测试 event_extractor.py
位置: evaluate_service/scripts/test_event_extractor_in_context.py
"""
import asyncio
import sys
import os
from pathlib import Path

# ✅ 正确设置项目根目录：从当前目录向上两级
current_dir = Path(__file__).parent.absolute()  # evaluate_service/scripts
project_root = current_dir.parent.parent        # ai_theme_app/

print(f"当前目录: {current_dir}")
print(f"项目根目录: {project_root}")

# 添加项目根目录到Python路径
sys.path.insert(0, str(project_root))

# 检查项目结构
print("\n🔍 检查项目结构:")
for item in ['model_service', 'theme_service', 'database_service']:
    dir_path = project_root / item
    if dir_path.exists():
        print(f"✅ {item}: {dir_path}")
    else:
        print(f"❌ {item}: 不存在")

# 尝试导入
print("\n尝试导入核心模块...")
try:
    from model_service.service.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor")
    
    # 检查是否已修改
    import inspect
    source = inspect.getsource(AIEventExtractor.extract_event)
    if "'original_data'" in source and "'data_integrity'" in source:
        print("✅ event_extractor.py 已修复（包含original_data和data_integrity）")
    else:
        print("❌ event_extractor.py 未修复或修复不完整")
        
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("\n检查Python路径:")
    for i, path in enumerate(sys.path[:5]):
        print(f"  {i+1}. {path}")
    sys.exit(1)

from unittest.mock import Mock, AsyncMock

async def run_comprehensive_test():
    """运行综合测试"""
    print("\n" + "="*60)
    print("🧪 运行 event_extractor 综合测试")
    print("="*60)
    
    # 1. 创建模拟解析器
    mock_parser = Mock()
    mock_parser.parse_news = AsyncMock()
    mock_parser.health_check = AsyncMock(return_value=True)
    
    # 2. 模拟AI响应
    ai_response = {
        "event_info": {
            "event_type": "技术突破",
            "summary": "某公司发布新一代AI大模型，性能提升30%，在多项基准测试中领先",
            "impact_industries": ["人工智能", "云计算", "芯片半导体"],
            "direction": "利好",
            "confidence": 0.88
        },
        "theme_discovery_directive": {
            "action": "CREATE_NEW",
            "confidence": 0.85,
            "reason": "重大技术突破，可能定义新的AI基础设施标准"
        }
    }
    
    mock_parser.parse_news.return_value = ai_response
    
    # 3. 创建提取器
    extractor = AIEventExtractor(mock_parser)
    
    # 4. 测试数据
    test_cases = [
        {
            'name': '长内容技术新闻',
            'data': {
                'news_id': 'tech_001',
                'title': 'DeepSeek发布新一代千亿参数大模型',
                'content': '''人工智能公司DeepSeek今日正式发布了新一代千亿参数大模型"DeepSeek-V3"。
该模型采用创新的混合专家架构，在自然语言理解、代码生成、数学推理等多项基准测试中均取得领先成绩。
相比上一代模型，性能提升超过30%，同时推理成本降低了40%。
DeepSeek CEO表示，该模型将开源发布，供全球研究者和开发者使用。
技术细节包括：1) 混合专家架构，包含16个专家网络；2) 动态路由机制；3) 高效训练算法。
市场分析师认为，这一突破将加速AI在各行业的应用落地，相关产业链公司有望受益。'''
            }
        },
        {
            'name': '短内容公告',
            'data': {
                'news_id': 'short_001',
                'title': '公司董事会决议',
                'content': '公司董事会通过年度分红方案。'
            }
        }
    ]
    
    test_results = []
    
    for test_case in test_cases:
        print(f"\n🔬 测试: {test_case['name']}")
        print(f"  标题: {test_case['data']['title']}")
        print(f"  内容长度: {len(test_case['data']['content'])}字符")
        
        try:
            # 执行提取
            result = await extractor.extract_event(test_case['data'])
            
            if result is None:
                print("  ❌ 提取返回None")
                test_results.append((test_case['name'], False, "返回None"))
                continue
            
            # 检查关键字段
            checks = []
            
            # 基础字段
            for field in ['news_id', 'event_type', 'summary', 'theme_directive']:
                if field in result:
                    checks.append((f"有{field}字段", True))
                else:
                    checks.append((f"缺少{field}字段", False))
            
            # 🚀 新增修复字段
            repair_fields = ['original_data', 'data_integrity', 'ai_response']
            for field in repair_fields:
                if field in result:
                    checks.append((f"有{field}字段（修复）", True))
                else:
                    checks.append((f"缺少{field}字段", False))
            
            # 详细检查 original_data
            if 'original_data' in result:
                od = result['original_data']
                if 'content' in od:
                    content_len = len(od['content'])
                    expected_len = len(test_case['data']['content'])
                    
                    if content_len == expected_len:
                        checks.append(("完整保存原始内容", True))
                    else:
                        checks.append((f"内容长度不匹配: {content_len} vs {expected_len}", False))
                
                if 'content_length' in od:
                    checks.append(("记录内容长度", True))
            
            # 检查 data_integrity
            if 'data_integrity' in result:
                di = result['data_integrity']
                if 'content_length' in di and 'ai_summary_length' in di:
                    checks.append(("记录数据完整性指标", True))
            
            # 统计结果
            passed = sum(1 for _, success in checks if success)
            total = len(checks)
            
            print(f"  检查结果: {passed}/{total} 通过")
            
            # 显示失败项
            for check_name, success in checks:
                if not success:
                    print(f"    ❌ {check_name}")
            
            test_results.append((test_case['name'], passed/total > 0.8, f"{passed}/{total}通过"))
            
        except Exception as e:
            print(f"  💥 测试异常: {e}")
            import traceback
            traceback.print_exc()
            test_results.append((test_case['name'], False, f"异常: {str(e)[:50]}"))
    
    # 打印汇总
    print("\n" + "="*60)
    print("📊 测试结果汇总:")
    
    all_passed = True
    for name, passed, detail in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status} ({detail})")
        if not passed:
            all_passed = False
    
    return all_passed

async def inspect_current_implementation():
    """检查当前实现"""
    print("\n🔍 检查当前 event_extractor.py 实现")
    print("="*60)
    
    # 读取文件
    extractor_file = project_root / "model_service" / "service" / "event_extractor.py"
    
    if not extractor_file.exists():
        print(f"❌ 文件不存在: {extractor_file}")
        return False
    
    with open(extractor_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键部分
    checks = [
        ("有extract_event方法", "async def extract_event" in content),
        ("有original_data字段", "'original_data'" in content or '"original_data"' in content),
        ("有data_integrity字段", "'data_integrity'" in content or '"data_integrity"' in content),
        ("有ai_response字段", "'ai_response'" in content or '"ai_response"' in content),
        ("保存content内容", "content': content" in content or '"content": content' in content),
    ]
    
    print("代码检查:")
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
    
    # 查找返回语句
    import re
    return_pattern = r'return\s*{[^}]*}'
    returns = re.findall(return_pattern, content, re.DOTALL)
    
    if returns:
        print(f"\n找到 {len(returns)} 个返回语句")
        last_return = returns[-1]
        print("最后一个返回语句预览:")
        print(last_return[:300] + "..." if len(last_return) > 300 else last_return)
        
        # 检查字段
        if "'original_data'" in last_return or '"original_data"' in last_return:
            print("✅ 返回语句中包含 original_data")
        else:
            print("❌ 返回语句中缺少 original_data")
            
        if "'data_integrity'" in last_return or '"data_integrity"' in last_return:
            print("✅ 返回语句中包含 data_integrity")
        else:
            print("❌ 返回语句中缺少 data_integrity")
    else:
        print("❌ 未找到返回语句")
    
    return all(passed for _, passed in checks)

async def main():
    """主函数"""
    print("🚀 event_extractor 修复验证测试")
    print("位置: evaluate_service/scripts/")
    print("="*60)
    
    # 1. 检查当前实现
    implementation_ok = await inspect_current_implementation()
    
    if not implementation_ok:
        print("\n⚠️  代码实现未完全修复，需要先修改 event_extractor.py")
        print("修改建议:")
        print("1. 在 extract_event 方法中")
        print("2. 在返回的字典中添加:")
        print("   - 'original_data': {'title': title, 'content': content, ...}")
        print("   - 'data_integrity': {'has_content': bool(content), ...}")
        print("   - 'ai_response': parsed_result")
        return 1
    
    # 2. 运行功能测试
    print("\n" + "="*60)
    tests_passed = await run_comprehensive_test()
    
    print("\n" + "="*60)
    if tests_passed:
        print("🎉 所有测试通过！event_extractor.py 修复成功")
        print("\n下一步: 修改 deepseek_parser.py")
        return 0
    else:
        print("⚠️  测试失败，需要修复 event_extractor.py")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
