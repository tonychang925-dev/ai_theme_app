# /Users/admin/Desktop/ai_theme_app/theme_service/creators/theme_rule_generator.py
import re
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import jieba.analyse

from theme_service.schemas.strict_dto import StrictCompleteThemeDTO

logger = logging.getLogger(__name__)


class ShenwanCodeGenerator:
    """申万编码生成器 - 完整版"""
    
    @staticmethod
    def generate_investment_level2_code(level1_code: str, existing_codes: List[str]) -> str:
        """
        为行业题材生成二级分类代码
        格式：前4位继承一级，后2位为序列号
        例如：110000 → 110100, 110200, 110300
        """
        if not level1_code or len(level1_code) != 6:
            return "999999"
        
        base_prefix = level1_code[:4]
        
        # 找出该一级分类下最大的二级分类序号
        max_seq = 0
        for code in existing_codes:
            if code.startswith(base_prefix) and len(code) == 6:
                try:
                    seq_str = code[4:6]
                    if seq_str.isdigit():
                        seq = int(seq_str)
                        max_seq = max(max_seq, seq)
                except:
                    continue
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{base_prefix}{next_seq:02d}"
    
    @staticmethod
    def generate_concept_level1_code(existing_codes: List[str]) -> str:
        """生成概念一级分类代码 - 确保编码唯一性"""
        # 1. 首先提取所有现有的CT编码
        existing_ct_codes = []
        existing_ct_numbers = set()  # 用于快速查找
        
        for code in existing_codes:
            if isinstance(code, str) and code.startswith('CT'):
                # 解析数字部分
                match = re.match(r'CT(\d{4})$', code)  # 只匹配标准格式：CT0001
                if match:
                    try:
                        ct_num = int(match.group(1))
                        existing_ct_codes.append(code)
                        existing_ct_numbers.add(ct_num)
                    except (ValueError, TypeError):
                        continue
        
        # 2. 如果没有现有CT编码，从0001开始
        if not existing_ct_numbers:
            return "CT0001"
        
        # 3. 找出当前最大的CT编码
        max_ct_num = max(existing_ct_numbers)
        
        # 4. 生成新的编码（递增）
        next_ct_num = max_ct_num + 1
        
        # 5. 如果超过9999，从最小的空缺开始找
        if next_ct_num > 9999:
            # 寻找空缺的编码（从0001开始找第一个可用的）
            for i in range(1, 10000):
                if i not in existing_ct_numbers:
                    next_ct_num = i
                    break
            else:
                # 如果没有空缺，生成一个基于哈希的临时编码
                import hashlib
                timestamp = str(int(datetime.now().timestamp()))
                hash_val = hashlib.md5(timestamp.encode()).hexdigest()[:4].upper()
                return f"CT{hash_val}"
        
        # 6. 🔥 关键：检查新编码是否已被占用（可能由于并发等原因）
        generated_code = f"CT{next_ct_num:04d}"
        
        # 如果编码已被占用，继续找下一个可用的
        attempts = 0
        while generated_code in existing_ct_codes and attempts < 10:
            next_ct_num += 1
            if next_ct_num > 9999:
                next_ct_num = 1
            generated_code = f"CT{next_ct_num:04d}"
            attempts += 1
        
        if attempts >= 10:
            # 10次尝试后仍然冲突，使用时间戳
            timestamp = datetime.now().strftime('%H%M%S')
            return f"CT{timestamp[:4]}"
        
        return generated_code
    
    @staticmethod
    def generate_concept_level2_code(level1_code: str, existing_codes: List[str]) -> str:
        """为概念题材生成二级分类代码 - 格式: 一级编码 + "_C" + 2位序号"""
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
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{level1_code}_C{next_seq:02d}"
    
    @staticmethod
    def generate_theme_code(theme_name: str, category1_code: Optional[str], 
                           category2_code: Optional[str], theme_type: str, 
                           is_test: bool = True) -> str:
        """生成题材代码 - 测试阶段以"TEST_"开头"""
        prefix = "TEST_" if is_test else ""
        
        if theme_type == "investment" and category2_code:
            # 行业题材：TEST_INVEST_SW_ + 二级分类代码
            return f"{prefix}INVEST_SW_{category2_code}"
        elif theme_type == "concept":
            # 概念题材：TEST_CONCEPT_ + 时间戳 + 哈希
            timestamp = datetime.now().strftime("%y%m%d")
            name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
            return f"{prefix}CONCEPT_{timestamp}{name_hash}"
        else:
            timestamp = datetime.now().strftime("%y%m%d")
            name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
            return f"{prefix}{theme_type.upper()}_{timestamp}{name_hash}"


class CategoryDataGenerator:
    """分类数据生成器 - 生成完整的分类数据"""
    
    @staticmethod
    def generate_category_description(level1_name: str, level2_name: str = None, 
                                    category_type: str = 'concept', 
                                    core_concept: str = None) -> str:
        """
        生成分类描述 - 遵循层级关系
        
        Args:
            level1_name: 一级分类名称
            level2_name: 二级分类名称
            category_type: 分类类型 (concept/industry)
            core_concept: 核心概念
            
        Returns:
            完整的分类描述
        """
        if category_type == 'concept':
            if level2_name:
                # 概念分类：二级描述要体现从属关系
                main_concept = core_concept or level2_name
                return f"概念分类：{level1_name} › {level2_name}，{level2_name}是{level1_name}的核心子概念，" \
                       f"涵盖{main_concept}相关的技术研发、应用场景和市场发展。"
            else:
                # 概念分类：一级描述要涵盖所有子概念
                main_concept = core_concept or level1_name
                return f"概念分类：{level1_name}，作为核心概念板块，涵盖{main_concept}相关的" \
                       f"所有技术体系、应用生态和市场概念，包含多个细分领域的子概念。"
        else:
            # 行业分类
            if level2_name:
                main_concept = core_concept or level2_name
                return f"行业分类：{level1_name} › {level2_name}，属于{level1_name}的细分行业，" \
                       f"聚焦{main_concept}相关的产业链、技术发展和市场应用。"
            else:
                main_concept = core_concept or level1_name
                return f"行业分类：{level1_name}，作为一级行业分类，涵盖{main_concept}相关的" \
                       f"全产业链条，包括多个二级细分行业板块。"
    
    @staticmethod
    def generate_category_keywords(level1_name: str, level2_name: str = None, 
                                 core_concept: str = None, event_keywords: List[str] = None) -> List[str]:
        """
        生成分类关键词 - 遵循层级关系
        
        原则：
        1. 一级关键词要能涵盖二级关键词
        2. 关键词要有层次性
        """
        keywords = []
        
        # 基础关键词
        base_keywords = []
        if core_concept:
            base_keywords.append(core_concept)
            base_keywords.append(f"{core_concept}技术")
            base_keywords.append(f"{core_concept}应用")
        
        # 一级分类关键词
        level1_keywords = [
            level1_name,
            f"{level1_name}板块",
            f"{level1_name}领域"
        ]
        
        # 如果是一级分类，使用更广泛的关键词
        if not level2_name:
            keywords.extend(level1_keywords)
            keywords.extend(base_keywords)
            keywords.append("概念投资")
            keywords.append("新兴概念")
        else:
            # 二级分类关键词
            level2_keywords = [
                level2_name,
                f"{level2_name}概念",
                f"{level2_name}技术"
            ]
            
            # 关键词组合：一级+二级
            keywords.extend(level1_keywords[:1])  # 添加一级分类名称
            keywords.extend(level2_keywords)
            keywords.extend(base_keywords)
            keywords.append(f"{level1_name}_{level2_name}")
        
        # 添加事件关键词
        if event_keywords:
            keywords.extend(event_keywords[:3])
        
        # 去重
        unique_keywords = []
        seen = set()
        for kw in keywords:
            if kw and kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:15]


class ThemeRuleBasedGeneratorFixed:
    """
    净化版：保持类名不变，但移除所有指令生成逻辑
    职责：只生成数据，不生成任何指令
    """
    
    def __init__(self, existing_categories: List[Dict]):
        """初始化时传入真实现有分类数据"""
        self.existing_categories = existing_categories or []
        self._build_category_caches()
        
        # 🔥 关键修复：使用FixedCategoryGenerator而不是硬编码
        try:
            from .fixed_category_generator import FixedCategoryGenerator
            self.category_generator = FixedCategoryGenerator(existing_categories)
            logger.info("✅ 初始化FixedCategoryGenerator成功")
        except ImportError as e:
            logger.error(f"❌ 无法导入FixedCategoryGenerator: {e}")
            # ❌ 绝不降级：如果修复组件不存在，直接报错
            raise RuntimeError("FixedCategoryGenerator不存在，必须先创建该组件")
        
        logger.info(f"✅ ThemeRuleBasedGeneratorFixed初始化，现有分类数: {len(self.existing_categories)}")
    
    def _build_category_caches(self):
        """构建分类数据缓存"""
        self.category_by_code = {}
        self.category_by_name = {}
        
        for cat in self.existing_categories:
            code = cat.get('category_code')
            name = cat.get('category_name')
            
            if code:
                self.category_by_code[code] = cat
            if name:
                self.category_by_name[name] = cat
    
    def generate_theme_data_only(self, event_data: Dict) -> StrictCompleteThemeDTO:
        """
        净化版：只生成数据，不生成任何指令
        返回：StrictCompleteThemeDTO
        
        数据格式严格遵循：
        1. theme_data: 完整的题材数据（可直接插入数据库）
        2. categories_to_create: 需要创建的分类列表
        3. category_info: 分类匹配信息（供ThemeProcessor决策用）
        4. metadata: 元数据
        
        ❌ 绝不包含：
        - operations指令列表
        - database_instructions数据库指令
        - 任何执行动作或流程控制
        """
        try:
            event_id = event_data.get('event_id', 'unknown')
            logger.info(f"🔧 净化版生成器：开始生成纯数据 (事件: {event_id})")
            
            # 1. 提取AI分析数据
            ai_analysis = self._extract_ai_analysis(event_data)
            if not ai_analysis:
                logger.warning("没有AI分析数据")
                raise ValueError("AI分析数据不存在")
            
            # 2. 分类真源策略：
            #    - 有上游分类结果：严格复用，禁止二次分类推断
            #    - 无上游分类结果：走概念新建路径（由AI关键词驱动）
            classification_source = "created_from_ai_keywords"
            classification_result = event_data.get('classification_result')
            matched_level1 = None
            matched_level2 = None

            if isinstance(classification_result, dict) and classification_result:
                matched_level1, matched_level2 = self._resolve_categories_from_upstream(
                    classification_result
                )
                if matched_level1 or matched_level2:
                    classification_source = "upstream"
            
            # 3. 确定规则类型和题材类型
            rule_info = self._determine_rule_type(matched_level1, matched_level2)
            if not rule_info:
                raise ValueError("无法确定规则类型")
            
            rule_type, theme_type, category_action = rule_info
            
            logger.info(f"   规则类型: {rule_type}, 题材类型: {theme_type}, 分类动作: {category_action}")
            
            # 4. 生成分类数据（使用修复版分类生成器）
            category_result = self._generate_category_data_only(
                matched_level1, matched_level2, category_action, theme_type, 
                event_data, ai_analysis
            )
            
            # 5. 生成题材名称
            theme_name = self._generate_theme_name(event_data, ai_analysis, theme_type)
            
            # 6. 生成题材编码
            category1_code = None
            category2_code = None
            if category_result:
                if category_result.get('level1'):
                    category1_code = category_result['level1'].get('category_code')
                if category_result.get('level2'):
                    category2_code = category_result['level2'].get('category_code')
            
            theme_code = self._generate_theme_code(
                theme_name, category1_code, category2_code, theme_type,event_id
            )
            
            # 7. 生成完整的题材描述
            description = self._generate_theme_description(
                ai_analysis, theme_name, theme_type, 
                category_result.get('level1'), category_result.get('level2')
            )
            
            # 8. 构建完整的分类路径
            category_path, level3_category = self._build_category_path(
                theme_name, category_result.get('level1'), category_result.get('level2')
            )
            
            # 9. 构建完整的theme_data
            theme_data = self._build_theme_data_only(
                theme_name, theme_code, description, theme_type, rule_type,
                category_result.get('level1'), category_result.get('level2'),
                level3_category, category_path, event_data, ai_analysis
            )
            
            # 10. 准备需要创建的分类数据
            categories_to_create = self._prepare_categories_to_create_only(
                category_result.get('level1'), category_result.get('level2'), category_action
            )
            
            # 11. 构建category_info（供ThemeProcessor决策用）
            category_info = self._build_category_info_only(
                matched_level1, matched_level2, category_result, 
                rule_type, theme_type, category_action, classification_source
            )
            
            # 12. 构建StrictCompleteThemeDTO
            dto = StrictCompleteThemeDTO(
                theme_data=theme_data,
                categories_to_create=categories_to_create,
                category_info=category_info,
                metadata={
                    'rule_applied': rule_type,
                    'generated_at': datetime.now().isoformat(),
                    'event_id': event_id,
                    'generator_version': 'clean_v1.0',
                    'classification_source': classification_source,
                }
            )
            
            logger.info(f"✅ 净化版生成完成: {theme_name} ({theme_code})")
            logger.info(f"   需要创建分类: {len(categories_to_create)} 个")
            logger.info(f"   题材类型: {theme_type}")
            
            return dto
            
        except Exception as e:
            logger.error(f"❌ 净化版生成器失败: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"纯数据生成失败: {str(e)[:200]}") from e
    
    # ============ 数据生成方法（纯净版） ============
    
    def _extract_ai_analysis(self, event_data: Dict) -> Dict:
        """提取AI分析数据"""
        ai_analysis = event_data.get('ai_analysis', {})
        if isinstance(ai_analysis, str):
            try:
                return json.loads(ai_analysis)
            except:
                return {}
        return ai_analysis

    def _resolve_categories_from_upstream(
        self,
        classification_result: Dict
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        复用上游分类结果（不做二次推断）。
        优先按编码匹配，其次按名称匹配。
        """
        level1_code = classification_result.get("level1_code")
        level2_code = classification_result.get("level2_code")
        category_code = classification_result.get("category_code")
        category_level = classification_result.get("category_level")

        if not level2_code and category_code and category_level == 2:
            level2_code = category_code
        if not level1_code:
            level1_code = classification_result.get("parent_code")

        matched_level1 = self.category_by_code.get(level1_code) if level1_code else None
        matched_level2 = self.category_by_code.get(level2_code) if level2_code else None

        if not matched_level1:
            l1_name = classification_result.get("level1_category")
            if l1_name:
                matched_level1 = self.category_by_name.get(l1_name)

        if not matched_level2:
            l2_name = classification_result.get("level2_category")
            if l2_name:
                matched_level2 = self.category_by_name.get(l2_name)

        if matched_level2 and not matched_level1:
            parent_code = matched_level2.get("parent_code")
            if parent_code:
                matched_level1 = self.category_by_code.get(parent_code)

        return matched_level1, matched_level2
    
    def _match_categories(self, classification_result: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """匹配分类 - 使用KeywordMatcher进行语义匹配"""
        level1_name = classification_result.get('level1_category')
        level2_name = classification_result.get('level2_category')
        
        matched_level1 = None
        matched_level2 = None
        
        # 🔥 关键改进：使用KeywordMatcher进行语义匹配
        
        # 如果有KeywordMatcher实例可用，优先使用它
        if hasattr(self, 'keyword_matcher'):
            # 模拟一个事件数据，使用分类名称作为关键词
            simulated_event = {
                'event_id': 'category_match_simulation',
                'title': level2_name or level1_name or '',
                'ai_analysis': {
                    'industry_keywords': [level2_name, level1_name],
                    'core_concept': level2_name or level1_name
                }
            }
            
            # 调用KeywordMatcher匹配分类
            match_results = self.keyword_matcher.match(simulated_event, precision='normal')
            
            # 从匹配结果中提取分类
            if match_results:
                for result in match_results:
                    if result.match_details.get('data_type') == 'category':
                        category = self._get_category_by_id(result.theme_id)
                        if category:
                            cat_level = category.get('category_level', 1)
                            if cat_level == 2 and not matched_level2:
                                matched_level2 = category
                            elif cat_level == 1 and not matched_level1:
                                matched_level1 = category
        
        # 🔥 备用方案：如果没有KeywordMatcher，使用语义相似度
        if (not matched_level1 or not matched_level2) and hasattr(self, 'categories'):
            matched_level1, matched_level2 = self._semantic_match_categories(
                level1_name, level2_name
            )
        
        return matched_level1, matched_level2

    def _semantic_match_categories(self, level1_name: str, level2_name: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """语义匹配分类"""
        from difflib import SequenceMatcher
        
        matched_level1 = None
        matched_level2 = None
        best_score1 = 0
        best_score2 = 0
        
        for cat_id, category in self.categories.items():
            cat_name = category.get('category_name', '')
            cat_level = category.get('category_level', 1)
            
            # 匹配二级分类
            if level2_name and cat_level == 2:
                similarity = SequenceMatcher(None, level2_name.lower(), cat_name.lower()).ratio()
                if similarity > best_score2 and similarity > 0.6:  # 阈值0.6
                    best_score2 = similarity
                    matched_level2 = category
            
            # 匹配一级分类
            if level1_name and cat_level == 1:
                similarity = SequenceMatcher(None, level1_name.lower(), cat_name.lower()).ratio()
                if similarity > best_score1 and similarity > 0.6:
                    best_score1 = similarity
                    matched_level1 = category
        
        if matched_level2 and best_score2 > 0:
            logger.info(f"   语义匹配二级分类: {level2_name} → {matched_level2.get('category_name')} (相似度: {best_score2:.2f})")
        
        if matched_level1 and best_score1 > 0:
            logger.info(f"   语义匹配一级分类: {level1_name} → {matched_level1.get('category_name')} (相似度: {best_score1:.2f})")
        
        return matched_level1, matched_level2
    
    def _determine_rule_type(self, matched_level1: Optional[Dict], 
                           matched_level2: Optional[Dict]) -> Optional[Tuple[str, str, str]]:
        """
        确定应用的规则类型
        返回: (规则类型描述, 题材类型, 分类操作)
        """
        if matched_level1 and matched_level2:
            # 检查分类类型
            level2_type = (
                matched_level2.get('category_type')
                or self._infer_category_type_by_code(matched_level2.get('category_code'))
                or matched_level1.get('category_type')
                or self._infer_category_type_by_code(matched_level1.get('category_code'))
            )
            if level2_type == 'industry':
                return "匹配到1、2级行业分类", "investment", "use_existing"
            elif level2_type == 'concept':
                return "匹配到1、2级概念分类", "concept", "use_existing"
        
        elif matched_level1 and not matched_level2:
            level1_type = matched_level1.get('category_type')
            if level1_type == 'industry':
                return "匹配到1级行业分类，无2级分类", "investment", "create_level2"
            elif level1_type == 'concept':
                return "匹配到1级概念分类，无2级分类", "concept", "create_level2"
        
        elif not matched_level1 and not matched_level2:
            # 未命中上游分类：进入概念新建路径（主概念/子概念）
            return "未匹配到任何分类", "concept", "create_both"
        
        return None

    def _infer_category_type_by_code(self, category_code: Optional[str]) -> Optional[str]:
        """根据分类编码推断类型：CT* 视为 concept，其它数字编码视为 industry。"""
        if not category_code:
            return None
        code = str(category_code).upper()
        if code.startswith("CT"):
            return "concept"
        if code.isdigit():
            return "industry"
        return None
    
    def _generate_category_data_only(self, matched_level1, matched_level2, category_action, 
                                 theme_type, event_data, ai_analysis):
        """
        只生成分类数据 - 修复版
        """
        logger.info("🔧 纯净版生成分类数据")
        
        try:
            # 记录输入状态
            logger.info(f"   输入状态: level1匹配={matched_level1 is not None}, "
                       f"level2匹配={matched_level2 is not None}, "
                       f"theme_type={theme_type}, action={category_action}")
            
            # 🔥 添加详细的调试信息
            print(f"\n🔥 DEBUG _generate_category_data_only:")
            print(f"   1. matched_level1: {matched_level1}")
            print(f"   2. matched_level2: {matched_level2}")
            print(f"   3. category_action: {category_action}")
            print(f"   4. theme_type: {theme_type}")
            
            # 🔥 情况1：概念题材且未匹配到任何分类（创建主/子概念）
            if (theme_type == 'concept' and 
                not matched_level1 and not matched_level2 and
                category_action == 'create_both'):

                logger.info("   🎯 情况1：创建主/子概念分类")
                result = self._generate_concept_category_hierarchy(ai_analysis, event_data)
                return result
            
            # 🔥 情况2：匹配到一级行业分类，但无二级分类
            elif (matched_level1 and not matched_level2 and
                  matched_level1.get('category_type') == 'industry' and
                  theme_type == 'investment'):
                
                logger.info("   🎯 情况2：为一级行业分类生成二级分类")
                print("   🔥 进入情况2")
                result = self._generate_industry_level2_category(
                    matched_level1, event_data, ai_analysis
                )
                print(f"   🔥 情况2返回: {result}")
                return result
            
            # 🔥 情况3：匹配到完整分类（概念或行业）
            elif matched_level1 and matched_level2:
                logger.info("   🎯 情况3：使用现有完整分类")
                print("   🔥 进入情况3")
                result = {
                    'level1': matched_level1,
                    'level2': matched_level2,
                    'need_create_category': False,
                    'action': 'use_existing'
                }
                print(f"   🔥 情况3返回: {result}")
                return result
            
            # 🔥 情况4：匹配到一级概念分类，但无二级分类
            elif (matched_level1 and not matched_level2 and
                  matched_level1.get('category_type') == 'concept'):
                
                logger.info("   🎯 情况4：为一级概念分类生成二级分类")
                print("   🔥 进入情况4")
                result = self._generate_concept_level2_category(
                    matched_level1, ai_analysis, event_data
                )
                print(f"   🔥 情况4返回: {result}")
                return result
            
            # ❌ 其他情况：直接报错，不降级
            else:
                error_msg = (f"无法处理的分类匹配情况: "
                           f"level1={matched_level1 is not None}, "
                           f"level2={matched_level2 is not None}, "
                           f"theme_type={theme_type}, "
                           f"category_action={category_action}")
                logger.error(f"❌ {error_msg}")
                print(f"   🔥 进入其他情况，抛出异常")
                raise ValueError(error_msg)
                
        except Exception as e:
            logger.error(f"❌ 分类数据生成失败: {e}")
            print(f"   🔥 异常发生: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"分类数据生成失败: {str(e)[:200]}") from e

    def _generate_concept_category_hierarchy(self, ai_analysis: Dict, event_data: Dict) -> Dict:
        """无上游分类时，基于AI关键词创建概念主类(L1)与子类(L2)。"""
        existing_codes = [
            cat.get('category_code') for cat in self.existing_categories if cat.get('category_code')
        ]
        level1_code = ShenwanCodeGenerator.generate_concept_level1_code(existing_codes)

        main_concept = self._get_concrete_concept_name(ai_analysis, event_data)
        sub_concept = self._get_sub_concept_name(ai_analysis, event_data, main_concept)

        level1_data = {
            'category_code': level1_code,
            'category_name': main_concept,
            'category_level': 1,
            'category_type': 'concept',
            'description': None,
            'keywords': self._build_category_keywords(ai_analysis, event_data, main_concept),
            'source_system': 'ai_theme_discovery'
        }

        existing_child_codes = [
            cat.get('category_code', '')
            for cat in self.existing_categories
            if cat.get('parent_code') == level1_code and cat.get('category_level') == 2
        ]
        level2_code = self._generate_concept_level2_code(level1_code, existing_child_codes)
        level2_data = {
            'category_code': level2_code,
            'category_name': sub_concept,
            'category_level': 2,
            'category_type': 'concept',
            'parent_code': level1_code,
            'description': None,
            'keywords': self._build_category_keywords(ai_analysis, event_data, main_concept, sub_concept),
            'source_system': 'ai_theme_discovery'
        }

        return {
            'level1': level1_data,
            'level2': level2_data,
            'need_create_category': True,
            'action': 'create_both'
        }

    def _generate_simple_concept_category_only_level1(self, ai_analysis: Dict, event_data: Dict) -> Dict:
        """生成简单的概念分类（只创建1级）- 修复版"""
        # 提取现有编码
        existing_codes = [cat.get('category_code') for cat in self.existing_categories 
                        if cat.get('category_code')]
        
        # 生成1级分类编码
        level1_code = ShenwanCodeGenerator.generate_concept_level1_code(existing_codes)
        
        # 🔥 生成有意义的1级分类名称（使用具体的概念名称）
        level1_name = self._get_concrete_concept_name(ai_analysis, event_data)
        
        level1_data = {
            'category_code': level1_code,
            'category_name': level1_name,  # ✅ 具体的概念名称，不是"综合概念"
            'category_level': 1,
            'category_type': 'concept',
            'description': f'概念分类：{level1_name}',
            'keywords': self._build_category_keywords(ai_analysis, event_data, level1_name),
            'source_system': 'ai_theme_discovery'
        }
        
        logger.info(f"   ✅ 生成1级概念分类（只创建1级）: {level1_code} - {level1_name}")
        
        return {
            'level1': level1_data,
            'level2': None,  # ❌ 不创建2级分类！
            'need_create_category': True,
            'action': 'create_level1'  # 🔥 明确只创建1级
        }

    def _get_concrete_concept_name(self, ai_analysis: Dict, event_data: Dict) -> str:
        """获取具体的概念名称"""
        # 1. 优先使用AI核心概念
        core_concept = ai_analysis.get('core_concept', '')
        if core_concept:
            # 清理"概念"后缀
            if core_concept.endswith('概念'):
                return core_concept[:-2]  # 去掉"概念"
            return core_concept
        
        # 2. 使用事件标题
        title = event_data.get('title', '')
        if title:
            # 移除常见后缀
            for suffix in ['相关新闻', '事件', '新闻', '消息', '报道']:
                if title.endswith(suffix):
                    title = title[:-len(suffix)]
                    break
            if len(title) <= 20:
                return title
        
        # 3. 使用AI关键词
        keywords = ai_analysis.get('event_keywords', [])
        if keywords:
            return keywords[0]
        
        # 4. 生成基于时间的唯一名称
        timestamp = datetime.now().strftime('%m%d%H%M')
        return f"概念_{timestamp}"

    def _get_sub_concept_name(self, ai_analysis: Dict, event_data: Dict, main_concept: str) -> str:
        """从AI关键词中推断子概念名称。"""
        for key in ("industry_keywords", "event_keywords"):
            kws = ai_analysis.get(key, [])
            if isinstance(kws, list):
                for kw in kws:
                    if kw and kw != main_concept:
                        return str(kw)[:20]

        title = event_data.get("title", "")
        short = self._simplify_for_category_name(title, max_length=20)
        if short and short != main_concept:
            return short
        return f"{main_concept}子概念"

    def _build_category_keywords(self, ai_analysis: Dict, event_data: Dict, *extra: str) -> List[str]:
        """组装新分类关键词，确保分类关键词非空且可复用匹配。"""
        merged: List[str] = []

        for key in ("industry_keywords", "event_keywords"):
            kws = ai_analysis.get(key, [])
            if isinstance(kws, list):
                merged.extend([str(k).strip() for k in kws if str(k).strip()])

        core_concept = str(ai_analysis.get("core_concept", "")).strip()
        if core_concept:
            merged.append(core_concept)

        title = str(event_data.get("title", "")).strip()
        if title:
            merged.append(self._simplify_for_category_name(title, max_length=20))

        for item in extra:
            val = str(item).strip()
            if val:
                merged.append(val)

        return list(dict.fromkeys([k for k in merged if k]))[:8]
    
    def _generate_industry_level2_category(self, level1_data: Dict, 
                                         event_data: Dict, ai_analysis: Dict) -> Dict:
        """为一级行业分类生成二级分类"""
        try:
            # 生成二级分类编码
            existing_level2_codes = []
            for cat in self.existing_categories:
                if (cat.get('parent_code') == level1_data.get('category_code') and 
                    cat.get('category_level') == 2):
                    existing_level2_codes.append(cat.get('category_code', ''))
            
            level2_code = self._generate_investment_level2_code(
                level1_data.get('category_code'), existing_level2_codes
            )
            
            # 基于AI分析生成有意义的二级分类名称
            core_concept = ai_analysis.get('core_concept', '')
            event_title = event_data.get('title', '新事件')
            
            if core_concept and len(core_concept) <= 15:
                level2_name = f"{core_concept}"
            else:
                # 简化事件标题
                level2_name = self._simplify_for_category_name(event_title)
            
            # 构建二级分类数据
            level2_data = {
                'category_code': level2_code,
                'category_name': level2_name,
                'category_level': 2,
                'category_type': 'industry',
                'parent_code': level1_data.get('category_code'),
                'description': f'{level1_data.get("category_name")}细分行业: {level2_name}',
                'keywords': self._build_category_keywords(ai_analysis, event_data, level2_name),
                'source_system': 'ai_theme_discovery'
            }
            
            logger.info(f"   ✅ 生成行业二级分类: {level2_code} - {level2_name}")
            
            return {
                'level1': level1_data,
                'level2': level2_data,
                'need_create_category': True,
                'action': 'create_level2'
            }
            
        except Exception as e:
            logger.error(f"❌ 生成行业二级分类失败: {e}")
            raise
    
    def _generate_investment_level2_code(self, level1_code: str, existing_codes: List[str]) -> str:
        """为行业题材生成二级分类代码"""
        if not level1_code or len(level1_code) != 6:
            return "999999"
        
        base_prefix = level1_code[:4]
        
        # 找出该一级分类下最大的二级分类序号
        max_seq = 0
        for code in existing_codes:
            if code.startswith(base_prefix) and len(code) == 6:
                try:
                    seq_str = code[4:6]
                    if seq_str.isdigit():
                        seq = int(seq_str)
                        max_seq = max(max_seq, seq)
                except:
                    continue
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{base_prefix}{next_seq:02d}"
    
    def _generate_concept_level2_category(self, level1_data: Dict,
                                        ai_analysis: Dict, event_data: Dict) -> Dict:
        """为一级概念分类生成二级分类"""
        try:
            # 获取该一级分类下已有的二级分类编码
            existing_child_codes = []
            for cat in self.existing_categories:
                if (cat.get('parent_code') == level1_data.get('category_code') and
                    cat.get('category_level') == 2):
                    existing_child_codes.append(cat.get('category_code', ''))
            
            # 生成二级分类编码
            level2_code = self._generate_concept_level2_code(
                level1_data.get('category_code'), existing_child_codes
            )
            
            # 生成有意义的二级分类名称
            level2_name = self.category_generator._generate_concept_level2_name(
                ai_analysis, event_data
            )
            
            # 构建二级分类数据
            level2_data = {
                'category_code': level2_code,
                'category_name': level2_name,
                'category_level': 2,
                'category_type': 'concept',
                'parent_code': level1_data.get('category_code'),
                'description': f'概念子类: {level2_name}',
                'keywords': self._build_category_keywords(ai_analysis, event_data, level2_name),
                'source_system': 'ai_theme_discovery'
            }
            
            logger.info(f"   ✅ 生成概念二级分类: {level2_code} - {level2_name}")
            
            return {
                'level1': level1_data,
                'level2': level2_data,
                'need_create_category': True,
                'action': 'create_level2'
            }
            
        except Exception as e:
            logger.error(f"❌ 生成概念二级分类失败: {e}")
            raise
    
    def _generate_concept_level2_code(self, level1_code: str, existing_codes: List[str]) -> str:
        """为概念题材生成二级分类代码"""
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
        
        next_seq = max_seq + 1
        if next_seq > 99:
            next_seq = 1
        
        return f"{level1_code}_C{next_seq:02d}"
    
    def _simplify_for_category_name(self, text: str, max_length: int = 12) -> str:
        """简化文本作为分类名称"""
        if not text:
            return "新分类"
        
        # 移除常见后缀
        suffixes = ['相关新闻', '事件', '新闻', '消息', '报道', '资讯', '动态']
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
                break
        
        # 截断过长的文本
        if len(text) > max_length:
            text = text[:max_length-3] + '...'
        
        return text
    
    def _generate_theme_name(self, event_data: Dict, ai_analysis: Dict, theme_type: str) -> str:
        """生成题材名称"""
        # 优先使用AI核心概念
        core_concept = ai_analysis.get('core_concept', '')
        if core_concept:
            if theme_type == 'concept' and not core_concept.endswith('概念'):
                return f"{core_concept}概念"
            elif theme_type == 'investment' and not core_concept.endswith(('投资', '题材')):
                return f"{core_concept}投资"
            return core_concept
        
        # 使用标题
        title = event_data.get('title', '新题材')
        if theme_type == 'concept' and not title.endswith('概念'):
            return f"{title}概念"
        elif theme_type == 'investment' and not title.endswith(('投资', '题材')):
            return f"{title}投资"
        
        return title[:50]
    
    def _generate_theme_code(self, theme_name, category1_code, category2_code, theme_type, event_id=None):
        """生成题材代码"""
        prefix = "TEST_"  # 保持与原来一致
        
        if theme_type == "investment" and category2_code:
            # 行业题材：TEST_INVEST_SW_ + 二级分类代码
            return f"{prefix}INVEST_SW_{category2_code}"
        elif theme_type == "concept" and event_id:
            # 概念题材：TEST_CONCEPT_ + 时间戳 + 哈希
            event_hash = hashlib.md5(event_id.encode()).hexdigest()[:6].upper()
            timestamp = datetime.now().strftime("%y%m%d%H%M%S")
            return f"TEST_CONCEPT_{timestamp}_{event_hash}"
        else:
            timestamp = datetime.now().strftime("%y%m%d")
            name_hash = hashlib.md5(theme_name.encode('utf-8')).hexdigest()[:4].upper()
            return f"{prefix}{theme_type.upper()}_{timestamp}{name_hash}"
    
    def _generate_theme_description(self, ai_analysis: Dict, theme_name: str, 
                                  theme_type: str, level1: Optional[Dict], 
                                  level2: Optional[Dict]) -> str:
        """生成题材描述"""
        # 优先使用AI提供的完整summary
        if ai_analysis.get('summary'):
            return ai_analysis['summary']
        
        # 构建标准描述
        core_concept = ai_analysis.get('core_concept', theme_name)
        
        if theme_type == 'investment':
            if level2:
                level2_name = level2.get('category_name', '')
                return f"投资题材：{theme_name}（源于申万行业：{level2_name}）"
            elif level1:
                level1_name = level1.get('category_name', '')
                return f"投资题材：{theme_name}（源于{level1_name}相关领域）"
            else:
                return f"投资题材：{theme_name}（基于相关事件形成的新兴投资主题）"
        else:
            return f"概念题材：{theme_name}（基于{core_concept}相关事件形成的新兴概念主题）"
    
    def _build_category_path(self, theme_name: str, level1: Optional[Dict], 
                           level2: Optional[Dict]) -> Tuple[List[str], str]:
        """构建分类路径"""
        category_path = []
        
        if level1:
            category_path.append(level1.get('category_name', ''))
        
        if level2:
            category_path.append(level2.get('category_name', ''))
        
        # 三级分类就是题材名称
        level3_category = theme_name
        category_path.append(level3_category)
        
        return category_path, level3_category
    
    def _build_theme_data_only(self, theme_name: str, theme_code: str, description: str,
                         theme_type: str, rule_type: str, final_level1: Optional[Dict],
                         final_level2: Optional[Dict], level3_category: str, 
                         category_path: List[str], event_data: Dict, ai_analysis: Dict) -> Dict:
        """构建完整的题材数据（不包含指令）"""
        # 提取分类编码
        category1_code = final_level1.get('category_code') if final_level1 else None
        category2_code = final_level2.get('category_code') if final_level2 else None
        
        # 计算初始热度和置信度
        heat_score = self._calculate_initial_heat(ai_analysis)
        confidence_score = ai_analysis.get('concept_confidence', 0.5)
        
        # 🔥 修复：生成正确的tags数据
        tags = self._build_tags_data(ai_analysis, theme_type, event_data)
        
        # 完整的题材数据
        theme_data = {
            # 基础信息
            'name': theme_name,
            'code': theme_code,
            'description': description,
            'status': 'active',
            
            # 分类信息
            'level1_category': final_level1.get('category_name') if final_level1 else None,
            'level2_category': final_level2.get('category_name') if final_level2 else None,
            'level3_category': level3_category,
            'category_path': category_path,
            'category1_code': category1_code,
            'category2_code': category2_code,
            'category3_code': None,
            
            # 🔥 修复：添加tags字段
            'tags': tags,
            
            # 类型和热度
            'theme_type': theme_type,
            'heat_score': heat_score,
            'confidence_score': confidence_score,
            'lifecycle_stage': 'emerging',
            
            # 统计信息（初始为0）
            'related_stocks': {},
            'stock_count': 0,
            'news_count': 0,
            'mention_count': 0,
            'last_mentioned': None,
            
            # 来源信息
            'source_system': 'ai_theme_discovery',
            'source_id': event_data.get('event_id', 'unknown'),
            'created_by': 'theme_rule_generator',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'last_active_at': datetime.now().isoformat(),
            
            # 规则信息
            'rule_applied': rule_type,
            'generated_by': 'ThemeRuleBasedGeneratorFixed_clean'
        }
        
        return theme_data

    def _build_tags_data(self, ai_analysis: Dict, theme_type: str, event_data: Dict) -> Dict:
        """构建正确的tags数据"""
        # 从AI分析中提取关键词
        keywords = []
        
        # 优先使用industry_keywords
        if 'industry_keywords' in ai_analysis:
            keywords.extend(ai_analysis['industry_keywords'])
        
        # 使用event_keywords作为补充
        if 'event_keywords' in ai_analysis:
            # 添加不在keywords中的event_keywords
            existing_set = set(keywords)
            for kw in ai_analysis['event_keywords']:
                if kw not in existing_set:
                    keywords.append(kw)
                    existing_set.add(kw)
        
        # 如果没有关键词，使用核心概念
        if not keywords and 'core_concept' in ai_analysis:
            keywords.append(ai_analysis['core_concept'])
        
        # 确定热度等级
        heat_level = ai_analysis.get('impact_level', 'medium')
        
        # 构建tags结构
        tags = {
            'source': 'ai_theme_discovery',  # 🔥 不是"shenwan"！
            'aliases': [],
            'version': '2.0',
            'concepts': [ai_analysis.get('core_concept', '')] if ai_analysis.get('core_concept') else [],
            'keywords': keywords[:10],  # 限制最多10个关键词
            'heat_level': heat_level,
            'industries': [],
            'industry_code': None,
            'merge_candidates': []
        }
        
        # 如果是行业题材，添加行业信息
        if theme_type == 'investment' and 'industry_keywords' in ai_analysis:
            tags['industries'] = ai_analysis['industry_keywords'][:5]
        
        return tags
    
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
    
    def _prepare_categories_to_create_only(self, final_level1: Dict, final_level2: Optional[Dict] = None,
                                     category_action: str = None) -> List[Dict]:
        """准备要创建的分类数据（纯净版）"""
        categories_to_create = []
        
        # 处理一级分类
        if final_level1 and category_action in ['create_both', 'create_level1']:
            level1_data = self._ensure_category_data_format(final_level1)
            if level1_data and level1_data.get('category_name') != 'create_both':
                categories_to_create.append(level1_data)
        
        # 处理二级分类
        if final_level2 and category_action in ['create_both', 'create_level2']:
            level2_data = self._ensure_category_data_format(final_level2)
            if level2_data and level2_data.get('category_name') != 'create_both':
                categories_to_create.append(level2_data)
        
        logger.info(f"📊 准备创建 {len(categories_to_create)} 个分类")
        return categories_to_create
    
    def _ensure_category_data_format(self, category_data) -> Optional[Dict]:
        """确保分类数据是字典类型"""
        if category_data is None:
            return None
        
        if isinstance(category_data, dict):
            return category_data
        
        if isinstance(category_data, str):
            logger.info(f"🛠️ 将字符串分类转换为字典: '{category_data}'")
            
            # 检查是否是分类代码格式
            if category_data.startswith('CT') and '_C' in category_data:
                return {
                    'category_code': category_data,
                    'category_name': f"概念分类{category_data[-4:]}",
                    'category_level': 2,
                    'category_type': 'concept',
                    'description': f"自动生成的概念子分类",
                    'keywords': []
                }
            elif category_data.startswith('CT'):
                return {
                    'category_code': category_data,
                    'category_name': f"概念分类{category_data[-4:]}",
                    'category_level': 1,
                    'category_type': 'concept',
                    'description': f"自动生成的概念分类",
                    'keywords': []
                }
            else:
                return {
                    'category_code': f"AUTO_{hash(category_data) % 10000:04d}",
                    'category_name': category_data,
                    'category_level': 1,
                    'category_type': 'unknown',
                    'description': f"自动转换的分类: {category_data}",
                    'keywords': [category_data]
                }
        
        logger.error(f"❌ 未知的分类数据类型: {type(category_data)} - {category_data}")
        return None
    
    def _build_category_info_only(self, matched_level1, matched_level2, category_result, 
                                rule_type, theme_type, category_action, classification_source: str) -> Dict:
        """构建category_info（供ThemeProcessor决策用）"""
        # 🔥 添加对 category_result 的检查
        level1_code = None
        level2_code = None
        category_type = 'concept'
        
        if category_result:
            if category_result.get('level1'):
                level1_code = category_result['level1'].get('category_code')
                category_type = category_result['level1'].get('category_type', 'concept')
            if category_result.get('level2'):
                level2_code = category_result['level2'].get('category_code')
        
        return {
            'matched_level1': matched_level1 is not None,
            'matched_level2': matched_level2 is not None,
            'rule_type': rule_type,
            'theme_type': theme_type,
            'category_action': category_action,
            'need_create_category': category_action != 'use_existing',
            'level1_code': level1_code,
            'level2_code': level2_code,
            'category_type': category_type,
            'classification_source': classification_source,
        }
    
    # ============ 保留原始方法以保持向后兼容性 ============
    
    def generate_complete_theme_data(self, event_data: Dict) -> Optional[Dict]:
        """
        原始方法（保持向后兼容）
        注：此方法将逐渐废弃，使用generate_theme_data_only代替
        """
        try:
            logger.warning("⚠️ 使用即将废弃的方法generate_complete_theme_data，请使用generate_theme_data_only")
            
            # 调用纯净版方法
            dto = self.generate_theme_data_only(event_data)
            
            # 转换为旧格式以保持兼容性
            return {
                'theme_data': dto.theme_data,
                'category_info': dto.category_info,
                'database_instructions': {
                    'operations': self._determine_operations_from_category_info(dto.category_info),
                    'categories_to_create': dto.categories_to_create,
                    'theme_create_data': dto.theme_data,
                    'mapping_data': {
                        'event_id': event_data.get('event_id'),
                        'match_type': 'new_theme_creation'
                    }
                },
                'metadata': dto.metadata
            }
        except Exception as e:
            logger.error(f"❌ 兼容性方法失败: {e}")
            return None
    
    def _determine_operations_from_category_info(self, category_info: Dict) -> List[str]:
        """根据category_info确定operations（供兼容性使用）"""
        operations = []
        
        if category_info.get('need_create_category'):
            operations.append('create_category')
        
        operations.extend(['create_theme', 'create_mapping'])
        
        return operations
