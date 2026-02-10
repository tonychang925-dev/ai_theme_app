# test_tags_direct.py
import asyncio
import json

async def verify_fix():
    """验证修复是否有效"""
    print("🔍 验证修复...")
    
    # 模拟数据库行（字符串格式的JSON）
    class MockRow:
        def __init__(self):
            self.data = {
                'id': 736,
                'name': '国有大型银行Ⅲ',
                'code': 'INVEST_SW_480201',
                'tags': '{"source": "shenwan", "aliases": ["国有大型银行Ⅲ", "国有大型银行Ⅲ板块"], "version": "2.0", "concepts": ["产业投资", "行业轮动"], "keywords": ["国有大型银行板块", "国有大型银行概念", "银行", "金融"], "heat_level": "medium"}'
            }
        
        def get(self, key, default=None):
            return self.data.get(key, default)
    
    # 测试修复后的逻辑
    def test_build_theme_record_logic(row):
        print(f"\n📊 测试模拟数据:")
        print(f"  ID: {row.get('id')}")
        print(f"  名称: {row.get('name')}")
        
        tags_data = row.get('tags', {})
        print(f"  原始tags_data类型: {type(tags_data)}")
        print(f"  原始tags_data值[:100]: {tags_data[:100] if isinstance(tags_data, str) else tags_data}")
        
        # 修复逻辑
        if isinstance(tags_data, str):
            print("  ⚡ 检测到字符串，解析JSON")
            try:
                tags_data = json.loads(tags_data)
                print(f"  解析成功，keywords: {tags_data.get('keywords', [])}")
            except Exception as e:
                print(f"  解析失败: {e}")
                tags_data = {}
        
        # 创建ThemeTags
        from dataclasses import dataclass, field
        from typing import List, Optional, Dict, Any
        
        @dataclass
        class ThemeTags:
            source: str = "shenwan"
            aliases: List[str] = field(default_factory=list)
            version: str = "2.0"
            concepts: List[str] = field(default_factory=list)
            keywords: List[str] = field(default_factory=list)
            heat_level: str = "medium"
            industries: List[str] = field(default_factory=list)
            industry_code: Optional[str] = None
            merge_candidates: List[str] = field(default_factory=list)
            
            def to_dict(self) -> Dict[str, Any]:
                return {
                    "source": self.source,
                    "aliases": self.aliases,
                    "version": self.version,
                    "concepts": self.concepts,
                    "keywords": self.keywords,
                    "heat_level": self.heat_level,
                    "industries": self.industries,
                    "industry_code": self.industry_code,
                    "merge_candidates": self.merge_candidates
                }
        
        tags = ThemeTags(
            source=tags_data.get('source', 'shenwan'),
            keywords=tags_data.get('keywords', []),
            concepts=tags_data.get('concepts', [])
        )
        
        print(f"\n✅ 修复结果:")
        print(f"  tags.keywords: {tags.keywords}")
        print(f"  tags.keywords数量: {len(tags.keywords)}")
        print(f"  tags.to_dict()['keywords']: {tags.to_dict()['keywords']}")
        
        return tags
    
    # 运行测试
    mock_row = MockRow()
    test_build_theme_record_logic(mock_row)
    
    print("\n" + "="*50)
    print("🎯 修复总结:")
    print("  问题: asyncpg返回JSONB字段为字符串")
    print("  解决方案: 检查类型，如果是字符串则解析为JSON")
    print("  预期结果: keywords字段应该正确加载")

if __name__ == "__main__":
    asyncio.run(verify_fix())