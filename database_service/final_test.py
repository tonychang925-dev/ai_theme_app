# final_test.py
"""
最终测试 - 完全独立，不依赖任何现有导入
"""
import sys
import os

print("=" * 60)
print("🚀 最终测试启动")
print("=" * 60)

# 设置工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
print(f"📁 工作目录: {current_dir}")

# 1. 检查文件
print("\n🔍 检查文件...")
files = ["config.py", "factory.py", "managers/memory_manager.py"]
for file in files:
    path = os.path.join(current_dir, file)
    exists = os.path.exists(path)
    print(f"  {file}: {'✅ 存在' if exists else '❌ 不存在'}")
    if not exists:
        print(f"    路径: {path}")

# 2. 使用最直接的方法：创建一个包含所有代码的测试文件
print("\n🔧 创建集成测试...")

test_code = '''
"""
集成测试 - 在一个文件中测试所有功能
"""
import sys
import os
import asyncio

print("=" * 50)
print("集成测试开始")
print("=" * 50)

# 临时添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- 第1部分：模拟配置类 ---
print("\\n1. 创建模拟配置类...")

class DatabaseType:
    MEMORY = 'memory'
    POSTGRESQL = 'postgresql'
    HYBRID = 'hybrid'
    
    def __init__(self, value='memory'):
        self.value = value

class RedisConfig:
    def __init__(self, enabled=False, host='localhost', port=6379, db=0, password=None):
        self.enabled = enabled
        self.host = host
        self.port = port
        self.db = db
        self.password = password

class DatabaseConfig:
    def __init__(self, db_type='memory', **kwargs):
        if isinstance(db_type, str):
            self.db_type = type('obj', (object,), {'value': db_type})()
        else:
            self.db_type = db_type
        
        # Redis配置
        redis_kwargs = kwargs.get('redis', {})
        if isinstance(redis_kwargs, dict):
            self.redis = RedisConfig(**redis_kwargs)
        else:
            self.redis = redis_kwargs
        
        # 其他属性
        self.table_names_config = kwargs.get('table_names_config', {})
        self.postgres_host = kwargs.get('postgres_host', 'localhost')
        self.postgres_port = kwargs.get('postgres_port', 5432)
        self.postgres_database = kwargs.get('postgres_database', 'test_db')
        self.postgres_username = kwargs.get('postgres_username', 'postgres')
        self.postgres_password = kwargs.get('postgres_password', '')

print("✅ 模拟配置类创建完成")

# --- 第2部分：加载并执行factory.py ---
print("\\n2. 加载factory.py...")

try:
    # 读取factory.py内容
    with open('factory.py', 'r', encoding='utf-8') as f:
        factory_content = f.read()
    
    # 修复factory.py中的相对导入
    import_lines = []
    other_lines = []
    
    for line in factory_content.split('\\n'):
        if line.strip().startswith('from .'):
            # 转换相对导入为绝对导入
            fixed_line = line.replace('from .', 'from ')
            import_lines.append(fixed_line)
        elif line.strip().startswith('import'):
            import_lines.append(line)
        else:
            other_lines.append(line)
    
    # 创建修复后的factory代码
    fixed_factory = '\\n'.join(import_lines + other_lines)
    
    # 执行修复后的代码
    exec(fixed_factory, globals())
    
    print("✅ factory.py加载并执行成功")
    
except Exception as e:
    print(f"❌ factory.py加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- 第3部分：测试工厂 ---
print("\\n3. 测试DatabaseManagerFactory...")

async def test_factory():
    print("   创建配置...")
    config = DatabaseConfig(
        db_type='memory',
        redis={'enabled': False}
    )
    
    print(f"   配置: db_type={config.db_type.value}, redis.enabled={config.redis.enabled}")
    
    print("   调用DatabaseManagerFactory.create_manager()...")
    try:
        manager = await DatabaseManagerFactory.create_manager(config)
        print(f"   ✅ 管理器创建成功: {type(manager).__name__}")
        
        # 测试方法
        print("   测试管理器方法...")
        methods_to_test = ['connect', 'health_check', 'get_stats', 'disconnect']
        
        for method_name in methods_to_test:
            if hasattr(manager, method_name):
                try:
                    method = getattr(manager, method_name)
                    if asyncio.iscoroutinefunction(method):
                        result = await method()
                        print(f"      ✅ {method_name}(): {result}")
                    else:
                        result = method()
                        print(f"      ✅ {method_name}(): {result}")
                except Exception as e:
                    print(f"      ⚠️ {method_name}() 执行出错: {e}")
            else:
                print(f"      ❌ {method_name} 方法不存在")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 创建管理器失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- 第4部分：运行测试 ---
print("\\n4. 运行异步测试...")
try:
    success = asyncio.run(test_factory())
    
    if success:
        print("\\n" + "🎉" * 20)
        print("🎉 集成测试成功！")
        print("🎉" * 20)
    else:
        print("\\n❌ 测试失败")
        
except Exception as e:
    print(f"\\n💥 测试运行出错: {e}")
    import traceback
    traceback.print_exc()

print("\\n" + "=" * 50)
print("集成测试结束")
print("=" * 50)
'''

# 写入测试文件
test_file = "integrated_test.py"
with open(test_file, 'w', encoding='utf-8') as f:
    f.write(test_code)

print(f"📄 测试文件创建: {test_file}")

# 3. 运行测试
print("\n▶️ 运行集成测试...")
print("-" * 60)

# 运行测试
import subprocess
result = subprocess.run([sys.executable, test_file], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("标准错误输出:")
    print(result.stderr)

# 4. 清理
print("\n🧹 清理...")
if os.path.exists(test_file):
    os.remove(test_file)
    print(f"✅ 删除临时文件: {test_file}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)