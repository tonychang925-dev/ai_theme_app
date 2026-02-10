"""
虚拟主题数据库 - 用于评估系统的模拟数据库
兼容MemoryDatabaseManager接口，但简化实现
🚀 修复：更新方法调用，移除对废弃方法的依赖
"""
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import re
import json
from collections import defaultdict

logger = logging.getLogger(__name__)


class VirtualThemeDatabase:
    """
    虚拟主题数据库 - 专为评估系统设计
    
    🔥 重要：这是测试专用数据库，不是生产数据库
    🚀 修复：更新方法实现，不再依赖将被移除的方法
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """初始化虚拟数据库"""
        self.config = config or {}
        self.themes: Dict[str, Dict[str, Any]] = {}  # theme_name -> theme_data
        self.event_themes: Dict[str, List[str]] = {}  # event_id -> [theme_names]
        self.theme_events: Dict[str, List[str]] = {}  # theme_name -> [event_ids]
        
        # 模拟数据
        self._init_mock_data()
        
        logger.info(f"VirtualThemeDatabase 初始化完成，主题数: {len(self.themes)}")
    
    def _init_mock_data(self):
        """初始化模拟数据"""
        # 添加一些常见主题
        common_themes = [
            {
                'name': '商业航天',
                'keywords': ['航天', '商业', '卫星', '火箭', '发射'],
                'description': '民营企业参与的航天发射、卫星运营等相关事件',
                'event_count': 15,
                'heat': 85
            },
            {
                'name': '人工智能',
                'keywords': ['AI', '人工智能', '机器学习', '深度学习', '大模型'],
                'description': '人工智能技术发展、应用落地、产业生态等相关事件',
                'event_count': 25,
                'heat': 95
            },
            {
                'name': '新能源汽车',
                'keywords': ['新能源', '电动汽车', '电池', '充电', '自动驾驶'],
                'description': '新能源汽车技术、市场发展、政策支持等相关事件',
                'event_count': 20,
                'heat': 90
            },
            {
                'name': '半导体',
                'keywords': ['芯片', '半导体', '集成电路', '制造', '设计'],
                'description': '半导体产业技术突破、产业发展、供应链等相关事件',
                'event_count': 18,
                'heat': 88
            },
            {
                'name': '生物医药',
                'keywords': ['生物', '医药', '医疗', '创新药', '疫苗'],
                'description': '生物医药研发、临床试验、药品审批等相关事件',
                'event_count': 12,
                'heat': 75
            }
        ]
        
        for theme in common_themes:
            self.themes[theme['name']] = theme
    
    # ========== 主题查询方法 ==========
    
    def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[str]:
        """
        🔥 已更新：简化实现，不再进行复杂的相关性计算
        🚀 修复：参数名统一为limit，移除对_calculate_relevance_score的依赖
        
        Args:
            event_data: 事件数据
            limit: 最大返回数量
            
        Returns:
            相关主题名称列表
        """
        if not self.themes:
            return []
        
        logger.debug(f"查找相关主题，事件ID: {event_data.get('id', 'unknown')}, limit: {limit}")
        
        # 🚀 简化：不再进行复杂的相关性计算
        # 只基于简单关键词匹配，让AI做复杂的相似性分析
        
        # 从事件数据中提取简单关键词
        search_terms = self._extract_simple_keywords(event_data)
        if not search_terms:
            # 如果没有关键词，返回热度最高的主题
            return self._get_hottest_themes(limit)
        
        # 简单关键词匹配
        matched_themes = []
        for theme_name, theme_data in self.themes.items():
            score = self._simple_match_score(theme_data, search_terms)
            if score > 0:
                matched_themes.append((theme_name, score))
        
        # 按匹配度排序
        matched_themes.sort(key=lambda x: x[1], reverse=True)
        
        # 返回主题名称
        result = [theme_name for theme_name, _ in matched_themes[:limit]]
        
        logger.debug(f"找到 {len(result)} 个相关主题: {result}")
        return result
    
    def _extract_simple_keywords(self, event_data: Dict[str, Any]) -> List[str]:
        """
        简化版关键词提取
        🚀 修复：不再使用将被移除的_extract_search_keywords方法
        """
        keywords = []
        
        # 从标题提取
        title = event_data.get('title', '')
        if title:
            # 简单提取中文关键词
            words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
            keywords.extend(words[:3])
        
        # 从摘要提取
        summary = event_data.get('summary', '')
        if summary:
            words = re.findall(r'[\u4e00-\u9fff]{2,4}', summary)
            keywords.extend(words[:2])
        
        # 添加影响行业
        industries = event_data.get('impact_industries', [])
        keywords.extend(industries)
        
        # 去重
        return list(set(keywords))
    
    def _simple_match_score(self, theme_data: Dict[str, Any], search_terms: List[str]) -> float:
        """
        简化版匹配得分计算
        🚀 修复：不再使用将被移除的_calculate_relevance_score方法
        """
        if not search_terms:
            return 0.0
        
        # 获取主题关键词
        theme_keywords = theme_data.get('keywords', [])
        theme_name = theme_data.get('name', '').lower()
        
        # 简单关键词匹配
        matches = 0
        for term in search_terms:
            term_lower = term.lower()
            
            # 检查是否在主题关键词中
            for kw in theme_keywords:
                if term_lower in kw.lower() or kw.lower() in term_lower:
                    matches += 1
                    break
            # 检查是否在主题名称中
            elif term_lower in theme_name:
                matches += 1
        
        # 简单得分计算
        score = matches / len(search_terms) if search_terms else 0
        
        # 考虑主题热度
        heat = theme_data.get('heat', 0)
        heat_bonus = heat / 100.0 * 0.2  # 热度最高贡献20%的加分
        
        return min(1.0, score + heat_bonus)
    
    def _get_hottest_themes(self, limit: int) -> List[str]:
        """获取热度最高的主题"""
        themes_with_heat = [(name, data.get('heat', 0)) for name, data in self.themes.items()]
        themes_with_heat.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in themes_with_heat[:limit]]
    
    # ========== 其他兼容方法 ==========
    
    def get_theme_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取主题"""
        return self.themes.get(name)
    
    def get_all_themes(self) -> List[str]:
        """获取所有主题名称"""
        return list(self.themes.keys())
    
    def get_theme_details(self, theme_name: str) -> Optional[Dict[str, Any]]:
        """获取主题详情"""
        theme = self.themes.get(theme_name)
        if not theme:
            return None
        
        # 返回增强的主题信息
        enhanced = theme.copy()
        
        # 添加模拟的事件信息
        event_ids = self.theme_events.get(theme_name, [])
        enhanced['event_ids'] = event_ids
        enhanced['event_count'] = len(event_ids)
        
        # 添加AI分析所需的信息
        enhanced['ai_context'] = {
            'description': theme.get('description', ''),
            'keywords': theme.get('keywords', []),
            'common_industries': ['科技', '制造'],  # 模拟数据
            'strength': '高' if theme.get('heat', 0) > 80 else '中' if theme.get('heat', 0) > 60 else '低'
        }
        
        return enhanced
    
    def create_theme(self, name: str, keywords: List[str] = None, 
                    description: str = None) -> bool:
        """创建新主题（模拟）"""
        if name in self.themes:
            logger.warning(f"主题 '{name}' 已存在")
            return False
        
        self.themes[name] = {
            'name': name,
            'keywords': keywords or [],
            'description': description or f"{name}相关主题",
            'event_count': 0,
            'heat': 50,
            'created_at': datetime.now().isoformat()
        }
        
        logger.info(f"创建虚拟主题: {name}")
        return True
    
    def add_event_to_theme(self, event_id: str, theme_name: str) -> bool:
        """将事件添加到主题"""
        if theme_name not in self.themes:
            logger.warning(f"主题 '{theme_name}' 不存在")
            return False
        
        # 更新事件-主题映射
        self.event_themes.setdefault(event_id, []).append(theme_name)
        self.theme_events.setdefault(theme_name, []).append(event_id)
        
        # 更新主题统计
        self.themes[theme_name]['event_count'] = len(self.theme_events[theme_name])
        self.themes[theme_name]['heat'] = min(100, self.themes[theme_name].get('heat', 0) + 5)
        
        logger.debug(f"事件 {event_id} 添加到主题 {theme_name}")
        return True
    
    def get_event_themes(self, event_id: str) -> List[str]:
        """获取事件关联的主题"""
        return self.event_themes.get(event_id, [])
    
    def get_theme_events(self, theme_name: str) -> List[str]:
        """获取主题关联的事件"""
        return self.theme_events.get(theme_name, [])
    
    def search_themes(self, query: str, limit: int = 10) -> List[str]:
        """搜索主题"""
        if not query:
            return []
        
        query_lower = query.lower()
        matched = []
        
        for theme_name, theme_data in self.themes.items():
            # 在名称、关键词、描述中搜索
            search_text = f"{theme_name} {' '.join(theme_data.get('keywords', []))} {theme_data.get('description', '')}"
            
            if query_lower in search_text.lower():
                matched.append(theme_name)
        
        return matched[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_events = sum(len(events) for events in self.theme_events.values())
        
        return {
            'total_themes': len(self.themes),
            'total_events': total_events,
            'theme_names': list(self.themes.keys()),
            'avg_events_per_theme': total_events / max(len(self.themes), 1),
            'hottest_themes': self._get_hottest_themes(3)
        }
    
    def clear(self):
        """清空数据库（用于测试）"""
        self.themes.clear()
        self.event_themes.clear()
        self.theme_events.clear()
        self._init_mock_data()
        logger.info("虚拟数据库已清空并重新初始化")
