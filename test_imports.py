#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

try:
    from database_service.config import DatabaseConfig, DatabaseType, init_config
    print("✓ database_service.config imported")
except Exception as e:
    print(f"✗ database_service.config import failed: {e}")

try:
    from database_service.gateway import DatabaseGateway
    print("✓ DatabaseGateway imported")
except Exception as e:
    print(f"✗ DatabaseGateway import failed: {e}")

try:
    from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
    print("✓ UnifiedRedisStreamBus imported")
except Exception as e:
    print(f"✗ UnifiedRedisStreamBus import failed: {e}")

try:
    from database_service.streams.gateway_integration import get_gateway
    print("✓ get_gateway imported")
except Exception as e:
    print(f"✗ get_gateway import failed: {e}")

try:
    from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
    print("✓ NewsStreamHandler imported")
except Exception as e:
    print(f"✗ NewsStreamHandler import failed: {e}")

try:
    from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
    print("✓ NewsStreamProcessor imported")
except Exception as e:
    print(f"✗ NewsStreamProcessor import failed: {e}")

try:
    from database_service.streams.handlers.theme_processor import ThemeProcessor
    print("✓ ThemeProcessor imported")
except Exception as e:
    print(f"✗ ThemeProcessor import failed: {e}")