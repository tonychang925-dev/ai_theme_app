#!/usr/bin/env python3
"""
测试主题保存功能
"""
import asyncio
import sys
sys.path.append('.')

async def test_theme_save():
    from theme_service.config import settings
    from theme_service.database import ThemeDatabase
    
    db = ThemeDatabase(settings.DATABASE_URL)
    await db.initialize()
    
    # 测试保存主题
    test_theme = {
        "name": "人工智能测试主题",
        "keywords": ["AI", "人工智能", "机器学习"],
        "discovery_source": "test_save",
        "confidence": 0.85
    }
    
    theme_id = await db.save_theme(test_theme)
    print(f"保存主题结果: ID={theme_id}")
    
    # 验证保存
    if theme_id:
        themes = await db.get_themes_by_status("active", 5)
        print(f"找到 {len(themes)} 个主题:")
        for theme in themes[:3]:
            print(f"  - {theme['name']} (ID: {theme['id']})")
    
    await db.close()

asyncio.run(test_theme_save())
