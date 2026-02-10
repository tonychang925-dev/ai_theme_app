#!/usr/bin/env python3
"""
直接测试event_extractor
"""
import asyncio
import sys
import os

print("当前工作目录:", os.getcwd())
print("Python路径:", sys.path)

# 添加当前目录和父目录到路径
sys.path.insert(0, os.getcwd())

# 尝试导入
try:
    # 方法1: 直接导入
    import model_service.service.event_extractor as extractor_module
    print("✅ 导入模块成功")
    
    from model_service.service.event_extractor import AIEventExtractor
    print("✅ 导入类成功")
    
    # 创建模拟解析器
    from unittest.mock import Mock, AsyncMock
    
    mock_parser = Mock()
    mock_parser.parse_news = AsyncMock()
    mock_parser.parse_news.return_value = {
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
    
    # 创建提取器
    extractor = AIEventExtractor(mock_parser)
    print("✅ 创建提取器成功")
    
    async def run_test():
        # 测试数据
        test_data = {
            'news_id': 'direct_test',
            'title': '直接测试',
            'content': '这是完整的测试内容，应该被保存'
        }
        
        print(f"\n📝 测试数据: {test_data['title']}")
        print(f"内容长度: {len(test_data['content'])}字符")
        
        # 执行提取
        result = await extractor.extract_event(test_data)
        
        if result:
            print("✅ 提取成功")
            
            # 检查关键字段
            checks = [
                ('original_data', '原始数据保存'),
                ('data_integrity', '数据完整性标记'),
                ('ai_response', 'AI响应保存'),
            ]
            
            all_good = True
            for field, desc in checks:
                if field in result:
                    print(f"  ✅ {desc}")
                    
                    # 详细检查original_data
                    if field == 'original_data' and 'content' in result[field]:
                        saved_content = result[field]['content']
                        if saved_content == test_data['content']:
                            print(f"    ✅ 完整保存了原始内容 ({len(saved_content)}字符)")
                        else:
                            print(f"    ❌ 内容保存错误")
                            all_good = False
                else:
                    print(f"  ❌ 缺少{desc}")
                    all_good = False
            
            if all_good:
                print("\n🎉 event_extractor.py 修复正确！")
                print("原始内容完整保存功能正常")
                return True
            else:
                print("\n⚠️  部分功能需要检查")
                return False
        else:
            print("❌ 提取返回None")
            return False
    
    # 运行测试
    success = asyncio.run(run_test())
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("\n尝试其他导入方式...")
    
    # 方法2: 直接执行文件
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", """
import asyncio
from unittest.mock import Mock, AsyncMock

async def test():
    try:
        from model_service.service.event_extractor import AIEventExtractor
        
        mock_parser = Mock()
        mock_parser.parse_news = AsyncMock(return_value={
            "event_info": {"summary": "test", "event_type": "test"},
            "theme_discovery_directive": {"action": "CLUSTER"}
        })
        
        extractor = AIEventExtractor(mock_parser)
        result = await extractor.extract_event({
            'news_id': 'test',
            'title': 'test',
            'content': 'test content'
        })
        
        if result and 'original_data' in result:
            print("SUCCESS: original_data exists")
            return True
        else:
            print("FAILED: no original_data")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

asyncio.run(test())
            """],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print("Stderr:", result.stderr)
    except Exception as e:
        print(f"子进程错误: {e}")

except Exception as e:
    print(f"❌ 其他错误: {e}")
    import traceback
    traceback.print_exc()
