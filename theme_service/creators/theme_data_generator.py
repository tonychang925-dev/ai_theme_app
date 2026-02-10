"""
题材数据结构生成器 - 生成新题材的数据结构
基于实际数据库表结构和现有题材模式
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re
import jieba
import jieba.analyse
from collections import Counter

@dataclass
class NewThemeData:
    """新题材数据结构 - 基于theme_master表结构"""
    # 基础信息
    name: str                      # 题材名称
    code: str                      # 题材代码
    description: str               # 描述
    
    # 分类信息
    level1_category: Optional[str] = None           # 一级分类名称（可以为空）
    level2_category: Optional[str] = None           # 二级分类名称（可以为空）
    level3_category: Optional[str] = None           # 三级分类名称（可以为空）
    category1_code: Optional[str] = None            # 一级分类代码（可以为空）
    category2_code: Optional[str] = None            # 二级分类代码（可以为空）
    category3_code: Optional[str] = None            # 三级分类代码

    is_concept: bool = False                         # 是否是概念题材

    category_path: List[str] = field(default_factory=list)  # 分类路径
    
    # 标签和类型
    tags: Dict[str, Any] = field(default_factory=dict)      # tags标签（jsonb格式）
    theme_type: str = "concept"    # 题材类型：concept/industry/policy/relation/event/investment
    status: str = "active"         # 状态：active/inactive/archived
    lifecycle_stage: str = "emerging"  # 生命周期：emerging/growth/mature/decline/archived
    
    # 分数和统计
    heat_score: int = 50           # 热度分数
    confidence_score: float = 0.5  # 置信度（0.0-1.0）
    related_stocks: List[str] = field(default_factory=list)  # 相关股票数组
    stock_count: int = 0
    news_count: int = 1
    mention_count: int = 1
    
    # 来源信息
    source_system: str = "auto_discovered"  # 来源系统
    source_id: str = ""                     # 来源ID
    created_by: str = "theme_discovery_system"  # 创建者
    
    # 元数据
    source_event: Dict[str, Any] = field(default_factory=dict)  # 来源事件
    metadata: Dict[str, Any] = field(default_factory=dict)    # 元数据
    last_mentioned: Optional[datetime] = None  # 最后提及时间
    
    def to_dict(self) -> Dict:
        """转换为数据库插入格式"""
        result = {
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'level1_category': self.level1_category,  # ✅ 可以为None
            'level2_category': self.level2_category,  # ✅ 可以为None
            'level3_category': self.level3_category,  # ✅ 可以为None
            'category1_code': self.category1_code,    # ✅ 可以为None
            'category2_code': self.category2_code,    # ✅ 可以为None
            'category3_code': self.category3_code,
            'is_concept': self.is_concept,            # ✅ 新增概念标志
            'category_path': self.category_path,
            'tags': self.tags,
            'theme_type': self.theme_type,
            'status': self.status,
            'lifecycle_stage': self.lifecycle_stage,
            'heat_score': self.heat_score,
            'confidence_score': round(self.confidence_score, 2),
            'related_stocks': self.related_stocks,
            'stock_count': self.stock_count,
            'news_count': self.news_count,
            'mention_count': self.mention_count,
            'source_system': self.source_system,
            'source_id': self.source_id if self.source_id else f"event_{self.source_event.get('event_id', 'unknown')}",
            'created_by': self.created_by
        }
        
        # 添加时间戳
        if self.last_mentioned:
            result['last_mentioned'] = self.last_mentioned.isoformat()
        
        # 如果是概念题材，确保分类信息合理
        if self.is_concept:
            # 概念题材可以有简化的分类路径
            if not self.category_path:
                self.category_path = ['概念题材', self.name[:20]]
        
        return result


class ThemeDataGenerator:
    """题材数据结构生成器"""
    
    def __init__(self, themes: List[Dict], categories: List[Dict]):  # ✅ 修改参数顺序
        """
        初始化新题材生成器
        
        Args:
            themes: 题材数据列表
            categories: 分类数据列表
        """
        self.themes = themes or []
        self.categories = categories or []

        #self.themes = themes
        #self.categories = categories
        
        # ✅ 修复：确保数据格式正确
        self._validate_and_fix_data()
        
        # 构建缓存
        self._build_caches()
        
        # 分析现有题材模式
        self._analyze_existing_patterns()

    def _validate_and_fix_data(self):
        """验证并修复数据格式"""
        # 确保分类数据有category_code字段
        if self.categories:
            for i, cat in enumerate(self.categories):
                if 'category_code' not in cat or not cat['category_code']:
                    cat['category_code'] = f"AUTO_CAT_{i:06d}"
                if 'category_name' not in cat or not cat['category_name']:
                    cat['category_name'] = f"分类_{i}"
                if 'category_level' not in cat:
                    cat['category_level'] = 1

    def _build_caches(self):
        """构建缓存"""
        # ✅ 修复：更健壮的构建方法
        self.category_by_code = {}
        self.category_by_name = {}
        self.categories_by_level = {1: [], 2: [], 3: []}
        
        # 构建分类缓存
        for cat in self.categories:
            category_code = cat.get('category_code')
            category_name = cat.get('category_name')
            
            if category_code:
                self.category_by_code[category_code] = cat
            if category_name:
                self.category_by_name[category_name] = cat
            
            # 按级别分组
            level = cat.get('category_level', 1)
            if level in self.categories_by_level:
                self.categories_by_level[level].append(cat)
        
        # 构建题材缓存
        self.theme_by_name = {}
        self.theme_by_code = {}
        
        if self.themes:
            for theme in self.themes:
                theme_name = theme.get('name')
                theme_code = theme.get('code')
                
                if theme_name:
                    self.theme_by_name[theme_name] = theme
                if theme_code:
                    self.theme_by_code[theme_code] = theme
        
        print(f"✅ ThemeDataGenerator缓存构建完成: "
            f"{len(self.category_by_code)} 分类, {len(self.theme_by_name)} 题材")
    
    def _analyze_existing_patterns(self):
        """分析现有题材模式"""
        self.theme_type_distribution = Counter()
        self.name_patterns = {
            'investment': [],  # 投资题材：股份制银行Ⅲ
            'policy': [],      # 政策题材：某某政策
            'concept': [],     # AI芯片概念
            'industry': []     # 半导体材料
        }
        
        for theme in self.themes:
            theme_type = theme.get('theme_type', 'concept')
            self.theme_type_distribution[theme_type] += 1
            
            name = theme.get('name', '')
            if name.startswith('投资题材：'):
                self.name_patterns['investment'].append(name)
            elif name.startswith('政策题材：'):
                self.name_patterns['policy'].append(name)
            elif any(c in name for c in ['概念', '题材', '板块']):
                self.name_patterns['concept'].append(name)
            else:
                self.name_patterns['industry'].append(name)
    
    def generate_for_major_event(self, event_data: Dict, 
                            classification_result: Dict,
                            theme_type: str = None) -> Optional[NewThemeData]:
        """为Major事件生成新题材数据 - 最终修复版本"""
        print(f"🔧 为Major事件生成新题材数据: {event_data.get('title', '')[:50]}...")
        
        try:
            # 确保导入 datetime
            from datetime import datetime
            
            # 1. 获取分类（可能为None）
            print(f"   🔍 步骤1: 获取分类...")
            level1, level2 = None, None
            try:
                level1, level2 = self._get_determined_categories(event_data, classification_result)
                print(f"   🔍 分类结果: level1={'有' if level1 else '无'}, level2={'有' if level2 else '无'}")
            except Exception as e:
                print(f"   ❌ 获取分类失败: {e}")
                level1, level2 = None, None
            
            # 安全获取分类名称
            level1_name = ""
            level2_name = ""
            if level1 and isinstance(level1, dict):
                level1_name = level1.get('category_name', '')
            if level2 and isinstance(level2, dict):
                level2_name = level2.get('category_name', '')
            
            # 2. 判断是否是概念题材
            is_concept = (level1 is None or level2 is None)
            print(f"   🔍 是否是概念题材: {is_concept}")
            
            # 3. 推断题材类型
            if not theme_type:
                try:
                    theme_type = self._infer_theme_type(event_data, level1, level2)
                    print(f"   🔍 推断的题材类型: {theme_type}")
                except Exception as e:
                    print(f"   ❌ 推断题材类型失败: {e}")
                    theme_type = "concept"
            
            # 4. 生成三级分类名称
            level3_name = ""
            if is_concept:
                print(f"   🔍 步骤4: 生成概念题材名称...")
                # 概念题材：使用AI核心概念
                ai_analysis = event_data.get('ai_analysis', {})
                if ai_analysis:
                    level3_name = ai_analysis.get('core_concept', '')
                
                if not level3_name:
                    # 从标题提取（使用安全版本）
                    try:
                        safe_level1 = level1 if level1 else {}
                        safe_level2 = level2 if level2 else {}
                        level3_name = self._extract_core_concept(
                            event_data.get('title', ''), 
                            safe_level1, 
                            safe_level2
                        )
                    except Exception as e:
                        print(f"   ❌ 提取核心概念失败: {e}")
                        # 使用标题作为备选
                        title = event_data.get('title', '新概念')
                        level3_name = title[:6] if title else "新概念"
                
                # 确保概念名称合适
                if theme_type == "concept" and not level3_name.endswith('概念'):
                    level3_name = f"{level3_name}概念"
            else:
                # 行业题材：使用原有逻辑
                print(f"   🔍 步骤4: 生成行业题材名称...")
                try:
                    level3_name = self._generate_level3_name(event_data, level1, level2, theme_type)
                except Exception as e:
                    print(f"   ❌ 生成三级分类名称失败: {e}")
                    level3_name = "新题材"
            
            print(f"   🔍 三级分类名称: {level3_name}")
            
            # 5. 检查是否已存在类似题材
            display_level1 = level1_name if level1_name else "概念题材"
            display_level2 = level2_name if level2_name else level3_name
            
            print(f"   🔍 检查已存在题材: {display_level1} → {display_level2} → {level3_name}")
            try:
                if self._check_existing_theme(level3_name, display_level1, display_level2, theme_type):
                    print(f"   已存在类似题材: {level3_name}")
                    return None
            except Exception as e:
                print(f"   ❌ 检查已存在题材失败: {e}")
                # 继续执行，不因为这个失败
            
            # 6. 生成题材名称
            print(f"   🔍 步骤6: 生成题材名称...")
            theme_name = ""
            try:
                theme_name = self._generate_theme_name(event_data, level1, level2, level3_name, theme_type)
            except Exception as e:
                print(f"   ❌ 生成题材名称失败: {e}")
                theme_name = level3_name
            
            print(f"   🔍 题材名称: {theme_name}")
            
            # 7. 生成题材代码
            print(f"   🔍 步骤7: 生成题材代码...")
            theme_code = ""
            try:
                theme_code = self._generate_theme_code(theme_name, level1, level2, theme_type)
            except Exception as e:
                print(f"   ❌ 生成题材代码失败: {e}")
                # 使用简单的代码生成
                timestamp = datetime.now().strftime("%y%m%d")
                import hashlib
                name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
                theme_code = f"THM_{timestamp}{name_hash}"
            
            print(f"   🔍 题材代码: {theme_code}")
            
            # 8. 提取关键词
            print(f"   🔍 步骤8: 提取关键词...")
            keywords = []
            try:
                keywords = self._extract_keywords_from_event(event_data)
            except Exception as e:
                print(f"   ❌ 提取关键词失败: {e}")
                keywords = []
            
            print(f"   🔍 关键词数: {len(keywords)}")
            
            # 9. 构建tags
            print(f"   🔍 步骤9: 构建tags...")
            tags = {}
            try:
                tags = self._build_tags(event_data, keywords, level1, level2, level3_name, theme_type)
            except Exception as e:
                print(f"   ❌ 构建tags失败: {e}")
                # 构建最小化的tags
                tags = {
                    "source": "auto_discovered",
                    "version": "1.0",
                    "keywords": keywords[:10],
                    "heat_level": "low",
                    "industries": [display_level1, display_level2],
                    "creation_source": "theme_discovery"
                }
            
            # 10. 构建描述
            print(f"   🔍 步骤10: 构建描述...")
            description = ""
            try:
                description = self._generate_description(event_data, level1, level2, level3_name, theme_type)
            except Exception as e:
                print(f"   ❌ 构建描述失败: {e}")
                description = f"『{level3_name}』是一个新兴的概念。"
            
            # 11. 提取相关股票
            print(f"   🔍 步骤11: 提取相关股票...")
            related_stocks = []
            try:
                related_stocks = self._extract_stocks_from_event(event_data)
            except Exception as e:
                print(f"   ❌ 提取相关股票失败: {e}")
                related_stocks = []
            
            print(f"   🔍 相关股票数: {len(related_stocks)}")
            
            # 12. 构建完整数据结构
            print(f"   🔍 步骤12: 构建完整数据结构...")
            
            # 安全获取分类代码
            level1_code = level1.get('category_code') if level1 and isinstance(level1, dict) else None
            level2_code = level2.get('category_code') if level2 and isinstance(level2, dict) else None
            
            try:
                theme_data = NewThemeData(
                    name=theme_name,
                    code=theme_code,
                    description=description,
                    level1_category=level1_name,
                    level2_category=level2_name,
                    level3_category=level3_name,
                    category1_code=level1_code,
                    category2_code=level2_code,
                    category3_code=None,
                    is_concept=is_concept,
                    category_path=[display_level1, display_level2, level3_name],
                    tags=tags,
                    theme_type=theme_type,
                    status="active",
                    lifecycle_stage="emerging",
                    heat_score=60,  # 默认热度
                    confidence_score=0.5,  # 默认置信度
                    related_stocks=related_stocks,
                    stock_count=len(related_stocks),
                    source_system=self._determine_source_system(event_data),
                    created_by="theme_discovery_system",
                    source_event=event_data,
                    last_mentioned=datetime.now(),
                    metadata={
                        'creation_reason': 'major_event_no_match',
                        'creation_strategy': 'immediate_creation',
                        'event_type': event_data.get('event_type', 'major'),
                        'keywords_count': len(keywords),
                        'created_at': datetime.now().isoformat(),
                        'event_title': event_data.get('title', '')[:100],
                        'event_id': event_data.get('event_id', 'unknown'),
                        'ai_analysis_used': 'ai_analysis' in event_data,
                        'is_concept_theme': is_concept
                    }
                )
                
                print(f"✅ 生成新题材数据: {theme_name} ({theme_code})")
                print(f"   类型: {theme_type}, 概念题材: {'是' if is_concept else '否'}")
                
                if not is_concept:
                    print(f"   分类: {level1_name} → {level2_name} → {level3_name}")
                else:
                    print(f"   概念: {level3_name} (无具体行业分类)")
                
                print(f"   热度: {theme_data.heat_score}, 置信度: {theme_data.confidence_score}")
                print(f"   来源: {theme_data.source_system}")
                
                return theme_data
                
            except Exception as e:
                print(f"❌ 构建数据结构失败: {e}")
                import traceback
                traceback.print_exc()
                return None
                
        except Exception as e:
            print(f"❌ generate_for_major_event 发生严重异常: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_determined_categories(self, event_data: Dict, classification_result: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """从分类结果中获取确定的分类 - ✅ 最终修复版本"""
        print(f"   🔍 尝试确定分类...")
        
        try:
            # 获取AI分析数据
            ai_analysis = event_data.get('ai_analysis', {})
            
            # ✅ 第一步：检查AI分类推断结果
            if 'ai_category_inference' in classification_result:
                ai_category_result = classification_result['ai_category_inference']
                
                if ai_category_result and isinstance(ai_category_result, dict):
                    matched = ai_category_result.get('matched')
                    
                    # AI推断为概念题材
                    if matched is False:
                        print(f"   🚀 AI推断为概念题材")
                        return None, None
                    
                    # AI推断有具体分类
                    elif matched is True:
                        level1_name = ai_category_result.get('level1_category', '')
                        level2_name = ai_category_result.get('level2_category', '')
                        
                        if level1_name and level2_name:
                            level1 = self.category_by_name.get(level1_name)
                            level2 = self.category_by_name.get(level2_name)
                            
                            if level1 and level2:
                                print(f"   ✅ 使用AI推断的分类: {level1_name} → {level2_name}")
                                return level1, level2
                            else:
                                # 分类不存在于申万体系中，作为概念题材
                                print(f"   ⚠️  AI推断的分类不在申万体系中，创建概念题材")
                                return None, None
            
            # ✅ 第二步：如果有AI分析数据，尝试匹配申万分类
            if ai_analysis:
                print(f"   🤖 尝试从AI关键词推断分类...")
                
                ai_industry_keywords = ai_analysis.get('industry_keywords', [])
                
                # ✅ 修复：确保keywords是可迭代的列表
                if ai_industry_keywords and isinstance(ai_industry_keywords, (list, tuple, set)):
                    # 基于AI关键词匹配申万分类
                    level1, level2 = self._match_shenwan_by_keywords(ai_industry_keywords)
                    
                    if level1 and level2:
                        level1_name = level1.get('category_name', '')
                        level2_name = level2.get('category_name', '')
                        print(f"   ✅ 从AI关键词匹配到申万分类: {level1_name} → {level2_name}")
                        return level1, level2
                    else:
                        # 无法匹配申万分类，创建概念题材
                        core_concept = ai_analysis.get('core_concept', '')
                        if core_concept:
                            print(f"   🚀 AI概念 '{core_concept}' 无法匹配申万分类，创建概念题材")
                        else:
                            print(f"   🚀 AI关键词无法匹配申万分类，创建概念题材")
                        return None, None
                else:
                    # AI分析没有行业关键词，创建概念题材
                    print(f"   🚀 AI分析缺少行业关键词，创建概念题材")
                    return None, None
            
            # ✅ 第三步：检查匹配算法结果
            themes = classification_result.get('themes', [])
            
            if themes and isinstance(themes, (list, tuple)):
                best_match = themes[0] if themes else {}
                level1_name = best_match.get('level1_category', '')
                level2_name = best_match.get('level2_category', '')
                
                if level1_name and level2_name:
                    level1 = self.category_by_name.get(level1_name)
                    level2 = self.category_by_name.get(level2_name)
                    
                    if level1 and level2:
                        print(f"   ✅ 使用匹配算法的分类: {level1_name} → {level2_name}")
                        return level1, level2
            
            # ✅ 第四步：没有AI分析，没有匹配结果，创建概念题材
            print(f"   🚀 无法确定具体行业分类，创建概念题材")
            return None, None
            
        except Exception as e:
            print(f"   ❌ _get_determined_categories 发生异常: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def _match_shenwan_by_keywords(self, ai_keywords: List[str]) -> Tuple[Optional[Dict], Optional[Dict]]:
        """基于AI关键词匹配申万分类"""
        # ✅ 修复：确保keywords是有效的列表
        if not ai_keywords or not isinstance(ai_keywords, (list, tuple, set)):
            return None, None
        
        best_level1 = None
        best_level2 = None
        best_score = 0.3  # 匹配阈值
        
        # 先匹配二级分类
        for category in self.categories:
            if category and isinstance(category, dict) and category.get('category_level') == 2:
                # 计算匹配分数
                match_score = self._calculate_shenwan_match_score(ai_keywords, category)
                
                if match_score >= best_score:
                    # 找到对应的父分类（一级分类）
                    parent_code = category.get('parent_code')
                    if parent_code:
                        parent_category = self.category_by_code.get(parent_code)
                        
                        if parent_category:
                            best_score = match_score
                            best_level1 = parent_category
                            best_level2 = category
        
        return best_level1, best_level2

    def _calculate_shenwan_match_score(self, ai_keywords: List[str], category: Dict) -> float:
        """计算AI关键词与申万分类的匹配分数"""
        # ✅ 修复：确保输入有效
        if not ai_keywords or not isinstance(ai_keywords, (list, tuple, set)) or not category:
            return 0.0
        
        # 获取分类的关键词
        category_name = category.get('category_name', '')
        category_keywords = category.get('keywords', [])
        
        # ✅ 确保ai_keywords是可迭代的字符串列表
        try:
            ai_keywords_lower = [str(kw).lower() for kw in ai_keywords[:10] if kw]
        except Exception as e:
            print(f"   ⚠️  处理AI关键词失败: {e}")
            return 0.0
        
        category_name_lower = str(category_name).lower()
        
        # 处理分类关键词
        category_keywords_lower = []
        if isinstance(category_keywords, list):
            category_keywords_lower = [str(kw).lower() for kw in category_keywords if kw]
        elif isinstance(category_keywords, str):
            category_keywords_lower = [kw.strip().lower() for kw in str(category_keywords).split(',') if kw.strip()]
        
        # 计算匹配分数
        matches = 0
        
        for ai_kw in ai_keywords_lower:
            # 1. 检查分类名称匹配
            if ai_kw and ai_kw in category_name_lower:
                matches += 2.0  # 名称匹配权重更高
                continue
            
            # 2. 检查分类关键词匹配
            for cat_kw in category_keywords_lower:
                if ai_kw and cat_kw and (ai_kw in cat_kw or cat_kw in ai_kw):
                    matches += 1.0
                    break
        
        # 归一化分数
        total_keywords = len(ai_keywords_lower)
        return matches / total_keywords if total_keywords > 0 else 0.0
    
    def _extract_category_keywords(self, category: Optional[Dict]) -> List[str]:
        """提取分类关键词 - ✅ 修复：处理None情况"""
        if not category:
            return []
        
        keywords = []
        
        # 添加分类名称
        category_name = category.get('category_name', '')
        if category_name:
            keywords.append(category_name)
        
        # 添加分类的关键词字段
        category_keywords = category.get('keywords', [])
        if category_keywords:
            if isinstance(category_keywords, str):
                keywords.extend(category_keywords.split(','))
            elif isinstance(category_keywords, list):
                keywords.extend(category_keywords)
        
        return keywords
    
    def _infer_theme_type(self, event_data: Dict, level1: Optional[Dict], level2: Optional[Dict]) -> str:
        """推断题材类型 - ✅ 修复：处理空分类"""
        # ✅ 如果是概念题材，返回concept类型
        if level1 is None or level2 is None:
            return "concept"
        
        # ✅ 检查是否有AI分析
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            # 如果有AI分析，检查是否匹配到分类
            classification_result = event_data.get('classification_result', {})
            if 'ai_category_inference' in classification_result:
                ai_result = classification_result['ai_category_inference']
                theme_type = ai_result.get('theme_type', '')
                if theme_type:
                    print(f"   🤖 使用AI推断的题材类型: {theme_type}")
                    return theme_type
        
        try:
            event_title = event_data.get('title', '').lower()
            event_content = event_data.get('content', '').lower()
            event_text = f"{event_title} {event_content}"
            
            # 检查政策关键词
            policy_keywords = ['政策', '规划', '方案', '意见', '通知', '法规', '条例', 
                            '指导意见', '行动计划', '发展计划', '国务院', '发改委']
            if any(keyword in event_text for keyword in policy_keywords):
                return "policy"
            
            # 检查投资关键词
            investment_keywords = ['投资', '融资', '募资', 'IPO', '上市', '并购', '收购',
                                '估值', '市值', '股价', '财报', '业绩']
            if any(keyword in event_text for keyword in investment_keywords):
                return "investment"
            
            # ✅ 安全访问分类名称
            level1_name = level1.get('category_name', '') if level1 else ''
            
            # 检查行业分类
            industry_categories = ['银行', '证券', '保险', '房地产', '医药', '电子', 
                                '计算机', '通信', '汽车', '机械']
            if any(category in level1_name for category in industry_categories):
                return "industry"
            
            # 默认为概念类型
            return "concept"
        except Exception as e:
            print(f"   ⚠️  推断题材类型失败: {e}，返回concept")
            return "concept"
    
    def _generate_level3_name(self, event_data: Dict, level1: Dict, level2: Dict, 
                         theme_type: str) -> str:
        """
        生成三级分类名称
        ✅ 修复：处理空分类
        """
        ai_analysis = event_data.get('ai_analysis', {})
        title = event_data.get('title', '')
        
        # ✅ 安全获取分类名称
        level1_name = level1.get('category_name') if level1 else ""
        level2_name = level2.get('category_name') if level2 else ""
        
        # 优先使用AI核心概念
        if ai_analysis:
            core_concept = ai_analysis.get('core_concept', '')
            if core_concept:
                print(f"   🤖 使用AI核心概念作为三级分类: {core_concept}")
                return core_concept
        
        # 尝试从标题提取
        if title:
            # 提取标题中的关键词作为概念名称
            keywords = self._extract_keywords_from_text(title)
            if keywords:
                # 过滤掉分类关键词
                filtered_keywords = []
                for kw in keywords:
                    if (kw not in level1_name and 
                        kw not in level2_name and 
                        len(kw) >= 2):
                        filtered_keywords.append(kw)
                
                if filtered_keywords:
                    return ''.join(filtered_keywords[:2])
        
        # 最后方案：使用二级分类名称
        if level2_name:
            return level2_name
        
        # 备选方案：使用事件ID
        event_id = event_data.get('event_id', '')
        if event_id:
            return f"新题材_{event_id[-4:]}"
        
        return "新题材"
    
    def _extract_policy_name(self, text: str) -> str:
        """提取政策名称"""
        patterns = [
            r'《([^》]+)》',
            r'「([^」]+)」',
            r'"([^"]+)"',
            r"'([^']+)'",
            r'([^，。；！？]+)(?:政策|规划|方案|意见)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                for match in matches:
                    if len(match) >= 4 and len(match) <= 20:
                        return match
        
        return ""
    
    def _extract_core_concept(self, title: str, level1: Dict = None, level2: Dict = None) -> str:
        """
        从标题提取核心概念
        ✅ 修复：安全处理空分类
        """
        if not title:
            return "新概念"
        
        # ✅ 安全获取分类名称
        level1_name = level1.get('category_name') if level1 else ""
        level2_name = level2.get('category_name') if level2 else ""
        
        # 移除常见的修饰词
        exclude_words = ['市场', '行业', '板块', '概念', '领域', '技术', '应用', 
                        '发展', '研究', '分析', '前景', '趋势', '动态', '新闻']
        
        # 使用jieba分词
        import jieba
        
        try:
            # ✅ 安全分词：确保输入是字符串
            title_words = set(jieba.lcut(str(title)))  # ✅ 确保转换为字符串
            
            # ✅ 安全分词：只对非空字符串分词
            level1_words = set(jieba.lcut(str(level1_name))) if level1_name else set()
            level2_words = set(jieba.lcut(str(level2_name))) if level2_name else set()
            
            # 移除常见修饰词和分类词汇
            filtered_words = []
            for word in title_words:
                if (len(word) > 1 and 
                    word not in exclude_words and
                    word not in level1_words and
                    word not in level2_words):
                    filtered_words.append(word)
            
            # 取前2-3个关键词组成概念
            if filtered_words:
                # 优先选择较长的词汇
                filtered_words.sort(key=len, reverse=True)
                core_concept = ''.join(filtered_words[:2])
                return core_concept[:10]  # 限制长度
            
            # 备选方案：取标题中的关键词
            title_keywords = []
            for word in title_words:
                if len(word) >= 2 and word not in exclude_words:
                    title_keywords.append(word)
            
            if title_keywords:
                return title_keywords[0][:8]
            
            # 最后方案：返回标题的前几个字
            return title[:6]
        except Exception as e:
            print(f"   ⚠️  提取核心概念失败: {e}, 使用默认名称")
            return "新概念"
    
    def _check_existing_theme(self, level3_name: str, level1_name: str, 
                         level2_name: str, theme_type: str) -> bool:
        """
        检查是否已存在类似题材
        ✅ 修复：安全处理None值
        """
        if not hasattr(self, 'theme_by_name') or not self.theme_by_name:
            return False
        
        # 检查完全相同的三级分类名称
        for theme_name, theme in self.theme_by_name.items():
            # ✅ 安全访问theme字段
            theme_level3 = theme.get('level3_category', '')
            theme_name_str = theme.get('name', '')
            
            # 检查三级分类名称
            if (str(theme_level3).lower() == str(level3_name).lower() or
                str(theme_name_str).lower().startswith(str(level3_name).lower())):
                
                # 检查分类是否匹配
                theme_level1 = theme.get('level1_category', '')
                theme_level2 = theme.get('level2_category', '')
                
                # 如果是概念题材，分类可能为空
                is_concept = (theme_level1 == "概念题材" or 
                            theme_level1 is None or 
                            theme_level1 == "")
                
                # 概念题材的分类匹配更宽松
                if is_concept:
                    # 概念题材主要检查名称相似性
                    if level1_name == "概念题材":
                        return True
                else:
                    # 行业题材需要分类匹配
                    if (str(theme_level1) == str(level1_name) and 
                        str(theme_level2) == str(level2_name)):
                        return True
        
        return False
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """计算名称相似度"""
        suffixes = ['概念', '题材', '板块', '政策', '投资']
        name1_clean = name1
        name2_clean = name2
        
        for suffix in suffixes:
            if name1_clean.endswith(suffix):
                name1_clean = name1_clean[:-len(suffix)]
            if name2_clean.endswith(suffix):
                name2_clean = name2_clean[:-len(suffix)]
        
        set1 = set(name1_clean)
        set2 = set(name2_clean)
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _generate_theme_name(self, event_data: Dict, level1: Optional[Dict], 
                        level2: Optional[Dict], level3_name: str, 
                        theme_type: str) -> str:
        """
        生成题材名称
        ✅ 修复：处理空分类
        """
        # ✅ 安全获取分类名称
        level1_name = level1.get('category_name') if level1 else ""
        level2_name = level2.get('category_name') if level2 else ""
        
        if theme_type == "concept":
            # 概念题材：使用三级分类名称
            if not level3_name.endswith('概念'):
                return f"{level3_name}概念"
            return level3_name
        
        elif theme_type == "industry":
            # 行业题材：组合分类名称
            if level2_name:
                return f"{level2_name} - {level3_name}"
            elif level1_name:
                return f"{level1_name} - {level3_name}"
            else:
                return level3_name
        
        elif theme_type == "investment":
            # 投资题材：添加"投资"后缀
            if not level3_name.endswith('投资'):
                return f"{level3_name}投资"
            return level3_name
        
        else:
            # 默认：使用三级分类名称
            return level3_name
    
    def _int_to_roman(self, num: int) -> str:
        """整数转罗马数字"""
        roman_map = {1: 'Ⅰ', 2: 'Ⅱ', 3: 'Ⅲ', 4: 'Ⅳ', 5: 'Ⅴ'}
        return roman_map.get(num, '')
    
    def _generate_theme_code(self, theme_name: str, level1: Optional[Dict], 
                        level2: Optional[Dict], theme_type: str) -> str:
        """
        生成题材代码
        ✅ 修复：处理空分类
        """
        import hashlib
        
        # ✅ 安全获取分类代码
        if level2 and isinstance(level2, dict):
            category_code = level2.get('category_code', '000000')
        else:
            category_code = 'CONCEPT'  # 概念题材的特殊代码
        
        # 生成时间戳部分
        from datetime import datetime
        timestamp = datetime.now().strftime("%y%m%d")
        
        # 生成名称哈希
        name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
        
        # 组合代码
        if theme_type == "concept":
            code_prefix = "THM_CONCEPT_"
        elif theme_type == "industry":
            code_prefix = "THM_INDUSTRY_"
        elif theme_type == "investment":
            code_prefix = "THM_INVEST_"
        else:
            code_prefix = "THM_"
        
        # ✅ 根据是否是概念题材生成不同格式的代码
        if level1 is None or level2 is None:
            # 概念题材：使用时间戳+哈希
            theme_code = f"{code_prefix}{timestamp}{name_hash}"
        else:
            # 行业题材：使用分类代码+时间戳
            theme_code = f"{code_prefix}{category_code}_{timestamp}"
        
        return theme_code
    
    def _extract_keywords_from_event(self, event_data: Dict) -> List[str]:
        """
        从事件中提取关键词
        ✅ 修复：安全处理各种输入
        """
        keywords = []
        
        # 从事件中提取关键词
        event_keywords = event_data.get('keywords')
        if event_keywords:
            try:
                if isinstance(event_keywords, (list, tuple, set)):
                    keywords.extend([str(kw) for kw in event_keywords if kw is not None])
                elif isinstance(event_keywords, str):
                    keywords.extend([kw.strip() for kw in event_keywords.split(',') if kw.strip()])
            except Exception as e:
                print(f"   ⚠️  提取事件关键词失败: {e}")
        
        # 从AI分析中提取关键词
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            ai_keywords = ai_analysis.get('event_keywords')
            if ai_keywords:
                try:
                    if isinstance(ai_keywords, (list, tuple, set)):
                        keywords.extend([str(kw) for kw in ai_keywords if kw is not None])
                    elif isinstance(ai_keywords, str):
                        keywords.extend([kw.strip() for kw in ai_keywords.split(',') if kw.strip()])
                except Exception as e:
                    print(f"   ⚠️  提取AI关键词失败: {e}")
        
        # 去重
        unique_keywords = []
        seen = set()
        for kw in keywords:
            try:
                kw_str = str(kw).strip()
                if kw_str and kw_str not in seen:
                    seen.add(kw_str)
                    unique_keywords.append(kw_str)
            except Exception as e:
                print(f"   ⚠️  处理关键词 '{kw}' 失败: {e}")
        
        return unique_keywords[:20]  # 限制数量
    
    def _build_tags(self, event_data: Dict, keywords: List[str],
               level1: Optional[Dict], level2: Optional[Dict], level3_name: str,
               theme_type: str) -> Dict:
        """构建tags标签 - ✅ 修复：处理空分类"""
        # ✅ 安全获取分类名称
        level1_name = level1.get('category_name') if level1 else "概念题材"
        level2_name = level2.get('category_name') if level2 else level3_name
        level1_code = level1.get('category_code') if level1 else ""
        level2_code = level2.get('category_code') if level2 else ""
        
        tags = {
            "source": "auto_discovered",
            "aliases": self._generate_aliases(level2_name, level3_name, theme_type),
            "version": "1.0",
            "keywords": self._format_keywords(keywords, level2_name, theme_type),
            "heat_level": "low",
            "industries": [level1_name, level2_name],
            "industry_code": level2_code,
            "merge_candidates": [],
            "concepts": self._extract_concepts(event_data, theme_type),
            "is_hot": False,
            "trend_score": 0.5,
            "volatility": 0.3,
            "sector": level1_name,
            "sub_sector": level2_name,
            "creation_source": "theme_discovery",
            "event_id": event_data.get('event_id', ''),
            "event_type": event_data.get('event_type', 'normal'),
            "discovery_method": "keyword_matching"
        }
        
        # ✅ 如果有AI分析，添加AI信息
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            tags.update({
                "ai_generated": True,
                "ai_core_concept": ai_analysis.get('core_concept', ''),
                "ai_impact_level": ai_analysis.get('impact_level', 'medium'),
                "ai_confidence": ai_analysis.get('concept_confidence', 0.8),
                "ai_industry_keywords": ai_analysis.get('industry_keywords', [])[:10],
                "ai_event_keywords": ai_analysis.get('event_keywords', [])[:10],
                "ai_investment_logic": ai_analysis.get('investment_logic', '')[:200]
            })
        
        return tags
    
    def _generate_aliases(self, level2_name: str, concept: str, theme_type: str) -> List[str]:
        """生成别名列表"""
        aliases = []
        
        if theme_type == "investment":
            base_name = f"投资题材：{level2_name}"
            aliases.extend([
                base_name,
                f"{base_name}题材",
                f"{base_name}板块",
                f"{level2_name}投资机会",
                f"{level2_name}投资主题"
            ])
        elif theme_type == "policy":
            aliases.extend([
                f"政策题材：{concept}",
                f"{concept}政策",
                f"{concept}题材"
            ])
        else:
            aliases.extend([
                concept,
                f"{concept}题材",
                f"{concept}板块",
                f"{concept}概念股"
            ])
        
        return aliases[:10]
    
    def _format_keywords(self, keywords: List[str], level2_name: str, theme_type: str) -> List[str]:
        """格式化关键词列表"""
        formatted_keywords = []
        
        if theme_type == "investment":
            formatted_keywords.extend([
                f"{level2_name}概念",
                f"{level2_name}题材",
                f"{level2_name}板块",
                f"投资{level2_name}",
                f"{level2_name}投资"
            ])
        elif theme_type == "policy":
            formatted_keywords.extend([
                f"{level2_name}政策",
                f"政策{level2_name}",
                f"{level2_name}题材"
            ])
        else:
            formatted_keywords.extend([
                f"{level2_name}概念",
                f"{level2_name}题材",
                f"{level2_name}板块"
            ])
        
        formatted_keywords.extend(keywords[:10])
        
        finance_keywords = ['投资', '收益', '风险', '增长', '市场', '估值', '流动性']
        formatted_keywords.extend(finance_keywords)
        
        return list(set(formatted_keywords))[:20]
    
    def _extract_concepts(self, event_data: Dict, theme_type: str) -> List[str]:
        """提取概念标签"""
        # ✅ 修改：如果有AI分析，使用AI的核心概念
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            core_concept = ai_analysis.get('core_concept', '')
            if core_concept:
                return [core_concept, "AI发现", "新兴概念"]
        
        if theme_type == "investment":
            return ["产业投资", "行业轮动", "经济周期"]
        elif theme_type == "policy":
            return ["政策驱动", "政府支持", "规划引导"]
        else:
            return ["技术创新", "产业升级", "市场需求"]
    
    def _extract_policy_type(self, event_data: Dict) -> str:
        """提取政策类型"""
        event_title = event_data.get('title', '')
        
        policy_types = {
            '规划': 'development_plan',
            '方案': 'implementation_scheme',
            '意见': 'guidance_opinion',
            '通知': 'administrative_notice',
            '法规': 'regulation',
            '条例': 'ordinance'
        }
        
        for keyword, policy_type in policy_types.items():
            if keyword in event_title:
                return policy_type
        
        return 'general_policy'
    
    def _generate_description(self, event_data: Dict, level1: Optional[Dict], 
                         level2: Optional[Dict], level3_name: str, 
                         theme_type: str) -> str:
        """
        生成题材描述
        ✅ 修复：处理空分类
        """
        title = event_data.get('title', '')
        ai_analysis = event_data.get('ai_analysis', {})
        
        description_parts = []
        
        # ✅ 安全获取分类名称
        level1_name = level1.get('category_name') if level1 else None
        level2_name = level2.get('category_name') if level2 else None
        
        # 1. 开头描述
        if theme_type == "concept":
            description_parts.append(f"『{level3_name}』是一个新兴的资本市场概念。")
        elif theme_type == "industry":
            description_parts.append(f"『{level3_name}』是一个重要的行业细分领域。")
        elif theme_type == "investment":
            description_parts.append(f"『{level3_name}』是一个值得关注的投资主题。")
        else:
            description_parts.append(f"『{level3_name}』是一个新兴的主题。")
        
        # 2. 分类描述
        if level1_name and level2_name:
            description_parts.append(f"属于{level1_name}行业的{level2_name}细分领域。")
        elif level1_name:
            description_parts.append(f"属于{level1_name}行业领域。")
        elif level2_name:
            description_parts.append(f"属于{level2_name}相关领域。")
        else:
            description_parts.append("这是一个跨行业的新兴概念。")
        
        # 3. 事件来源描述
        if title:
            title_preview = title[:50] + "..." if len(title) > 50 else title
            description_parts.append(f"该题材源于事件：{title_preview}")
        
        # 4. AI分析描述
        if ai_analysis:
            core_concept = ai_analysis.get('core_concept', '')
            investment_logic = ai_analysis.get('investment_logic', '')
            
            if core_concept:
                description_parts.append(f"核心概念：{core_concept}。")
            
            if investment_logic:
                # 截取投资逻辑的前部分
                logic_preview = investment_logic[:100] + "..." if len(investment_logic) > 100 else investment_logic
                description_parts.append(f"投资逻辑：{logic_preview}")
        
        # 5. 状态描述
        description_parts.append("该题材目前处于早期发展阶段，具有较高的成长潜力。")
        
        # 组合所有部分
        description = ' '.join(description_parts)
        
        # 确保描述长度合适
        if len(description) > 500:
            description = description[:497] + "..."
        
        return description
    
    def _extract_stocks_from_event(self, event_data: Dict) -> List[str]:
        """从事件中提取相关股票"""
        content = event_data.get('content', '')
        
        stock_pattern = r'\b(60[0-9]{4}|00[0-9]{4}|300[0-9]{3}|688[0-9]{3})\b'
        stocks = re.findall(stock_pattern, content)
        
        return list(set(stocks))[:10]
    
    def _get_category3_code(self, level2: Dict, level3_name: str) -> Optional[str]:
        """获取三级分类代码"""
        return None
    
    def _calculate_initial_heat(self, event_data: Dict, theme_type: str, classification_result: Dict = None) -> int:
        """计算初始热度 - ✅ 修改：考虑AI影响级别"""
        base_heat = 50
        
        # 事件类型加成
        event_type = event_data.get('event_type', 'normal')
        if event_type == 'major':
            base_heat += 10
        
        # ✅ 修改：如果有AI分析，使用AI影响级别
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            impact_level = ai_analysis.get('impact_level', 'medium')
            impact_bonus = {
                'high': 20,
                'medium': 10,
                'low': 5
            }.get(impact_level, 10)
            base_heat += impact_bonus
            
            # AI置信度加成
            confidence = ai_analysis.get('concept_confidence', 0.8)
            base_heat += int(confidence * 10)
        
        # 题材类型加成
        type_bonus = {
            'investment': 5,
            'policy': 8,
            'concept': 3,
            'industry': 2
        }
        base_heat += type_bonus.get(theme_type, 0)
        
        # 标题长度加成
        title_length = len(event_data.get('title', ''))
        if title_length > 50:
            base_heat += 5
        
        return min(base_heat, 100)
    
    def _calculate_confidence(self, event_data: Dict, classification_result: Dict) -> float:
        """计算置信度 - ✅ 修改：考虑AI置信度"""
        base_confidence = classification_result.get('confidence', 0.0)
        
        # ✅ 修改：如果有AI分析，使用AI置信度
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            ai_confidence = ai_analysis.get('concept_confidence', 0.8)
            
            # 结合AI置信度和匹配置信度
            if classification_result.get('themes'):
                # 有匹配结果：综合计算
                combined_confidence = (ai_confidence * 0.6) + (base_confidence * 0.4)
                base_confidence = combined_confidence
            else:
                # 无匹配结果：主要使用AI置信度
                base_confidence = ai_confidence * 0.8
        
        # 事件类型加成
        event_type = event_data.get('event_type', 'normal')
        if event_type == 'major':
            base_confidence = min(base_confidence + 0.1, 0.9)
        
        return max(0.3, min(base_confidence, 0.9))
    
    def _determine_source_system(self, event_data: Dict) -> str:
        """确定来源系统 - ✅ 新增：根据是否有AI分析确定"""
        ai_analysis = event_data.get('ai_analysis', {})
        if ai_analysis:
            return "ai_major_event"
        else:
            return "auto_discovered"