# theme_service/matcher/theme_matcher.py
"""
本地题材匹配引擎基础框架
从数据库加载题材库并建立内存索引
"""
import asyncio
import asyncpg
import logging
from typing import List, Dict, Any, Set
from collections import defaultdict
import jieba
import json

logger = logging.getLogger(__name__)

class ThemeMatcher:
    """本地题材匹配引擎"""
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or "postgresql://postgres:zxbzj~925@localhost/stock_data"
        self.pool = None
        
        # 内存索引
        self.theme_by_id = {}  # {id: theme_info}
        self.keyword_index = defaultdict(list)  # {keyword: [theme_ids]}
        self.name_index = {}  # {name: theme_id}
        
        # 加载状态
        self.is_initialized = False
    
    async def initialize(self):
        """初始化：从数据库加载题材库并建立内存索引"""
        if self.is_initialized:
            return True
        
        logger.info("🔄 正在加载题材库到内存...")
        
        try:
            # 连接数据库
            self.pool = await asyncpg.create_pool(self.db_url, min_size=2, max_size=5)
            
            async with self.pool.acquire() as conn:
                # 加载所有活跃的标准题材
                themes = await conn.fetch("""
                    SELECT 
                        id, name, keywords, merge_keywords,
                        category, category_path, description,
                        heat_score, discovery_confidence
                    FROM theme_master
                    WHERE status = 'active' 
                      AND is_standard_theme = TRUE
                    ORDER BY heat_score DESC
                """)
                
                # 构建内存索引
                for theme in themes:
                    theme_id = theme['id']
                    theme_dict = dict(theme)
                    
                    # 存储主题信息
                    self.theme_by_id[theme_id] = theme_dict
                    self.name_index[theme['name']] = theme_id
                    
                    # 索引名称
                    for keyword in self._extract_keywords(theme['name']):
                        self.keyword_index[keyword].append(theme_id)
                    
                    # 索引关键词
                    if theme['keywords']:
                        for keyword in theme['keywords']:
                            if keyword:  # 确保不是空字符串
                                self.keyword_index[keyword].append(theme_id)
                    
                    # 索引合并关键词（用于去重）
                    if theme['merge_keywords']:
                        for keyword in theme['merge_keywords']:
                            if keyword:
                                self.keyword_index[keyword].append(theme_id)
                
                logger.info(f"✅ 题材库加载完成: {len(self.theme_by_id)} 个主题")
                logger.info(f"✅ 关键词索引: {len(self.keyword_index)} 个关键词")
                
                self.is_initialized = True
                return True
                
        except Exception as e:
            logger.error(f"❌ 题材库加载失败: {e}")
            return False
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词（中文分词）"""
        if not text:
            return []
        
        # 使用jieba分词
        words = jieba.lcut(text)
        
        # 过滤：只保留2个字符以上的中文词
        keywords = []
        for word in words:
            if len(word) >= 2 and all('\u4e00' <= char <= '\u9fff' for char in word):
                keywords.append(word)
        
        return list(set(keywords))  # 去重
    
    async def match_by_keywords(self, keywords: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """通过关键词匹配题材"""
        if not self.is_initialized:
            await self.initialize()
        
        score_map = defaultdict(float)
        
        for keyword in keywords:
            if keyword in self.keyword_index:
                for theme_id in self.keyword_index[keyword]:
                    # 基础得分：关键词匹配
                    score_map[theme_id] += 1.0
                    
                    # 增强得分：完全匹配名称
                    theme = self.theme_by_id[theme_id]
                    if keyword == theme['name']:
                        score_map[theme_id] += 2.0
        
        # 排序并返回结果
        sorted_themes = sorted(
            score_map.items(),
            key=lambda x: (x[1], self.theme_by_id[x[0]]['heat_score']),
            reverse=True
        )[:limit]
        
        results = []
        for theme_id, score in sorted_themes:
            theme = self.theme_by_id[theme_id]
            results.append({
                'theme_id': theme_id,
                'theme_name': theme['name'],
                'category_path': theme['category_path'],
                'match_score': score,
                'heat_score': theme['heat_score'],
                'keywords': theme['keywords'][:5]  # 前5个关键词
            })
        
        return results
    
    async def find_theme_by_name(self, name: str) -> Dict[str, Any]:
        """通过名称精确查找题材"""
        if not self.is_initialized:
            await self.initialize()
        
        if name in self.name_index:
            theme_id = self.name_index[name]
            return self.theme_by_id[theme_id]
        
        # 模糊匹配
        for theme_name, theme_id in self.name_index.items():
            if name in theme_name or theme_name in name:
                return self.theme_by_id[theme_id]
        
        return None
    
    async def close(self):
        """关闭连接"""
        if self.pool:
            await self.pool.close()
            self.is_initialized = False

# 快速测试函数
async def test_theme_matcher():
    """测试题材匹配引擎"""
    print("🧪 测试本地题材匹配引擎...")
    
    matcher = ThemeMatcher()
    
    try:
        # 初始化
        if not await matcher.initialize():
            print("❌ 初始化失败")
            return
        
        # 测试1：关键词匹配
        test_keywords = ["人工智能", "芯片", "新能源"]
        print(f"\n🔍 测试关键词匹配: {test_keywords}")
        
        matches = await matcher.match_by_keywords(test_keywords, limit=5)
        for i, match in enumerate(matches, 1):
            print(f"  {i}. {match['theme_name']} (得分: {match['match_score']:.1f})")
        
        # 测试2：名称查找
        print(f"\n🔍 测试名称查找: '中日关系'")
        theme = await matcher.find_theme_by_name("中日关系")
        if theme:
            print(f"  找到: {theme['name']}")
            print(f"  分类: {' → '.join(theme['category_path'])}")
            print(f"  关键词: {', '.join(theme['keywords'][:3])}")
        
        print("\n✅ 题材匹配引擎测试通过！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        await matcher.close()

if __name__ == "__main__":
    asyncio.run(test_theme_matcher())