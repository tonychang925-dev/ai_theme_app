#!/usr/bin/env python3
"""
核心组件修复验证 - 统一验证脚本
位置: evaluate_service/runners/verify_core_fixes.py
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 设置项目路径
EVALUATE_DIR = Path(__file__).parent.parent.absolute()
PROJECT_ROOT = EVALUATE_DIR.parent.absolute()

print("="*80)
print("🔧 金融投资AI助理 - 核心组件修复验证")
print("="*80)
print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"评估目录: {EVALUATE_DIR}")
print(f"项目根目录: {PROJECT_ROOT}")

def verify_event_extractor():
    """验证event_extractor.py修复"""
    print("\n" + "="*60)
    print("🧪 验证 1: event_extractor.py 数据完整性修复")
    print("="*60)
    
    result = {
        "component": "event_extractor.py",
        "checks": [],
        "passed": False
    }
    
    # 检查文件
    extractor_file = PROJECT_ROOT / "model_service" / "services" / "event_extractor.py"
    print(f"检查文件: {extractor_file}")
    
    if not extractor_file.exists():
        result["checks"].append({"check": "file_exists", "passed": False})
        print("❌ 文件不存在")
        return result
    
    result["checks"].append({"check": "file_exists", "passed": True})
    
    # 检查文件内容
    with open(extractor_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"文件大小: {len(content)} 字符")
    
    # 关键修复检查
    repair_fields = [
        ("original_data", "保存原始数据"),
        ("content': content", "保存完整内容"),
        ("data_integrity", "数据完整性标记"),
        ("ai_response", "保存AI响应"),
        ("enhancement_ratio", "计算增强比例"),
    ]
    
    for field, description in repair_fields:
        if field in content:
            print(f"✅ {description}")
            result["checks"].append({"check": f"has_{field}", "passed": True, "description": description})
        else:
            print(f"❌ {description}")
            result["checks"].append({"check": f"has_{field}", "passed": False, "description": description})
    
    # 统计结果
    passed_checks = sum(1 for check in result["checks"] if check["passed"])
    total_checks = len(result["checks"])
    
    result["passed_checks"] = passed_checks
    result["total_checks"] = total_checks
    result["passed"] = passed_checks == total_checks
    
    if result["passed"]:
        print(f"\n🎉 event_extractor.py 修复验证通过！ ({passed_checks}/{total_checks})")
    else:
        print(f"\n⚠️  event_extractor.py 修复验证失败 ({passed_checks}/{total_checks})")
    
    return result

def verify_deepseek_parser():
    """验证deepseek_parser.py修复"""
    print("\n" + "="*60)
    print("🧪 验证 2: deepseek_parser.py 提示词修复")
    print("="*60)
    
    result = {
        "component": "deepseek_parser.py",
        "checks": [],
        "passed": False
    }
    
    # 检查文件
    parser_file = PROJECT_ROOT / "model_service" / "llm_parser" / "deepseek_parser.py"
    print(f"检查文件: {parser_file}")
    
    if not parser_file.exists():
        result["checks"].append({"check": "file_exists", "passed": False})
        print("❌ 文件不存在")
        return result
    
    result["checks"].append({"check": "file_exists", "passed": True})
    
    # 检查文件内容
    with open(parser_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查提示词修复
    checks = [
        ("判断摘要要求", "判断摘要" in content),
        ("50-100字长度", "50-100字" in content),
        ("判断理由说明", "判断理由" in content),
        ("不是详细新闻摘要", "不是详细新闻摘要" in content),
        ("已移除一句中文摘要", "一句中文摘要" not in content),
    ]
    
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
        result["checks"].append({"check": check_name, "passed": passed})
    
    # 显示修改部分
    print(f"\n🔍 修改部分预览:")
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "判断摘要" in line:
            start = max(0, i-1)
            end = min(len(lines), i+2)
            for j in range(start, end):
                prefix = ">>>" if j == i else "   "
                print(f"{prefix} {j+1:3d}: {lines[j]}")
            break
    
    # 统计结果
    passed_checks = sum(1 for check in result["checks"] if check["passed"])
    total_checks = len(result["checks"])
    
    result["passed_checks"] = passed_checks
    result["total_checks"] = total_checks
    result["passed"] = passed_checks == total_checks
    
    if result["passed"]:
        print(f"\n🎉 deepseek_parser.py 修复验证通过！ ({passed_checks}/{total_checks})")
        print("✅ 第一轮AI现在专注于判断事件重要性")
    else:
        print(f"\n⚠️  deepseek_parser.py 修复验证失败 ({passed_checks}/{total_checks})")
    
    return result

def generate_fix_plan():
    """生成修复计划"""
    print("\n" + "="*60)
    print("📋 下一步修复计划")
    print("="*60)
    
    plan = [
        {
            "step": 3,
            "component": "related_theme_fetcher.py",
            "description": "修改数据增强逻辑，优先使用完整内容",
            "location": "theme_service/related_theme_fetcher.py",
            "action": "修改 _enhance_event_data 方法"
        },
        {
            "step": 4,
            "component": "ai_similarity_analyzer.py",
            "description": "修改提示词，基于完整内容分析",
            "location": "theme_service/ai_similarity_analyzer.py",
            "action": "修改 _format_event_for_ai 和 _build_enhanced_prompt 方法"
        },
        {
            "step": 5,
            "description": "重建数据集并运行集成测试",
            "action": "使用修复后的组件重新处理数据"
        }
    ]
    
    for item in plan:
        print(f"\n{item['step']}. {item['component']}")
        print(f"   📍 位置: {item['location']}")
        print(f"   📝 {item['description']}")
        print(f"   🔧 操作: {item['action']}")
    
    return plan

def main():
    """主函数"""
    print("\n📋 验证计划:")
    print("1. event_extractor.py - 数据完整性修复验证")
    print("2. deepseek_parser.py - 提示词修复验证")
    print("3. 生成下一步修复计划")
    print()
    
    # 运行验证
    results = []
    results.append(verify_event_extractor())
    results.append(verify_deepseek_parser())
    
    # 生成修复计划
    plan = generate_fix_plan()
    
    # 保存结果
    results_dir = EVALUATE_DIR / "data" / "test_results"
    results_dir.mkdir(exist_ok=True)
    
    result_file = results_dir / f"core_fixes_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = {
        "metadata": {
            "validation_time": datetime.now().isoformat(),
            "project_root": str(PROJECT_ROOT),
            "total_components": len(results)
        },
        "results": results,
        "next_steps": plan,
        "summary": {
            "total_passed": sum(1 for r in results if r["passed"]),
            "total_failed": sum(1 for r in results if not r["passed"]),
            "all_passed": all(r["passed"] for r in results)
        }
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*80)
    print("📊 最终验证结果汇总")
    print("="*80)
    
    all_passed = True
    for result in results:
        component = result["component"]
        passed = result["passed"]
        passed_checks = result.get("passed_checks", 0)
        total_checks = result.get("total_checks", 0)
        
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{component}: {status} ({passed_checks}/{total_checks})")
        if not passed:
            all_passed = False
    
    print(f"\n📄 详细报告: {result_file}")
    
    print("\n" + "="*80)
    if all_passed:
        print("🎉 前两个核心组件修复验证通过！")
        print("✅ 可以开始修改 related_theme_fetcher.py")
        print("\n💡 建议修改顺序:")
        print("  1. related_theme_fetcher.py - 数据增强逻辑")
        print("  2. ai_similarity_analyzer.py - 完整内容分析")
        print("  3. 重建数据集测试")
        return 0
    else:
        print("⚠️  有组件验证失败，请先修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())
