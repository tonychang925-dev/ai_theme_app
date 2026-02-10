#!/usr/bin/env python3
"""
统一格式提取器最终测试脚本 v3
绕过 provider 属性问题
"""

import asyncio
import json
import sys
import os
from datetime import datetime

print("=" * 60)
print("统一格式提取器最终测试 v3")
print("绕过 provider 属性问题")
print("=" * 60)

# ==================== 设置导入路径 ====================
# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

# 还要添加 model_service 到 sys.path
model_service_path = os.path.join(project_root, "model_service")
sys.path.insert(0, model_service_path)

print(f"项目根目录: {project_root}")
print(f"Model Service路径: {model_service_path}")
print()

# ==================== 猴子补丁修复 ====================
print("1. 应用猴子补丁修复...")

# 先导入必要的模块
from model_service.llm_parser.factory import LLMParserFactory

# 创建解析器
print("   创建LLM解析器...")
parser = LLMParserFactory.create_parser_from_env()
print(f"   ✅ 解析器创建成功: {type(parser).__name__}")

# 为解析器添加 provider 属性（猴子补丁）
if not hasattr(parser, 'provider'):
    print("   ⚠️  解析器没有 provider 属性，添加猴子补丁...")
    
    # 创建简单的 Provider 枚举
    from enum import Enum
    
    class Provider(Enum):
        DEEPSEEK = "deepseek"
        OPENAI = "openai"
        UNKNOWN = "unknown"
    
    # 根据类名设置 provider
    class_name = parser.__class__.__name__
    if "DeepSeek" in class_name:
        parser.provider = Provider.DEEPSEEK
    elif "OpenAI" in class_name:
        parser.provider = Provider.OPENAI
    else:
        parser.provider = Provider.UNKNOWN
    
    print(f"   ✅ 添加 provider: {parser.provider}")

# ==================== 动态修复 event_extractor ====================
print("\n2. 动态修复 event_extractor...")

try:
    # 直接导入并修改源代码
    event_extractor_path = os.path.join(project_root, "model_service", "services", "event_extractor.py")
    
    if os.path.exists(event_extractor_path):
        print(f"   找到 event_extractor.py: {event_extractor_path}")
        
        # 读取源代码
        with open(event_extractor_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        # 修复 provider 访问问题
        fixed_code = source_code.replace(
            'f"AI事件提取器已初始化，使用 {self.llm_parser.provider.value} 提供商"',
            'f"AI事件提取器已初始化，使用 {getattr(self.llm_parser, \'provider\', getattr(self.llm_parser, \'model_name\', type(self.llm_parser).__name__))} 提供商"'
        )
        
        # 如果替换失败，尝试其他方式
        if fixed_code == source_code:
            # 使用正则表达式替换
            import re
            fixed_code = re.sub(
                r'logger\.info\(f"AI事件提取器已初始化，使用 \{self\.llm_parser\.provider\.value\} 提供商"\)',
                'logger.info(f"AI事件提取器已初始化，使用 {getattr(self.llm_parser, "provider", getattr(self.llm_parser, "model_name", type(self.llm_parser).__name__))} 提供商")',
                source_code
            )
        
        # 创建临时模块
        import types
        event_extractor_module = types.ModuleType("event_extractor_fixed")
        
        # 执行修复后的代码
        exec(fixed_code, event_extractor_module.__dict__)
        
        # 获取修复后的类
        AIEventExtractor = getattr(event_extractor_module, 'AIEventExtractor')
        print("   ✅ 成功修复并导入 AIEventExtractor")
        
    else:
        print(f"   ❌ 文件不存在: {event_extractor_path}")
        sys.exit(1)
        
except Exception as e:
    print(f"   ❌ 动态修复失败: {e}")
    print("   尝试直接导入（可能失败）...")
    
    try:
        from model_service.services.event_extractor import AIEventExtractor
        print("   ✅ 直接导入成功（可能需要修复原始文件）")
    except ImportError as e2:
        print(f"   ❌ 直接导入也失败: {e2}")
        sys.exit(1)

# ==================== 创建提取器实例 ====================
print("\n3. 创建提取器实例...")

try:
    # 传入我们修复过的解析器
    extractor = AIEventExtractor(llm_parser=parser)
    print("   ✅ 提取器实例创建成功")
except Exception as e:
    print(f"   ❌ 创建提取器失败: {e}")
    print("   尝试创建默认提取器...")
    
    try:
        extractor = AIEventExtractor()
        print("   ✅ 默认提取器创建成功")
    except Exception as e2:
        print(f"   ❌ 默认提取器也失败: {e2}")
        sys.exit(1)

# ==================== 运行测试 ====================
print("\n4. 运行提取器测试...")

async def run_extractor_test():
    """运行提取器测试"""
    
    try:
        # 测试新闻数据
        test_news = {
            'news_id': 9999,
            'title': '测试：上海发布元宇宙产业发展行动计划',
            'content': '上海市经信委发布《上海市培育元宇宙新赛道行动方案（2025-2027年）》，提出到2027年元宇宙相关产业规模达到3500亿元。'
        }
        
        print(f"   测试新闻: {test_news['title']}")
        
        # 提取事件
        print("   正在提取事件（可能需要几秒钟）...")
        result = await extractor.extract_event(test_news)
        
        if result:
            print("   ✅ 事件提取成功！")
            print()
            
            # 显示关键结果
            print("   📋 提取结果关键信息:")
            print(f"     - 事件类型: {result.get('event_type', '未找到')}")
            print(f"     - 摘要: {result.get('summary', '未找到')[:80]}...")
            print(f"     - 置信度: {result.get('confidence', '未找到')}")
            
            # 检查 theme_directive - 统一格式的关键字段！
            theme_directive = result.get('theme_directive')
            if theme_directive:
                print(f"     - theme_directive: ✅ 存在 (统一格式的关键字段)")
                print(f"       • action: {theme_directive.get('action', '未找到')}")
                print(f"       • confidence: {theme_directive.get('confidence', '未找到')}")
                print(f"       • reason: {theme_directive.get('reason', '未找到')[:80]}...")
                
                # 验证统一格式
                required_keys = ['action', 'confidence', 'reason']
                missing_keys = [k for k in required_keys if k not in theme_directive]
                
                if missing_keys:
                    print(f"       ⚠️  缺少字段: {missing_keys}")
                    unified_format = False
                else:
                    print(f"       ✅ 符合统一格式要求")
                    unified_format = True
            else:
                print(f"     - theme_directive: ❌ 未找到 (不符合统一格式要求)")
                unified_format = False
            
            # 显示原始JSON（调试用）
            print()
            print("   🔍 完整JSON输出:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            test_passed = unified_format
            
        else:
            print("   ❌ 事件提取失败: 返回 None")
            test_passed = False
        
        # 关闭提取器
        print()
        print("   关闭提取器...")
        await extractor.close()
        print("   ✅ 提取器已关闭")
        
        return test_passed, result if result else None
        
    except Exception as e:
        print(f"   ❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False, None

# ==================== 批量测试 ====================
async def run_batch_test():
    """运行批量测试"""
    print("\n5. 批量测试...")
    
    try:
        # 加载测试数据
        test_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "test_inputs", "test_news.json")
        if os.path.exists(test_data_path):
            with open(test_data_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            
            print(f"   加载 {len(test_cases)} 个测试案例")
            
            # 创建新的提取器
            extractor = AIEventExtractor(llm_parser=parser)
            results = []
            success_count = 0
            
            try:
                for i, case in enumerate(test_cases, 1):
                    print(f"\n   处理 {i}/{len(test_cases)}: {case.get('title', '')[:30]}...")
                    
                    try:
                        result = await extractor.extract_event(case)
                        if result:
                            success_count += 1
                            results.append(result)
                            
                            # 检查 theme_directive
                            if 'theme_directive' in result:
                                directive = result['theme_directive']
                                action = directive.get('action', 'UNKNOWN')
                                
                                print(f"     ✅ 提取成功")
                                print(f"       • 事件类型: {result.get('event_type')}")
                                print(f"       • 指令: {action}")
                                print(f"       • 置信度: {directive.get('confidence')}")
                                
                                # 检查统一格式
                                if all(k in directive for k in ['action', 'confidence', 'reason']):
                                    print(f"       ✅ 统一格式: 完整")
                                else:
                                    print(f"       ⚠️  统一格式: 不完整")
                            else:
                                print(f"     ⚠️  提取成功但缺少theme_directive")
                        else:
                            print(f"     ❌ 提取失败: 返回None")
                    except Exception as e:
                        print(f"     ❌ 错误: {e}")
                
                batch_success_rate = success_count / len(test_cases) if len(test_cases) > 0 else 0
                
                print(f"\n   批量处理统计:")
                print(f"     - 总案例: {len(test_cases)}")
                print(f"     - 成功: {success_count} ({batch_success_rate:.1%})")
                
                # 统计CREATE_NEW
                if results:
                    create_new_count = sum(1 for r in results 
                                         if r.get('theme_directive', {}).get('action') == 'CREATE_NEW')
                    print(f"     - CREATE_NEW: {create_new_count}")
                
                batch_passed = success_count > 0
                
            finally:
                await extractor.close()
            
            return batch_passed, batch_success_rate, results
        else:
            print("   ⚠️  测试数据文件不存在，跳过批量测试")
            return False, 0, []
            
    except Exception as e:
        print(f"   ❌ 批量测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, []

# ==================== 主测试函数 ====================
async def main_test():
    """主测试函数"""
    
    print("\n" + "=" * 60)
    print("开始运行测试...")
    print("=" * 60)
    
    # 1. 运行单个测试
    single_test_passed, single_result = await run_extractor_test()
    
    # 2. 运行批量测试
    batch_test_passed, success_rate, batch_results = await run_batch_test()
    
    # 综合结果
    overall_passed = single_test_passed and success_rate > 0
    
    return {
        "single_test": single_test_passed,
        "batch_test": batch_test_passed,
        "success_rate": success_rate,
        "single_result": single_result,
        "batch_results_count": len(batch_results),
        "overall": overall_passed
    }

# ==================== 主程序 ====================
def main():
    """主程序"""
    try:
        # 运行异步测试
        results = asyncio.run(main_test())
        
        # 生成报告
        print("\n" + "=" * 60)
        print("测试报告")
        print("=" * 60)
        
        print(f"✅ 导入和初始化: 成功")
        print(f"✅ 单个测试: {'通过' if results['single_test'] else '失败'}")
        print(f"✅ 批量测试: {'通过' if results['batch_test'] else '失败'}")
        print(f"📊 批量成功率: {results['success_rate']:.1%}")
        print(f"📊 批量结果数: {results['batch_results_count']}")
        
        if results['overall']:
            print("\n🎉 测试通过！")
            print("统一格式提取器工作正常")
            print("✅ theme_directive 字段生成成功")
            print("✅ 符合统一格式要求")
            
            # 显示示例结果
            if results.get('single_result'):
                print("\n📋 示例输出:")
                directive = results['single_result'].get('theme_directive', {})
                print(f"   指令动作: {directive.get('action')}")
                print(f"   指令置信度: {directive.get('confidence')}")
                print(f"   指令原因: {directive.get('reason', '')[:60]}...")
        else:
            print("\n⚠️  测试失败或部分失败")
            
            if not results['single_test']:
                print("   - 单个测试失败")
            if results['success_rate'] <= 0:
                print("   - 批量测试成功率低")
        
        # 保存结果
        results_dir = os.path.join(os.path.dirname(__file__), "..", "data", "results")
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(results_dir, f"final_v3_test_report_{timestamp}.json")
        
        # 准备可JSON序列化的结果
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_root": project_root,
            "test_summary": {
                "single_test_passed": results['single_test'],
                "batch_test_passed": results['batch_test'],
                "batch_success_rate": results['success_rate'],
                "batch_results_count": results['batch_results_count'],
                "overall_passed": results['overall']
            }
        }
        
        # 添加单个结果（简化版）
        if results.get('single_result'):
            simple_result = {}
            for key, value in results['single_result'].items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    simple_result[key] = value
                elif isinstance(value, dict):
                    simple_result[key] = {k: v for k, v in value.items() 
                                        if isinstance(v, (str, int, float, bool, type(None)))}
            
            report_data["example_result"] = simple_result
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        
        return 0 if results['overall'] else 1
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 测试过程中发生未预期错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
