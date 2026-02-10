#!/usr/bin/env python3
"""
统一格式提取器测试脚本 - 修复导入路径
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

print("=" * 60)
print("统一格式提取器测试 - 修复导入路径")
print(f"项目根目录: {project_root}")
print("=" * 60)

# 首先检查导入
print("\n1. 检查导入...")
try:
    # 注意：正确的导入路径是 model_service.services.event_extractor
    from model_service.services.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor")
    print(f"  来自: model_service.services.event_extractor")
    
    # 尝试导入NewsEvent
    try:
        from model_service.models.news_event import NewsEvent
        print("✅ 成功导入 NewsEvent")
    except ImportError as e:
        print(f"⚠️  NewsEvent导入失败: {e}")
        # 尝试不同的路径
        try:
            from model_service.models.news_event import NewsEvent
            print("✅ 成功导入 NewsEvent (第二次尝试)")
        except ImportError:
            print("⚠️  无法导入NewsEvent，继续测试其他功能")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("\n可用的model_service结构:")
    try:
        import model_service
        print(f"  找到model_service包: {model_service.__file__}")
        
        # 检查services目录
        services_path = os.path.join(os.path.dirname(model_service.__file__), "services")
        if os.path.exists(services_path):
            print(f"  services目录: {services_path}")
            files = os.listdir(services_path)
            print(f"  services中的文件: {files}")
    except:
        pass
    
    # 尝试其他可能的导入路径
    print("\n尝试其他导入路径...")
    try:
        # 尝试直接导入
        from model_service.services.event_extractor import AIEventExtractor
        print("✅ 成功通过绝对路径导入")
    except ImportError as e2:
        print(f"❌ 再次失败: {e2}")
        print("\n请检查model_service结构:")
        print("ls -la model_service/")
        print("ls -la model_service/services/")
        sys.exit(1)

async def test_extractor():
    """测试提取器功能"""
    print("\n2. 测试提取器功能...")
    
    extractor = None
    try:
        # 创建提取器实例
        extractor = AIEventExtractor()
        print("✅ 提取器实例创建成功")
        
        # 测试数据
        test_news = {
            'news_id': 1001,
            'title': '上海发布元宇宙产业发展行动计划',
            'content': '上海市经信委发布《上海市培育元宇宙新赛道行动方案（2025-2027年）》，提出到2027年元宇宙相关产业规模达到3500亿元。'
        }
        
        print(f"   测试新闻: {test_news['title']}")
        
        # 提取事件
        print("   正在提取事件...")
        result = await extractor.extract_event(test_news)
        
        if result:
            print("   ✅ 事件提取成功")
            
            # 检查必要字段
            required_fields = ['event_type', 'summary', 'confidence', 'theme_directive']
            missing_fields = [f for f in required_fields if f not in result]
            
            if missing_fields:
                print(f"   ⚠️  缺少字段: {missing_fields}")
            else:
                print(f"   ✅ 所有必需字段都存在")
                
                # 显示结果
                print(f"   事件类型: {result.get('event_type')}")
                print(f"   摘要: {result.get('summary', '')[:50]}...")
                print(f"   置信度: {result.get('confidence')}")
                
                # 检查theme_directive
                directive = result.get('theme_directive', {})
                if directive:
                    print(f"   主题指令:")
                    print(f"     - 动作: {directive.get('action')}")
                    print(f"     - 置信度: {directive.get('confidence')}")
                    print(f"     - 原因: {directive.get('reason', '')[:50]}...")
                    
                    # 验证这是否是统一格式
                    if 'action' in directive and 'confidence' in directive and 'reason' in directive:
                        print(f"   ✅ theme_directive符合统一格式要求")
                    else:
                        print(f"   ⚠️  theme_directive格式不完整")
                else:
                    print(f"   ❌ 未找到theme_directive字段")
            
            # 尝试创建NewsEvent（如果可用）
            try:
                news_event = NewsEvent.from_ai_response(
                    news_db_id=test_news['news_id'],
                    news_hash_id=f"test_{test_news['news_id']}",
                    ai_data=result,
                    raw_news=test_news
                )
                print(f"   ✅ 成功创建NewsEvent对象")
                print(f"     持久化指令: {news_event.theme_directive}")
            except NameError:
                print(f"   ⚠️  NewsEvent不可用，跳过兼容性测试")
            except Exception as e:
                print(f"   ⚠️  NewsEvent创建失败: {e}")
                
        else:
            print("   ❌ 事件提取失败: 返回None")
            return False
            
        return True
        
    except Exception as e:
        print(f"   ❌ 测试过程中出错: {e}")
        return False
        
    finally:
        if extractor:
            await extractor.close()
            print("   ✅ 提取器已关闭")

async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始完整测试")
    print("=" * 60)
    
    test_results = []
    
    # 测试1: 基本功能
    print("\n测试1: 基本功能测试")
    result1 = await test_extractor()
    test_results.append(("基本功能", result1))
    
    # 测试2: 批量测试
    print("\n测试2: 批量测试")
    try:
        # 加载测试数据
        test_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "test_inputs", "simple_cases.json")
        if os.path.exists(test_data_path):
            with open(test_data_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            
            print(f"   加载 {len(test_cases)} 个测试案例")
            
            extractor = AIEventExtractor()
            try:
                success_count = 0
                for i, case in enumerate(test_cases, 1):
                    print(f"   处理 {i}/{len(test_cases)}: {case.get('title', '')[:30]}...")
                    
                    try:
                        result = await extractor.extract_event(case)
                        if result and 'theme_directive' in result:
                            success_count += 1
                            directive = result['theme_directive']
                            print(f"     ✅ 成功, 指令: {directive.get('action')}")
                        else:
                            print(f"     ❌ 失败")
                    except Exception as e:
                        print(f"     ❌ 错误: {e}")
                
                success_rate = success_count / len(test_cases)
                print(f"   批量处理结果: {success_count}/{len(test_cases)} 成功 ({success_rate:.1%})")
                test_results.append(("批量处理", success_rate > 0.5))
                
            finally:
                await extractor.close()
        else:
            print("   ⚠️  测试数据文件不存在")
            test_results.append(("批量处理", False))
    except Exception as e:
        print(f"   ❌ 批量测试失败: {e}")
        test_results.append(("批量处理", False))
    
    # 生成报告
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for _, result in test_results if result)
    
    print(f"总测试项目: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {total_tests - passed_tests}")
    print(f"成功率: {passed_tests/total_tests*100:.1f}%")
    
    print("\n详细结果:")
    for test_name, result in test_results:
        status = "✅" if result else "❌"
        print(f"  {status} {test_name}: {'通过' if result else '失败'}")
    
    # 保存结果
    results_dir = os.path.join(os.path.dirname(__file__), "..", "data", "results")
    os.makedirs(results_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(results_dir, f"test_report_{timestamp}.json")
    
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "project_root": project_root,
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": total_tests - passed_tests,
        "success_rate": passed_tests/total_tests if total_tests > 0 else 0,
        "import_path": "model_service.services.event_extractor",
        "tests": [
            {"name": name, "passed": passed} 
            for name, passed in test_results
        ]
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细报告已保存: {report_file}")
    
    return passed_tests / total_tests if total_tests > 0 else 0

def main():
    """主函数"""
    try:
        success_rate = asyncio.run(run_all_tests())
        
        print("\n" + "=" * 60)
        if success_rate >= 0.7:
            print("🎉 测试通过！")
            print("统一格式提取器工作正常")
        elif success_rate >= 0.5:
            print("⚠️  测试基本通过，但有需要注意的事项")
            print("部分功能可能需要调整")
        else:
            print("❌ 测试失败")
            print("需要检查提取器实现")
        print("=" * 60)
        
        return 0 if success_rate >= 0.5 else 1
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 测试过程中发生未预期错误: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
