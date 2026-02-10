#!/usr/bin/env python3
"""
修复版启动脚本 - 避免导入问题
"""
import os
import sys

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, ".."))

# 导入并启动服务
try:
    from app import app
    import uvicorn
    
    print("🚀 启动 theme_service...")
    print(f"当前目录: {current_dir}")
    print(f"Python路径: {sys.path[:2]}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请检查依赖是否安装: pip install fastapi uvicorn")
    sys.exit(1)
except Exception as e:
    print(f"❌ 启动失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
