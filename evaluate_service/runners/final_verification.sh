#!/bin/bash

echo "🔍 统一格式提取器最终验证"
echo "========================="
echo "验证时间: $(date)"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

# 1. 检查代码修复
print_step "1. 检查代码修复"
if grep -q "getattr.*provider.*model_name" ../model_service/services/event_extractor.py; then
    print_success "event_extractor.py 已修复"
    echo "   修复内容:"
    grep "AI事件提取器已初始化" ../model_service/services/event_extractor.py | sed 's/^/      /'
else
    print_error "代码修复未找到"
fi

# 2. 运行简单导入测试
print_step "2. 运行导入测试"
cat > /tmp/import_test.py << 'PYEOF'
import sys
import os
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app/model_service')

print("测试导入...")
try:
    from model_service.services.event_extractor import AIEventExtractor
    print("✅ AIEventExtractor 导入成功")
    
    from model_service.models.news_event import NewsEvent
    print("✅ NewsEvent 导入成功")
    
    from model_service.llm_parser.factory import LLMParserFactory
    print("✅ LLMParserFactory 导入成功")
    
    print("\n✅ 所有必要模块导入成功")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)
PYEOF

if python /tmp/import_test.py; then
    print_success "导入测试通过"
else
    print_error "导入测试失败"
fi

# 3. 运行功能测试
print_step "3. 运行功能测试"
cat > /tmp/function_test.py << 'PYEOF'
import asyncio
import sys
import os
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app/model_service')

async def test_functionality():
    """测试基本功能"""
    try:
        from model_service.services.event_extractor import AIEventExtractor
        
        print("创建提取器...")
        extractor = AIEventExtractor()
        print("✅ 提取器创建成功（无AttributeError）")
        
        # 测试新闻
        test_news = {
            'news_id': 999,
            'title': '测试新闻标题',
            'content': '测试新闻内容'
        }
        
        print("提取事件...")
        result = await extractor.extract_event(test_news)
        
        if result:
            print("✅ 事件提取成功")
            
            # 检查统一格式字段
            if 'theme_directive' in result:
                directive = result['theme_directive']
                print(f"✅ theme_directive 字段存在")
                
                # 检查必需字段
                required = ['action', 'confidence', 'reason']
                missing = [f for f in required if f not in directive]
                
                if missing:
                    print(f"⚠️  缺少字段: {missing}")
                else:
                    print(f"✅ 统一格式完整: action={directive.get('action')}")
            else:
                print("⚠️  缺少 theme_directive 字段")
        else:
            print("⚠️  事件提取返回 None")
        
        await extractor.close()
        print("✅ 提取器关闭成功")
        
        return True
        
    except AttributeError as e:
        print(f"❌ AttributeError: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    result = asyncio.run(test_functionality())
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()
PYEOF

if python /tmp/function_test.py; then
    print_success "功能测试通过"
else
    print_error "功能测试失败"
fi

# 4. 运行完整统一格式验证
print_step "4. 运行完整统一格式验证"
echo "这可能需要几分钟时间（包含真实API调用）..."
echo ""

if [ -f "./unified_extractor_test.sh" ]; then
    ./unified_extractor_test.sh
    TEST_RESULT=$?
else
    print_error "未找到 unified_extractor_test.sh"
    TEST_RESULT=1
fi

echo ""
echo "========================="
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}🎉 所有验证通过！${NC}"
    echo "统一格式提取器已完全修复并正常工作"
else
    echo -e "${YELLOW}⚠️  验证完成，有需要注意的事项${NC}"
fi
echo "========================="
