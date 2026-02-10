#!/bin/bash

# 统一格式提取器全面测试脚本
# 位置: /Users/admin/Desktop/ai_theme_app/evaluate_service/
# 用法: ./run_comprehensive_test.sh

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
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║               统一格式提取器全面测试套件                ║"
    echo "╚══════════════════════════════════════════════════════════╝"
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
    cat > data/test_inputs/simple_cases.json << 'TEST1_EOF'
[
    {
        "news_id": 1001,
        "title": "上海发布元宇宙产业发展行动计划",
        "content": "上海市经信委发布《上海市培育元宇宙新赛道行动方案（2025-2027年）》，提出到2027年元宇宙相关产业规模达到3500亿元。",
        "source": "上海发布",
        "expected_type": "政策发布"
    },
    {
        "news_id": 1002,
        "title": "宁德时代发布新一代麒麟电池",
        "content": "宁德时代发布新一代麒麟电池，体积利用率突破72%，能量密度可达255Wh/kg，续航里程超过1000公里。",
        "source": "财联社",
        "expected_type": "产品发布"
    }
]
TEST1_EOF
    
    cat > data/test_inputs/major_events.json << 'TEST2_EOF'
[
    {
        "news_id": 2001,
        "title": "国务院印发《新一代人工智能发展规划》",
        "content": "国务院近日印发《新一代人工智能发展规划》，提出到2025年我国人工智能核心产业规模超过4000亿元，带动相关产业规模超过5万亿元。",
        "source": "新华社",
        "expected_type": "政策发布",
        "is_major": true
    }
]
TEST2_EOF
    print_success "测试数据创建完成"
    
    # 创建Python测试脚本
    print_step "4. 创建Python测试脚本"
    cat > scripts/test_unified_extractor.py << 'PYTHON_EOF'
#!/usr/bin/env python3
"""
统一格式提取器测试脚本
测试theme_directive字段生成
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
print("统一格式提取器测试")
print(f"项目根目录: {project_root}")
print("=" * 60)

async def test_unified_extractor():
    """测试统一格式提取器"""
    
    try:
        # 导入模块
        print("\n1. 导入模块...")
        from model_service.service.event_extractor import AIEventExtractor
        from model_service.models.news_event import NewsEvent
        print("✅ 成功导入 AIEventExtractor 和 NewsEvent")
        
        # 创建提取器实例
        print("\n2. 创建提取器实例...")
        extractor = AIEventExtractor()
        print("✅ 提取器创建成功")
        
        # 测试数据
        test_cases = [
            {
                'news_id': 1001,
                'title': '上海发布元宇宙产业发展行动计划',
                'content': '上海市经信委发布《上海市培育元宇宙新赛道行动方案（2025-2027年）》，提出到2027年元宇宙相关产业规模达到3500亿元。'
            },
            {
                'news_id': 1002,
                'title': '国务院印发人工智能发展规划',
                'content': '国务院印发《新一代人工智能发展规划》，提出到2025年我国人工智能核心产业规模超过4000亿元。',
                'is_major': True
            }
        ]
        
        results = []
        
        print("\n3. 测试新闻提取...")
        for i, news in enumerate(test_cases, 1):
            print(f"\n   测试案例 {i}: {news['title'][:30]}...")
            
            try:
                # 提取事件
                result = await extractor.extract_event(news)
                
                if result:
                    print(f"      ✅ 提取成功")
                    
                    # 检查必要字段
                    required = ['event_type', 'summary', 'confidence', 'theme_directive']
                    missing = [f for f in required if f not in result]
                    
                    if missing:
                        print(f"      ❌ 缺少字段: {missing}")
                        results.append({"success": False, "error": f"缺少字段: {missing}"})
                        continue
                    
                    # 获取theme_directive
                    directive = result.get('theme_directive', {})
                    
                    print(f"      事件类型: {result.get('event_type')}")
                    print(f"      置信度: {result.get('confidence')}")
                    print(f"      主题指令: {directive.get('action')}")
                    print(f"      指令置信度: {directive.get('confidence')}")
                    
                    # 验证NewsEvent兼容性
                    try:
                        news_event = NewsEvent.from_ai_response(
                            news_db_id=news['news_id'],
                            news_hash_id=f"test_{news['news_id']}",
                            ai_data=result,
                            raw_news=news
                        )
                        print(f"      ✅ NewsEvent兼容性验证通过")
                        print(f"      持久化指令: {news_event.theme_directive.get('action')}")
                    except Exception as e:
                        print(f"      ⚠️  NewsEvent创建失败: {e}")
                    
                    results.append({
                        "success": True,
                        "news_id": news['news_id'],
                        "event_type": result.get('event_type'),
                        "theme_directive": directive
                    })
                    
                else:
                    print(f"      ❌ 提取失败: 返回None")
                    results.append({"success": False, "error": "返回None"})
                    
            except Exception as e:
                print(f"      ❌ 提取错误: {e}")
                results.append({"success": False, "error": str(e)})
        
        # 关闭提取器
        print("\n4. 关闭提取器...")
        await extractor.close()
        print("✅ 提取器关闭成功")
        
        # 生成报告
        print("\n" + "=" * 60)
        print("测试报告")
        print("=" * 60)
        
        total = len(results)
        success = sum(1 for r in results if r['success'])
        
        print(f"总测试案例: {total}")
        print(f"成功: {success}")
        print(f"失败: {total - success}")
        print(f"成功率: {success/total*100:.1f}%")
        
        if success > 0:
            create_new_count = sum(1 for r in results if r.get('success') and r.get('theme_directive', {}).get('action') == 'CREATE_NEW')
            print(f"CREATE_NEW指令数: {create_new_count}")
        
        # 保存结果
        results_dir = os.path.join(os.path.dirname(__file__), "..", "data", "results")
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(results_dir, f"unified_test_report_{timestamp}.json")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total,
            "successful": success,
            "failed": total - success,
            "success_rate": success/total if total > 0 else 0,
            "results": results
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        
        # 返回退出码
        return 0 if success/total >= 0.5 else 1
        
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("请检查:")
        print("1. 确保在正确目录运行")
        print("2. 确保model_service目录存在")
        return 1
    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        return 1

def main():
    """主函数"""
    exit_code = asyncio.run(test_unified_extractor())
    
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("🎉 测试完成！")
    else:
        print("⚠️  测试完成，但有错误")
    print("=" * 60)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
PYTHON_EOF
    
    chmod +x scripts/test_unified_extractor.py
    print_success "Python脚本创建完成"
    
    # 设置环境变量
    print_step "5. 设置环境变量"
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    export TEST_MODE=1
    print_success "环境变量设置完成"
    
    # 运行测试
    echo ""
    print_step "6. 运行统一格式提取器测试"
    echo -e "${YELLOW}注意: 这可能需要几分钟时间...${NC}"
    echo ""
    
    cd "$PROJECT_ROOT"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$SCRIPT_DIR/logs/test_$TIMESTAMP.log"
    
    # 运行测试
    python "$SCRIPT_DIR/scripts/test_unified_extractor.py" 2>&1 | tee "$LOG_FILE"
    
    TEST_RESULT=${PIPESTATUS[0]}
    
    # 显示结果
    echo ""
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
    if [ $TEST_RESULT -eq 0 ]; then
        echo -e "${GREEN}🎉 测试通过！${NC}"
    else
        echo -e "${YELLOW}⚠️  测试完成，但有需要注意的事项${NC}"
    fi
    
    # 显示报告文件
    echo ""
    LATEST_REPORT=$(ls -1t "$SCRIPT_DIR/data/results"/unified_test_report_*.json 2>/dev/null | head -1)
    if [ -n "$LATEST_REPORT" ]; then
        echo -e "${GREEN}📄 测试报告:${NC} $LATEST_REPORT"
        echo ""
        echo "使用以下命令查看报告:"
        echo "cat $LATEST_REPORT | python -m json.tool"
    fi
    
    echo ""
    echo -e "${GREEN}📋 日志文件:${NC} $LOG_FILE"
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
    
    exit $TEST_RESULT
}

# 运行主函数
main
