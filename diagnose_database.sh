#!/bin/bash
# diagnose_database.sh - 完整数据库诊断
echo "🔍 完整数据库诊断"
echo "================="

# 1. 检查PostgreSQL服务状态
echo "1. 检查PostgreSQL服务状态..."
if command -v brew &> /dev/null; then
    echo "   🍺 Homebrew环境检测到"
    brew services list | grep postgresql
elif command -v systemctl &> /dev/null; then
    echo "   🐧 Systemd环境检测到"
    systemctl status postgresql | head -5
else
    echo "   ℹ️  无法检测服务管理器"
fi

# 2. 检查Python环境
echo ""
echo "2. 检查Python环境..."
python --version
pip --version

# 3. 检查asyncpg安装
echo ""
echo "3. 检查asyncpg安装..."
python -c "import asyncpg; print(f'   ✅ asyncpg版本: {asyncpg.__version__}')" 2>/dev/null || echo "   ❌ asyncpg未安装"

# 4. 检查配置
echo ""
echo "4. 检查数据库配置..."
cat theme_service/config.py | grep -A5 -B5 DATABASE_URL

# 5. 直接测试连接
echo ""
echo "5. 直接测试数据库连接..."
cat > /tmp/test_connection.py << 'PYEOF'
import asyncio
import asyncpg
import sys

async def test_connection():
    print("🔌 直接连接测试...")
    
    # 测试多个可能的连接字符串
    test_urls = [
        "postgresql://postgres:zxbzj~925@localhost/stock_data",
        "postgresql://postgres:zxbzj~925@localhost:5432/stock_data",
        "postgresql://postgres@localhost/stock_data",
        "postgresql://localhost/stock_data"
    ]
    
    for url in test_urls:
        print(f"\n尝试连接: {url}")
        try:
            conn = await asyncpg.connect(url)
            print("   ✅ 连接成功!")
            
            # 检查版本
            version = await conn.fetchval('SELECT version()')
            print(f"   数据库版本: {version.split(',')[0]}")
            
            # 检查数据库信息
            db_name = await conn.fetchval('SELECT current_database()')
            db_user = await conn.fetchval('SELECT current_user')
            print(f"   数据库: {db_name}, 用户: {db_user}")
            
            await conn.close()
            return True
            
        except asyncpg.InvalidPasswordError:
            print("   ❌ 密码错误")
        except asyncpg.ConnectionDoesNotExistError:
            print("   ❌ 数据库不存在")
        except asyncpg.ConnectionFailureError:
            print("   ❌ 连接失败")
        except Exception as e:
            print(f"   ❌ 错误: {e}")
    
    print("\n💡 建议解决方案:")
    print("   1. 启动PostgreSQL: brew services start postgresql")
    print("   2. 创建数据库: createdb stock_data")
    print("   3. 重置密码: psql -c \"ALTER USER postgres PASSWORD 'zxbzj~925';\"")
    return False

asyncio.run(test_connection())
PYEOF

python /tmp/test_connection.py

# 6. 检查防火墙和端口
echo ""
echo "6. 检查端口和防火墙..."
if command -v lsof &> /dev/null; then
    echo "   检查5432端口占用:"
    lsof -i :5432 || echo "   5432端口未被占用"
elif command -v netstat &> /dev/null; then
    echo "   检查5432端口占用:"
    netstat -an | grep 5432 || echo "   5432端口未被占用"
fi

echo ""
echo "="*50
echo "诊断完成，请根据输出解决问题"
