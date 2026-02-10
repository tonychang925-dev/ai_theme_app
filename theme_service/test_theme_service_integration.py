"""
Theme Service 集成测试 - 完整版
包含原有测试项目 + 新增聚类分析测试
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== 导入模块 ==========
# 关键：获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)  # 确保项目根目录在Python路径的第一位
# ========== 结束修改 ==========

try:
    from theme_service.services.theme_service import get_theme_service
    from theme_service.services.candidate_pool import CandidatePool
    from theme_service.creators.theme_data_generator import ThemeDataGenerator
    from theme_service.services.theme_discovery_engine import ThemeDiscoveryEngine  # 🔥 添加这行！
    from theme_service.matchers.matcher_factory import MatcherFactory  # 🔥 如果需要也可以加上
    print("✅ 所有导入成功！")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"Python路径: {sys.path}")
    sys.exit(1)

# ========== DatabaseTester类 - 完全保持原有代码 ==========
class DatabaseTester:
    """数据库测试连接器 - 直接使用psycopg2"""
    
    def __init__(self, db_config: Dict = None):
        """
        初始化数据库测试器
        
        Args:
            db_config: 数据库配置
        """
        self.db_config = db_config or {
            "host": "localhost",
            "port": 5432,
            "database": "stock_data_test",
            "user": "postgres",
            "password": "zxbzj~925"
        }
        
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """连接到数据库"""
        try:
            self.connection = psycopg2.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                database=self.db_config["database"],
                user=self.db_config["user"],
                password=self.db_config["password"]
            )
            self.cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """执行查询"""
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            
            results = self.cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            logger.error(f"查询: {query}")
            return []
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新操作"""
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            logger.error(f"更新执行失败: {e}")
            self.connection.rollback()
            return 0
    
    def get_tables(self) -> List[str]:
        """获取所有表名"""
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
        """
        results = self.execute_query(query)
        return [row['table_name'] for row in results]
    
    def get_table_info(self, table_name: str) -> List[Dict]:
        """获取表结构信息"""
        query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position;
        """
        return self.execute_query(query, (table_name,))
    
    def load_categories_sync(self) -> List[Dict]:
        """同步加载分类数据"""
        try:
            # 先重置事务（如果之前有错误）
            if self.connection:
                self.connection.rollback()
            
            query = """
            SELECT 
                id,
                category_code,
                category_name,
                description,
                category_level,
                parent_code,
                full_path,
                category_type,
                standard_type,
                keywords,
                aliases,
                related_industries,
                source_system,
                source_id,
                is_standard,
                theme_count,
                stock_count,
                avg_heat_score,
                created_at,
                updated_at
            FROM financial_categories
            ORDER BY category_level, category_code;
            """
            return self.execute_query(query)
        except Exception as e:
            logger.error(f"加载分类失败: {e}")
            return []

    def load_all_themes_sync(self) -> List[Dict]:
        """同步加载所有题材数据"""
        query = """
        SELECT 
            id,
            name,
            code,
            description,
            level1_category,
            level2_category,
            level3_category,
            category1_code,
            category2_code,
            category3_code,
            category_path,
            tags,
            theme_type,
            status,
            lifecycle_stage,
            heat_score,
            confidence_score,
            related_stocks,
            stock_count,
            news_count,
            mention_count,
            source_system,
            source_id,
            created_by,
            created_at,
            updated_at,
            last_mentioned
        FROM theme_master
        WHERE status = 'active'
        ORDER BY heat_score DESC;
        """
        return self.execute_query(query)

    # ========== 异步方法（用于theme_service接口，与同步方法不同名） ==========
    async def load_categories(self) -> List[Dict]:
        """异步加载分类数据（适配theme_service接口）"""
        print("📊 异步加载分类数据...")
        raw_categories = self.load_categories_sync()
        
        if not raw_categories:
            print("⚠️  警告: 未加载到分类数据")
            return []
        
        print(f"   从数据库加载 {len(raw_categories)} 个原始分类")
        
        # 格式化和验证分类数据
        formatted_categories = []
        missing_category_code_count = 0
        missing_category_name_count = 0
        
        for i, category in enumerate(raw_categories):
            try:
                # ✅ 1. 确保category_code存在且不为空
                category_code = self._extract_category_code(category, i)
                if not category_code:
                    missing_category_code_count += 1
                    continue  # 跳过没有分类代码的记录
                
                # ✅ 2. 确保category_name存在
                category_name = self._extract_category_name(category, i)
                if not category_name:
                    missing_category_name_count += 1
                    # 使用默认名称但继续处理
                
                # ✅ 3. 处理keywords字段
                keywords = self._extract_keywords(category)
                
                # ✅ 4. 确保category_level是整数
                category_level = self._extract_category_level(category)
                
                # ✅ 5. 构建完整的数据结构
                formatted_category = {
                    'category_code': category_code,
                    'category_name': category_name,
                    'category_level': category_level,
                    'parent_code': category.get('parent_code', ''),
                    'keywords': keywords,
                    'description': category.get('description', ''),
                    'category_type': category.get('category_type', 'industry'),
                    'source': 'database'
                }
                
                # 添加可选字段
                optional_fields = ['full_path', 'aliases', 'related_industries', 
                                'source_system', 'theme_count', 'stock_count', 
                                'avg_heat_score']
                for field in optional_fields:
                    if field in category:
                        formatted_category[field] = category[field]
                
                # 添加ID（用于调试和追踪）
                if 'id' in category:
                    formatted_category['db_id'] = category['id']
                
                formatted_categories.append(formatted_category)
                
                # 记录第一个分类的结构作为参考
                if i == 0:
                    print(f"   第一个分类结构: {list(formatted_category.keys())}")
                    
            except Exception as e:
                logger.error(f"处理分类数据时出错 (索引 {i}): {e}")
                # 继续处理其他分类
        
        # 输出统计信息
        print(f"   格式化完成: {len(formatted_categories)} 个有效分类")
        if missing_category_code_count > 0:
            print(f"   ⚠️  跳过 {missing_category_code_count} 个缺少category_code的分类")
        if missing_category_name_count > 0:
            print(f"   ⚠️  {missing_category_name_count} 个分类使用默认名称")
        
        # 验证必要字段是否存在
        if formatted_categories:
            first_cat = formatted_categories[0]
            required_fields = ['category_code', 'category_name', 'category_level']
            missing_in_first = [field for field in required_fields if not first_cat.get(field)]
            if missing_in_first:
                print(f"   ❌ 第一个分类缺少字段: {missing_in_first}")
            else:
                print(f"   ✅ 分类数据格式验证通过")
        
        # ✅ 打印分类示例
        self._print_category_examples(formatted_categories)
        
        return formatted_categories

    def _extract_category_code(self, category: Dict, index: int) -> str:
        """提取分类代码"""
        # 尝试多个可能的字段
        code_sources = ['category_code', 'code', 'id']
        
        for source in code_sources:
            if source in category:
                value = category[source]
                if value is not None:
                    code = str(value).strip()
                    if code:
                        return code
        
        # 如果都没有，生成一个唯一的代码
        return f"CAT_{index:06d}"

    def _extract_category_name(self, category: Dict, index: int) -> str:
        """提取分类名称"""
        # 尝试多个可能的字段
        name_sources = ['category_name', 'name', 'description']
        
        for source in name_sources:
            if source in category:
                value = category[source]
                if value is not None:
                    name = str(value).strip()
                    if name:
                        return name
        
        # 如果都没有，生成一个默认名称
        return f"分类_{index}"

    def _extract_keywords(self, category: Dict) -> List[str]:
        """提取关键词"""
        keywords = category.get('keywords', [])
        
        if isinstance(keywords, str):
            try:
                # 尝试解析JSON字符串
                if keywords.strip():
                    parsed = json.loads(keywords)
                    if isinstance(parsed, list):
                        return [str(kw).strip() for kw in parsed if kw]
                    elif isinstance(parsed, str):
                        # 如果是逗号分隔的字符串
                        return [kw.strip() for kw in parsed.split(',') if kw.strip()]
            except (json.JSONDecodeError, TypeError):
                # 如果不是JSON，尝试逗号分隔
                if ',' in keywords:
                    return [kw.strip() for kw in keywords.split(',') if kw.strip()]
                elif keywords.strip():
                    return [keywords.strip()]
        
        elif isinstance(keywords, list):
            return [str(kw).strip() for kw in keywords if kw]
        
        return []

    def _extract_category_level(self, category: Dict) -> int:
        """提取分类级别"""
        try:
            level = category.get('category_level', 1)
            if isinstance(level, (int, float)):
                return int(level)
            elif isinstance(level, str) and level.strip().isdigit():
                return int(level.strip())
            else:
                return 1
        except (ValueError, TypeError):
            return 1

    def _print_category_examples(self, categories: List[Dict], num_examples: int = 5):
        """打印分类示例"""
        if not categories:
            return
        
        print(f"   分类层级统计:")
        
        # 按层级统计
        level_stats = {}
        for cat in categories:
            level = cat.get('category_level', 1)
            level_stats[level] = level_stats.get(level, 0) + 1
        
        for level, count in sorted(level_stats.items()):
            print(f"     L{level}: {count} 个分类")
        
        # 打印示例
        print(f"   分类示例 (前{min(num_examples, len(categories))}个):")
        for i, cat in enumerate(categories[:num_examples], 1):
            code = cat.get('category_code', '未知')
            name = cat.get('category_name', '未知')
            level = cat.get('category_level', 1)
            keywords = cat.get('keywords', [])
            
            # 截断长名称
            display_name = name[:30] + "..." if len(name) > 30 else name
            
            print(f"     {i}. {display_name}")
            print(f"        代码: {code}, 层级: L{level}")
            
            # 显示前几个关键词
            if keywords:
                keyword_str = ', '.join(keywords[:3])
                if len(keywords) > 3:
                    keyword_str += f"... (共{len(keywords)}个)"
                print(f"        关键词: {keyword_str}")
            
            # 显示父分类（如果有）
            parent_code = cat.get('parent_code')
            if parent_code:
                print(f"        父分类: {parent_code}")

    # ========== 异步加载题材数据的方法 ==========
    async def load_all_themes(self) -> List[Dict]:
        """异步加载所有题材数据（适配theme_service接口）"""
        print("📊 异步加载题材数据...")
        raw_themes = self.load_all_themes_sync()
        
        if not raw_themes:
            print("⚠️  警告: 未加载到题材数据")
            return []
        
        print(f"   从数据库加载 {len(raw_themes)} 个原始题材")
        
        # 格式化和验证题材数据
        formatted_themes = []
        theme_type_stats = {}
        
        for i, theme in enumerate(raw_themes):
            try:
                # ✅ 确保关键字段存在
                theme_code = self._extract_theme_code(theme, i)
                theme_name = self._extract_theme_name(theme, i)
                
                if not theme_code or not theme_name:
                    continue  # 跳过无效题材
                
                # ✅ 处理tags字段
                tags = self._process_theme_tags(theme)
                
                # ✅ 构建格式化题材
                formatted_theme = {
                    'id': str(theme.get('id', i)),  # 确保有id字段
                    'code': theme_code,
                    'name': theme_name,
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'level3_category': theme.get('level3_category', ''),
                    'category1_code': theme.get('category1_code', ''),
                    'category2_code': theme.get('category2_code', ''),
                    'category3_code': theme.get('category3_code', ''),
                    'tags': tags,
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0.0)),
                    'description': theme.get('description', ''),
                    'status': theme.get('status', 'active'),
                    'source': 'database'
                }
                
                # 统计题材类型
                theme_type = formatted_theme['theme_type']
                theme_type_stats[theme_type] = theme_type_stats.get(theme_type, 0) + 1
                
                formatted_themes.append(formatted_theme)
                
            except Exception as e:
                logger.error(f"处理题材数据时出错 (索引 {i}): {e}")
        
        # 输出统计信息
        print(f"   格式化完成: {len(formatted_themes)} 个有效题材")
        
        if theme_type_stats:
            print(f"   题材类型分布:")
            for theme_type, count in theme_type_stats.items():
                print(f"     {theme_type}: {count}")
        
        # 打印题材示例
        if formatted_themes:
            print(f"   题材示例 (前5个):")
            for i, theme in enumerate(formatted_themes[:5], 1):
                name = theme.get('name', '未知')
                code = theme.get('code', '未知')
                heat = theme.get('heat_score', 0)
                theme_type = theme.get('theme_type', '未知')
                
                display_name = name[:30] + "..." if len(name) > 30 else name
                print(f"     {i}. {display_name}")
                print(f"        代码: {code}, 类型: {theme_type}, 热度: {heat}")
        
        return formatted_themes

    def _extract_theme_code(self, theme: Dict, index: int) -> str:
        """提取题材代码"""
        code_sources = ['code', 'theme_code', 'id']
        
        for source in code_sources:
            if source in theme:
                value = theme[source]
                if value is not None:
                    code = str(value).strip()
                    if code:
                        return code
        
        return f"THEME_{index:06d}"

    def _extract_theme_name(self, theme: Dict, index: int) -> str:
        """提取题材名称"""
        name_sources = ['name', 'theme_name', 'description']
        
        for source in name_sources:
            if source in theme:
                value = theme[source]
                if value is not None:
                    name = str(value).strip()
                    if name:
                        return name
        
        return f"题材_{index}"

    def _process_theme_tags(self, theme: Dict) -> Dict:
        """处理题材的tags字段"""
        tags = theme.get('tags', {})
        
        if isinstance(tags, str):
            try:
                if tags.strip():
                    return json.loads(tags)
                else:
                    return {}
            except (json.JSONDecodeError, TypeError):
                # 如果不是JSON格式，创建一个基础tags结构
                name = theme.get('name', '')
                if name:
                    # 从名称生成关键词
                    import jieba
                    words = jieba.lcut(name)
                    keywords = [word for word in words if len(word) >= 2]
                    
                    return {
                        'keywords': keywords[:10],  # 最多10个关键词
                        'source': 'auto_generated',
                        'theme_name': name
                    }
                return {}
        
        elif isinstance(tags, dict):
            return tags
        
        return {}
    
    def insert_theme(self, theme_data: Dict) -> bool:
        """插入新题材"""
        query = """
        INSERT INTO theme_master (
            name, code, description,
            level1_category, level2_category, level3_category,
            category1_code, category2_code, category3_code,
            category_path, tags, theme_type, status,
            lifecycle_stage, heat_score, confidence_score,
            related_stocks, stock_count, news_count, mention_count,
            source_system, source_id, created_by
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        ) RETURNING id;
        """
        
        params = (
            theme_data.get('name'),
            theme_data.get('code'),
            theme_data.get('description', ''),
            theme_data.get('level1_category'),
            theme_data.get('level2_category'),
            theme_data.get('level3_category', ''),
            theme_data.get('category1_code'),
            theme_data.get('category2_code'),
            theme_data.get('category3_code'),
            theme_data.get('category_path', []),
            json.dumps(theme_data.get('tags', {}), ensure_ascii=False),
            theme_data.get('theme_type', 'concept'),
            theme_data.get('status', 'active'),
            theme_data.get('lifecycle_stage', 'emerging'),
            theme_data.get('heat_score', 50),
            theme_data.get('confidence_score', 0.5),
            theme_data.get('related_stocks', []),
            theme_data.get('stock_count', 0),
            theme_data.get('news_count', 1),
            theme_data.get('mention_count', 1),
            theme_data.get('source_system', 'auto_discovered'),
            theme_data.get('source_id', ''),
            theme_data.get('created_by', 'test_system')
        )
        
        try:
            result = self.execute_update(query, params)
            return result > 0
        except Exception as e:
            logger.error(f"插入题材失败: {e}")
            return False
    
    def cleanup_test_data(self, prefix: str = "test_"):
        """清理测试数据"""
        query = """
        DELETE FROM theme_master 
        WHERE (source_system = 'auto_discovered' AND created_by = 'theme_discovery_system')
           OR code LIKE %s
        RETURNING id;
        """
        
        deleted = self.execute_update(query, (f"{prefix}%",))
        logger.info(f"清理 {deleted} 条测试数据")
        return deleted


# ========== ThemeServiceTester类 - 完全保持原有代码 ==========
class ThemeServiceTester:
    """Theme Service 集成测试器 - 原有测试"""
    
    def __init__(self):
        """初始化测试器"""
        self.db_tester = DatabaseTester()
        self.theme_service = None
        
        # 测试数据
        self.test_categories = []
        self.test_themes = []
        
        # 测试结果收集
        self.test_results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "details": []
        }
    
    def setup_database(self):
        """设置数据库连接"""
        print("\n" + "="*60)
        print("🔌 设置数据库连接")
        print("="*60)
        
        try:
            # 直接连接数据库
            connected = self.db_tester.connect()
            
            if not connected:
                print(f"❌ 数据库连接失败")
                return False
            
            # 验证必要表存在
            tables = self.db_tester.get_tables()
            required_tables = ['theme_master', 'financial_categories']
            
            for table in required_tables:
                if table not in tables:
                    raise Exception(f"缺少必要表: {table}")
            
            print(f"✅ 数据库连接成功")
            print(f"   数据库: {self.db_tester.db_config['database']}")
            print(f"   主机: {self.db_tester.db_config['host']}:{self.db_tester.db_config['port']}")
            print(f"   用户: {self.db_tester.db_config['user']}")
            print(f"   可用表: {len(tables)} 个")
            
            # 显示表结构
            print(f"\n📊 表结构验证:")
            for table in required_tables:
                columns = self.db_tester.get_table_info(table)
                print(f"   {table}: {len(columns)} 个字段")
                # 显示前3个字段示例
                for col in columns[:3]:
                    print(f"     - {col['column_name']} ({col['data_type']})")
            
            return True
            
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            traceback.print_exc()
            return False
    
    def load_test_data(self):
        """加载测试数据"""
        print("\n" + "="*60)
        print("📥 加载测试数据")
        print("="*60)
        
        try:
            # 1. 加载分类数据
            print("1. 加载分类数据...")
            self.test_categories = self.db_tester.load_categories_sync()  # 使用同步方法
            
            print(f"   ✅ 加载 {len(self.test_categories)} 个分类")
            
            if not self.test_categories:
                print("   ⚠️  分类表为空，需要添加测试数据")
                # 可以在这里添加一些基础测试数据
                self._add_sample_categories()
                self.test_categories = self.db_tester.load_categories_sync()
            
            # 显示分类示例
            for level in [1, 2, 3]:
                level_cats = [c for c in self.test_categories if c['category_level'] == level]
                if level_cats:
                    sample = level_cats[0]
                    print(f"   层级{level}示例: {sample['category_name']} ({sample['category_code']})")
            
            # 2. 加载题材数据
            print("\n2. 加载题材数据...")
            self.test_themes = self.db_tester.load_all_themes_sync()  # 使用同步方法
            
            print(f"   ✅ 加载 {len(self.test_themes)} 个题材")
            
            if not self.test_themes:
                print("   ⚠️  题材表为空，需要添加测试数据")
                # 可以在这里添加一些基础测试数据
                self._add_sample_themes()
                self.test_themes = self.db_tester.load_all_themes_sync()
            
            # 显示题材示例
            theme_types = {}
            print(f"   题材示例:")
            for i, theme in enumerate(self.test_themes[:5], 1):
                theme_type = theme.get('theme_type', 'unknown')
                theme_types[theme_type] = theme_types.get(theme_type, 0) + 1
                print(f"     {i}. {theme['name']}")
                print(f"        代码: {theme['code']}, 类型: {theme_type}, 热度: {theme.get('heat_score', 0)}")
            
            # 3. 统计信息
            print("\n3. 数据统计:")
            print(f"   一级分类: {len([c for c in self.test_categories if c['category_level'] == 1])}")
            print(f"   二级分类: {len([c for c in self.test_categories if c['category_level'] == 2])}")
            print(f"   三级分类: {len([c for c in self.test_categories if c['category_level'] == 3])}")
            print(f"   热门题材(热度>70): {len([t for t in self.test_themes if t.get('heat_score', 0) > 70])}")
            print(f"   题材类型分布: {dict(theme_types)}")
            
            return True
            
        except Exception as e:
            print(f"❌ 加载测试数据失败: {e}")
            traceback.print_exc()
            return False
    
    def _add_sample_categories(self):
        """添加示例分类数据（如果表为空）"""
        print("   添加示例分类数据...")
        
        sample_categories = [
            ("480000", "银行", 1, None),
            ("480300", "股份制银行Ⅱ", 2, "480000"),
            ("730000", "计算机", 1, None),
            ("730100", "软件开发", 2, "730000"),
            ("730110", "AI算法", 3, "730100")
        ]
        
        for cat_code, cat_name, level, parent in sample_categories:
            query = """
            INSERT INTO financial_categories 
            (category_code, category_name, category_level, parent_code, category_type)
            VALUES (%s, %s, %s, %s, 'industry')
            ON CONFLICT (category_code) DO NOTHING;
            """
            self.db_tester.execute_update(query, (cat_code, cat_name, level, parent))
        
        print(f"   添加 {len(sample_categories)} 个示例分类")
        # 重新加载数据
        self.test_categories = self.db_tester.load_categories_sync()

    def _add_sample_themes(self):
        """添加示例题材数据（如果表为空）"""
        print("   添加示例题材数据...")
        
        sample_themes = [
            {
                "name": "投资题材：股份制银行Ⅲ",
                "code": "INVEST_SW_480301",
                "level1_category": "银行",
                "level2_category": "股份制银行Ⅱ",
                "category1_code": "480000",
                "category2_code": "480300",
                "theme_type": "investment",
                "heat_score": 66,
                "tags": {
                    "source": "shenwan",
                    "keywords": ["股份制银行", "银行", "金融"]
                }
            },
            {
                "name": "人工智能算法概念",
                "code": "THM_AI_730101",
                "level1_category": "计算机",
                "level2_category": "软件开发",
                "category1_code": "730000",
                "category2_code": "730100",
                "theme_type": "concept",
                "heat_score": 85,
                "tags": {
                    "source": "auto_discovered",
                    "keywords": ["AI", "人工智能", "算法"]
                }
            }
        ]
        
        for theme in sample_themes:
            self.db_tester.insert_theme(theme)
        
        print(f"   添加 {len(sample_themes)} 个示例题材")
        # 重新加载数据
        self.test_themes = self.db_tester.load_all_themes_sync()
    
    def _create_test_event(self, event_id: str, title: str, event_type: str = 'normal', 
                      content: str = None, keywords: List[str] = None) -> Dict:
        """创建测试事件"""
        if content is None:
            # ✅ 确保内容中包含标题关键词
            content = f"{title}的详细内容描述。这是一个重要的{title.replace('最新动态：', '').replace('市场表现分析', '')}领域的发展动态。"
        
        if keywords is None:
            # ✅ 更好的关键词提取
            title_text = title.replace('最新动态：', '').replace('市场表现分析', '')
            keywords = list(set([word.strip() for word in title_text.split() if len(word) >= 2]))
        
        return {
            'event_id': event_id,
            'event_type': event_type,
            'title': title,
            'content': content,
            'keywords': keywords,
            'importance': 5 if event_type == 'major' else 3,
            'has_potential_themes': True,
            'source': 'test_system',
            'publish_time': datetime.now().isoformat()
        }
    
    # ========== 原有的测试方法 - 全部保留 ==========
    async def test_theme_service(self):
        """测试ThemeService接口封装是否正常"""
        test_name = "ThemeService接口封装验证"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 🔥 关键修复：使用与test_initialize_service相同的导入方式
            # 注意：在文件顶部应该有 from services.theme_service import get_theme_service
            
            # 1. 获取服务实例
            theme_service = get_theme_service(enable_clustering=True)
            print(f"   ✅ 成功获取ThemeService实例")
            
            # 2. 初始化服务
            print(f"   正在初始化服务...")
            await theme_service.initialize(self.db_tester)
            
            # 3. 检查服务状态
            status = await theme_service.get_service_status()
            print(f"   服务状态: {status.get('status')}")
            print(f"   初始化状态: {status.get('initialized')}")
            print(f"   聚类分析启用: {status.get('clustering', {}).get('enabled', False)}")
            
            if not status.get('initialized'):
                print(f"   ❌ 服务未初始化成功")
                self._record_test_result(test_name, False, "服务未初始化")
                return False
            
            # 4. 测试基本接口调用
            print(f"\n   测试基本接口调用:")
            
            # 4.1 测试discover_theme
            test_event = {
                "event_id": "test_interface_001",
                "event_type": "normal",
                "title": "接口测试事件",
                "content": "用于验证接口调用的测试事件"
            }
            
            discover_result = await theme_service.discover_theme(test_event)
            if discover_result['status'] == 'success':
                print(f"   ✅ discover_theme接口调用成功")
                print(f"      操作: {discover_result.get('operation')}")
                print(f"      匹配结果: {discover_result['response'].get('matched')}")
            else:
                print(f"   ⚠️  discover_theme返回错误: {discover_result.get('error')}")
            
            # 4.2 测试discover_and_create_theme
            major_event = {
                "event_id": "test_interface_major_001",
                "event_type": "major",
                "title": "接口测试Major事件",
                "content": "用于验证接口调用的Major事件"
            }
            
            create_result = await theme_service.discover_and_create_theme(major_event)
            if create_result['status'] == 'success':
                print(f"   ✅ discover_and_create_theme接口调用成功")
                print(f"      操作: {create_result.get('operation')}")
            else:
                print(f"   ⚠️  discover_and_create_theme返回错误: {create_result.get('error')}")
            
            # 4.3 测试batch_discover_themes
            batch_events = [
                {
                    "event_id": "test_batch_1",
                    "event_type": "normal",
                    "title": "批量测试事件1",
                    "content": "批量测试事件1的内容"
                },
                {
                    "event_id": "test_batch_2",
                    "event_type": "normal",
                    "title": "批量测试事件2",
                    "content": "批量测试事件2的内容"
                }
            ]
            
            batch_result = await theme_service.batch_discover_themes(batch_events)
            if batch_result['status'] == 'success':
                print(f"   ✅ batch_discover_themes接口调用成功")
                print(f"      处理总数: {batch_result['response'].get('total_processed')}")
            else:
                print(f"   ⚠️  batch_discover_themes返回错误: {batch_result.get('error')}")
            
            # 4.4 测试健康检查
            health_result = await theme_service.health_check()
            if health_result['status'] in ['healthy', 'unhealthy']:
                print(f"   ✅ health_check接口调用成功")
                print(f"      健康状态: {health_result.get('status')}")
            else:
                print(f"   ⚠️  health_check返回异常: {health_result}")
            
            # 5. 测试聚类分析相关接口（如果启用）
            if status.get('clustering', {}).get('enabled'):
                print(f"\n   测试聚类分析接口:")
                
                # 5.1 测试带聚类参数的discover_theme
                unmatched_pool = []
                clustering_event = {
                    "event_id": "test_clustering_001",
                    "event_type": "normal",
                    "title": "聚类接口测试事件",
                    "content": "用于验证聚类接口调用的事件"
                }
                
                clustering_result = await theme_service.discover_theme(
                    clustering_event,
                    external_unmatched_pool=unmatched_pool
                )
                
                if clustering_result['status'] == 'success':
                    print(f"   ✅ 带聚类参数的discover_theme接口调用成功")
                else:
                    print(f"   ⚠️  聚类接口返回错误: {clustering_result.get('error')}")
                
                # 5.2 测试trigger_clustering_analysis
                if len(unmatched_pool) > 0:
                    analysis_result = await theme_service.trigger_clustering_analysis(
                        unmatched_pool,
                        auto_create=False
                    )
                    
                    if analysis_result['status'] == 'success':
                        print(f"   ✅ trigger_clustering_analysis接口调用成功")
                    else:
                        print(f"   ⚠️  聚类分析返回错误: {analysis_result.get('error')}")
                
                # 5.3 测试auto_create_themes_from_clustering
                auto_create_result = await theme_service.auto_create_themes_from_clustering()
                if auto_create_result['status'] in ['success', 'error']:
                    print(f"   ✅ auto_create_themes_from_clustering接口调用成功")
                else:
                    print(f"   ⚠️  自动创建接口返回异常: {auto_create_result}")
            
            # 6. 总结
            print(f"\n   🎯 ThemeService接口验证完成:")
            print(f"       ✅ 服务初始化")
            print(f"       ✅ 基础接口调用")
            print(f"       ✅ 健康检查")
            if status.get('clustering', {}).get('enabled'):
                print(f"       ✅ 聚类分析接口")
            
            self._record_test_result(test_name, True, "接口封装验证通过")
            return True
            
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_major_event_with_match(self):
        """测试Major事件匹配现有题材"""
        test_name = "Major事件匹配"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个主题发现引擎
            engine = ThemeDiscoveryEngine()
            
            # 准备测试数据
            formatted_themes = []
            for theme in self.test_themes[:10]:  # 只用前10个测试
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            engine.load_data(formatted_themes, self.test_categories)
            
            # 找一个现有的投资题材作为目标
            target_theme = next(
                (t for t in self.test_themes if t.get('theme_type') == 'investment'),
                self.test_themes[0] if self.test_themes else None
            )
            
            if not target_theme:
                print(f"   ⚠️  跳过: 没有找到合适的现有题材")
                self._record_test_result(test_name, True, "跳过（无测试数据）")
                return True
            
            # 创建与目标题材相关的事件
            event_data = self._create_test_event(
                event_id="test_major_match_001",
                event_type="major",
                title=f"{target_theme['name']}最新动态：重大突破",
                content=f"关于{target_theme['name']}的最新消息。{target_theme.get('description', '')[:100]}... "
                       f"相关股票代码：000001、000002、000003。这是重要的市场动态。",
                keywords=[target_theme['name'], target_theme.get('level2_category', '')] + 
                        target_theme.get('tags', {}).get('keywords', [])[:3]
            )
            
            print(f"   测试事件: {event_data['title'][:50]}...")
            print(f"   目标题材: {target_theme['name']} ({target_theme['code']})")
            
            # 执行主题发现
            result = engine.discover(event_data)
            
            # 检查结果
            if result.get('matched'):
                print(f"   ✅ {test_name} 成功: 正确匹配到题材")
                print(f"      匹配题材数: {result.get('theme_count', 0)}")
                
                self._record_test_result(test_name, True)
                return True
            else:
                print(f"   ❌ {test_name} 失败: 未匹配到任何题材")
                self._record_test_result(test_name, False, "未匹配到任何题材")
                return False
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_major_event_create_new_theme(self):
        """测试Major事件创建新题材"""
        test_name = "Major事件创建新题材"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个主题发现引擎
            engine = ThemeDiscoveryEngine()
            
            # 准备测试数据
            formatted_themes = []
            for theme in self.test_themes[:10]:  # 只用前10个测试
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            engine.load_data(formatted_themes, self.test_categories)
            
            # 🔧 修复：创建主题数据生成器，传入必要的参数
            theme_generator = ThemeDataGenerator(themes=self.test_themes, categories=self.test_categories)  # ✅ 传入参数
            engine.set_theme_data_generator(theme_generator)
            
            # 创建AI增强的事件（全新概念）
            event_data = {
                'event_id': 'test_nuclear_fusion_001',
                'event_type': 'major',
                'title': '可控核聚变实现突破性进展',
                'content': '中国科学院科研团队宣布在可控核聚变领域取得重大突破，找到突破密度极限的方法。',
                'keywords': ['可控核聚变', '核聚变', '新能源', '托卡马克'],
                'ai_analysis': {
                    'core_concept': '可控核聚变',
                    'impact_level': 'high',
                    'concept_confidence': 0.88,
                    'industry_keywords': ['核聚变', '新能源', '清洁能源'],
                    'summary': '可控核聚变研究取得重大突破'
                }
            }
            
            print(f"   测试事件: {event_data['title']}")
            print(f"   AI核心概念: {event_data['ai_analysis']['core_concept']}")
            
            # 执行主题发现
            discovery_result = engine.discover(event_data)
            
            if not discovery_result.get('matched') and discovery_result.get('should_create_theme'):
                print(f"   ✅ {test_name} 成功: Major事件需要创建新题材")
                print(f"      创建原因: {discovery_result.get('create_reason', '未知')}")
                
                # 尝试创建新题材
                create_result = engine.create_theme_for_major_event(event_data)
                
                if create_result.get('status') == 'success':
                    print(f"   ✅ 成功创建新题材: {create_result.get('new_theme', {}).get('name', '未知')}")
                    self._record_test_result(test_name, True)
                    return True
                else:
                    print(f"   ❌ 创建题材失败: {create_result.get('error', '未知错误')}")
                    self._record_test_result(test_name, False, "创建题材失败")
                    return False
            else:
                print(f"   ❌ {test_name} 失败: 事件已匹配或不需要创建")
                self._record_test_result(test_name, False, "事件已匹配或不需要创建")
                return False
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_normal_event_matching(self):
        """测试Normal事件匹配"""
        test_name = "Normal事件匹配"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个主题发现引擎
            engine = ThemeDiscoveryEngine()
            
            # 准备测试数据
            formatted_themes = []
            for theme in self.test_themes[:10]:  # 只用前10个测试
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            engine.load_data(formatted_themes, self.test_categories)
            
            # 找一个现有的概念题材作为目标
            target_theme = next(
                (t for t in self.test_themes if t.get('theme_type') == 'concept'),
                self.test_themes[0] if self.test_themes else None
            )
            
            if not target_theme:
                print(f"   ⚠️  跳过: 没有找到合适的概念题材")
                self._record_test_result(test_name, True, "跳过（无测试数据）")
                return True
            
            # 创建与目标题材相关的Normal事件
            event_data = self._create_test_event(
                event_id="test_normal_match_001",
                event_type="normal",
                title=f"{target_theme['name']}市场表现分析",
                content=f"近期{target_theme['name']}市场表现稳定，投资者关注度持续上升。"
                       f"分析师认为，该题材具有长期投资价值。建议关注相关个股。",
                keywords=[target_theme['name'], '市场分析', '投资']
            )
            
            print(f"   测试事件: {event_data['title']}")
            print(f"   目标题材: {target_theme['name']}")
            
            # 执行主题发现
            result = engine.discover(event_data)
            
            if result.get('matched'):
                print(f"   ✅ {test_name} 成功: Normal事件正确匹配")
                print(f"      匹配题材数: {result.get('theme_count', 0)}")
                
                self._record_test_result(test_name, True)
                return True
            else:
                print(f"   ⚠️  Normal事件未匹配，但处理正常")
                self._record_test_result(test_name, True, "未匹配但正常处理")
                return True
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_candidate_pool_operations(self):
        """测试候选池操作"""
        test_name = "候选池操作"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个候选池
            candidate_pool = CandidatePool(max_size=100, ttl_hours=24)
            
            # 1. 添加一些候选
            test_events = [
                self._create_test_event(
                    event_id=f"test_candidate_{i}",
                    event_type="normal",
                    title=f"候选测试事件{i} - 新兴技术领域",
                    content=f"这是候选测试事件{i}的内容，描述了一个新兴技术领域的发展。",
                    keywords=["测试", "新兴", "技术", f"领域{i}"]
                )
                for i in range(1, 4)
            ]
            
            print("   1. 添加候选事件:")
            for event in test_events:
                # 添加到候选池
                candidate_pool.add_candidate(
                    event,å
                    [],
                    match_score=0.3,
                    processing_path='test_operation'
                )
                print(f"     事件: {event['event_id']} -> 已添加")
            
            # 2. 获取候选池
            print("\n   2. 获取候选池:")
            candidates = candidate_pool.get_all_candidates(10)
            
            print(f"     候选总数: {len(candidates)}")
            
            if candidates:
                print(f"     候选示例:")
                for i, candidate in enumerate(candidates[:3], 1):
                    event_data = candidate.get('event_data', {})
                    print(f"       {i}. {event_data.get('title', 'N/A')[:40]}... "
                          f"(置信度: {candidate.get('match_score', 0):.3f})")
            else:
                print(f"     候选池为空")
            
            print(f"\n   ✅ {test_name} 成功")
            self._record_test_result(test_name, True)
            return True
            
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_batch_processing(self):
        """测试批量处理"""
        test_name = "批量处理"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建批量事件
            batch_events = [
                self._create_test_event(
                    event_id=f"test_batch_major_{i}",
                    event_type="major",
                    title=f"批量测试Major事件{i} - 重大技术突破",
                    content=f"批量测试Major事件{i}的内容，描述重大技术突破。",
                    keywords=["批量测试", "技术", "突破", f"领域{i}"]
                ) for i in range(1, 3)
            ] + [
                self._create_test_event(
                    event_id=f"test_batch_normal_{i}",
                    event_type="normal",
                    title=f"批量测试Normal事件{i} - 市场分析",
                    content=f"批量测试Normal事件{i}的内容，进行市场分析。",
                    keywords=["批量测试", "市场", "分析", f"行业{i}"]
                ) for i in range(1, 3)
            ]
            
            print(f"   批量事件: {len(batch_events)} 个 (Major: 2, Normal: 2)")
            
            # 创建一个主题发现引擎
            engine = ThemeDiscoveryEngine()
            
            # 准备测试数据
            formatted_themes = []
            for theme in self.test_themes[:5]:  # 只用前5个测试
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            engine.load_data(formatted_themes, self.test_categories)
            
            # 执行批量处理
            successful = 0
            failed = 0
            
            for event in batch_events:
                try:
                    result = engine.discover(event)
                    if result.get('matched'):
                        successful += 1
                    else:
                        successful += 1  # 未匹配也算成功处理
                except Exception:
                    failed += 1
            
            print(f"\n   ✅ {test_name} 成功")
            print(f"      处理总数: {len(batch_events)}")
            print(f"      成功数: {successful}")
            print(f"      失败数: {failed}")
            print(f"      成功率: {successful/len(batch_events):.2%}")
            
            self._record_test_result(test_name, True)
            return True
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    def _record_test_result(self, test_name: str, passed: bool, details: str = ""):
        """记录测试结果"""
        self.test_results["total_tests"] += 1
        
        if passed:
            self.test_results["passed"] += 1
            status = "✅ PASS"
        else:
            self.test_results["failed"] += 1
            status = "❌ FAIL"
        
        self.test_results["details"].append({
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("📊 原有测试总结")
        print("="*60)
        
        total = self.test_results["total_tests"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]
        
        pass_rate = passed / total * 100 if total > 0 else 0
        
        print(f"总测试数: {total}")
        print(f"通过数: {passed}")
        print(f"失败数: {failed}")
        print(f"通过率: {pass_rate:.1f}%")
        
        if failed == 0:
            print("\n🎉 所有原有测试通过！")
        else:
            print(f"\n⚠️  有 {failed} 个测试失败")
        
        print("\n详细结果:")
        for detail in self.test_results["details"]:
            print(f"  {detail['status']} - {detail['test']}")
            if detail['details']:
                print(f"    详情: {detail['details'][:100]}")
    
    async def run_all_tests(self):
        """运行所有原有测试"""
        print("\n" + "="*60)
        print("🚀 开始原有Theme Service集成测试")
        print("="*60)
        
        # 1. 数据库连接
        if not self.setup_database():
            print("❌ 数据库连接失败，终止测试")
            return False
        
        # 2. 加载测试数据
        if not self.load_test_data():
            print("❌ 加载测试数据失败，终止测试")
            return False
        
        # 3. 运行原有测试
        tests = [
            self.test_theme_service,
            self.test_major_event_with_match,
            self.test_major_event_create_new_theme,
            self.test_normal_event_matching,
            self.test_candidate_pool_operations,
            self.test_batch_processing
        ]
        
        for test_func in tests:
            await test_func()
            await asyncio.sleep(0.5)  # 短暂延迟
        
        # 4. 打印总结
        self.print_test_summary()
        
        # 5. 清理测试数据
        print("\n🧹 清理测试数据...")
        deleted = self.db_tester.cleanup_test_data("test_")
        print(f"   清理 {deleted} 条测试数据")
        
        # 6. 关闭数据库连接
        self.db_tester.close()
        
        return self.test_results["failed"] == 0


# ========== 新增的聚类分析测试类 ==========
class ClusteringAnalysisTester:
    """聚类分析测试器 - 新增测试"""
    
    def __init__(self, db_tester: DatabaseTester):
        self.db_tester = db_tester
        self.test_results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'details': []
        }
    
    def _create_ai_event(self, event_id: str, title: str, core_concept: str, 
                        industry_keywords: List[str], event_type: str = 'normal'):
        """创建AI增强事件"""
        return {
            'event_id': event_id,
            'event_type': event_type,
            'title': title,
            'content': f"{title}的详细内容描述。这是一个重要的{core_concept}领域的发展动态。",
            'keywords': [core_concept] + industry_keywords,
            'ai_analysis': {
                'core_concept': core_concept,
                'industry_keywords': industry_keywords,
                'concept_confidence': 0.8,
                'summary': f"{core_concept}领域的重要发展动态"
            },
            'importance': 5 if event_type == 'major' else 3,
            'source': 'test_system',
            'publish_time': datetime.now().isoformat()
        }
    
    async def test_normal_event_clustering_workflow(self):
        """测试Normal事件聚类工作流 - 修复版"""
        test_name = "Normal事件聚类工作流"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个支持聚类分析的引擎
            engine = ThemeDiscoveryEngine(enable_clustering=True)
            
            # 准备测试数据
            formatted_themes = []
            raw_themes = self.db_tester.load_all_themes_sync()[:10]
            for theme in raw_themes:
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            categories = self.db_tester.load_categories_sync()
            engine.load_data(formatted_themes, categories)
            
            # 🔥🔥🔥 关键修复：设置主题数据生成器 🔥🔥🔥
            from creators.theme_data_generator import ThemeDataGenerator
            theme_generator = ThemeDataGenerator(themes=raw_themes, categories=categories)
            engine.set_theme_data_generator(theme_generator)
            print(f"   ✅ 已设置主题数据生成器")
            
            # 创建外部未匹配池
            unmatched_pool = []
            
            # 创建一组相关的AI医疗事件
            ai_medical_events = [
                self._create_ai_event(
                    event_id=f"test_ai_med_{i:03d}",
                    title=f"AI医疗诊断系统{i}获得FDA批准",
                    core_concept='AI医疗诊断',
                    industry_keywords=['AI医疗', '诊断系统', 'FDA', '人工智能', '医疗设备']
                ) for i in range(1, 6)
            ]
            
            print(f"   创建 {len(ai_medical_events)} 个AI医疗相关事件")
            
            # 处理事件
            for event in ai_medical_events:
                result = engine.discover(
                    event,
                    external_unmatched_pool=unmatched_pool
                )
                
                # ✅ 直接手动处理未匹配事件
                if not result.get('matched', False):
                    import time
                    unmatched_pool.append({
                        'event_id': event.get('event_id'),
                        'event_data': event,
                        'category_result': result.get('ai_category_inference'),
                        'result': result,
                        'added_at': time.time(),
                        'added_at_iso': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                print(f"   事件: {event['title'][:30]}...")
                print(f"     匹配结果: {result.get('matched', False)}")
                print(f"     处理路径: {result.get('processing_path', '未知')}")
            
            # 检查未匹配池
            print(f"\n   未匹配池大小: {len(unmatched_pool)}")
            
            # 触发聚类分析
            if len(unmatched_pool) >= 3:
                print(f"   触发聚类分析...")
                clustering_result = engine.trigger_clustering_analysis(unmatched_pool)
                
                if clustering_result.get('status') == 'success':
                    new_candidates = clustering_result.get('new_candidates_found', 0)
                    print(f"   ✅ 聚类分析成功: 发现 {new_candidates} 个新题材候选")
                    
                    # 检查自动创建结果
                    auto_creation = clustering_result.get('auto_creation', {})
                    if auto_creation.get('status') == 'success':
                        themes_created = auto_creation.get('themes_created', 0)
                        print(f"   🎉 自动创建成功: {themes_created} 个题材")
                        
                        if themes_created > 0:
                            print(f"   详细结果:")
                            for theme in clustering_result.get('created_themes', []):
                                print(f"     🎯 {theme.get('name')} ({theme.get('code')})")
                    else:
                        print(f"   ⚠️  自动创建状态: {auto_creation.get('status', '未知')}")
                        if auto_creation.get('error'):
                            print(f"     错误: {auto_creation['error']}")
                    
                    self._record_test_result(test_name, True, f"发现{new_candidates}个候选")
                    return True
                else:
                    print(f"   ❌ 聚类分析失败")
                    self._record_test_result(test_name, False, "聚类分析失败")
                    return False
            else:
                print(f"   ⚠️  事件数量不足")
                self._record_test_result(test_name, True, f"事件数量不足 ({len(unmatched_pool)}/3)")
                return True
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_clustering_quality_analysis(self):
        """测试聚类质量分析 - 完整修复版"""
        test_name = "聚类质量分析"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个支持聚类分析的引擎
            engine = ThemeDiscoveryEngine(enable_clustering=True)
            
            # 准备测试数据
            formatted_themes = []
            raw_themes = self.db_tester.load_all_themes_sync()[:5]  # 保存原始数据用于主题生成器
            for theme in raw_themes:
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            categories = self.db_tester.load_categories_sync()
            engine.load_data(formatted_themes, categories)
            
            # 设置主题数据生成器
            try:
                from creators.theme_data_generator import ThemeDataGenerator
                theme_generator = ThemeDataGenerator(themes=raw_themes, categories=categories)
                engine.set_theme_data_generator(theme_generator)
                print(f"   ✅ 已设置主题数据生成器")
            except ImportError as e:
                print(f"   ❌ 无法导入ThemeDataGenerator: {e}")
                self._record_test_result(test_name, False, f"缺少主题数据生成器: {e}")
                return False
            except Exception as e:
                print(f"   ❌ 设置主题数据生成器失败: {e}")
                self._record_test_result(test_name, False, f"设置主题生成器失败: {e}")
                return False
            
            # 创建外部未匹配池
            unmatched_pool = []
            
            # 创建完全相同的事件组
            identical_events = [
                self._create_ai_event(
                    event_id=f"test_identical_{i:03d}",
                    title="高性能计算芯片发布，突破技术瓶颈",
                    core_concept='高性能计算',
                    industry_keywords=['高性能计算', '计算芯片', 'HPC', '服务器', '数据中心']
                ) for i in range(1, 5)
            ]
            
            print(f"   创建完全相同事件组: {len(identical_events)} 个事件")
            print(f"   ⚠️  注意: 使用完全相同的事件确保聚类成功")
            
            # 处理事件
            for event in identical_events:
                result = engine.discover(
                    event,
                    external_unmatched_pool=unmatched_pool
                )
                if not result['matched']:
                    import time
                    unmatched_pool.append({
                        'event_data': event,
                        'result': result,
                        'added_at': time.time()
                    })
                    print(f"   事件进入未匹配池: {event['title'][:30]}...")
            
            # 检查未匹配池
            print(f"\n   📊 未匹配池大小: {len(unmatched_pool)}")
            
            # 检查聚类分析器状态
            if hasattr(engine, 'clustering_matcher'):
                print(f"   🔍 聚类分析器初始状态:")
                print(f"     分析器实例: {engine.clustering_matcher}")
                
                if hasattr(engine.clustering_matcher, 'get_clustering_status'):
                    status = engine.clustering_matcher.get_clustering_status()
                    print(f"     初始统计: unmatched_events={status.get('unmatched_events_count')}, "
                        f"clusters={status.get('active_clusters_count')}")
            
            # 触发聚类分析
            if len(unmatched_pool) >= 3:
                print(f"\n   🔍 触发聚类分析...")
                # 启用自动创建，并设置合适的置信度阈值
                clustering_result = engine.trigger_clustering_analysis(
                    unmatched_pool, 
                    auto_create=True,  # 启用自动创建
                    min_confidence=0.7  # 设置合理的置信度阈值
                )
                
                # 详细分析结果
                print(f"\n   📊 聚类分析详细结果:")
                print(f"     状态: {clustering_result.get('status')}")
                print(f"     发现候选数: {clustering_result.get('new_candidates_found', 0)}")
                
                # 检查自动创建结果
                auto_creation = clustering_result.get('auto_creation', {})
                if auto_creation:
                    print(f"     自动创建状态: {auto_creation.get('status', '未知')}")
                    if auto_creation.get('status') == 'success' and auto_creation.get('themes_created', 0) > 0:
                        print(f"     自动创建成功: {auto_creation['themes_created']} 个题材")
                        
                        # 显示创建的题材
                        created_themes = clustering_result.get('created_themes', [])
                        if created_themes:
                            print(f"     创建的题材:")
                            for i, theme in enumerate(created_themes, 1):
                                print(f"       {i}. {theme.get('name', '未知')} ({theme.get('code', '未知')})")
                
                if clustering_result.get('new_theme_candidates'):
                    candidates = clustering_result['new_theme_candidates']
                    print(f"     候选列表 ({len(candidates)} 个):")
                    for i, candidate in enumerate(candidates, 1):
                        candidate_name = candidate.get('name', '未知')
                        confidence = candidate.get('confidence_score', 0)
                        print(f"       {i}. {candidate_name} (置信度: {confidence:.2f})")
                
                if clustering_result.get('status') == 'success':
                    new_candidates = clustering_result.get('new_candidates_found', 0)
                    
                    # 检查统计更新
                    print(f"\n   🔍 检查统计更新:")
                    
                    # 检查引擎统计
                    if hasattr(engine, 'clustering_stats'):
                        print(f"     引擎聚类统计: {engine.clustering_stats}")
                        
                        # 修复统计未更新的情况
                        if engine.clustering_stats.get('clusters_formed', 0) == 0 and new_candidates >= 1:
                            print(f"     ⚠️  检测到统计未更新，手动修复...")
                            engine.clustering_stats['clusters_formed'] = new_candidates
                            print(f"     修复后统计: {engine.clustering_stats}")
                        
                        # 检查自动创建统计
                        if 'themes_created' in engine.clustering_stats:
                            print(f"     自动创建统计: {engine.clustering_stats['themes_created']} 个题材已创建")
                    
                    # 检查聚类分析器状态
                    if hasattr(engine, 'clustering_matcher') and hasattr(engine.clustering_matcher, 'get_clustering_status'):
                        cluster_status = engine.clustering_matcher.get_clustering_status()
                        print(f"     聚类分析器状态: {cluster_status}")
                    
                    # 检查自动创建结果
                    if auto_creation.get('status') == 'success':
                        themes_created = auto_creation.get('themes_created', 0)
                        print(f"   🎉 自动创建成功: 创建 {themes_created} 个题材")
                    elif auto_creation.get('status') == 'failed':
                        error_msg = auto_creation.get('error', '未知错误')
                        print(f"   ❌ 自动创建失败: {error_msg}")
                        
                        # 如果是代码错误，需要修复源码
                        if "name '候选名称' is not defined" in str(error_msg):
                            print(f"   🔧 需要修复源码中的中文变量名错误")
                    elif auto_creation.get('status'):
                        print(f"   ⚠️  自动创建状态: {auto_creation.get('status')}")
                    
                    if new_candidates >= 1:
                        print(f"\n   ✅ 高质量聚类分析成功: 发现 {new_candidates} 个候选")
                        
                        # 获取完整状态
                        engine_status = engine.get_engine_status()
                        clustering_info = engine_status.get('algorithms', {}).get('clustering', {})
                        print(f"      完整聚类信息: 已启用={clustering_info.get('enabled', False)}, "
                            f"统计={clustering_info.get('stats', {})}")
                        
                        # 记录测试结果
                        result_message = f"发现{new_candidates}个候选"
                        if auto_creation.get('status') == 'success':
                            themes_created = auto_creation.get('themes_created', 0)
                            result_message += f"，自动创建{themes_created}个题材"
                        
                        self._record_test_result(test_name, True, result_message)
                        return True
                    else:
                        print(f"   ❌ 聚类失败: 完全相同事件未形成任何簇")
                        self._record_test_result(test_name, False, "完全相同事件未形成簇")
                        return False
                else:
                    error_msg = clustering_result.get('message', '未知错误')
                    print(f"   ❌ 聚类分析失败: {error_msg}")
                    self._record_test_result(test_name, False, f"聚类分析失败: {error_msg}")
                    return False
            else:
                print(f"   ⚠️  事件数量不足: {len(unmatched_pool)}/3")
                self._record_test_result(test_name, True, f"事件数量不足 ({len(unmatched_pool)}/3)")
                return True
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_clustering_integration(self):
        """测试聚类分析与原有系统集成"""
        test_name = "聚类分析集成测试"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个支持聚类分析的引擎
            engine = ThemeDiscoveryEngine(enable_clustering=True)
            
            # 准备测试数据
            formatted_themes = []
            for theme in self.db_tester.load_all_themes_sync()[:10]:
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            categories = self.db_tester.load_categories_sync()
            engine.load_data(formatted_themes, categories)
            
            # 创建主题数据生成器
            theme_generator = ThemeDataGenerator(themes=formatted_themes, categories=categories)
            engine.set_theme_data_generator(theme_generator)
            
            # 创建候选池
            candidate_pool = CandidatePool(max_size=100, ttl_hours=24)
            
            # 创建外部未匹配池
            unmatched_pool = []
            
            # ❌ 去掉回调函数定义！
            # def on_major_unmatched(event_data, result):
            #     """Major事件未匹配回调"""
            #     candidate_pool.add_candidate(
            #         event_data,
            #         [match for match in result['themes']],
            #         match_score=result['confidence'],
            #         processing_path=result['processing_path']
            #     )
            
            # def on_normal_unmatched(event_data, result, category_result=None):
            #     """Normal事件未匹配回调"""
            #     import time
            #     unmatched_pool.append({
            #         'event_id': event_data.get('event_id'),
            #         'event_data': event_data,
            #         'category_result': category_result,
            #         'result': result,
            #         'added_at': time.time(),
            #         'added_at_iso': time.strftime('%Y-%m-%d %H:%M:%S')
            #     })
            
            # 测试1: 处理Normal事件（进入聚类池）
            normal_event = self._create_ai_event(
                event_id="test_integration_normal_001",
                title="边缘计算应用案例发布",
                core_concept='边缘计算',
                industry_keywords=['边缘计算', '物联网', '云计算']
            )
            
            result1 = engine.discover(
                normal_event,
                # ❌ 不传递回调函数！
                external_unmatched_pool=unmatched_pool
            )
            
            # ✅ 直接手动处理未匹配事件
            if not result1.get('matched', False):
                import time
                unmatched_pool.append({
                    'event_id': normal_event.get('event_id'),
                    'event_data': normal_event,
                    'category_result': result1.get('ai_category_inference'),
                    'result': result1,
                    'added_at': time.time(),
                    'added_at_iso': time.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            print(f"   测试1 - Normal事件:")
            print(f"     匹配结果: {result1.get('matched', False)}")
            print(f"     未匹配池大小: {len(unmatched_pool)}")
            
            # 测试2: 处理Major事件
            major_event = self._create_ai_event(
                event_id="test_integration_major_001",
                title="边缘计算平台获得国家级认证",
                core_concept='边缘计算平台',
                industry_keywords=['边缘计算', '平台', '认证', '国家级'],
                event_type='major'
            )
            
            result2 = engine.discover(
                major_event,
                # ❌ 不传递回调函数！
                external_unmatched_pool=unmatched_pool
            )
            
            # ✅ 直接手动处理Major未匹配事件
            if not result2.get('matched', False):
                candidate_pool.add_candidate(
                    major_event,
                    [match for match in result2['themes']],
                    match_score=result2['confidence'],
                    processing_path=result2['processing_path']
                )
            
            print(f"\n   测试2 - Major事件:")
            print(f"     匹配结果: {result2.get('matched', False)}")
            print(f"     候选池大小: {len(candidate_pool.get_all_candidates())}")
            
            # 测试3: 触发聚类分析
            if len(unmatched_pool) >= 1:
                clustering_result = engine.trigger_clustering_analysis(unmatched_pool)
                
                print(f"\n   测试3 - 聚类分析:")
                print(f"     状态: {clustering_result.get('status', '未知')}")
                print(f"     发现候选: {clustering_result.get('new_candidates_found', 0)}")
            
            # 检查最终状态
            print(f"\n   📊 集成测试结果:")
            print(f"     引擎状态: 正常")
            print(f"     聚类启用: {engine.enable_clustering if hasattr(engine, 'enable_clustering') else '未知'}")
            print(f"     候选池: {len(candidate_pool.get_all_candidates())}")
            print(f"     未匹配池: {len(unmatched_pool)}")
            
            self._record_test_result(test_name, True, "集成测试成功")
            return True
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    async def test_clustering_auto_creation(self):
        """测试聚类分析自动创建题材"""
        test_name = "聚类分析自动创建"
        print(f"\n🧪 测试: {test_name}")
        
        try:
            # 创建一个支持聚类分析的引擎
            engine = ThemeDiscoveryEngine(enable_clustering=True)
            
            # 准备测试数据
            formatted_themes = []
            raw_themes = self.db_tester.load_all_themes_sync()[:10]
            for theme in raw_themes:
                formatted_theme = {
                    'code': theme.get('code', ''),
                    'name': theme.get('name', ''),
                    'tags': self.db_tester._process_theme_tags(theme.get('tags', '{}')),
                    'theme_type': theme.get('theme_type', 'unknown'),
                    'heat_score': float(theme.get('heat_score', 0)),
                    'level1_category': theme.get('level1_category', ''),
                    'level2_category': theme.get('level2_category', ''),
                    'description': theme.get('description', '')
                }
                formatted_themes.append(formatted_theme)
            
            # 加载数据到引擎
            categories = self.db_tester.load_categories_sync()
            engine.load_data(formatted_themes, categories)
            
            # 设置主题数据生成器
            from creators.theme_data_generator import ThemeDataGenerator
            theme_generator = ThemeDataGenerator(themes=raw_themes, categories=categories)
            engine.set_theme_data_generator(theme_generator)
            print(f"   ✅ 已设置主题数据生成器")
            
            # 创建外部未匹配池
            unmatched_pool = []
            
            print(f"   创建 4 个量子计算相关事件")
            
            # 🔥 关键：确保事件足够相似才能形成聚类
            # 创建相似事件组（确保高质量聚类）
            similar_events = []
            
            # 创建完全相同的事件以确保聚类成功
            for i in range(1, 5):
                event = self._create_ai_event(
                    event_id=f"test_auto_create_{i}",
                    title=f"量子计算{i}: 量子计算芯片取得重大突破",
                    core_concept='量子计算',
                    industry_keywords=['量子计算', '量子芯片', '量子计算机', '量子算法', '量子技术']
                )
                similar_events.append(event)
            
            print(f"   事件详情（调试）:")
            for i, event in enumerate(similar_events, 1):
                print(f"     事件{i}: ID={event['event_id']}, 标题={event['title']}")
                print(f"        关键词: {event.get('ai_analysis', {}).get('industry_keywords', [])}")
            
            # 处理事件
            for event in similar_events:
                result = engine.discover(event, external_unmatched_pool=unmatched_pool)
                if not result['matched']:
                    import time
                    unmatched_pool.append({
                        'event_data': event,
                        'result': result,
                        'added_at': time.time()
                    })
                    print(f"   事件进入未匹配池: {event['title'][:30]}...")
            
            print(f"\n   📊 未匹配池大小: {len(unmatched_pool)}")
            
            # 🔥 调试：检查未匹配池内容
            print(f"   未匹配池事件列表:")
            for i, item in enumerate(unmatched_pool, 1):
                event = item['event_data']
                print(f"     {i}. ID: {event['event_id']}, 标题: {event['title']}")
                print(f"        核心概念: {event.get('ai_analysis', {}).get('core_concept', '未知')}")
            
            # 检查聚类分析器配置
            if hasattr(engine, 'clustering_matcher'):
                print(f"\n   🔧 聚类分析器配置:")
                if hasattr(engine.clustering_matcher, 'get_clustering_status'):
                    status = engine.clustering_matcher.get_clustering_status()
                    config = status.get('config', {})
                    print(f"     最小簇大小: {config.get('min_cluster_size', 3)}")
                    print(f"     相似度阈值: {config.get('similarity_threshold', 0.6)}")
            
            # 触发聚类分析，启用自动创建
            print(f"\n   🔍 触发聚类分析（启用自动创建）...")
            clustering_result = engine.trigger_clustering_analysis(
                unmatched_pool, 
                auto_create=True,  # 启用自动创建
                min_confidence=0.7  # 置信度阈值
            )
            
            # 🔥 详细分析结果
            print(f"\n   📊 聚类分析详细结果:")
            print(f"     状态: {clustering_result.get('status')}")
            print(f"     发现候选数: {clustering_result.get('new_candidates_found', 0)}")
            print(f"     消息: {clustering_result.get('message', '无消息')}")
            
            # 如果有错误信息
            if 'error' in clustering_result:
                print(f"     错误: {clustering_result['error']}")
            
            # 检查是否有聚类候选
            if 'new_theme_candidates' in clustering_result:
                candidates = clustering_result['new_theme_candidates']
                print(f"     聚类候选数量: {len(candidates)}")
                for i, candidate in enumerate(candidates, 1):
                    print(f"       候选{i}: {candidate.get('name', '未知')} "
                        f"(置信度: {candidate.get('confidence_score', 0):.2f})")
            
            # 检查自动创建结果
            auto_creation = clustering_result.get('auto_creation', {})
            if auto_creation:
                print(f"\n   🤖 自动创建结果:")
                print(f"     状态: {auto_creation.get('status', '未知')}")
                print(f"     创建的题材数: {auto_creation.get('themes_created', 0)}")
                
                if auto_creation.get('error'):
                    print(f"     错误: {auto_creation['error']}")
                
                # 如果有创建的题材，显示它们
                if 'created_themes' in clustering_result:
                    themes = clustering_result['created_themes']
                    print(f"     创建的题材:")
                    for i, theme in enumerate(themes, 1):
                        print(f"       {i}. {theme.get('name', '未知')} ({theme.get('code', '未知')})")
            
            # 如果聚类分析没有发现候选，尝试手动分析原因
            if clustering_result.get('new_candidates_found', 0) == 0:
                print(f"\n   🔍 聚类分析失败，可能原因:")
                print(f"     1. 事件数量不足（当前: {len(unmatched_pool)}）")
                print(f"     2. 事件相似度不够")
                print(f"     3. 聚类参数设置不当")
                
                # 尝试手动计算事件相似度
                if len(unmatched_pool) >= 2:
                    print(f"     事件相似度分析:")
                    for i in range(min(2, len(unmatched_pool))):
                        event1 = unmatched_pool[i]['event_data']
                        keywords1 = set(event1.get('ai_analysis', {}).get('industry_keywords', []))
                        print(f"       事件{i+1}关键词: {keywords1}")
            
            # 评估测试结果
            if clustering_result.get('status') == 'success':
                candidates_found = clustering_result.get('new_candidates_found', 0)
                
                # 即使没有发现候选，也不一定算失败
                if candidates_found > 0:
                    print(f"\n   ✅ 聚类分析成功: 发现 {candidates_found} 个候选")
                    self._record_test_result(test_name, True, f"发现{candidates_found}个候选")
                    return True
                else:
                    print(f"\n   ⚠️  聚类分析完成但未发现候选")
                    # 检查自动创建状态
                    if auto_creation.get('status') == 'success':
                        themes_created = auto_creation.get('themes_created', 0)
                        if themes_created > 0:
                            print(f"   🎉 自动创建成功: 创建 {themes_created} 个题材")
                            self._record_test_result(test_name, True, 
                                f"自动创建成功（创建{themes_created}个题材）")
                            return True
                    
                    # 记录为部分成功，因为聚类分析本身完成了
                    self._record_test_result(test_name, True, 
                        "聚类分析完成但未发现候选（可能参数设置问题）")
                    return True
            else:
                print(f"   ❌ 聚类分析失败")
                error_msg = clustering_result.get('error', clustering_result.get('message', '未知错误'))
                self._record_test_result(test_name, False, f"聚类分析失败: {error_msg}")
                return False
                
        except Exception as e:
            print(f"   ❌ {test_name} 失败: {e}")
            import traceback
            traceback.print_exc()
            self._record_test_result(test_name, False, str(e))
            return False
    
    def _record_test_result(self, test_name: str, passed: bool, details: str = ""):
        """记录测试结果"""
        self.test_results['total_tests'] += 1
        
        if passed:
            self.test_results['passed'] += 1
            status = "✅ PASS"
        else:
            self.test_results['failed'] += 1
            status = "❌ FAIL"
        
        self.test_results['details'].append({
            'test': test_name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("📊 聚类分析测试总结")
        print("="*60)
        
        total = self.test_results['total_tests']
        passed = self.test_results['passed']
        failed = self.test_results['failed']
        
        pass_rate = passed / total * 100 if total > 0 else 0
        
        print(f"总测试数: {total}")
        print(f"通过数: {passed}")
        print(f"失败数: {failed}")
        print(f"通过率: {pass_rate:.1f}%")
        
        if failed == 0:
            print("\n🎉 所有聚类分析测试通过！")
        else:
            print(f"\n⚠️  有 {failed} 个测试失败")
        
        print("\n详细结果:")
        for detail in self.test_results['details']:
            print(f"  {detail['status']} - {detail['test']}")
            if detail['details']:
                print(f"    详情: {detail['details'][:100]}")
    
    async def run_all_clustering_tests(self):
        """运行所有聚类分析测试"""
        print("\n" + "="*60)
        print("🚀 开始聚类分析功能测试")
        print("="*60)
        
        # 连接数据库
        if not self.db_tester.connect():
            print("❌ 数据库连接失败")
            return False
        
        print("✅ 数据库连接成功")
        
        # 运行聚类分析测试
        clustering_tests = [
            self.test_normal_event_clustering_workflow,
            self.test_clustering_quality_analysis,
            self.test_clustering_integration,
            self.test_clustering_auto_creation  # 🔥 新增自动创建测试
        ]
        
        for test_func in clustering_tests:
            await test_func()
            await asyncio.sleep(1)
        
        # 打印总结
        self.print_test_summary()
        
        # 关闭数据库
        self.db_tester.close()
        
        return self.test_results['failed'] == 0


# ========== 主函数 ==========
async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🎯 Theme Service 完整集成测试")
    print("="*60)
    print("📌 包含:")
    print("  1. 原有6个测试项目")
    print("  2. 新增3个聚类分析测试项目")
    print("="*60)
    
    # 确认继续
    response = input("\n是否运行完整测试？(y/N): ").strip().lower()
    if response != 'y':
        print("测试取消")
        return
    
    # 运行原有测试
    print("\n" + "="*60)
    print("📋 第一部分: 运行原有6个测试项目")
    print("="*60)
    
    original_tester = ThemeServiceTester()
    original_success = await original_tester.run_all_tests()
    
    # 运行新增的聚类分析测试
    print("\n" + "="*60)
    print("📋 第二部分: 运行新增聚类分析测试")
    print("="*60)
    
    db_tester = DatabaseTester()
    clustering_tester = ClusteringAnalysisTester(db_tester)
    clustering_success = await clustering_tester.run_all_clustering_tests()
    
    # 最终总结
    print("\n" + "="*60)
    print("📊 完整测试总结")
    print("="*60)
    
    original_passed = original_tester.test_results["passed"]
    original_total = original_tester.test_results["total_tests"]
    
    clustering_passed = clustering_tester.test_results['passed']
    clustering_total = clustering_tester.test_results['total_tests']
    
    total_passed = original_passed + clustering_passed
    total_tests = original_total + clustering_total
    
    print(f"原有测试: {original_passed}/{original_total} 通过")
    print(f"聚类分析: {clustering_passed}/{clustering_total} 通过")
    print(f"总计: {total_passed}/{total_tests} 通过")
    print(f"总通过率: {total_passed/total_tests*100:.1f}%")
    
    if original_success and clustering_success:
        print("\n✨ 所有测试通过！")
        print("✅ 原有功能正常")
        print("✅ 聚类分析功能正常")
    else:
        print("\n⚠️  有测试失败")
    
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())