#!/usr/bin/env python3
"""
测试服务是否准备好
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.getcwd())

print("🧪 测试 theme_service 准备状态")
print("=" * 50)

tests = [
    {
        "name": "配置模块",
        "import": "from theme_service.config import settings",
        "check": lambda: f"端口: {settings.PORT}, 模式: {settings.INTEGRATION_MODE}"
    },
    {
        "name": "数据库模块",
        "import": "from theme_service.database import ThemeDatabase",
        "check": lambda: "✅ 数据库类可用"
    },
    {
        "name": "AI客户端",
        "import": "from theme_service.services.ai_client import AIThemeClient",
        "check": lambda: "✅ AI客户端类可用"
    },
    {
        "name": "主题发现引擎",
        "import": "from theme_service.services.theme_discovery import ThemeDiscoveryEngine",
        "check": lambda: "✅ 主题发现引擎可用"
    },
    {
        "name": "FastAPI应用",
        "import": "from theme_service.app import app",
        "check": lambda: f"✅ 应用: {app.title}, 版本: {app.version}"
    },
    {
        "name": "主题映射器",
        "import": "from theme_service.services.theme_mapper import ThemeMapper",
        "check": lambda: "✅ 主题映射器可用"
    }
]

all_passed = True
for test in tests:
    try:
        exec(test["import"])
        result = test["check"]()
        print(f"✅ {test['name']}: {result}")
    except Exception as e:
        print(f"❌ {test['name']}: 失败 - {str(e)[:50]}...")
        all_passed = False

print("\n" + "=" * 50)
if all_passed:
    print("🎉 所有测试通过！theme_service 已准备好")
    print("\n✅ 现在可以启动服务:")
    print("   ./start_theme_service.sh")
else:
    print("⚠️  有测试失败，需要先修复问题")
    print("\n🔧 建议检查导入路径和模块依赖")
print("=" * 50)
