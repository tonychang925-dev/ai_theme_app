#!/usr/bin/env python3
"""
修复 database.py 的核心问题
"""
import re

with open("theme_service/database.py", "r") as f:
    content = f.read()

# 备份原文件
with open("theme_service/database.py.backup", "w") as f:
    f.write(content)

print("📝 开始修复 database.py...")

# 修复1: health_check 方法 - 直接使用连接池，而不是 get_connection()
old_health_check_pattern = r'async def health_check\(self\) -> bool:\s*"""数据库健康检查"""\s*try:\s*async with self\.get_connection\(\) as conn:\s*result = await conn\.fetchval\("SELECT 1"\)\s*return result == 1\s*except Exception as e:\s*logger\.error\(f"❌ 数据库健康检查失败: {e}"\)\s*return False'

new_health_check = '''async def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            if not self._connection_pool:
                await self.initialize()
            
            # 直接从连接池获取连接
            async with self._connection_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"❌ 数据库健康检查失败: {e}")
            return False'''

# 使用正则表达式替换
import re
content = re.sub(old_health_check_pattern, new_health_check, content, flags=re.DOTALL)

# 修复2: 修复 get_connection 方法（如果存在）
if "async def get_connection(self):" in content:
    print("⚠️  发现 get_connection 方法，建议移除或修改")
    
    # 替换为简单的连接获取方法
    old_get_connection = '''async def get_connection(self):
        """获取数据库连接（用于上下文管理器）"""
        if not self._connection_pool:
            await self.initialize()
        
        return await self._connection_pool.acquire()'''
    
    new_get_connection = '''async def acquire_connection(self):
        """直接获取数据库连接"""
        if not self._connection_pool:
            await self.initialize()
        return await self._connection_pool.acquire()'''
    
    content = content.replace(old_get_connection, new_get_connection)

# 修复3: 修改所有使用 async with self.get_connection() 的地方
# 查找所有使用 get_connection 的地方
pattern = r'async with self\.get_connection\(\) as'
matches = re.findall(pattern, content)
if matches:
    print(f"⚠️  发现 {len(matches)} 处使用 async with self.get_connection()")
    content = re.sub(r'async with self\.get_connection\(\) as', 'async with self._connection_pool.acquire() as', content)

# 修复4: 添加简单的连接获取方法（如果不存在）
if "async def acquire_connection" not in content:
    # 在 class 中添加方法
    class_end_pattern = r'class ThemeDatabase.*?:'
    match = re.search(class_end_pattern, content)
    if match:
        # 在第一个方法前插入
        method_pattern = r'\s+async def'
        method_match = re.search(method_pattern, content[match.end():])
        if method_match:
            insert_pos = match.end() + method_match.start()
            new_method = '''
    async def acquire_connection(self):
        """获取数据库连接"""
        if not self._connection_pool:
            await self.initialize()
        return await self._connection_pool.acquire()
    
    async def release_connection(self, conn):
        """释放数据库连接"""
        if self._connection_pool:
            await self._connection_pool.release(conn)'''
            
            content = content[:insert_pos] + new_method + content[insert_pos:]

# 修复5: 确保 initialize 方法正确
if "async def initialize" in content:
    print("✅ initialize 方法已存在")
else:
    # 添加 initialize 方法
    content = content.replace(
        "def __init__(self, database_url: str):",
        '''def __init__(self, database_url: str):
        self.database_url = database_url
        self._connection_pool = None
    
    async def initialize(self) -> bool:
        """初始化数据库连接池"""
        try:
            if not self._connection_pool:
                self._connection_pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=5,
                    max_size=20
                )
                logger.info("✅ 数据库连接池初始化成功")
                return True
        except Exception as e:
            logger.error(f"❌ 数据库连接池初始化失败: {e}")
        return False'''
    )

# 写入修复后的文件
with open("theme_service/database.py", "w") as f:
    f.write(content)

print("✅ database.py 修复完成")
print("📋 修复内容:")
print("   1. 修复 health_check 方法 - 直接使用连接池")
print("   2. 修复/移除 get_connection 方法")
print("   3. 添加 acquire_connection/release_connection 方法")
print("   4. 确保 initialize 方法存在")

# 验证修复
print("\n🔍 验证修复结果...")
with open("theme_service/database.py", "r") as f:
    fixed_content = f.read()
    
# 检查关键方法是否存在
checks = [
    ("health_check", "async def health_check" in fixed_content),
    ("acquire_connection", "async def acquire_connection" in fixed_content),
    ("initialize", "async def initialize" in fixed_content),
    ("async with self.get_connection", "async with self.get_connection()" not in fixed_content),
]

print("\n验证结果:")
for method, exists in checks:
    status = "✅" if exists else "❌"
    print(f"   {status} {method}")

print("\n🎉 修复完成，现在测试数据库连接...")
