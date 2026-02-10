# theme_service/creators/fixed_category_generator.py
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

class FixedCategoryGenerator:
    """
    修复版分类生成器
    严格遵守编码规则，不使用任何硬编码或模拟数据
    """
    
    def __init__(self, existing_categories: List[Dict]):
        """必须传入真实的现有分类数据"""
        self.existing_categories = existing_categories or []
        self.existing_codes = self._extract_existing_codes()
        
    def _extract_existing_codes(self) -> List[str]:
        """从现有分类中提取所有编码"""
        codes = []
        for cat in self.existing_categories:
            code = cat.get('category_code')
            if code and isinstance(code, str):
                codes.append(code)
        logger.info(f"📊 提取到 {len(codes)} 个现有分类编码")
        return codes
    
    def generate_concept_categories(self, ai_analysis: Dict, event_data: Dict) -> Dict:
        """
        为概念题材生成分类数据
        
        严格遵循规则：
        1. 使用ShenwanCodeGenerator生成唯一编码
        2. 基于AI分析生成有意义的名称
        3. 确保编码不重复
        """
        try:
            # 从ShenwanCodeGenerator导入（必须使用项目中已存在的）
            from .theme_rule_generator import ShenwanCodeGenerator
            
            # 1. 生成一级分类编码（确保唯一）
            level1_code = ShenwanCodeGenerator.generate_concept_level1_code(self.existing_codes)
            
            # 2. 生成有意义的分类名称（基于AI分析）
            level1_name = self._generate_concept_level1_name(ai_analysis)
            
            # 3. 生成二级分类编码
            # 先找出该一级分类下已有的二级分类
            child_codes = [
                code for code in self.existing_codes 
                if code.startswith(f"{level1_code}_C") and "_C" in code
            ]
            
            level2_code = ShenwanCodeGenerator.generate_concept_level2_code(
                level1_code, child_codes
            )
            
            # 4. 生成具体的二级分类名称
            level2_name = self._generate_concept_level2_name(ai_analysis, event_data)
            
            # 5. 验证生成的编码是否唯一
            self._validate_code_uniqueness(level1_code, level2_code)
            
            # 6. 构建完整的分类数据
            level1_data = {
                'category_code': level1_code,
                'category_name': level1_name,
                'category_level': 1,
                'category_type': 'concept',
                'description': f'{level1_name}分类，涵盖相关概念题材',
                'keywords': self._generate_category_keywords(ai_analysis, level=1),
                'source_system': 'ai_theme_discovery',
                'created_by': 'fixed_category_generator'
            }
            
            level2_data = {
                'category_code': level2_code,
                'category_name': level2_name,
                'category_level': 2,
                'category_type': 'concept',
                'parent_code': level1_code,
                'description': f'概念子类：{level2_name}，源于相关事件或趋势',
                'keywords': self._generate_category_keywords(ai_analysis, level=2),
                'source_system': 'ai_theme_discovery',
                'created_by': 'fixed_category_generator'
            }
            
            logger.info(f"✅ 生成概念分类:")
            logger.info(f"   一级: {level1_code} - {level1_name}")
            logger.info(f"   二级: {level2_code} - {level2_name}")
            
            return {
                'level1': level1_data,
                'level2': level2_data,
                'need_create_category': True,
                'action': 'create_both'
            }
            
        except ImportError as e:
            # ❌ 绝不降级：如果找不到ShenwanCodeGenerator，直接报错
            logger.error(f"❌ 无法导入ShenwanCodeGenerator: {e}")
            raise RuntimeError("ShenwanCodeGenerator不存在，必须修复项目依赖")
        except Exception as e:
            logger.error(f"❌ 生成概念分类失败: {e}")
            raise
    
    def _generate_concept_level1_name(self, ai_analysis: Dict) -> str:
        """基于AI分析生成有意义的一级分类名称"""
        # 分析概念类型
        concept_type = self._analyze_concept_type(ai_analysis)
        
        # 映射到具体的分类名称
        type_to_name = {
            'geopolitical': '地缘政治概念',
            'technology': '技术概念',
            'economic': '经济概念',
            'environmental': '环境概念',
            'social': '社会概念',
            'health': '健康概念',
            'default': '综合概念'
        }
        
        return type_to_name.get(concept_type, type_to_name['default'])
    
    def _analyze_concept_type(self, ai_analysis: Dict) -> str:
        """分析AI分析结果，确定概念类型"""
        keywords = ai_analysis.get('event_keywords', [])
        core_concept = ai_analysis.get('core_concept', '')
        
        all_text = ' '.join([core_concept] + keywords).lower()
        
        # 定义类型关键词
        type_keywords = {
            'geopolitical': ['地缘政治', '国际关系', '外交', '军事', '安全', '领土', '制裁'],
            'technology': ['技术', '科技', '创新', '研发', '半导体', '芯片', '人工智能', '软件', '硬件'],
            'economic': ['经济', '金融', '市场', '贸易', '投资', '消费', '货币', '汇率', '通胀'],
            'environmental': ['环境', '气候', '能源', '环保', '可持续', '绿色', '碳中和', '污染'],
            'social': ['社会', '民生', '教育', '医疗', '文化', '娱乐', '体育', '旅游'],
            'health': ['健康', '医疗', '医药', '疫苗', '治疗', '疾病', '保健']
        }
        
        # 计算各类型匹配分数
        scores = {}
        for concept_type, type_words in type_keywords.items():
            score = sum(1 for word in type_words if word in all_text)
            if score > 0:
                scores[concept_type] = score
        
        # 返回最高分的类型
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        
        return 'default'
    
    def _generate_concept_level2_name(self, ai_analysis: Dict, event_data: Dict) -> str:
        """生成具体的二级分类名称"""
        core_concept = ai_analysis.get('core_concept', '')
        event_title = event_data.get('title', '')
        
        # 优先使用核心概念
        if core_concept and len(core_concept) <= 20:
            # 移除可能的"概念"后缀
            if core_concept.endswith('概念'):
                return core_concept[:-2]
            return core_concept
        
        # 使用事件标题（简化）
        if event_title:
            # 简化标题作为分类名称
            simplified = self._simplify_title(event_title)
            if simplified and len(simplified) <= 15:
                return simplified
        
        # 使用AI关键词
        keywords = ai_analysis.get('event_keywords', [])
        if keywords:
            return keywords[0] if len(keywords[0]) <= 15 else keywords[0][:15]
        
        # 最后手段：生成基于时间的名称（但至少不是硬编码）
        timestamp = datetime.now().strftime('%m%d')
        return f"新概念{timestamp}"
    
    def _simplify_title(self, title: str) -> str:
        """简化事件标题作为分类名称"""
        # 移除常见后缀
        for suffix in ['相关新闻', '事件', '新闻', '消息', '报道']:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
        
        # 截断过长的标题
        if len(title) > 15:
            title = title[:12] + '...'
        
        return title
    
    def _validate_code_uniqueness(self, level1_code: str, level2_code: str):
        """验证生成的编码在现有编码中唯一"""
        if level1_code in self.existing_codes:
            raise ValueError(f"❌ 生成的一级分类编码已存在: {level1_code}")
        
        if level2_code in self.existing_codes:
            raise ValueError(f"❌ 生成的二级分类编码已存在: {level2_code}")
        
        logger.debug(f"✅ 编码验证通过: {level1_code}, {level2_code} 唯一")
    
    def _generate_category_keywords(self, ai_analysis: Dict, level: int) -> List[str]:
        """生成分类关键词"""
        keywords = []
        
        # 基础关键词
        base_keywords = ai_analysis.get('event_keywords', [])[:5]
        keywords.extend(base_keywords)
        
        # 根据级别添加关键词
        if level == 1:
            keywords.extend(['概念题材', '主题投资', '新兴概念'])
        else:
            keywords.extend(['概念子类', '细分概念'])
        
        # 去重
        return list(dict.fromkeys(keywords))