# database_service/tests/streams/test_message_serializer.py
"""
MessageSerializer测试
测试压缩、序列化功能
"""
import json
import zlib
import sys
import os

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
service_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)

def test_message_serializer_creation():
    """测试创建序列化器"""
    try:
        from database_service.streams.utils.message_serializer import MessageSerializer
        
        serializer = MessageSerializer()
        assert serializer is not None
        assert hasattr(serializer, 'serialize')
        assert hasattr(serializer, 'deserialize')
        
        print("✅ MessageSerializer创建成功")
        return True
    except Exception as e:
        print(f"❌ MessageSerializer创建失败: {e}")
        return False

def test_serialize_deserialize():
    """测试序列化和反序列化"""
    try:
        from database_service.streams.utils.message_serializer import MessageSerializer
        
        serializer = MessageSerializer(compress_threshold=50, enable_compression=True)
        
        # 测试小数据（不压缩）
        small_data = {"id": "test", "action": "ping"}
        serialized = serializer.serialize(small_data)
        
        assert isinstance(serialized, bytes)
        assert serialized[0] == 74  # 'J' - JSON
        
        deserialized = serializer.deserialize(serialized)
        assert deserialized["id"] == "test"
        
        print("✅ 小数据序列化/反序列化成功")
        
        # 测试大数据（压缩）
        large_data = {
            "id": "large_data",
            "content": "A" * 1000,  # 1000个字符
            "list": list(range(100))
        }
        serialized = serializer.serialize(large_data)
        
        assert isinstance(serialized, bytes)
        assert serialized[0] == 67  # 'C' - Compressed
        
        deserialized = serializer.deserialize(serialized)
        assert deserialized["id"] == "large_data"
        assert len(deserialized["content"]) == 1000
        
        print("✅ 大数据压缩序列化/反序列化成功")
        
        return True
    except Exception as e:
        print(f"❌ 序列化/反序列化测试失败: {e}")
        return False

def test_disable_compression():
    """测试禁用压缩"""
    try:
        from database_service.streams.utils.message_serializer import MessageSerializer
        
        serializer = MessageSerializer(enable_compression=False)
        
        large_data = {"content": "A" * 2000}
        serialized = serializer.serialize(large_data)
        
        assert serialized[0] == 74  # 'J' - 即使大数据也不压缩
        
        deserialized = serializer.deserialize(serialized)
        assert deserialized["content"] == "A" * 2000
        
        print("✅ 禁用压缩测试成功")
        return True
    except Exception as e:
        print(f"❌ 禁用压缩测试失败: {e}")
        return False

def test_edge_cases():
    """测试边界情况"""
    try:
        from database_service.streams.utils.message_serializer import MessageSerializer
        
        serializer = MessageSerializer()
        
        # 测试空数据
        empty_data = {}
        serialized = serializer.serialize(empty_data)
        deserialized = serializer.deserialize(serialized)
        assert deserialized == {}
        
        # 测试嵌套数据
        nested_data = {
            "user": {
                "name": "测试用户",
                "preferences": {
                    "theme": "dark",
                    "notifications": True
                }
            },
            "list": [1, 2, {"item": "value"}]
        }
        serialized = serializer.serialize(nested_data)
        deserialized = serializer.deserialize(serialized)
        assert deserialized["user"]["name"] == "测试用户"
        assert deserialized["list"][2]["item"] == "value"
        
        print("✅ 边界情况测试成功")
        return True
    except Exception as e:
        print(f"❌ 边界情况测试失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("🧪 MessageSerializer测试套件")
    print("=" * 50)
    
    tests = [
        ("创建测试", test_message_serializer_creation),
        ("序列化测试", test_serialize_deserialize),
        ("压缩测试", test_disable_compression),
        ("边界测试", test_edge_cases),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            print(f"\n📋 {name}:")
            success = test_func()
            status = "✅ 通过" if success else "❌ 失败"
            results.append((name, success))
            print(f"  {status}")
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 50)
    print("📊 测试总结")
    print("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print("-" * 50)
    success_rate = passed / total * 100 if total > 0 else 0
    print(f"总计: {passed}/{total} 通过 ({success_rate:.1f}%)")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)