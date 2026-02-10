# test_theme_tags.py
import asyncio
import json
from database_service.gateway import DatabaseGateway

async def test_theme_tags():
    """测试题材的tags字段"""
    print("🔍 测试题材tags字段...")
    
    # 初始化DatabaseGateway
    gateway = DatabaseGateway(db_type='postgres')
    
    # 连接数据库
    # （这里需要你已有的连接逻辑）
    
    # 测试查询特定分类的题材
    level2_code = "480200"  # 国有大型银行Ⅱ
    
    print(f"📊 查询分类: {level2_code}")
    
    if hasattr(gateway, 'get_themes_by_category'):
        themes = await gateway.get_themes_by_category(level2_code, level=2, limit=5)
        print(f"✅ 获取到 {len(themes)} 个题材")
        
        for i, theme in enumerate(themes):
            print(f"\n📋 题材 {i+1}:")
            
            # 检查ThemeRecord类型
            if hasattr(theme, 'to_dict'):
                theme_dict = theme.to_dict()
            elif hasattr(theme, '__dict__'):
                theme_dict = theme.__dict__.copy()
                if '_sa_instance_state' in theme_dict:
                    del theme_dict['_sa_instance_state']
            
            print(f"  名称: {theme_dict.get('name')}")
            print(f"  代码: {theme_dict.get('code')}")
            
            tags = theme_dict.get('tags')
            print(f"  tags类型: {type(tags)}")
            print(f"  tags值: {tags}")
            
            if isinstance(tags, str):
                print(f"  tags字符串长度: {len(tags)}")
                try:
                    parsed = json.loads(tags)
                    print(f"  解析后的keywords: {parsed.get('keywords', [])}")
                except:
                    print(f"  无法解析JSON")
            elif isinstance(tags, dict):
                print(f"  keywords: {tags.get('keywords', [])}")
                print(f"  concepts: {tags.get('concepts', [])}")

if __name__ == "__main__":
    asyncio.run(test_theme_tags())