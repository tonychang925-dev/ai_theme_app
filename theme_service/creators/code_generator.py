"""
题材代码生成器 - 生成唯一的题材代码
"""
import re
from typing import List, Dict, Any

class ThemeCodeGenerator:
    """题材代码生成器 - 基于实际代码格式"""
    
    def __init__(self, existing_themes: List[Dict]):
        self.existing_codes = {theme['code'] for theme in existing_themes}
        self.theme_type_prefixes = {
            'investment': 'INVEST',
            'policy': 'POLICY',
            'relation': 'REL',
            'event': 'EVENT',
            'concept': 'THM',
            'industry': 'IND'
        }
    
    def generate_code(self, theme_name: str, level1: Dict, level2: Dict,
                     theme_type: str = "concept", source_system: str = "shenwan") -> str:
        """
        生成题材代码（基于实际格式）
        
        实际代码格式示例：INVEST_SW_480301
        格式：类型_来源_分类代码
        """
        # 确定类型前缀
        type_prefix = self.theme_type_prefixes.get(theme_type, 'THM')
        
        # 确定来源前缀
        source_prefix = self._get_source_prefix(source_system)
        
        # 获取分类代码（优先使用实际的分类代码）
        category_code = self._get_category_code(level1, level2)
        
        # 生成基础代码
        base_code = f"{type_prefix}_{source_prefix}_{category_code}"
        
        # 确保唯一性
        final_code = self._ensure_unique_code(base_code)
        
        return final_code
    
    def _get_source_prefix(self, source_system: str) -> str:
        """获取来源系统前缀"""
        source_prefixes = {
            'shenwan': 'SW',
            'transformed': 'TRANS',
            'ai_generated': 'AI',
            'manual': 'MAN',
            'auto_discovered': 'AD'
        }
        return source_prefixes.get(source_system.lower(), 'GEN')
    
    def _get_category_code(self, level1: Dict, level2: Dict) -> str:
        """获取分类代码"""
        # 优先使用二级分类的代码
        if level2 and level2.get('category_code'):
            cat_code = level2['category_code']
            # 提取数字部分，如 480300 -> 480301
            if cat_code and cat_code.isdigit() and len(cat_code) >= 4:
                # 查找该分类下已有的题材数量
                existing_count = self._count_themes_in_category(cat_code)
                # 生成新的序号
                new_number = int(cat_code[-3:]) + existing_count
                return f"{cat_code[:-3]}{new_number:03d}"
        
        # 如果没有分类代码，生成基于名称的代码
        return self._generate_code_from_name(level2['category_name'])
    
    def _count_themes_in_category(self, category_code: str) -> int:
        """统计该分类下已有的题材数量"""
        count = 0
        for code in self.existing_codes:
            # 检查代码中是否包含该分类代码
            if f"_{category_code[:4]}" in code:
                count += 1
        return count
    
    def _generate_code_from_name(self, name: str) -> str:
        """从名称生成代码"""
        if not name:
            return "000000"
        
        # 简单的拼音首字母映射
        pinyin_map = {
            '银行': '480',
            '证券': '490',
            '保险': '500',
            '房地产': '700',
            '医药': '270',
            '电子': '720',
            '计算机': '730',
            '通信': '740',
            '传媒': '750',
            '军工': '650',
            '汽车': '220',
            '机械': '640',
            '电力': '440',
            '化工': '430',
            '有色': '330',
            '煤炭': '210',
            '钢铁': '310',
            '建筑': '620',
            '建材': '610',
            '家电': '630',
            '食品': '340',
            '农业': '110',
            '零售': '520',
            '旅游': '800',
            '运输': '420'
        }
        
        # 查找匹配的行业代码
        for keyword, code in pinyin_map.items():
            if keyword in name:
                # 生成6位代码：行业代码 + 3位序号
                existing_counts = {}
                for existing_code in self.existing_codes:
                    if existing_code.startswith(code[:3]):
                        try:
                            seq = int(existing_code[-3:])
                            existing_counts[code] = max(existing_counts.get(code, 0), seq)
                        except:
                            continue
                
                next_seq = existing_counts.get(code, 0) + 1
                return f"{code}{next_seq:03d}"
        
        # 默认生成代码
        return "999001"
    
    def _ensure_unique_code(self, base_code: str) -> str:
        """确保代码唯一性"""
        if base_code not in self.existing_codes:
            return base_code
        
        # 如果冲突，尝试添加后缀
        suffix = 1
        while True:
            new_code = f"{base_code}_{suffix:02d}"
            if new_code not in self.existing_codes:
                return new_code
            suffix += 1