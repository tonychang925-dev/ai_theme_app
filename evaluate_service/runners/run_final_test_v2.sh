#!/bin/bash

# 统一格式提取器最终测试脚本 v2
# 修复 provider 属性问题

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_header() {
    echo -e "${BLUE}"
    echo "=========================================="
    echo "    统一格式提取器最终测试 v2"
    echo "=========================================="
    echo -e "${NC}"
}

# 主函数
main() {
    print_header
    
    # 获取目录信息
    SCRIPT_DIR="/Users/admin/Desktop/ai_theme_app/evaluate_service"
    PROJECT_ROOT="/Users/admin/Desktop/ai_theme_app"
    
    echo -e "${YELLOW}执行位置:${NC} $SCRIPT_DIR"
    echo -e "${YELLOW}项目根目录:${NC} $PROJECT_ROOT"
    echo ""
    
    # 检查项目结构
    print_step "1. 检查项目结构"
    if [ ! -d "$PROJECT_ROOT/model_service" ]; then
        print_error "未找到 model_service 目录"
        exit 1
    fi
    
    print_success "项目结构检查通过"
    
    # 创建目录
    print_step "2. 创建测试目录结构"
    mkdir -p data/test_inputs data/results scripts logs
    print_success "目录创建完成"
    
    # 创建测试数据
    print_step "3. 创建测试数据"
    cat > data/test_inputs/test_news.json << 'TEST_EOF'
[
    {
        "news_id": 1001,
        "title": "上海发布元宇宙产业发展行动计划",
        "content": "上海市经信委发布《上海市培育元宇宙新赛道行动方案（2025-2027年）》，提出到2027年元宇宙相关产业规模达到3500亿元。",
        "source": "上海发布"
    },
    {
        "news_id": 1002,
        "title": "国务院印发人工智能发展规划",
        "content": "国务院印发《新一代人工智能发展规划》，提出到2025年我国人工智能核心产业规模超过4000亿元。",
        "source": "新华社"
    }
]
TEST_EOF
    print_success "测试数据创建完成"
    
    # 创建Python测试脚本 - 修复 provider 问题
    print_step "4. 创建Python测试脚本 (修复provider问题)"
    cat > scripts/test_final_v2.py << 'PYTHON_EOF'
#!/usr/bin/env python3
"""
统一格式提取器最终测试脚本 v2
修复 provider 属性问题
"""

import asyncio
import json
import sys
import os
from datetime import datetime

print("=" * 60)
print("统一格式提取器最终测试 v2")
print("修复 provider 属性问题")
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

# ==================== 测试导入 ====================
print("1. 测试导入...")

try:
    # 导入 LLMParserFactory
    from model_service.llm_parser.factory import LLMParserFactory
    print("✅ 成功导入 LLMParserFactory")
    
    # 创建解析器（不检查provider属性）
    print("   创建LLM解析器...")
    parser = LLMParserFactory.create_parser_from_env()
    print(f"   ✅ 解析器创建成功: {type(parser).__name__}")
    
    # 检查解析器是否有 provider 属性
    if hasattr(parser, 'provider'):
        print(f"   ✅ 解析器有 provider 属性: {parser.provider}")
    else:
        print(f"   ⚠️  解析器没有 provider 属性")
        # 尝试其他属性
        if hasattr(parser, '__class__'):
            print(f"   ℹ️  解析器类名: {parser.__class__.__name__}")
        if hasattr(parser, 'model_name'):
            print(f"   ℹ️  模型名称: {parser.model_name}")
            
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# ==================== 测试事件提取器 ====================
print("\n2. 测试事件提取器...")

try:
    # 导入事件提取器
    from model_service.services.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor")
    
    # 创建提取器实例
    print("   创建提取器实例...")
    extractor = AIEventExtractor()
    print("   ✅ 提取器实例创建成功")
    
except ImportError as e:
    print(f"❌ AIEventExtractor 导入失败: {e}")
    
    # 尝试直接导入
    try:
        event_extractor_path = os.path.join(project_root, "model_service", "services", "event_extractor.py")
        if os.path.exists(event_extractor_path):
            print(f"✅ 找到 event_extractor.py: {event_extractor_path}")
            
            # 动态导入
            import importlib.util
            spec = importlib.util.spec_from_file_location("event_extractor", event_extractor_path)
            event_extractor_module = importlib.util.module_from_spec(spec)
            sys.modules["event_extractor"] = event_extractor_module
            
            # 执行模块代码
            with open(event_extractor_path, 'r', encoding='utf-8') as f:
                code = f.read()
            exec(code, event_extractor_module.__dict__)
            
            # 获取类
            AIEventExtractor = getattr(event_extractor_module, 'AIEventExtractor')
            print("✅ 成功动态导入 AIEventExtractor")
            
            # 创建实例
            print("   创建提取器实例...")
            extractor = AIEventExtractor()
            print("   ✅ 提取器实例创建成功")
        else:
            print(f"❌ 文件不存在: {event_extractor_path}")
            sys.exit(1)
    except Exception as e2:
        print(f"❌ 动态导入失败: {e2}")
        sys.exit(1)

# ==================== 运行测试 ====================
print("\n3. 运行提取器测试...")

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
            print(f"   返回结果类型: {type(result)}")
            print()
            
            # 显示关键结果
            print("   📋 提取结果关键信息:")
            print(f"     - 事件类型: {result.get('event_type', '未找到')}")
            print(f"     - 摘要: {result.get('summary', '未找到')[:80]}...")
            print(f"     - 置信度: {result.get('confidence', '未找到')}")
            
            # 检查 theme_directive - 这是统一格式的关键字段！
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
            
            # 显示所有字段（调试用）
            print()
            print("   🔍 所有字段 (调试信息):")
            for key, value in result.items():
                if key == 'theme_directive' and isinstance(value, dict):
                    print(f"     - {key}: (统一格式指令)")
                    for sub_key, sub_value in value.items():
                        value_str = str(sub_value)
                        print(f"       • {sub_key}: {value_str[:60]}{'...' if len(value_str) > 60 else ''}")
                elif isinstance(value, dict):
                    print(f"     - {key}: (字典 {len(value)} 项)")
                    for i, (sub_key, sub_value) in enumerate(list(value.items())[:3]):
                        value_str = str(sub_value)
                        print(f"       • {sub_key}: {value_str[:40]}{'...' if len(value_str) > 40 else ''}")
                    if len(value) > 3:
                        print(f"       • ... 还有 {len(value)-3} 项")
                elif isinstance(value, list):
                    print(f"     - {key}: (列表 {len(value)} 项)")
                    for i, item in enumerate(value[:3]):
                        item_str = str(item)
                        print(f"       • [{i}]: {item_str[:40]}{'...' if len(item_str) > 40 else ''}")
                    if len(value) > 3:
                        print(f"       • ... 还有 {len(value)-3} 项")
                else:
                    value_str = str(value)
                    print(f"     - {key}: {value_str[:80]}{'...' if len(value_str) > 80 else ''}")
            
            test_passed = unified_format
            
        else:
            print("   ❌ 事件提取失败: 返回 None")
            test_passed = False
        
        # 关闭提取器
        print()
        print("   关闭提取器...")
        await extractor.close()
        print("   ✅ 提取器已关闭")
        
        return test_passed
        
    except Exception as e:
        print(f"   ❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== 批量测试 ====================
async def run_batch_test():
    """运行批量测试"""
    print("\n4. 批量测试...")
    
    try:
        # 加载测试数据
        test_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "test_inputs", "test_news.json")
        if os.path.exists(test_data_path):
            with open(test_data_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            
            print(f"   加载 {len(test_cases)} 个测试案例")
            
            extractor = AIEventExtractor()
            success_count = 0
            create_new_count = 0
            total_with_directive = 0
            
            try:
                for i, case in enumerate(test_cases, 1):
                    print(f"   处理 {i}/{len(test_cases)}: {case.get('title', '')[:30]}...")
                    
                    try:
                        result = await extractor.extract_event(case)
                        if result and 'theme_directive' in result:
                            success_count += 1
                            directive = result['theme_directive']
                            action = directive.get('action', 'UNKNOWN')
                            
                            if action == 'CREATE_NEW':
                                create_new_count += 1
                                print(f"     ✅ 成功, action: {action} (重大事件!)")
                            else:
                                print(f"     ✅ 成功, action: {action}")
                            
                            # 检查统一格式
                            if all(k in directive for k in ['action', 'confidence', 'reason']):
                                total_with_directive += 1
                        else:
                            print(f"     ❌ 失败: 缺少theme_directive或返回None")
                    except Exception as e:
                        print(f"     ❌ 错误: {e}")
                
                batch_success_rate = success_count / len(test_cases) if len(test_cases) > 0 else 0
                unified_format_rate = total_with_directive / success_count if success_count > 0 else 0
                
                print(f"   批量处理结果:")
                print(f"     - 成功: {success_count}/{len(test_cases)} ({batch_success_rate:.1%})")
                print(f"     - CREATE_NEW: {create_new_count} 条")
                print(f"     - 统一格式: {total_with_directive}/{success_count} ({unified_format_rate:.1%})")
                
                batch_passed = success_count > 0
                
            finally:
                await extractor.close()
            
            return batch_passed, batch_success_rate, create_new_count, unified_format_rate
        else:
            print("   ⚠️  测试数据文件不存在，跳过批量测试")
            return False, 0, 0, 0
            
    except Exception as e:
        print(f"   ❌ 批量测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, 0, 0

# ==================== 主测试函数 ====================
async def main_test():
    """主测试函数"""
    
    print("\n" + "=" * 60)
    print("开始运行测试...")
    print("=" * 60)
    
    # 1. 运行单个测试
    single_test_result = await run_extractor_test()
    
    # 2. 运行批量测试
    batch_test_result, success_rate, create_new_count, unified_rate = await run_batch_test()
    
    # 综合结果
    overall_result = single_test_result and success_rate > 0
    
    return {
        "single_test": single_test_result,
        "batch_test": batch_test_result,
        "success_rate": success_rate,
        "create_new_count": create_new_count,
        "unified_format_rate": unified_rate,
        "overall": overall_result
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
        
        print(f"单个测试: {'✅ 通过' if results['single_test'] else '❌ 失败'}")
        print(f"批量测试: {'✅ 通过' if results['batch_test'] else '❌ 失败'}")
        print(f"批量成功率: {results['success_rate']:.1%}")
        print(f"CREATE_NEW事件数: {results['create_new_count']}")
        print(f"统一格式比例: {results['unified_format_rate']:.1%}")
        
        if results['overall']:
            print("\n🎉 测试通过！")
            print("统一格式提取器工作正常")
            print("✅ theme_directive 字段生成成功")
            print("✅ 符合统一格式要求")
        else:
            print("\n⚠️  测试失败或部分失败")
            print("需要检查提取器实现或导入路径")
        
        # 保存结果
        results_dir = os.path.join(os.path.dirname(__file__), "..", "data", "results")
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(results_dir, f"final_v2_test_report_{timestamp}.json")
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_root": project_root,
            "test_results": results,
            "import_paths": {
                "project_root": project_root,
                "model_service_path": model_service_path
            },
            "summary": {
                "passed": results['overall'],
                "has_unified_format": results['single_test'],
                "batch_success_rate": results['success_rate'],
                "create_new_events": results['create_new_count']
            }
        }
        
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
PYTHON_EOF
    
    chmod +x scripts/test_final_v2.py
    print_success "Python脚本创建完成"
    
    # 设置环境变量
    print_step "5. 设置环境变量"
    export PYTHONPATH="/Users/admin/Desktop/ai_theme_app:/Users/admin/Desktop/ai_theme_app/model_service:$PYTHONPATH"
    export TEST_MODE=1
    print_success "环境变量设置完成"
    
    # 运行测试
    echo ""
    print_step "6. 运行最终测试 v2"
    echo -e "${YELLOW}注意: 这可能需要几分钟时间...${NC}"
    echo ""
    
    cd "$PROJECT_ROOT"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$SCRIPT_DIR/logs/final_v2_test_$TIMESTAMP.log"
    
    # 运行测试
    echo "运行测试脚本..."
    python "$SCRIPT_DIR/scripts/test_final_v2.py" 2>&1 | tee "$LOG_FILE"
    
    TEST_RESULT=${PIPESTATUS[0]}
    
    # 显示结果
    echo ""
    echo -e "${BLUE}==========================================${NC}"
    if [ $TEST_RESULT -eq 0 ]; then
        echo -e "${GREEN}🎉 测试通过！${NC}"
        echo "统一格式提取器工作正常"
        echo "✅ theme_directive 字段生成成功"
    else
        echo -e "${YELLOW}⚠️  测试完成，但有需要注意的事项${NC}"
        echo "请查看上面的错误信息"
    fi
    
    # 显示报告文件
    echo ""
    LATEST_REPORT=$(ls -1t "$SCRIPT_DIR/data/results"/final_v2_test_report_*.json 2>/dev/null | head -1)
    if [ -n "$LATEST_REPORT" ]; then
        echo -e "${GREEN}📄 测试报告:${NC} $LATEST_REPORT"
        echo ""
        echo "报告摘要:"
        cat "$LATEST_REPORT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'通过: {data[\"summary\"][\"passed\"]}')
print(f'有统一格式: {data[\"summary\"][\"has_unified_format\"]}')
print(f'批量成功率: {data[\"summary\"][\"batch_success_rate\"]:.1%}')
print(f'CREATE_NEW事件: {data[\"summary\"][\"create_new_events\"]}')
" 2>/dev/null || echo "使用: cat $LATEST_REPORT | python -m json.tool"
    fi
    
    echo ""
    echo -e "${GREEN}📋 日志文件:${NC} $LOG_FILE"
    echo -e "${BLUE}==========================================${NC}"
    
    exit $TEST_RESULT
}

# 运行主函数
main
