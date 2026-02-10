#!/usr/bin/env python3
"""
28字段表结构验证测试
专门验证28字段结构的完整性和正确性
"""
import asyncio
import sys
import inspect
import json
from pathlib import Path
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, service_dir)   # database_service

try:
    from database_service.interface import ThemeRecord, ThemeTags
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.factory import DatabaseManagerFactory
    print("✅ 成功导入所需模块")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


class SchemaValidationTest:
    """28字段表结构验证测试类"""
    
    def __init__(self):
        self.results = {}
        self.expected_fields = [
            # 基本信息 (4个)
            'id', 'name', 'code', 'description', 'status',
            
            # 分类信息 (9个)
            'level1_category', 'level2_category', 'level3_category',
            'category_path', 'category1_code', 'category2_code', 'category3_code',
            
            # 标签信息 (1个，但包含多个子字段)
            'tags',
            
            # 类型与状态 (2个)
            'theme_type', 'lifecycle_stage',
            
            # 热度与置信度 (2个)
            'heat_score', 'confidence_score',
            
            # 关联统计 (5个)
            'related_stocks', 'stock_count', 'news_count', 'mention_count',
            
            # 时间戳 (2个)
            'last_mentioned', 'last_active_at',
            
            # 来源信息 (3个)
            'source_system', 'source_id', 'created_by',
            
            # 系统时间戳 (2个)
            'created_at', 'updated_at'
        ]
        
        # ThemeTags的预期字段
        self.expected_tags_fields = [
            'source', 'aliases', 'version', 'concepts',
            'keywords', 'heat_level', 'industries',
            'industry_code', 'merge_candidates'
        ]
    
    async def run_all_validations(self):
        """运行所有验证"""
        print("🔍 28字段表结构验证测试")
        print("=" * 60)
        
        try:
            # 验证1: ThemeRecord结构
            await self.validate_theme_record_structure()
            
            # 验证2: ThemeTags结构
            await self.validate_theme_tags_structure()
            
            # 验证3: 内存管理器集成
            await self.validate_memory_integration()
            
            # 验证4: 工厂类验证
            await self.validate_factory_adaptation()
            
            # 验证5: 数据序列化
            await self.validate_data_serialization()
            
            # 验证6: 字段默认值
            await self.validate_field_defaults()
            
            # 汇总结果
            await self.summarize_results()
            
        except Exception as e:
            print(f"❌ 结构验证失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return all(result == "PASS" for result in self.results.values())
    
    async def validate_theme_record_structure(self):
        """验证ThemeRecord的28字段结构"""
        print("\n📝 验证1: ThemeRecord结构")
        try:
            # 使用dataclasses.fields获取字段
            from dataclasses import fields
            theme_fields = [field.name for field in fields(ThemeRecord)]
            
            # 检查字段数量
            print(f"  ThemeRecord字段数量: {len(theme_fields)}")
            
            # 检查每个预期字段是否存在
            missing_fields = []
            for expected in self.expected_fields:
                if expected not in theme_fields:
                    missing_fields.append(expected)
            
            if missing_fields:
                print(f"  ❌ 缺少字段: {missing_fields}")
                self.results["theme_record_structure"] = "FAIL"
                raise ValueError(f"ThemeRecord缺少字段: {missing_fields}")
            
            # 验证字段类型（部分）
            theme = ThemeRecord(
                id=1,
                name="测试主题",
                code="TEST_001",
                description="测试"
            )
            
            # 验证必填字段
            assert hasattr(theme, 'id')
            assert hasattr(theme, 'name')
            assert hasattr(theme, 'code')
            assert hasattr(theme, 'description')
            
            # 验证数组字段
            assert hasattr(theme, 'category_path')
            assert isinstance(theme.category_path, list) or theme.category_path is None
            
            assert hasattr(theme, 'related_stocks')
            assert isinstance(theme.related_stocks, list) or theme.related_stocks is None
            
            # 验证数值字段
            assert hasattr(theme, 'heat_score')
            assert isinstance(theme.heat_score, int) or theme.heat_score is None
            
            assert hasattr(theme, 'confidence_score')
            assert isinstance(theme.confidence_score, float) or theme.confidence_score is None
            
            print(f"  ✅ ThemeRecord结构验证通过 (共{len(theme_fields)}个字段)")
            self.results["theme_record_structure"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ ThemeRecord结构验证失败: {e}")
            self.results["theme_record_structure"] = "FAIL"
            raise
    
    async def validate_theme_tags_structure(self):
        """验证ThemeTags结构"""
        print("\n🏷️  验证2: ThemeTags结构")
        try:
            # 使用dataclasses.fields获取字段
            from dataclasses import fields
            tags_fields = [field.name for field in fields(ThemeTags)]
            
            print(f"  ThemeTags字段数量: {len(tags_fields)}")
            
            # 检查每个预期字段是否存在
            missing_fields = []
            for expected in self.expected_tags_fields:
                if expected not in tags_fields:
                    missing_fields.append(expected)
            
            if missing_fields:
                print(f"  ❌ ThemeTags缺少字段: {missing_fields}")
                self.results["theme_tags_structure"] = "FAIL"
                raise ValueError(f"ThemeTags缺少字段: {missing_fields}")
            
            # 创建ThemeTags实例验证
            tags = ThemeTags(
                source="shenwan",
                aliases=["测试"],
                keywords=["测试"],
                heat_level="medium"
            )
            
            # 验证字段
            assert tags.source == "shenwan"
            assert isinstance(tags.aliases, list)
            assert isinstance(tags.keywords, list)
            assert tags.heat_level == "medium"
            
            # 测试from_dict方法
            tags_dict = {
                "source": "test",
                "keywords": ["keyword1", "keyword2"],
                "heat_level": "high"
            }
            tags_from_dict = ThemeTags.from_dict(tags_dict)
            
            assert tags_from_dict.source == "test"
            assert "keyword1" in tags_from_dict.keywords
            assert tags_from_dict.heat_level == "high"
            
            # 测试to_dict方法
            back_to_dict = tags_from_dict.to_dict()
            assert isinstance(back_to_dict, dict)
            assert back_to_dict["source"] == "test"
            
            print(f"  ✅ ThemeTags结构验证通过")
            self.results["theme_tags_structure"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ ThemeTags结构验证失败: {e}")
            self.results["theme_tags_structure"] = "FAIL"
            raise
    
    async def validate_memory_integration(self):
        """验证内存管理器集成"""
        print("\n💾 验证3: 内存管理器集成")
        try:
            config = DatabaseConfig(
                db_type=DatabaseType.MEMORY
            )
            config.redis.enabled = False
            
            # 创建管理器
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 验证管理器功能
            assert manager is not None
            
            # 创建新主题验证28字段
            new_theme = await manager.create_theme(
                name="28字段验证主题",
                code="28FIELDS_VALIDATION_001",
                description="28字段验证主题",
                level1_category="验证分类",
                level2_category="二级验证",
                level3_category="三级验证",
                category_path=["验证分类", "二级验证", "三级验证"],
                category1_code="V001",
                category2_code="V002",
                category3_code="V003",
                tags={
                    "keywords": ["验证", "28字段"],
                    "heat_level": "medium",
                    "industries": ["验证行业"]
                },
                theme_type="investment",
                lifecycle_stage="growth",
                heat_score=75,
                confidence_score=0.8,
                related_stocks=["VALID001", "VALID002"],
                stock_count=2,
                news_count=5,
                mention_count=3,
                source_system="transformed",
                source_id="validation_source",
                created_by="validator"
            )
            
            # 验证所有字段都正确设置
            assert new_theme.code == "28FIELDS_VALIDATION_001"
            assert new_theme.level1_category == "验证分类"
            assert new_theme.level2_category == "二级验证"
            assert new_theme.level3_category == "三级验证"
            assert new_theme.category_path == ["验证分类", "二级验证", "三级验证"]
            assert new_theme.category1_code == "V001"
            assert new_theme.category2_code == "V002"
            assert new_theme.category3_code == "V003"
            
            # 验证tags字段
            if hasattr(new_theme.tags, 'keywords'):
                # ThemeTags对象
                assert "验证" in new_theme.tags.keywords
                assert new_theme.tags.heat_level == "medium"
            elif isinstance(new_theme.tags, dict):
                # 字典格式
                assert "验证" in new_theme.tags.get('keywords', [])
                assert new_theme.tags.get('heat_level') == "medium"
            
            assert new_theme.theme_type == "investment"
            assert new_theme.lifecycle_stage == "growth"
            assert new_theme.heat_score == 75
            assert new_theme.confidence_score == 0.8
            assert new_theme.related_stocks == ["VALID001", "VALID002"]
            assert new_theme.stock_count == 2
            assert new_theme.news_count == 5
            assert new_theme.mention_count == 3
            assert new_theme.source_system == "transformed"
            assert new_theme.source_id == "validation_source"
            assert new_theme.created_by == "validator"
            assert new_theme.created_at is not None
            assert new_theme.updated_at is not None
            
            await manager.disconnect()
            
            print("  ✅ 内存管理器集成验证通过")
            self.results["memory_integration"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 内存管理器集成验证失败: {e}")
            self.results["memory_integration"] = "FAIL"
            raise
    
    async def validate_factory_adaptation(self):
        """验证工厂类适配"""
        print("\n🏭 验证4: 工厂类适配")
        try:
            # 测试工厂创建内存管理器
            config = DatabaseConfig(
                db_type=DatabaseType.MEMORY
            )
            config.redis.enabled = False
            
            manager = await DatabaseManagerFactory.create_manager(config)
            
            # 验证管理器支持28字段操作
            # 创建主题
            theme = await manager.create_theme(
                name="工厂验证主题",
                code="FACTORY_VALIDATION_001",
                description="工厂类验证主题",
                heat_score=60
            )
            
            # 按code获取主题
            theme_by_code = await manager.get_theme_by_code("FACTORY_VALIDATION_001")
            assert theme_by_code is not None
            assert theme_by_code.id == theme.id
            
            # 测试更新操作
            updated = await manager.update_theme(theme.id, {
                "heat_score": 85,
                "description": "更新后的描述"
            })
            assert updated.heat_score == 85
            
            # 测试增加提及次数
            await manager.increment_mention_count(theme.id, 2)
            updated_theme = await manager.get_theme(theme.id)
            assert updated_theme.mention_count == 2
            
            # 测试搜索功能
            search_results = await manager.search_themes("工厂验证", limit=5)
            assert len(search_results) > 0
            
            await manager.disconnect()
            
            print("  ✅ 工厂类适配验证通过")
            self.results["factory_adaptation"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 工厂类适配验证失败: {e}")
            self.results["factory_adaptation"] = "FAIL"
            raise
    
    async def validate_data_serialization(self):
        """验证数据序列化"""
        print("\n🔄 验证5: 数据序列化")
        try:
            # 创建完整的ThemeRecord
            theme = ThemeRecord(
                id=1001,
                name="序列化测试主题",
                code="SERIALIZATION_TEST_001",
                description="序列化测试主题",
                status="active",
                level1_category="序列化分类",
                level2_category="二级序列化",
                level3_category="三级序列化",
                category_path=["序列化分类", "二级序列化", "三级序列化"],
                category1_code="S001",
                category2_code="S002",
                category3_code="S003",
                tags=ThemeTags(
                    source="test",
                    aliases=["序列化", "测试"],
                    version="1.0",
                    concepts=["数据序列化"],
                    keywords=["序列化", "测试", "28字段"],
                    heat_level="medium",
                    industries=["测试行业"],
                    industry_code="TEST001",
                    merge_candidates=[]
                ),
                theme_type="investment",
                lifecycle_stage="growth",
                heat_score=85,
                confidence_score=0.9,
                related_stocks=["STOCK001", "STOCK002"],
                stock_count=2,
                news_count=10,
                mention_count=5,
                last_mentioned=None,
                last_active_at=None,
                source_system="transformed",
                source_id="serialization_source",
                created_by="validator",
                created_at=None,
                updated_at=None
            )
            
            # 测试to_dict方法
            theme_dict = theme.to_dict()
            assert isinstance(theme_dict, dict)
            
            # 验证关键字段
            assert theme_dict['code'] == "SERIALIZATION_TEST_001"
            assert theme_dict['level1_category'] == "序列化分类"
            assert theme_dict['heat_score'] == 85
            
            # 验证tags字段序列化
            assert 'tags' in theme_dict
            tags_dict = theme_dict['tags']
            assert isinstance(tags_dict, dict)
            assert tags_dict['source'] == "test"
            assert "序列化" in tags_dict['keywords']
            
            # 测试JSON序列化
            json_str = json.dumps(theme_dict, ensure_ascii=False)
            assert isinstance(json_str, str)
            assert "SERIALIZATION_TEST_001" in json_str
            
            # 测试从dict重建
            reconstructed_theme = ThemeRecord.from_dict(theme_dict)
            assert reconstructed_theme.code == "SERIALIZATION_TEST_001"
            assert reconstructed_theme.level1_category == "序列化分类"
            assert isinstance(reconstructed_theme.tags, ThemeTags)
            assert "序列化" in reconstructed_theme.tags.keywords
            
            print("  ✅ 数据序列化验证通过")
            self.results["data_serialization"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 数据序列化验证失败: {e}")
            self.results["data_serialization"] = "FAIL"
            raise
    
    async def validate_field_defaults(self):
        """验证字段默认值"""
        print("\n⚙️  验证6: 字段默认值")
        try:
            # 创建只有必要字段的主题
            theme = ThemeRecord(
                id=1,
                name="默认值测试主题",
                code="DEFAULT_TEST_001",
                description="默认值测试"
            )
            
            # 验证数组字段默认值
            assert isinstance(theme.category_path, list)
            assert isinstance(theme.related_stocks, list)
            
            # 验证tags字段默认值
            assert theme.tags is not None
            assert isinstance(theme.tags, ThemeTags)
            assert isinstance(theme.tags.keywords, list)
            assert isinstance(theme.tags.aliases, list)
            assert isinstance(theme.tags.concepts, list)
            assert isinstance(theme.tags.industries, list)
            assert isinstance(theme.tags.merge_candidates, list)
            
            # 验证数值字段默认值
            assert theme.heat_score == 50  # 根据interface.py中的默认值
            assert theme.confidence_score == 0.80  # 根据interface.py中的默认值
            assert theme.stock_count == 0
            assert theme.news_count == 0
            assert theme.mention_count == 0
            
            # 验证状态字段默认值
            assert theme.status == "active"
            assert theme.theme_type == "investment"
            assert theme.lifecycle_stage == "growth"
            assert theme.source_system == "transformed"
            
            # 验证ThemeTags默认值
            assert theme.tags.source == "shenwan"
            assert theme.tags.heat_level == "medium"
            assert theme.tags.version == "2.0"
            
            print("  ✅ 字段默认值验证通过")
            self.results["field_defaults"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 字段默认值验证失败: {e}")
            self.results["field_defaults"] = "FAIL"
            raise
    
    async def summarize_results(self):
        """汇总验证结果"""
        print("\n" + "=" * 60)
        print("📋 28字段结构验证结果汇总")
        print("=" * 60)
        
        total_validations = len(self.results)
        passed_validations = sum(1 for result in self.results.values() if result == "PASS")
        failed_validations = total_validations - passed_validations
        
        # 显示每个验证结果
        for validation_name, result in self.results.items():
            status = "✅ PASS" if result == "PASS" else "❌ FAIL"
            print(f"  {validation_name:25} {status}")
        
        # 显示统计
        print(f"\n📊 统计:")
        print(f"  总验证数: {total_validations}")
        print(f"  通过数: {passed_validations}")
        print(f"  失败数: {failed_validations}")
        
        # 字段统计
        print(f"\n📋 字段统计:")
        print(f"  ThemeRecord字段数: {len(self.expected_fields)}")
        print(f"  ThemeTags字段数: {len(self.expected_tags_fields)}")
        print(f"  总计字段数: {len(self.expected_fields) + len(self.expected_tags_fields)}")
        
        # 总体结果
        if failed_validations == 0:
            print("\n🎉 所有28字段结构验证通过！")
            print("  数据结构完整，符合28字段表结构要求")
        else:
            print(f"\n⚠️  有 {failed_validations} 个验证失败")
            print("  请检查数据结构是否符合28字段要求")


async def main():
    """主函数"""
    print("=" * 60)
    print("🔍 28字段表结构验证测试启动")
    print("=" * 60)
    
    validator = SchemaValidationTest()
    success = await validator.run_all_validations()
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())