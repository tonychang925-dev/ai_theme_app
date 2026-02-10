# ai_theme_app/check_config.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.config import settings

print("检查配置加载...")
print("=" * 60)

print(f"ENABLED_SOURCES: {settings.ENABLED_SOURCES}")
print(f"类型: {type(settings.ENABLED_SOURCES)}")
print(f"长度: {len(settings.ENABLED_SOURCES)}")

print("\n所有配置项:")
for key, value in settings.dict().items():
    print(f"  {key}: {value}")

print("\n.env文件路径:", os.path.abspath('.env') if os.path.exists('.env') else "不存在")