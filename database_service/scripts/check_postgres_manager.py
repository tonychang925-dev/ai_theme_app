# scripts/check_postgres_manager.py
"""
检查Postgres管理器结构
"""
import sys
import os
import inspect

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
database_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(database_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, database_dir)

print("🔍 检查PostgresDatabaseManager结构")
print("="*60)

try:
    from managers.postgres_manager import PostgresDatabaseManager
    
    print(f"✅ PostgresDatabaseManager 导入成功")
    print(f"   类名: {PostgresDatabaseManager.__name__}")
    
    # 查看类的文档
    if PostgresDatabaseManager.__doc__:
        print(f"   文档: {PostgresDatabaseManager.__doc__[:100]}...")
    
    # 获取所有方法
    methods = []
    for name, method in inspect.getmembers(PostgresDatabaseManager):
        if not name.startswith('_') and callable(method):
            methods.append(name)
    
    print(f"\n📋 现有方法 ({len(methods)}个):")
    for i, method in enumerate(sorted(methods), 1):
        print(f"  {i:2d}. {method}")
        if i >= 30:
            print(f"  ... 还有 {len(methods)-30} 个方法")
            break
    
    # 检查是否有新闻相关方法
    news_methods = [m for m in methods if 'news' in m.lower()]
    if news_methods:
        print(f"\n✅ 找到新闻相关方法: {', '.join(news_methods)}")
    else:
        print(f"\n❌ 没有找到新闻相关方法，需要扩展")
        
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()