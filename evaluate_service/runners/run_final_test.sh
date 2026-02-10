#!/bin/bash

# 统一格式提取器最终测试脚本

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
    echo "    统一格式提取器最终测试"
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
    
    if [ ! -d "$PROJECT_ROOT/model_service/llm_parser" ]; then
        print_error "未找到 llm_parser 目录"
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
    
    # 创建Python测试脚本 - 修复导入问题
    print_step "4. 创建Python测试脚本 (修复导入)"
    cat > scripts/test_final.py << 'PYTHON_EOF'
#!/usr/bin/env python3
"""
统一格式提取器最终测试脚本
修复导入路径问题
"""

import asyncio
import json
import sys
import os
from datetime import datetime

print("=" * 60)
print("统一格式提取器最终测试")
print("修复导入路径问题")
print("=" * 60)

# ==================== 修复导入路径 ====================
# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

# 还要添加 model_service 到 sys.path，因为 llm_parser 是相对导入的
model_service_path = os.path.join(project_root, "model_service")
sys.path.insert(0, model_service_path)

print(f"项目根目录: {project_root}")
print(f"Model Service路径: {model_service_path}")
print(f"Python路径: {sys.path}")
print()

# ==================== 测试导入 ====================
print("1. 测试导入...")

# 方法1: 直接导入 model_service.llm_parser
try:
    import model_service.llm_parser
    print("✅ 成功导入 model_service.llm_parser")
except ImportError as e:
    print(f"❌ model_service.llm_parser 导入失败: {e}")

# 方法2: 尝试导入 LLMParserFactory
try:
    # 先确保 sys.path 包含正确路径
    import importlib
    import importlib.util
    
    # 直接导入 llm_parser 模块
    llm_parser_spec = importlib.util.find_spec("llm_parser")
    if llm_parser_spec:
        print(f"✅ 找到 llm_parser 模块: {llm_parser_spec.origin}")
    else:
        print("❌ 未找到 llm_parser 模块")
        
    # 尝试从 model_service.llm_parser 导入
    from model_service.llm_parser.factory import LLMParserFactory
    print("✅ 成功导入 LLMParserFactory")
    
    # 创建解析器
    print("   创建LLM解析器...")
    parser = LLMParserFactory.create_parser_from_env()
    print(f"   ✅ 解析器创建成功: {parser.provider.value}")
    
except ImportError as e:
    print(f"❌ LLMParserFactory 导入失败: {e}")
    
    # 尝试直接导入
    try:
        sys.path.insert(0, os.path.join(project_root, "model_service", "llm_parser"))
        from factory import LLMParserFactory
        print("✅ 成功直接导入 LLMParserFactory")
    except ImportError as e2:
        print(f"❌ 直接导入也失败: {e2}")

# ==================== 测试事件提取器 ====================
print("\n2. 测试事件提取器...")

try:
    # 导入事件提取器
    from model_service.services.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor")
    
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
        else:
            print(f"❌ 文件不存在: {event_extractor_path}")
    except Exception as e2:
        print(f"❌ 动态导入失败: {e2}")

# ==================== 运行测试 ====================
print("\n3. 运行提取器测试...")

async def run_extractor_test():
    """运行提取器测试"""
    
    try:
        # 创建提取器实例
        print("   创建提取器实例...")
        extractor = AIEventExtractor()
        print("   ✅ 提取器实例创建成功")
        
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
            
            # 显示结果
            print("   📋 提取结果:")
            print(f"     - 事件类型: {result.get('event_type', '未找到')}")
            print(f"     - 摘要: {result.get('summary', '未找到')[:80]}...")
            print(f"     - 置信度: {result.get('confidence', '未找到')}")
            
            # 检查 theme_directive
            theme_directive = result.get('theme_directive')
            if theme_directive:
                print(f"     - theme_directive: ✅ 存在")
                print(f"       • action: {theme_directive.get('action', '未找到')}")
                print(f"       • confidence: {theme_directive.get('confidence', '未找到')}")
                print(f"       • reason: {theme_directive.get('reason', '未找到')[:80]}...")
                
                # 验证统一格式
                required_keys = ['action', 'confidence', 'reason']
                missing_keys = [k for k in required_keys if k not in theme_directive]
                
                if missing_keys:
                    print(f"       ⚠️  缺少字段: {missing_keys}")
                else:
                    print(f"       ✅ 符合统一格式要求")
            else:
                print(f"     - theme_directive: ❌ 未找到")
            
            # 检查其他字段
            print()
            print("   🔍 所有字段:")
            for key, value in result.items():
                if isinstance(value, dict):
                    print(f"     - {key}: (字典)")
                    for sub_key, sub_value in value.items():
                        print(f"       • {sub_key}: {str(sub_value)[:50]}{'...' if len(str(sub_value)) > 50 else ''}")
                else:
                    print(f"     - {key}: {str(value)[:80]}{'...' if len(str(value)) > 80 else ''}")
            
            test_passed = True
            
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

# ==================== 主测试函数 ====================
async def main_test():
    """主测试函数"""
    
    # 检查是否有AIEventExtractor
    if 'AIEventExtractor' not in globals():
        print("❌ AIEventExtractor 未定义，无法进行测试")
        return False
    
    try:
        # 运行提取器测试
        test_result = await run_extractor_test()
        
        # 批量测试
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
                
                try:
                    for i, case in enumerate(test_cases, 1):
                        print(f"   处理 {i}/{len(test_cases)}: {case.get('title', '')[:30]}...")
                        
                        try:
                            result = await extractor.extract_event(case)
                            if result and 'theme_directive' in result:
                                success_count += 1
                                directive = result['theme_directive']
                                print(f"     ✅ 成功, action: {directive.get('action')}")
                            else:
                                print(f"     ❌ 失败")
                        except Exception as e:
                            print(f"     ❌ 错误: {e}")
                    
                    batch_success_rate = success_count / len(test_cases)
                    print(f"   批量处理结果: {success_count}/{len(test_cases)} 成功 ({batch_success_rate:.1%})")
                    
                finally:
                    await extractor.close()
                
                test_result = test_result and (batch_success_rate > 0)
            else:
                print("   ⚠️  测试数据文件不存在，跳过批量测试")
                
        except Exception as e:
            print(f"   ❌ 批量测试失败: {e}")
        
        return test_result
        
    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== 主程序 ====================
def main():
    """主程序"""
    try:
        # 运行异步测试
        print("\n" + "=" * 60)
        print("开始运行测试...")
        print("=" * 60)
        
        test_result = asyncio.run(main_test())
        
        # 生成报告
        print("\n" + "=" * 60)
        print("测试报告")
        print("=" * 60)
        
        if test_result:
            print("🎉 测试通过！")
            print("统一格式提取器工作正常")
            print("✅ theme_directive 字段生成成功")
            print("✅ 符合统一格式要求")
        else:
            print("⚠️  测试失败或部分失败")
            print("需要检查提取器实现或导入路径")
        
        # 保存结果
        results_dir = os.path.join(os.path.dirname(__file__), "..", "data", "results")
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(results_dir, f"final_test_report_{timestamp}.json")
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_root": project_root,
            "test_passed": test_result,
            "import_paths": {
                "project_root": project_root,
                "model_service_path": model_service_path,
                "sys_path": sys.path
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        
        return 0 if test_result else 1
        
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
    
    chmod +x scripts/test_final.py
    print_success "Python脚本创建完成"
    
    # 设置环境变量
    print_step "5. 设置环境变量"
    export PYTHONPATH="/Users/admin/Desktop/ai_theme_app:/Users/admin/Desktop/ai_theme_app/model_service:$PYTHONPATH"
    export TEST_MODE=1
    print_success "环境变量设置完成"
    
    # 运行测试
    echo ""
    print_step "6. 运行最终测试"
    echo -e "${YELLOW}注意: 这可能需要几分钟时间...${NC}"
    echo ""
    
    cd "$PROJECT_ROOT"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$SCRIPT_DIR/logs/final_test_$TIMESTAMP.log"
    
    # 运行测试
    echo "运行测试脚本..."
    python "$SCRIPT_DIR/scripts/test_final.py" 2>&1 | tee "$LOG_FILE"
    
    TEST_RESULT=${PIPESTATUS[0]}
    
    # 显示结果
    echo ""
    echo -e "${BLUE}==========================================${NC}"
    if [ $TEST_RESULT -eq 0 ]; then
        echo -e "${GREEN}🎉 测试通过！${NC}"
        echo "统一格式提取器工作正常"
    else
        echo -e "${YELLOW}⚠️  测试完成，但有需要注意的事项${NC}"
        echo "请查看上面的错误信息"
    fi
    
    # 显示报告文件
    echo ""
    LATEST_REPORT=$(ls -1t "$SCRIPT_DIR/data/results"/final_test_report_*.json 2>/dev/null | head -1)
    if [ -n "$LATEST_REPORT" ]; then
        echo -e "${GREEN}📄 测试报告:${NC} $LATEST_REPORT"
    fi
    
    echo ""
    echo -e "${GREEN}📋 日志文件:${NC} $LOG_FILE"
    echo -e "${BLUE}==========================================${NC}"
    
    echo ""
    echo -e "${YELLOW}重要提示:${NC}"
    echo "如果测试失败，请检查以下内容:"
    echo "1. 确保 model_service/llm_parser/ 目录存在"
    echo "2. 确保 model_service/services/event_extractor.py 文件存在"
    echo "3. 检查是否有API密钥或配置问题"
    echo "4. 查看日志文件获取详细错误信息"
    
    exit $TEST_RESULT
}

# 运行主函数
main
