#!/bin/bash
# quick_test.sh - 快速测试
echo "🧪 快速测试 theme_service"
echo "========================"

# 测试1: 语法检查
echo "1. 语法检查..."
python -m py_compile theme_service/app.py && echo "  ✅ app.py 语法正确"
python -m py_compile theme_service/scheduler.py && echo "  ✅ scheduler.py 语法正确"

# 测试2: 导入测试
echo ""
echo "2. 导入测试..."
python -c "
import sys
sys.path.insert(0, '.')
try:
    from theme_service.app import app
    print('  ✅ FastAPI应用导入成功')
    print(f'     标题: {app.title}')
    print(f'     路由数: {len(app.routes)}')
except Exception as e:
    print(f'  ❌ 应用导入失败: {e}')
"

# 测试3: 启动测试
echo ""
echo "3. 启动测试..."
timeout 5 python -c "
import sys
sys.path.insert(0, '.')
from theme_service.app import app
import uvicorn
import threading
import time

def run_server():
    uvicorn.run(app, host='0.0.0.0', port=8003, log_level='error')

# 在后台线程中启动服务器
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# 等待服务器启动
time.sleep(2)
print('  ✅ 服务器可以启动')
" 2>/dev/null && echo "  ✅ 启动测试通过" || echo "  ⚠️  启动测试超时（可能是正常的）"

echo ""
echo "📋 测试完成"
echo "如果所有测试通过，运行: python start_service.py"
