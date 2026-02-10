# check_data_file.py
"""
检查测试数据文件的真实结构
"""
import json
import os

def check_data_file():
    """检查数据文件结构"""
    data_path = "evaluate_service/data/processed/validation_events_enhanced.json"
    
    if not os.path.exists(data_path):
        print(f"❌ 文件不存在: {data_path}")
        return
    
    print(f"检查文件: {data_path}")
    print("=" * 60)
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            print(f"✅ JSON解析成功")
            print(f"数据类型: {type(data)}")
            print(f"数据长度或键值: {len(data) if isinstance(data, list) else list(data.keys())[:10]}")
            
            if isinstance(data, dict):
                print("\n📋 字典结构:")
                for key, value in data.items():
                    print(f"  {key}: {type(value)}")
                    if key == "events" and isinstance(value, list):
                        print(f"    events列表长度: {len(value)}")
                        if value:
                            print(f"    第一个事件: {type(value[0])}")
                            if isinstance(value[0], dict):
                                print(f"    第一个事件的键: {list(value[0].keys())[:10]}")
            elif isinstance(data, list):
                print(f"\n📊 列表结构:")
                print(f"  列表长度: {len(data)}")
                if data:
                    print(f"  第一个元素类型: {type(data[0])}")
                    if isinstance(data[0], dict):
                        print(f"  第一个元素的键: {list(data[0].keys())[:10]}")
                        
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        print("请检查文件格式")
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_data_file()