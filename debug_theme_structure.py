#!/usr/bin/env python3
"""
调试脚本 - 检查ThemeRecord的实际结构
"""
import asyncio
import inspect

async def debug_theme_structure():
    try:
        # 导入数据库组件
        from database_service.config import get_config
        from database_service.memory_manager import MemoryDatabaseManager
        
        # 创建数据库连接
        config = get_config()
        db_manager = MemoryDatabaseManager(config)
        await db_manager.connect()
        
        print("🔍 检查ThemeRecord结构:")
        print("="*60)
        
        # 获取一个主题记录
        themes = await db_manager.get_all_active_themes(limit=1)
        if themes:
            theme = themes[0]
            
            # 方法1：查看对象属性
            print("1. ThemeRecord对象属性:")
            print(f"   类型: {type(theme)}")
            print(f"   属性列表: {dir(theme)}")
            
            # 方法2：查看是否有to_dict方法
            if hasattr(theme, 'to_dict'):
                theme_dict = theme.to_dict()
                print(f"\n2. to_dict() 结果:")
                for key, value in theme_dict.items():
                    print(f"   {key}: {value}")
            else:
                print(f"\n2. 对象属性直接访问:")
                # 尝试常见属性
                attrs_to_check = ['id', 'name', 'description', 'keywords', 
                                 'event_count', 'created_at', 'updated_at']
                for attr in attrs_to_check:
                    if hasattr(theme, attr):
                        value = getattr(theme, attr)
                        print(f"   {attr}: {value}")
        
        # 方法3：查看数据库表结构
        print(f"\n3. 检查数据库表结构:")
        try:
            # 检查数据库管理器的方法
            print("   可用的主题相关方法:")
            for method_name in dir(db_manager):
                if 'theme' in method_name.lower():
                    print(f"   - {method_name}")
        except Exception as e:
            print(f"   检查表结构失败: {e}")
        
        await db_manager.disconnect()
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_theme_structure())
