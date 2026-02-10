"""
基础数据库管理器（抽象类）
定义所有管理器必须实现的方法 - 适配28字段表结构
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime

# ========== 修复导入问题 ==========
# 使用动态导入避免相对导入错误
try:
    # 尝试相对导入（当managers作为包的一部分时）
    from ..interface import DatabaseManager, ThemeRecord, EventThemeRelation, ThemeTags
except ImportError:
    # 如果相对导入失败，使用绝对导入
    import sys
    import os
    
    # 获取当前文件的目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 获取父目录（database_service目录）
    parent_dir = os.path.dirname(current_dir)
    
    # 确保父目录在sys.path中
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    try:
        # 尝试从父目录导入
        from interface import DatabaseManager, ThemeRecord, EventThemeRelation, ThemeTags
    except ImportError as e:
        # 如果还是失败，尝试更直接的方式
        # 直接在父目录中查找interface.py
        interface_path = os.path.join(parent_dir, 'interface.py')
        if os.path.exists(interface_path):
            # 使用importlib直接导入
            import importlib.util
            spec = importlib.util.spec_from_file_location("interface", interface_path)
            interface_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(interface_module)
            
            # 从模块中获取需要的类
            DatabaseManager = getattr(interface_module, 'DatabaseManager')
            ThemeRecord = getattr(interface_module, 'ThemeRecord')
            EventThemeRelation = getattr(interface_module, 'EventThemeRelation')
            ThemeTags = getattr(interface_module, 'ThemeTags')
        else:
            # 如果都失败了，创建占位符类
            print(f"⚠️ 警告: 无法导入interface模块，使用占位符类。错误: {e}")
            
            class DatabaseManager(ABC):
                pass
            
            class ThemeRecord:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
                
                def get_keywords(self):
                    return []
            
            class EventThemeRelation:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            
            class ThemeTags:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
                
                @classmethod
                def from_dict(cls, data):
                    return cls(**data)


class BaseDatabaseManager(DatabaseManager, ABC):
    """基础数据库管理器（抽象基类）"""
    
    def __init__(self, config):
        self.config = config
        self.connected = False
        self.start_time = datetime.now()
    
    @abstractmethod
    async def connect(self) -> None:
        """建立数据库连接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """关闭数据库连接"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    def transaction(self) -> AsyncContextManager:
        """事务上下文管理器"""
        pass
    
    # ========== 主题操作（更新为28字段接口） ==========
    
    @abstractmethod
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（按ID）"""
        pass
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）"""
        # 默认实现，子类可以重写
        themes = await self.search_themes(code, limit=1)
        return themes[0] if themes else None
    
    @abstractmethod
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        pass
    
    @abstractmethod
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题"""
        pass
    
    @abstractmethod
    async def create_theme(self, name: str, code: str, **kwargs) -> ThemeRecord:
        """创建新主题（必须包含code字段）"""
        pass
    
    @abstractmethod
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题"""
        pass
    
    @abstractmethod
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        pass
    
    @abstractmethod
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        pass
    
    async def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """
        查找相关主题 - 基于关键词匹配
        
        参数:
            event_data: 事件数据，应包含keywords或impact_industries字段
            limit: 返回的最大主题数量
        
        返回:
            相关主题列表（按相关度排序）
        """
        # 基础实现，子类可以重写
        keywords = event_data.get('keywords', [])
        impact_industries = event_data.get('impact_industries', [])
        
        all_keywords = keywords + impact_industries
        if not all_keywords:
            return []
        
        return await self.get_themes_by_keywords(all_keywords, limit)
    
    @abstractmethod
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题"""
        pass
    
    @abstractmethod
    async def get_themes_by_category(self, category_code: str, level: int = 1, limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题"""
        pass
    
    @abstractmethod
    async def get_themes_by_heat_level(self, min_heat: int = 60, limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题"""
        pass
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        themes = []
        for data in themes_data:
            theme = await self.create_theme(
                data['name'],
                data['code'],
                description=data.get('description'),
                level1_category=data.get('level1_category'),
                level2_category=data.get('level2_category'),
                level3_category=data.get('level3_category'),
                category_path=data.get('category_path', []),
                category1_code=data.get('category1_code'),
                category2_code=data.get('category2_code'),
                category3_code=data.get('category3_code'),
                tags=data.get('tags', {}),
                theme_type=data.get('theme_type', 'investment'),
                heat_score=data.get('heat_score', 50),
                confidence_score=data.get('confidence_score', 0.80)
            )
            themes.append(theme)
        return themes
    
    @abstractmethod
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题（支持名称、描述、关键词搜索）"""
        pass
    
    # ========== 事件-主题关联 ==========
    
    @abstractmethod
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> EventThemeRelation:
        """创建事件-主题关联"""
        pass
    
    @abstractmethod
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的主题"""
        pass
    
    @abstractmethod
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        pass
    
    @abstractmethod
    async def update_event_theme_relation(self, relation_id: int, updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        """更新事件-主题关联"""
        pass
    
    # ========== 事件管理 ==========
    
    @abstractmethod
    async def mark_event_processed(self, event_id: int) -> None:
        """标记事件已处理"""
        pass
    
    @abstractmethod
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        pass
    
    @abstractmethod
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件"""
        pass
    
    # ========== 统计与监控 ==========
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass
    
    async def get_theme_stats(self) -> Dict[str, Any]:
        """获取主题统计信息"""
        stats = await self.get_stats()
        return stats.get('themes', {})
    
    # ========== 高级查询 ==========
    
    @abstractmethod
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """执行原始SQL查询"""
        pass
    
    # ========== 工具方法（更新为28字段结构） ==========
    
    def _format_keywords(self, keywords: List[str]) -> List[str]:
        """格式化关键词"""
        if not keywords:
            return []
        
        # 去重、去空、限制长度
        formatted = []
        seen = set()
        for kw in keywords:
            if not kw or not isinstance(kw, str):
                continue
            
            kw_clean = kw.strip()
            if kw_clean and kw_clean not in seen and len(kw_clean) <= 100:
                formatted.append(kw_clean)
                seen.add(kw_clean)
        
        return formatted
    
    def _build_theme_record(self, data: Dict[str, Any]) -> ThemeRecord:
        """从字典构建ThemeRecord（28字段结构）"""
        # 处理tags字段
        tags_data = data.get('tags', {})
        if isinstance(tags_data, ThemeTags):
            tags = tags_data
        elif isinstance(tags_data, dict):
            try:
                tags = ThemeTags.from_dict(tags_data)
            except:
                # 如果from_dict失败，直接创建
                tags = ThemeTags(**tags_data)
        else:
            tags = ThemeTags()
        
        return ThemeRecord(
            # 基本信息
            id=data.get('id', 0),
            name=data.get('name', ''),
            code=data.get('code', ''),
            description=data.get('description'),
            status=data.get('status', 'active'),
            
            # 分类信息
            level1_category=data.get('level1_category'),
            level2_category=data.get('level2_category'),
            level3_category=data.get('level3_category'),
            category_path=data.get('category_path', []),
            category1_code=data.get('category1_code'),
            category2_code=data.get('category2_code'),
            category3_code=data.get('category3_code'),
            
            # 标签信息
            tags=tags,
            
            # 类型与状态
            theme_type=data.get('theme_type', 'investment'),
            lifecycle_stage=data.get('lifecycle_stage', 'growth'),
            
            # 热度与置信度
            heat_score=data.get('heat_score', 50),
            confidence_score=data.get('confidence_score', 0.80),
            
            # 关联统计
            related_stocks=data.get('related_stocks', []),
            stock_count=data.get('stock_count', 0),
            news_count=data.get('news_count', 0),
            mention_count=data.get('mention_count', 0),
            
            # 时间戳
            last_mentioned=data.get('last_mentioned'),
            last_active_at=data.get('last_active_at'),
            
            # 来源信息
            source_system=data.get('source_system', 'transformed'),
            source_id=data.get('source_id'),
            created_by=data.get('created_by', 'system'),
            
            # 系统时间戳
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def _build_relation_record(self, data: Dict[str, Any]) -> EventThemeRelation:
        """从字典构建EventThemeRelation"""
        return EventThemeRelation(
            id=data.get('id'),
            event_id=data.get('event_id'),
            theme_id=data.get('theme_id'),
            confidence=data.get('confidence', 0.0),
            confidence_level=data.get('confidence_level', 'medium'),
            confidence_weight=data.get('confidence_weight', 50),
            evidence=data.get('evidence'),
            match_type=data.get('match_type', 'keyword'),
            matched_keywords=data.get('matched_keywords', []),
            created_at=data.get('created_at')
        )
    
    def _build_tags_from_dict(self, tags_data: Dict[str, Any]) -> ThemeTags:
        """从字典构建ThemeTags"""
        if isinstance(tags_data, ThemeTags):
            return tags_data
        
        try:
            return ThemeTags.from_dict(tags_data)
        except:
            # 如果from_dict失败，直接创建
            return ThemeTags(**tags_data)
    
    async def _execute_with_retry(self, func, *args, max_retries=3, **kwargs):
        """带重试的执行"""
        last_exception = None
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1 * (attempt + 1))
        
        raise last_exception
    
    # ========== 通用工具方法 ==========
    
    def _calculate_relevance_score(self, theme: ThemeRecord, keywords: List[str]) -> float:
        """计算主题与关键词的相关度评分"""
        if not keywords:
            return 0.0
        
        score = 0.0
        
        # 名称匹配
        for kw in keywords:
            if kw.lower() in theme.name.lower():
                score += 30.0
                break
        
        # 关键词匹配
        theme_keywords = theme.get_keywords()
        for kw in keywords:
            if any(kw.lower() in tk.lower() for tk in theme_keywords):
                score += 10.0
        
        # 分类匹配
        for kw in keywords:
            if (theme.level1_category and kw.lower() in theme.level1_category.lower() or
                theme.level2_category and kw.lower() in theme.level2_category.lower() or
                theme.level3_category and kw.lower() in theme.level3_category.lower()):
                score += 5.0
                break
        
        return score
    
    def _extract_matched_keywords(self, theme: ThemeRecord, keywords: List[str]) -> List[str]:
        """提取匹配的关键词"""
        if not keywords:
            return []
        
        matched = []
        theme_keywords = theme.get_keywords()
        
        for kw in keywords:
            # 检查名称匹配
            if kw.lower() in theme.name.lower():
                matched.append(kw)
                continue
            
            # 检查关键词匹配
            if any(kw.lower() in tk.lower() for tk in theme_keywords):
                matched.append(kw)
                continue
            
            # 检查分类匹配
            if (theme.level1_category and kw.lower() in theme.level1_category.lower() or
                theme.level2_category and kw.lower() in theme.level2_category.lower() or
                theme.level3_category and kw.lower() in theme.level3_category.lower()):
                matched.append(kw)
        
        return matched
    
    def _validate_theme_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证主题数据"""
        validated = data.copy()
        
        # 确保必填字段
        if 'name' not in validated:
            raise ValueError("主题名称不能为空")
        if 'code' not in validated:
            raise ValueError("主题code不能为空")
        
        # 验证数值范围
        if 'heat_score' in validated:
            validated['heat_score'] = max(0, min(100, validated['heat_score']))
        
        if 'confidence_score' in validated:
            validated['confidence_score'] = max(0.0, min(1.0, validated['confidence_score']))
        
        # 验证数组字段
        array_fields = ['category_path', 'related_stocks']
        for field in array_fields:
            if field in validated and not isinstance(validated[field], list):
                validated[field] = []
        
        # 验证tags字段
        if 'tags' in validated and not isinstance(validated['tags'], (dict, ThemeTags)):
            validated['tags'] = {}
        
        return validated