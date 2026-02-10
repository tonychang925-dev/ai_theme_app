# theme_service/matcher/core_matcher.py
import asyncio
import asyncpg
import jieba
import jieba.analyse
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict
from dataclasses import asdict

from theme_service.models.data_models import (
    Theme, NewsArticle, MatchResult, ThemeType
)

class CoreMatcher:
    """核心匹配引擎"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.themes: List[Theme] = []
        self.theme_index: Dict[str, Theme] = {}
        self.keyword_to_themes: Dict[str, List[Theme]] = defaultdict(list)
        
        # 初始化分词器
        self._init_jieba()
    
    def _init_jieba(self):
        """初始化结巴分词"""
        jieba.initialize()
        
        # 添加金融领域词典
        self._add_financial_dict()
    
    def _add_financial_dict(self):
        """添加金融领域词典"""
        financial_terms = [
            # 金融常用词
            "涨停", "跌停", "牛市", "熊市", "IPO", "财报", "季报",
            "年报", "分红", "配股", "增发", "减持", "增持", "回购",
            # 行业术语
            "人工智能", "大数据", "云计算", "物联网", "5G", "芯片",
            "半导体", "新能源", "光伏", "锂电池", "储能", "新能源汽车",
            # 投资概念
            "一带一路", "国企改革", "供给侧改革", "双碳", "碳中和",
            "数字经济", "元宇宙", "区块链", "web3"
        ]
        
        for term in financial_terms:
            jieba.add_word(term, freq=1000)
    
    async def load_themes(self):
        """从数据库加载所有题材"""
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # 查询所有活跃题材
            rows = await conn.fetch("""
                SELECT 
                    id, name, code, theme_type,
                    tags->'keywords' as keywords,
                    tags->'aliases' as aliases,
                    heat_score,
                    level1_category, level2_category, level3_category,
                    source_system
                FROM theme_master
                WHERE status = 'active'
                ORDER BY heat_score DESC
            """)
            
            self.themes = []
            for row in rows:
                theme = Theme(
                    id=row['id'],
                    name=row['name'],
                    code=row['code'],
                    theme_type=ThemeType(row['theme_type']),
                    keywords=row['keywords'] or [],
                    aliases=row['aliases'] or [],
                    heat_score=row['heat_score'] or 65,
                    categories={
                        'level1': row['level1_category'],
                        'level2': row['level2_category'],
                        'level3': row['level3_category']
                    },
                    source_system=row['source_system']
                )
                self.themes.append(theme)
                self.theme_index[theme.code] = theme
                
                # 构建关键词索引
                for keyword in theme.all_keywords:
                    if keyword:  # 确保不是空字符串
                        self.keyword_to_themes[keyword].append(theme)
            
            print(f"✅ 已加载 {len(self.themes)} 个题材")
            print(f"   建立 {len(self.keyword_to_themes)} 个关键词索引")
            
        finally:
            await conn.close()
    
    def extract_text_keywords(self, text: str, top_k: int = 30) -> List[str]:
        """
        从文本中提取关键词
        Args:
            text: 原始文本
            top_k: 返回关键词数量
        Returns:
            关键词列表
        """
        if not text or len(text.strip()) < 10:
            return []
        
        # 1. 使用TF-IDF提取关键词
        try:
            tfidf_keywords = jieba.analyse.extract_tags(
                text,
                topK=top_k,
                withWeight=False,
                allowPOS=('n', 'ns', 'nr', 'nt', 'nz', 'v', 'vn', 'eng')
            )
        except:
            tfidf_keywords = []
        
        # 2. 使用TextRank提取关键词
        try:
            textrank_keywords = jieba.analyse.textrank(
                text,
                topK=top_k,
                withWeight=False,
                allowPOS=('n', 'ns', 'nr', 'nt', 'nz', 'v', 'vn')
            )
        except:
            textrank_keywords = []
        
        # 3. 合并去重
        all_keywords = list(set(tfidf_keywords + textrank_keywords))
        
        # 4. 过滤停用词和短词
        filtered_keywords = []
        for kw in all_keywords:
            kw_clean = kw.strip()
            if (len(kw_clean) >= 2 and  # 至少2个字符
                not self._is_stop_word(kw_clean) and
                not kw_clean.isdigit()):  # 排除纯数字
                filtered_keywords.append(kw_clean)
        
        return filtered_keywords[:top_k]
    
    def _is_stop_word(self, word: str) -> bool:
        """判断是否为停用词"""
        stop_words = {
            '的', '了', '在', '是', '和', '与', '及', '或', '等',
            '有', '为', '对', '中', '上', '下', '这', '那', '就',
            '也', '都', '而', '但', '并', '且', '而', '虽然', '但是',
            '因为', '所以', '如果', '那么', '则', '于', '从', '到',
            '以', '之', '其', '此', '之', '者', '所', '个', '件',
            '条', '项', '种', '类', '些', '点', '次', '回', '年',
            '月', '日', '时', '分', '秒', '公司', '企业', '行业',
            '市场', '产品', '服务', '技术', '发展', '增长', '提高',
            '提升', '加强', '完善', '优化', '创新', '改革', '升级'
        }
        return word in stop_words
    
    async def match_article(self, article: NewsArticle) -> List[MatchResult]:
        """
        匹配单篇文章
        Args:
            article: 新闻文章
        Returns:
            匹配结果列表，按匹配度排序
        """
        if not self.themes:
            await self.load_themes()
        
        # 提取新闻关键词
        article.extracted_keywords = self.extract_text_keywords(
            f"{article.title} {article.content}"
        )
        
        # 计算每个主题的匹配度
        match_results = []
        
        for theme in self.themes:
            score, matched_kws = self._calculate_match_score(
                theme, article
            )
            
            if score > 0.15:  # 匹配阈值
                match_results.append(MatchResult(
                    theme=theme,
                    match_score=score,
                    matched_keywords=matched_kws,
                    match_details={
                        'news_title': article.title,
                        'news_source': article.source,
                        'extracted_keywords': article.extracted_keywords[:10]
                    }
                ))
        
        # 排序并返回前10个
        match_results.sort(key=lambda x: x.match_score, reverse=True)
        return match_results[:10]
    
    def _calculate_match_score(self, theme: Theme, article: NewsArticle) -> tuple:
        """计算主题与文章的匹配度"""
        score = 0.0
        matched_keywords = []
        
        text = f"{article.title} {article.content}"
        
        # 1. 标题匹配（权重最高）
        title_score, title_matches = self._match_in_text(
            theme, article.title, weight=3.0
        )
        score += title_score
        matched_keywords.extend(title_matches)
        
        # 2. 内容匹配
        content_score, content_matches = self._match_in_text(
            theme, article.content, weight=1.5
        )
        score += content_score
        matched_keywords.extend(content_matches)
        
        # 3. 关键词匹配（提取的关键词）
        keyword_score, keyword_matches = self._match_keywords(
            theme, article.extracted_keywords, weight=1.0
        )
        score += keyword_score
        matched_keywords.extend(keyword_matches)
        
        # 4. 主题名称特殊匹配
        if theme.name in article.title:
            score += 5.0
            matched_keywords.append(f"{theme.name}[主题名-标题]")
        elif theme.name in article.content:
            score += 3.0
            matched_keywords.append(f"{theme.name}[主题名-内容]")
        
        # 5. 热度加权
        heat_weight = theme.heat_score / 100.0
        score *= (1 + heat_weight * 0.3)  # 热度增加最多30%
        
        # 6. 归一化到0-1
        normalized_score = min(score / 15.0, 1.0)
        
        return normalized_score, matched_keywords
    
    def _match_in_text(self, theme: Theme, text: str, weight: float) -> tuple:
        """在文本中匹配主题关键词"""
        if not text:
            return 0.0, []
        
        score = 0.0
        matches = []
        
        for keyword in theme.all_keywords:
            if not keyword or len(keyword) < 2:
                continue
            
            # 统计出现次数
            count = text.count(keyword)
            if count > 0:
                score += weight * min(count, 3)  # 最多计算3次
                matches.append(f"{keyword}[{count}次]")
        
        return score, matches
    
    def _match_keywords(self, theme: Theme, keywords: List[str], weight: float) -> tuple:
        """在关键词列表中匹配"""
        if not keywords:
            return 0.0, []
        
        score = 0.0
        matches = []
        
        # 将主题关键词转换为集合以提高效率
        theme_keywords_set = set(theme.all_keywords)
        
        for keyword in keywords:
            if keyword in theme_keywords_set:
                score += weight
                matches.append(f"{keyword}[关键词]")
        
        return score, matches
    
    async def batch_match_articles(self, articles: List[NewsArticle]) -> Dict[str, List[MatchResult]]:
        """批量匹配多篇文章"""
        results = {}
        
        for article in articles:
            matches = await self.match_article(article)
            results[article.id] = matches
        
        return results
    
    async def save_match_results(self, news_id: str, results: List[MatchResult]):
        """保存匹配结果到数据库"""
        conn = await asyncpg.connect(self.db_url)
        
        try:
            for result in results:
                await conn.execute("""
                    INSERT INTO news_theme_matches 
                    (news_id, theme_id, theme_name, theme_code, theme_type,
                     match_score, matched_keywords, match_details,
                     news_title, news_source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (news_id, theme_id) DO UPDATE SET
                    match_score = EXCLUDED.match_score,
                    matched_keywords = EXCLUDED.matched_keywords,
                    match_details = EXCLUDED.match_details,
                    updated_at = CURRENT_TIMESTAMP
                """, 
                    news_id,
                    result.theme.id,
                    result.theme.name,
                    result.theme.code,
                    result.theme.theme_type.value,
                    float(result.match_score),
                    result.matched_keywords,
                    result.match_details,
                    result.match_details.get('news_title', ''),
                    result.match_details.get('news_source', '')
                )
            
            print(f"✅ 已保存 {len(results)} 条匹配结果到数据库")
            
        finally:
            await conn.close()