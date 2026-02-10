#!/usr/bin/env python3
"""
测试event_extractor.py修复 - 使用正确路径
"""
import os
import sys
import asyncio
from unittest.mock import Mock, AsyncMock

print("当前目录:", os.getcwd())
print("Python路径:", sys.path[:2])

# 添加当前目录到Python路径
sys.path.insert(0, os.getcwd())

# 检查文件是否存在
file_path = "model_service/services/event_extractor.py"
print(f"\n检查文件: {file_path}")
print(f"文件存在: {os.path.exists(file_path)}")

if not os.path.exists(file_path):
    print("❌ 文件不存在！")
    sys.exit(1)

# 直接读取文件内容检查修复
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"文件大小: {len(content)} 字符")

# 检查关键修复
checks = [
    ("original_data字段", "'original_data'" in content or '"original_data"' in content),
    ("保存完整content", "content': content" in content or '"content": content' in content),
    ("data_integrity字段", "'data_integrity'" in content or '"data_integrity"' in content),
    ("ai_response字段", "'ai_response'" in content or '"ai_response"' in content),
    ("event_result变量", "event_result = {" in content),
    ("enhancement_ratio计算", "enhancement_ratio" in content),
]

print("\n🔍 修复检查:")
all_passed = True
for check_name, passed in checks:
    status = "✅" if passed else "❌"
    print(f"  {status} {check_name}")
    if not passed:
        all_passed = False

# 显示关键代码部分
print("\n🔍 关键代码预览:")
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'original_data' in line.lower() and 'content' in line.lower():
        start = max(0, i-3)
        end = min(len(lines), i+8)
        print(f"\noriginal_data部分 (第{i+1}行附近):")
        for j in range(start, end):
            prefix = ">>>" if j == i else "   "
            print(f"{prefix} {j+1:3d}: {lines[j]}")
        break

async def test_functionality():
    """测试功能"""
    print("\n🔬 功能测试:")
    print("-"*60)
    
    try:
        # 导入模块
        from model_service.services.event_extractor import AIEventExtractor
        
        print("✅ 成功导入AIEventExtractor")
        
        # 创建模拟解析器
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock()
        
        # 模拟AI响应
        mock_response = {
            "event_info": {
                "event_type": "技术突破",
                "summary": "测试摘要",
                "impact_industries": ["人工智能"],
                "direction": "利好",
                "confidence": 0.9
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.85,
                "reason": "测试"
            }
        }
        mock_parser.parse_news.return_value = mock_response
        
        # 创建提取器
        extractor = AIEventExtractor(mock_parser)
        print("✅ 创建提取器成功")
        
        # 测试数据
        test_content = "这是完整的测试内容，应该被完整保存。"
        test_news = {
            'news_id': 'test_001',
            'title': '测试标题',
            'content': test_content
        }
        
        print(f"\n📝 测试数据:")
        print(f"  标题: {test_news['title']}")
        print(f"  内容: {test_news['content']}")
        print(f"  内容长度: {len(test_content)}字符")
        
        # 执行提取
        result = await extractor.extract_event(test_news)
        
        if not result:
            print("❌ 提取返回None")
            return False
        
        print(f"\n✅ 提取成功")
        print(f"返回字段: {list(result.keys())}")
        
        # 检查关键字段
        key_fields = ['original_data', 'data_integrity', 'ai_response']
        for field in key_fields:
            if field in result:
                print(f"  ✅ 有{field}字段")
            else:
                print(f"  ❌ 缺少{field}字段")
                return False
        
        # 检查原始内容保存
        if 'original_data' in result:
            od = result['original_data']
            if 'content' in od:
                saved_content = od['content']
                if saved_content == test_content:
                    print(f"  ✅ 完整保存了原始内容 ({len(saved_content)}字符)")
                else:
                    print(f"  ❌ 保存的内容不匹配")
                    return False
        
        # 验证原始内容 ≠ AI摘要
        if result.get('summary') != test_content:
            print("  ✅ 原始内容与AI摘要不同")
        else:
            print("  ❌ 原始内容与AI摘要相同")
            return False
        
        print("\n🎉 功能测试通过！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("\n" + "="*70)
    print("🧪 event_extractor.py 修复验证测试")
    print("="*70)
    
    # 检查文件修复
    if not all_passed:
        print("⚠️  文件修复检查未通过")
        return 1
    
    # 运行功能测试
    success = await test_functionality()
    
    print("\n" + "="*70)
    if success:
        print("🎉 event_extractor.py 修复验证完全通过！")
        print("\n✅ 可以进入下一步: 修改 deepseek_parser.py")
        return 0
    else:
        print("⚠️  event_extractor.py 功能测试失败")
        print("🔧 请检查代码实现")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
