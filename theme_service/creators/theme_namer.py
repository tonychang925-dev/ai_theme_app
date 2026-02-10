"""
题材命名器 - 生成合理的题材名称
"""
import jieba
from typing import List, Dict, Any

class ThemeNamer:
    """题材命名器 - 基于实际命名规则"""
    
    def __init__(self, existing_themes: List[Dict]):
        self.existing_themes = existing_themes
        self.existing_names = {theme['name'] for theme in existing_themes}
        
        # 分析现有命名模式
        self._analyze_naming_patterns()
    
    def _analyze_naming_patterns(self):
        """分析现有命名模式"""
        self.name_patterns = {
            '行业型': [],  # 如"股份制银行Ⅲ"
            '概念型': [],  # 如"人工智能算法"
            '投资型': [],  # 如"投资题材：股份制银行Ⅲ"
            '政策型': []   # 如"政策题材：某某政策"
        }
        
        for theme in self.existing_themes:
            name = theme.get('name', '')
            theme_type = theme.get('theme_type', '')
            
            if name.startswith('投资题材：'):
                self.name_patterns['投资型'].append(name)
            elif name.startswith('政策题材：'):
                self.name_patterns['政策型'].append(name)
            elif any(c in name for c in ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ']):
                self.name_patterns['行业型'].append(name)
            else:
                self.name_patterns['概念型'].append(name)
    
    def generate_theme_name(self, event_data: Dict,
                           level1: Dict, level2: Dict, level3_concept: str,
                           theme_type: str = "concept") -> str:
        """生成题材名称（基于实际规则）"""
        if theme_type == "investment":
            return self._generate_investment_name(level2, level3_concept)
        elif theme_type == "policy":
            return self._generate_policy_name(event_data, level3_concept)
        else:
            return self._generate_concept_name(level2, level3_concept)
    
    def _generate_investment_name(self, level2: Dict, concept: str) -> str:
        """生成投资题材名称"""
        # 投资题材名称格式：投资题材：二级分类名称（源于来源：三级概念）
        base_name = f"投资题材：{level2['category_name']}"
        
        # 检查是否已存在类似名称
        existing_investment = [n for n in self.name_patterns['投资型'] 
                              if n.startswith(f"投资题材：{level2['category_name']}")]
        
        if existing_investment:
            # 如果有多个，添加序号
            max_num = 0
            for name in existing_investment:
                # 提取序号：股份制银行Ⅰ -> 1
                roman_match = re.search(r'[ⅠⅡⅢⅣⅤ]+$', name)
                if roman_match:
                    roman_num = roman_match.group()
                    num = self._roman_to_int(roman_num)
                    max_num = max(max_num, num)
            
            if max_num > 0:
                next_roman = self._int_to_roman(max_num + 1)
                return f"投资题材：{level2['category_name']}{next_roman}"
        
        return base_name
    
    def _generate_concept_name(self, level2: Dict, concept: str) -> str:
        """生成概念题材名称"""
        # 概念题材格式：二级分类 + 三级概念
        if concept.endswith('概念'):
            return concept
        else:
            return f"{concept}概念"
    
    def _generate_policy_name(self, event_data: Dict, concept: str) -> str:
        """生成政策题材名称"""
        event_title = event_data.get('title', '')
        
        # 从事件标题提取政策关键词
        policy_keywords = self._extract_policy_keywords(event_title)
        
        if policy_keywords:
            return f"政策题材：{policy_keywords}"
        else:
            return f"政策题材：{concept}"
    
    def _extract_policy_keywords(self, text: str) -> str:
        """提取政策关键词"""
        policy_indicators = ['政策', '规划', '方案', '意见', '通知', '法规', '条例',
                           '指导意见', '行动计划', '发展计划']
        
        words = jieba.lcut(text)
        
        # 找到政策相关词后面的关键词
        for i, word in enumerate(words):
            if word in policy_indicators and i + 1 < len(words):
                next_word = words[i + 1]
                if len(next_word) >= 2:
                    return f"{word}{next_word}"
        
        return ""
    
    def _roman_to_int(self, roman: str) -> int:
        """罗马数字转整数"""
        roman_map = {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5}
        return roman_map.get(roman, 0)
    
    def _int_to_roman(self, num: int) -> str:
        """整数转罗马数字"""
        roman_map = {1: 'Ⅰ', 2: 'Ⅱ', 3: 'Ⅲ', 4: 'Ⅳ', 5: 'Ⅴ'}
        return roman_map.get(num, '')