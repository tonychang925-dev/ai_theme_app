# /Users/admin/Desktop/ai_theme_app/database_service/streams/processors/theme_rule_based_generator.py
"""
题材规则生成器 - 严格遵循数据库格式和规则
"""

import re
import uuid
import hashlib
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import jieba
import jieba.analyse


class ShenwanCodeGenerator:
    """申万编码生成器 - 严格遵循数据库格式"""
    
    # 申万行业编码映射
    SHENWAN_INDUSTRY_MAP = {
        '农林牧渔': '110000',
        '基础化工': '220000', 
        '钢铁': '230000',
        '有色金属': '240000',
        '电子': '270000',
        '汽车': '280000',
        '家用电器': '330000',
        '食品饮料': '340000',
        '纺织服饰': '350000',
        '轻工制造': '360000',
        '医药生物': '370000',
        '公用事业': '410000',
        '交通运输': '420000',
        '房地产': '430000',
        '商贸零售': '450000',
        '社会服务': '460000',
        '银行': '480000',
        '非银金融': '490000',
        '综合': '510000',
        '建筑材料': '610000',
        '建筑装饰': '620000',
        '电力设备': '630000',
        '机械设备': '640000',
        '国防军工': '650000',
        '计算机': '710000',
        '传媒': '720000',
        '通信': '730000',
        '煤炭': '740000',
        '石油石化': '750000',
        '环保': '760000',
        '美容护理': '770000'
    }
    
    @classmethod
    def generate_investment_level2_code(cls, level1_code: str, existing_codes: List[str]) -> str:
        """
        为行业题材生成二级分类代码
        
        规则：根据1级分类编码规范，生成对应的2级分类编码，2级编码要保持唯一性
        格式：前4位继承一级，中间1位为序列号，最后1位为0
        例如：110000 → 110100, 110200, 110300
        """
        if not level1_code or len(level1_code) != 6:
            return "999999"
        
        base_prefix = level1_code[:4]  # 前4位（如1100, 2200等）
        
        # 找出该一级分类下最大的二级分类序号
        max_seq = 0
        for code in existing_codes:
            if code.startswith(base_prefix) and len(code) == 6:
                try:
                    # 提取中间2位作为序号（如110100 -> 01）
                    seq_str = code[4:6]
                    if seq_str.isdigit():
                        seq = int(seq_str)
                        max_seq = max(max_seq, seq)
                except:
                    continue
        
        # 生成下一个序号（从01开始）
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1  # 如果超过99，从头开始
        
        return f"{base_prefix}{next_seq:02d}"
    
    @classmethod
    def generate_concept_level1_code(cls, existing_codes: List[str]) -> str:
        """
        生成概念题材的一级分类代码
        
        规则：创建唯一的1级分类编码，1级分类的category_type字段标识为"concept"
        格式：CT + 4位数字
        """
        # 找出最大的CT编码
        max_ct_num = 0
        for code in existing_codes:
            if code.startswith('CT'):
                try:
                    ct_num = int(code[2:6])
                    max_ct_num = max(max_ct_num, ct_num)
                except:
                    continue
        
        # 生成下一个CT编码
        next_ct_num = max_ct_num + 1
        if next_ct_num > 9999:
            next_ct_num = 1000
        
        return f"CT{next_ct_num:04d}"
    
    @classmethod
    def generate_concept_level2_code(cls, level1_code: str, existing_codes: List[str]) -> str:
        """
        为概念题材生成二级分类代码
        
        规则：2级编码要保持唯一性，2级编码的category_type字段填入"concept"
        格式：一级编码 + "_C" + 2位序号
        """
        if not level1_code.startswith('CT'):
            return f"{level1_code}_C01"
        
        # 找出该一级分类下最大的二级分类序号
        max_seq = 0
        pattern = re.compile(rf"^{re.escape(level1_code)}_C(\d{{2}})$")
        
        for code in existing_codes:
            match = pattern.match(code)
            if match:
                try:
                    seq = int(match.group(1))
                    max_seq = max(max_seq, seq)
                except:
                    continue
        
        # 生成下一个序号
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{level1_code}_C{next_seq:02d}"
    
    @classmethod
    def generate_theme_code(cls, theme_name: str, category1_code: Optional[str], 
                           category2_code: Optional[str], theme_type: str, 
                           is_test: bool = True) -> str:
        """
        生成题材代码 - 严格遵循数据库格式
        
        规则：
        1. 测试阶段以"TEST_"开头
        2. 行业题材格式：INVEST_SW_ + 二级分类代码
        3. 概念题材格式：CONCEPT_ + 时间戳 + 哈希
        """
        # 前缀处理
        prefix = "TEST_" if is_test else ""
        
        if theme_type == "investment" and category2_code:
            # 行业题材：INVEST_SW_ + 二级分类代码
            return f"{prefix}INVEST_SW_{category2_code}"
        
        elif theme_type == "concept":
            # 概念题材：CONCEPT_ + 时间戳 + 哈希
            timestamp = datetime.now().strftime("%y%m%d")
            name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
            return f"{prefix}CONCEPT_{timestamp}{name_hash}"
        
        else:
            # 其他类型
            timestamp = datetime.now().strftime("%y%m%d")
            name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
            return f"{prefix}{theme_type.upper()}_{timestamp}{name_hash}"
    
    @staticmethod
    def _int_to_roman(num: int) -> str:
        """整数转罗马数字"""
        roman_map = {1: 'Ⅰ', 2: 'Ⅱ', 3: 'Ⅲ', 4: 'Ⅳ', 5: 'Ⅴ', 6: 'Ⅵ', 7: 'Ⅶ', 8: 'Ⅷ', 9: 'Ⅸ', 10: 'Ⅹ'}
        return roman_map.get(num, f"_{num}")


class ThemeRuleBasedGeneratorFixed:
    """题材规则生成器 - 严格遵循数据库格式和规则"""
    
    def __init__(self, existing_themes: List[Dict], existing_categories: List[Dict]):
        self.existing_themes = existing_themes or []
        self.existing_categories = existing_categories or []
        
        # 构建缓存
        self._build_caches()
        # 跟踪已生成的CT编码
        self._generated_ct_codes_session = []
    
    def _build_caches(self):
        """构建缓存"""
        self.category_by_code = {}
        self.category_by_name = {}
        self.categories_by_level = {1: [], 2: [], 3: []}
        
        # 构建分类缓存
        for cat in self.existing_categories:
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
    
    def generate_new_theme(self, event_data: Dict, classification_result: Dict = None) -> Optional[Dict]:
        """
        生成新题材 - 严格遵循数据库格式
        """
        try:
            print(f"\n🔧 开始生成新题材，严格遵循数据库格式...")
            
            # 1. 获取事件基本信息
            event_id = event_data.get('event_id', 'unknown')
            title = event_data.get('title', '')[:100]  # 用于描述的标题
            event_type = event_data.get('event_type', 'normal')
            
            print(f"   事件: {title[:50]}... (ID: {event_id})")
            print(f"   类型: {event_type}")
            
            # 2. 获取AI分析 - 主要数据源
            ai_analysis = self._get_ai_analysis(event_data)
            if not ai_analysis:
                print(f"   ⚠️  没有AI分析数据")
                return None
            
            print(f"   📊 AI核心概念: {ai_analysis.get('core_concept', '未知')}")
            print(f"   🔑 AI关键词: {ai_analysis.get('industry_keywords', [])[:3]}")
            
            # 3. 处理 classification_result 参数（保持向后兼容）
            if not classification_result:
                classification_result = self._build_classification_from_ai_analysis(ai_analysis)
                print(f"   🔄 从AI分析构建分类结果")
            else:
                print(f"   🔄 使用传入的分类结果")
            
            # 4. 使用AI关键词进行匹配（主要逻辑）
            industry_keywords = ai_analysis.get('industry_keywords', [])
            matched_level1, matched_level2 = self._match_categories_by_ai_keywords(industry_keywords)
            
            # 如果AI关键词没有匹配到，尝试使用传入的分类结果
            if not matched_level1 and not matched_level2 and classification_result:
                matched_level1, matched_level2 = self._match_categories_by_classification_result(classification_result)
            
            # 5. 根据匹配结果确定处理逻辑
            theme_type, level1, level2, need_create_categories = self._determine_creation_logic(
                matched_level1, matched_level2, ai_analysis
            )
            
            print(f"   🎯 题材类型: {theme_type}")
            print(f"   📊 匹配结果: level1={'有' if matched_level1 else '无'}, "
                f"level2={'有' if matched_level2 else '无'}")
            
            # 6. 处理分类编码
            category1_code, category2_code = self._process_category_codes(
                theme_type, level1, level2, need_create_categories
            )
            
            print(f"   📍 分类编码: 1级={category1_code}, 2级={category2_code}")
            
            # 7. 生成三级分类名称
            level3_name = self._generate_level3_name(event_data, ai_analysis, level1, level2, theme_type)
            
            # 8. 检查是否已存在
            if self._check_existing_theme(level3_name, category1_code, category2_code, theme_type):
                print(f"   ⚠️  已存在类似题材: {level3_name}")
                return None
            
            # 9. 生成题材名称（优先使用事件标题）
            theme_name = self._generate_theme_name(event_data, ai_analysis, level3_name, theme_type)
            
            # 10. 生成题材代码（测试阶段以"TEST_"开头）
            theme_code = ShenwanCodeGenerator.generate_theme_code(
                theme_name, category1_code, category2_code, theme_type, is_test=True
            )
            
            # 11. 生成详细的tags（严格遵循数据库格式）
            tags = self._generate_detailed_tags(
                event_data, ai_analysis, level1, level2, level3_name, theme_type
            )
            
            # 12. 生成简明扼要的描述
            description = self._generate_concise_description(
                level3_name, theme_type
            )
            
            # 13. 构建完整数据（严格遵循数据库字段顺序）
            theme_data = self._build_theme_data(
                theme_name=theme_name,
                theme_code=theme_code,
                description=description,
                theme_type=theme_type,
                level1=level1,
                level2=level2,
                level3_name=level3_name,
                category1_code=category1_code,
                category2_code=category2_code,
                event_data=event_data,
                ai_analysis=ai_analysis,
                tags=tags
            )
            
            print(f"\n✅ 新题材生成成功:")
            print(f"   名称: {theme_name}")
            print(f"   代码: {theme_code} (以TEST_开头)")
            print(f"   类型: {theme_type}")
            if level1:
                print(f"   1级分类: {level1.get('category_name')} ({category1_code})")
            if level2:
                print(f"   2级分类: {level2.get('category_name')} ({category2_code})")
            
            return theme_data
            
        except Exception as e:
            print(f"❌ 生成新题材失败: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def _get_ai_analysis(self, event_data: Dict) -> Dict:
        """从事件数据获取AI分析"""
        ai_analysis = event_data.get('ai_analysis', {})
        if isinstance(ai_analysis, str):
            try:
                return json.loads(ai_analysis)
            except:
                return {}
        return ai_analysis

    def _build_classification_from_ai_analysis(self, ai_analysis: Dict) -> Dict:
        """从AI分析构建分类结果（用于保持向后兼容）"""
        core_concept = ai_analysis.get('core_concept', '')
        industry_keywords = ai_analysis.get('industry_keywords', [])
        concept_confidence = ai_analysis.get('concept_confidence', 0.5)
        
        # 尝试匹配分类
        matched_level1, matched_level2 = self._match_categories_by_ai_keywords(industry_keywords)
        
        if matched_level1 and matched_level2:
            return {
                'matched': True,
                'theme_type': 'investment' if matched_level2.get('category_type') == 'industry' else 'concept',
                'level1_category': matched_level1.get('category_name'),
                'level2_category': matched_level2.get('category_name'),
                'match_confidence': concept_confidence,
                'matched_keywords': industry_keywords[:3]
            }
        elif matched_level1:
            return {
                'matched': True,
                'theme_type': 'investment' if matched_level1.get('category_type') == 'industry' else 'concept',
                'level1_category': matched_level1.get('category_name'),
                'level2_category': None,
                'match_confidence': concept_confidence * 0.8,
                'matched_keywords': industry_keywords[:2]
            }
        else:
            return {
                'matched': False,
                'theme_type': 'concept',
                'level1_category': '概念题材',
                'level2_category': core_concept if core_concept else '新概念',
                'match_confidence': 0.0,
                'matched_keywords': []
            }

    def _match_categories_by_ai_keywords(self, industry_keywords: List[str]) -> Tuple[Optional[Dict], Optional[Dict]]:
        """使用AI关键词匹配分类 - 修复版：改进匹配逻辑"""
        if not industry_keywords:
            return None, None
        
        # 转换为小写便于匹配
        keywords_lower = [str(kw).lower() for kw in industry_keywords]
        
        print(f"   🧐 使用AI关键词匹配: {keywords_lower[:5]}")
        
        # 先尝试匹配2级分类
        best_level2 = None
        best_score = 0.0
        
        for category in self.categories_by_level.get(2, []):
            score = self._calculate_keyword_match_score_improved(keywords_lower, category)
            if score > best_score:
                best_score = score
                best_level2 = category
        
        if best_level2 and best_score >= 0.2:  # 降低阈值到0.2
            print(f"   ✅ 匹配到2级分类: {best_level2.get('category_name')} (分数: {best_score:.2f})")
            # 找到对应的1级分类
            parent_code = best_level2.get('parent_code')
            level1 = self.category_by_code.get(parent_code) if parent_code else None
            return level1, best_level2
        
        # 尝试匹配1级分类
        best_level1 = None
        best_score = 0.0
        
        for category in self.categories_by_level.get(1, []):
            score = self._calculate_keyword_match_score_improved(keywords_lower, category)
            if score > best_score:
                best_score = score
                best_level1 = category
        
        if best_level1 and best_score >= 0.2:  # 降低阈值到0.2
            print(f"   ✅ 匹配到1级分类: {best_level1.get('category_name')} (分数: {best_score:.2f})")
            return best_level1, None
        
        print(f"   ⚠️  未匹配到分类 (最高分数: {best_score:.2f})")
        return None, None

    def _calculate_keyword_match_score_improved(self, keywords: List[str], category: Dict) -> float:
        """计算关键词匹配分数 - 改进版：降低匹配难度"""
        category_name = category.get('category_name', '').lower()
        category_keywords = category.get('keywords', [])
        
        if isinstance(category_keywords, str):
            category_keywords = [kw.strip().lower() for kw in category_keywords.split(',') if kw.strip()]
        elif isinstance(category_keywords, list):
            category_keywords = [str(kw).lower() for kw in category_keywords]
        else:
            category_keywords = []
        
        # 构建所有匹配目标
        all_targets = [category_name] + category_keywords
        
        matches = 0
        total_checked = min(len(keywords), 8)  # 最多检查8个关键词
        
        for i, keyword in enumerate(keywords[:8]):
            kw_lower = str(keyword).lower()
            
            # 检查是否在任何目标中
            for target in all_targets:
                if not target:
                    continue
                    
                # 双向检查匹配
                if kw_lower in target or target in kw_lower:
                    matches += 1.0
                    break
        
        # 计算分数：匹配数 / 检查的关键词数
        score = matches / total_checked if total_checked > 0 else 0.0
        
        # 如果有关键词完全匹配分类名称，提高分数
        if any(str(kw).lower() == category_name for kw in keywords[:5]):
            score = max(score, 0.5)
        
        return score

    def _match_categories_by_classification_result(self, classification_result: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """使用传入的分类结果匹配分类（保持向后兼容）"""
        if not classification_result:
            return None, None
        
        level1_name = classification_result.get('level1_category')
        level2_name = classification_result.get('level2_category')
        
        matched_level1 = None
        matched_level2 = None
        
        if level2_name:
            matched_level2 = self.category_by_name.get(level2_name)
        
        if level1_name:
            matched_level1 = self.category_by_name.get(level1_name)
        
        # 如果只有2级分类，找到对应的1级分类
        if matched_level2 and not matched_level1:
            parent_code = matched_level2.get('parent_code')
            if parent_code:
                matched_level1 = self.category_by_code.get(parent_code)
        
        return matched_level1, matched_level2

    def _determine_creation_logic(self, matched_level1: Optional[Dict], 
                                matched_level2: Optional[Dict], 
                                ai_analysis: Dict) -> Tuple[str, Optional[Dict], Optional[Dict], str]:
        """确定创建逻辑 - 严格遵循规则"""
        
        if matched_level1 and matched_level2:
            level2_category_type = matched_level2.get('category_type', 'industry')
            
            if level2_category_type == 'industry':
                print(f"   🏭 匹配到1、2级行业分类，创建行业题材")
                return 'investment', matched_level1, matched_level2, 'none'
            else:
                print(f"   💡 匹配到1、2级概念分类，创建概念题材")
                return 'concept', matched_level1, matched_level2, 'none'
        
        elif matched_level1 and not matched_level2:
            level1_category_type = matched_level1.get('category_type', 'industry')
            
            if level1_category_type == 'industry':
                print(f"   🏭 匹配到1级行业分类，需要生成2级分类")
                return 'investment', matched_level1, None, 'level2'
            else:
                print(f"   💡 匹配到1级概念分类，需要生成2级分类")
                return 'concept', matched_level1, None, 'level2'
        
        else:
            # 未匹配到分类
            print(f"   🔍 未匹配到任何分类，创建概念题材")
            return 'concept', None, None, 'level1_and_2'
    
    def _process_category_codes(self, theme_type: str, level1: Optional[Dict], 
                           level2: Optional[Dict], need_create: str) -> Tuple[Optional[str], Optional[str]]:
        """处理分类编码 - 修复返回值问题"""
        if need_create == 'none':
            # 使用现有分类编码
            category1_code = level1.get('category_code') if level1 else None
            category2_code = level2.get('category_code') if level2 else None
            return category1_code, category2_code
        
        elif need_create == 'level2' and level1:
            # 生成2级分类编码
            level1_code = level1.get('category_code')
            
            # 找出该1级分类下所有的2级分类代码
            child_codes = []
            for cat in self.categories_by_level.get(2, []):
                if cat.get('parent_code') == level1_code:
                    child_codes.append(cat.get('category_code', ''))
            
            # 生成新的2级编码
            if theme_type == 'investment':
                # 行业题材编码规则
                new_code = self._generate_next_investment_code(level1_code, child_codes)
            else:
                # 概念题材编码规则
                new_code = self._generate_next_concept_code(level1_code, child_codes)
            
            return level1_code, new_code
        
        elif need_create == 'level1_and_2':
            # 创建新的1级和2级分类
            existing_codes = list(self.category_by_code.keys())
            
            if theme_type == 'concept':
                # 概念题材：CT开头，确保唯一性
                level1_code = self._generate_next_ct_code_fixed(existing_codes)
                level2_code = f"{level1_code}_C01"
                return level1_code, level2_code
            else:
                # 行业题材：正常编码
                level1_code = self._generate_next_industry_code(existing_codes)
                level2_code = self._generate_next_child_code(level1_code, existing_codes)
                return level1_code, level2_code
        
        # 默认返回
        return None, None
    
    def _generate_next_ct_code_fixed(self, existing_codes: List[str]) -> str:
        """生成下一个CT编码 - 修复版：确保唯一性"""
        # 首先从现有分类中找出最大的CT编码
        max_num = 0
        ct_codes_in_categories = []
        
        for cat in self.existing_categories:
            code = cat.get('category_code', '')
            if code.startswith('CT'):
                ct_codes_in_categories.append(code)
                try:
                    num = int(code[2:6])
                    max_num = max(max_num, num)
                except:
                    continue
        
        # 还要考虑当前会话中已经生成的CT编码
        for code in self._generated_ct_codes_session:
            if code.startswith('CT'):
                try:
                    num = int(code[2:6])
                    max_num = max(max_num, num)
                except:
                    continue
        
        # 生成下一个序号
        next_num = max_num + 1
        if next_num > 9999:
            next_num = 1000
        
        new_code = f"CT{next_num:04d}"
        
        # 记录在当前会话中已生成的CT编码
        self._generated_ct_codes_session.append(new_code)
        
        print(f"   🆕 生成新的CT编码: {new_code}")
        return new_code
    
    def _generate_next_investment_code(self, level1_code: str, child_codes: List[str]) -> str:
        """生成行业题材的下一级代码"""
        max_seq = 0
        for code in child_codes:
            try:
                # 提取最后两位数字
                seq = int(code[-2:])
                max_seq = max(max_seq, seq)
            except:
                continue
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{level1_code[:4]}{next_seq:02d}"
    
    def _generate_next_concept_code(self, level1_code: str, child_codes: List[str]) -> str:
        """生成概念题材的下一级代码"""
        pattern = re.compile(rf"^{re.escape(level1_code)}_C(\d{{2}})$")
        max_seq = 0
        
        for code in child_codes:
            match = pattern.match(code)
            if match:
                try:
                    seq = int(match.group(1))
                    max_seq = max(max_seq, seq)
                except:
                    continue
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{level1_code}_C{next_seq:02d}"
    
    def _generate_next_industry_code(self, existing_codes: List[str]) -> str:
        """生成下一个行业编码"""
        # 找出最大的行业编码（6位数字）
        max_num = 0
        for code in existing_codes:
            if code.isdigit() and len(code) == 6:
                try:
                    num = int(code)
                    max_num = max(max_num, num)
                except:
                    continue
        
        next_num = max_num + 10000  # 增加10000以保持6位
        if next_num > 999999:
            next_num = 100000
        
        return f"{next_num:06d}"
    
    def _generate_next_child_code(self, parent_code: str, existing_codes: List[str]) -> str:
        """生成下一个子分类编码"""
        # 简单实现：父编码 + "_01"
        return f"{parent_code}_01"
    
    def _generate_level3_name(self, event_data: Dict, ai_analysis: Dict, 
                             level1: Optional[Dict], level2: Optional[Dict], 
                             theme_type: str) -> str:
        """生成三级分类名称"""
        # 优先使用AI核心概念
        core_concept = ai_analysis.get('core_concept', '')
        if core_concept:
            return core_concept
        
        # 从标题提取
        title = event_data.get('title', '')
        if title:
            try:
                keywords = jieba.analyse.extract_tags(title, topK=3)
                if keywords:
                    # 组合前2个关键词
                    return ''.join(keywords[:2])
            except:
                pass
        
        # 根据题材类型生成默认名称
        if theme_type == 'investment':
            if level2:
                return f"{level2.get('category_name', '题材')}"
            elif level1:
                return f"{level1.get('category_name', '题材')}"
            else:
                return "新投资题材"
        else:
            return "新概念题材"
    
    def _check_existing_theme(self, level3_name: str, category1_code: Optional[str], 
                             category2_code: Optional[str], theme_type: str) -> bool:
        """检查是否已存在类似题材"""
        for theme in self.existing_themes:
            # 检查名称相似性
            existing_name = theme.get('name', '')
            existing_code = theme.get('code', '')
            
            # 如果代码已经以TEST_开头，可能是测试数据，不视为重复
            if existing_code.startswith('TEST_'):
                continue
            
            if level3_name in existing_name or existing_name in level3_name:
                # 检查分类编码
                existing_cat1 = theme.get('category1_code')
                existing_cat2 = theme.get('category2_code')
                
                if category2_code and existing_cat2 == category2_code:
                    return True
                elif category1_code and existing_cat1 == category1_code:
                    return True
        
        return False
    
    def _generate_theme_name(self, event_data: Dict, ai_analysis: Dict, 
                            level3_name: str, theme_type: str) -> str:
        """生成题材名称 - 优先使用事件标题"""
        # 规则：题材命名可以直接采用AI分析后提供的title来命名
        event_title = event_data.get('title', '')
        
        if event_title:
            # 清理title
            clean_title = event_title.strip()
            
            # 根据题材类型添加后缀
            if theme_type == 'concept' and not clean_title.endswith('概念'):
                return f"{clean_title}概念"
            elif theme_type == 'investment' and not clean_title.endswith(('投资', '题材')):
                return f"{clean_title}投资"
            return clean_title
        
        # 备用方案：使用三级分类名称
        if theme_type == 'concept' and not level3_name.endswith('概念'):
            return f"{level3_name}概念"
        elif theme_type == 'investment' and not level3_name.endswith(('投资', '题材')):
            return f"{level3_name}投资"
        
        return level3_name
    
    def _calculate_keyword_match_score(self, keywords: List[str], category: Dict) -> float:
        """计算关键词匹配分数"""
        category_name = category.get('category_name', '').lower()
        category_keywords = category.get('keywords', [])
        
        if isinstance(category_keywords, str):
            category_keywords = [kw.strip().lower() for kw in category_keywords.split(',') if kw.strip()]
        elif isinstance(category_keywords, list):
            category_keywords = [str(kw).lower() for kw in category_keywords]
        else:
            category_keywords = []
        
        matches = 0
        for keyword in keywords[:5]:  # 只检查前5个关键词
            kw_lower = str(keyword).lower()
            
            # 检查分类名称
            if kw_lower in category_name:
                matches += 2.0
                continue
            
            # 检查分类关键词
            for cat_kw in category_keywords:
                if kw_lower in cat_kw or cat_kw in kw_lower:
                    matches += 1.0
                    break
        
        return matches / len(keywords[:5]) if keywords else 0.0
    
    def _generate_detailed_tags(self, event_data: Dict, ai_analysis: Dict, 
                           level1: Optional[Dict], level2: Optional[Dict], 
                           level3_name: str, theme_type: str) -> Dict:
        """生成详细的tags - 严格遵循数据库格式"""
        # 基础tags结构
        tags = {
            "source": "ai_theme_discovery",
            "version": "1.0",
            "heat_level": self._determine_heat_level(ai_analysis),
            "merge_candidates": []
        }
        
        # 生成别名
        aliases = self._generate_aliases(level3_name, theme_type)
        tags["aliases"] = aliases
        
        # 生成关键词
        keywords = self._generate_keywords(event_data, ai_analysis, level1, level2)
        tags["keywords"] = keywords
        
        # 根据题材类型添加特定字段
        if theme_type == "investment":
            # 行业题材的tags结构
            tags.update({
                "concepts": ["产业投资", "行业轮动", "经济周期"],
                "industries": [
                    level1.get('category_name') if level1 else None,
                    level2.get('category_name') if level2 else None
                ],
                "industry_code": level3_name
            })
        else:
            # 概念题材的tags结构
            tags.update({
                "concepts": ["新兴概念", "事件驱动", "主题投资"],
                "concept_type": "emerging",
                "event_driven": True
            })
        
        # 清理None值
        return self._clean_none_values(tags)
    
    def _generate_aliases(self, theme_name: str, theme_type: str) -> List[str]:
        """生成别名列表"""
        aliases = [theme_name]
        
        if theme_type == "investment":
            aliases.extend([f"{theme_name}板块", f"{theme_name}行业"])
        else:
            aliases.extend([f"{theme_name}概念", f"{theme_name}主题"])
        
        return aliases
    
    def _generate_keywords(self, event_data: Dict, ai_analysis: Dict, 
                      level1: Optional[Dict], level2: Optional[Dict]) -> List[str]:
        """生成关键词列表"""
        keywords = []
        
        # 从AI分析获取关键词
        ai_keywords = ai_analysis.get('industry_keywords', [])[:5]
        keywords.extend(ai_keywords)
        
        # 从标题提取关键词
        title = event_data.get('title', '')
        if title:
            try:
                title_keywords = jieba.analyse.extract_tags(title, topK=3)
                keywords.extend(title_keywords)
            except:
                pass
        
        # 添加题材名称相关关键词
        if event_data.get('title'):
            keywords.append(event_data.get('title', '')[:20])
        
        # 添加分类相关关键词
        if level1:
            l1_name = level1.get('category_name', '')
            if l1_name:
                keywords.append(l1_name)
        
        if level2:
            l2_name = level2.get('category_name', '')
            if l2_name:
                keywords.append(l2_name)
        
        # 去重并限制数量
        unique_keywords = []
        seen = set()
        for kw in keywords:
            if kw and kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:10]
    
    def _determine_heat_level(self, ai_analysis: Dict) -> str:
        """确定热度等级"""
        impact = ai_analysis.get('impact_level', 'medium')
        confidence = ai_analysis.get('concept_confidence', 0.5)
        
        if impact == 'high' and confidence >= 0.7:
            return 'high'
        elif impact == 'medium' or confidence >= 0.5:
            return 'medium'
        else:
            return 'low'
    
    def _clean_none_values(self, data: Dict) -> Dict:
        """清理字典中的None值"""
        cleaned = {}
        for key, value in data.items():
            if value is not None:
                if isinstance(value, dict):
                    cleaned_value = self._clean_none_values(value)
                    if cleaned_value:  # 只添加非空字典
                        cleaned[key] = cleaned_value
                elif isinstance(value, list):
                    # 清理列表中的None值
                    cleaned_list = [v for v in value if v is not None]
                    if cleaned_list:  # 只添加非空列表
                        cleaned[key] = cleaned_list
                else:
                    cleaned[key] = value
        return cleaned
    
    def _extract_attributes(self, event_data: Dict, ai_analysis: Dict) -> List[str]:
        """提取题材属性"""
        attributes = []
        
        # 从事件类型
        if event_data.get('event_type') == 'major':
            attributes.append('重大事件驱动')
        
        # 从AI分析
        impact = ai_analysis.get('impact_level', 'medium')
        if impact == 'high':
            attributes.append('高影响')
        elif impact == 'medium':
            attributes.append('中影响')
        
        # 从内容判断
        title = event_data.get('title', '').lower()
        if any(word in title for word in ['技术', '创新', '研发', '专利']):
            attributes.append('技术创新')
        if any(word in title for word in ['政策', '规划', '支持', '补贴']):
            attributes.append('政策驱动')
        if any(word in title for word in ['增长', '扩张', '快速发展', '高增长']):
            attributes.append('高成长性')
        
        return attributes[:5]
    
    def _assess_risk_level(self, ai_analysis: Dict) -> Dict:
        """评估风险等级"""
        impact = ai_analysis.get('impact_level', 'medium')
        confidence = ai_analysis.get('concept_confidence', 0.5)
        
        if impact == 'high' and confidence >= 0.7:
            return {"level": "中低", "reason": "高影响高置信度"}
        elif impact == 'high' and confidence < 0.7:
            return {"level": "中高", "reason": "高影响低置信度"}
        elif impact == 'medium':
            return {"level": "中等", "reason": "中等影响"}
        else:
            return {"level": "中高", "reason": "低影响"}
    
    def _assess_growth_potential(self, ai_analysis: Dict) -> str:
        """评估成长潜力"""
        impact = ai_analysis.get('impact_level', 'medium')
        if impact == 'high':
            return '高'
        elif impact == 'medium':
            return '中等'
        else:
            return '一般'
    
    def _check_policy_support(self, event_data: Dict) -> bool:
        """检查政策支持"""
        title = event_data.get('title', '').lower()
        policy_keywords = ['政策', '规划', '方案', '意见', '通知', '指导意见', '行动计划']
        return any(keyword in title for keyword in policy_keywords)
    
    def _generate_concise_description(self, level3_name: str, theme_type: str) -> str:
        """生成简明扼要的描述 - 遵循数据库格式"""
        if theme_type == 'investment':
            return f"投资题材：{level3_name}（源于申万行业：{level3_name}）"
        else:
            return f"概念题材：{level3_name}"
    
    def _build_theme_data(self, theme_name: str, theme_code: str, description: str,
                     theme_type: str, level1: Optional[Dict], level2: Optional[Dict], 
                     level3_name: str, category1_code: Optional[str], 
                     category2_code: Optional[str], event_data: Dict, 
                     ai_analysis: Dict, tags: Dict) -> Dict:
        """构建题材数据 - 严格遵循数据库字段顺序"""
        # 构建分类路径
        category_path = []
        if level1:
            category_path.append(level1.get('category_name', ''))
        if level2:
            category_path.append(level2.get('category_name', ''))
        category_path.append(level3_name)
        
        # 生成三级分类代码（可以为null）
        category3_code = None
        
        # 计算初始热度和置信度
        heat_score = self._calculate_initial_heat(ai_analysis)
        confidence_score = ai_analysis.get('concept_confidence', 0.5)
        
        # 构建完整的主题数据（严格遵循数据库字段顺序）
        theme_data = {
            'name': theme_name,
            'code': theme_code,
            'description': description,
            'status': 'active',
            'level1_category': level1.get('category_name') if level1 else None,
            'level2_category': level2.get('category_name') if level2 else None,
            'level3_category': level3_name,
            'category_path': category_path,
            'category1_code': category1_code,
            'category2_code': category2_code,
            'category3_code': category3_code,
            'tags': tags,
            'theme_type': theme_type,
            'heat_score': heat_score,
            'confidence_score': confidence_score,
            'lifecycle_stage': 'emerging',
            'related_stocks': {},
            'stock_count': 0,
            'news_count': 0,
            'mention_count': 0,
            'last_mentioned': None,
            'source_system': 'ai_theme_discovery',
            'source_id': event_data.get('event_id', ''),
            'created_by': 'theme_discovery_system',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'last_active_at': datetime.now().isoformat()
        }
        
        return theme_data
    
    def _calculate_initial_heat(self, ai_analysis: Dict) -> int:
        """计算初始热度"""
        base_heat = 50
        impact = ai_analysis.get('impact_level', 'medium')
        confidence = ai_analysis.get('concept_confidence', 0.5)
        
        if impact == 'high':
            base_heat += 20
        elif impact == 'medium':
            base_heat += 10
        
        base_heat += int(confidence * 20)
        
        return min(base_heat, 100)


# 测试函数
def test_theme_generation():
    """测试题材生成"""
    # 模拟现有分类数据
    existing_categories = [
        # 行业分类 (industry)
        {"category_code": "110000", "category_name": "农林牧渔", "category_level": 1, 
         "category_type": "industry", "description": "申万一级行业[SW2021]：农林牧渔"},
        {"category_code": "110100", "category_name": "种植业", "category_level": 2, 
         "parent_code": "110000", "category_type": "industry"},
        {"category_code": "270000", "category_name": "电子", "category_level": 1, 
         "category_type": "industry", "description": "申万一级行业[SW2021]：电子"},
        {"category_code": "270100", "category_name": "半导体", "category_level": 2, 
         "parent_code": "270000", "category_type": "industry"},
        
        # 概念分类 (concept)
        {"category_code": "CT0001", "category_name": "人工智能概念", "category_level": 1, 
         "category_type": "concept", "description": "人工智能相关概念"},
        {"category_code": "CT0001_C01", "category_name": "AI芯片概念", "category_level": 2, 
         "parent_code": "CT0001", "category_type": "concept"},
    ]
    
    # 模拟现有题材
    existing_themes = [
        {"name": "教育出版", "code": "INVEST_SW_720901", "theme_type": "investment",
         "category1_code": "720000", "category2_code": "720900"},
        {"name": "AI芯片概念", "code": "CONCEPT_20240101_ABCD", "theme_type": "concept",
         "category1_code": "CT0001", "category2_code": "CT0001_C01"},
    ]
    
    generator = ThemeRuleBasedGeneratorFixed(existing_themes, existing_categories)
    
    # 测试用例1: 行业题材 - 匹配到1、2级分类
    print("\n" + "="*60)
    print("测试用例1: 行业题材 - 匹配到1、2级分类")
    print("="*60)
    
    event1 = {
        "event_id": "event_001",
        "title": "半导体设备国产化取得重大突破",
        "event_type": "major",
        "ai_analysis": {
            "core_concept": "半导体设备",
            "industry_keywords": ["半导体", "设备", "国产化"],
            "impact_level": "high",
            "concept_confidence": 0.8
        }
    }
    
    classification1 = {
        "ai_category_inference": {
            "matched": True,
            "level1_category": "电子",
            "level2_category": "半导体",
            "theme_type": "investment"
        }
    }
    
    theme1 = generator.generate_new_theme(event1, classification1)
    if theme1:
        print(f"✅ 生成成功: {theme1['name']} ({theme1['code']})")
        print(f"   类型: {theme1['theme_type']}")
        print(f"   代码格式检查: {theme1['code'].startswith('TEST_')}")
        print(f"   tags字段检查: {theme1['tags']}")
    
    # 测试用例2: 行业题材 - 只匹配到1级分类
    print("\n" + "="*60)
    print("测试用例2: 行业题材 - 只匹配到1级分类")
    print("="*60)
    
    event2 = {
        "event_id": "event_002",
        "title": "新型农业技术推广应用",
        "event_type": "normal",
        "ai_analysis": {
            "core_concept": "智慧农业",
            "industry_keywords": ["农业", "技术", "智慧"],
            "impact_level": "medium",
            "concept_confidence": 0.7
        }
    }
    
    classification2 = {
        "ai_category_inference": {
            "matched": True,
            "level1_category": "农林牧渔",
            "level2_category": None,
            "theme_type": "investment"
        }
    }
    
    theme2 = generator.generate_new_theme(event2, classification2)
    if theme2:
        print(f"✅ 生成成功: {theme2['name']} ({theme2['code']})")
        print(f"   类型: {theme2['theme_type']}")
        print(f"   新生成的2级分类编码: {theme2['category2_code']}")
        print(f"   代码格式检查: {theme2['code'].startswith('TEST_INVEST_SW_')}")
    
    # 测试用例3: 概念题材 - 未匹配到任何分类
    print("\n" + "="*60)
    print("测试用例3: 概念题材 - 未匹配到任何分类")
    print("="*60)
    
    event3 = {
        "event_id": "event_003",
        "title": "元宇宙虚拟现实技术新突破",
        "event_type": "major",
        "ai_analysis": {
            "core_concept": "元宇宙",
            "industry_keywords": ["虚拟现实", "数字孪生"],
            "impact_level": "high",
            "concept_confidence": 0.75
        }
    }
    
    classification3 = {
        "ai_category_inference": {
            "matched": False,
            "theme_type": "concept"
        }
    }
    
    theme3 = generator.generate_new_theme(event3, classification3)
    if theme3:
        print(f"✅ 生成成功: {theme3['name']} ({theme3['code']})")
        print(f"   类型: {theme3['theme_type']}")
        print(f"   新生成的1级分类编码: {theme3['category1_code']}")
        print(f"   新生成的2级分类编码: {theme3['category2_code']}")
        print(f"   代码格式检查: {theme3['code'].startswith('TEST_CONCEPT_')}")


if __name__ == "__main__":
    test_theme_generation()