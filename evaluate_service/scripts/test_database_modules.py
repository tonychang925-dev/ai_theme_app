#!/usr/bin/env python3
"""
数据库模块功能完整性测试
位置: evaluate_service/scripts/test_database_modules.py
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
log_dir = project_root / "evaluate_service" / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"database_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

class DatabaseModuleTester:
    """数据库模块测试器"""
    
    def __init__(self):
        self.results = {
            "test_time": datetime.now().isoformat(),
            "test_phase": "database_modules",
            "modules": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "success_rate": 0.0
            },
            "details": []
        }
    
    def record_test(self, module: str, test_name: str, passed: bool, error: str = None):
        """记录测试结果"""
        self.results["summary"]["total_tests"] += 1
        if passed:
            self.results["summary"]["passed"] += 1
            logger.info(f"✅ [{module}] {test_name} - 通过")
        else:
            self.results["summary"]["failed"] += 1
            logger.error(f"❌ [{module}] {test_name} - 失败: {error}")
        
        # 记录详情
        self.results["details"].append({
            "module": module,
            "test": test_name,
            "passed": passed,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
        
        # 更新模块状态
        if module not in self.results["modules"]:
            self.results["modules"][module] = {"tests": [], "status": "PASS"}
        
        self.results["modules"][module]["tests"].append({
            "name": test_name,
            "passed": passed
        })
        
        # 如果模块有任何失败，标记为失败
        if not passed:
            self.results["modules"][module]["status"] = "FAIL"
    
    async def test_memory_database_manager(self):
        """测试MemoryDatabaseManager"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 MemoryDatabaseManager")
        logger.info("="*60)
        
        try:
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            
            # 1. 创建实例
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            self.record_test("MemoryDatabaseManager", "创建实例", True)
            
            # 2. 连接测试
            try:
                connected = await db_manager.connect()
                self.record_test("MemoryDatabaseManager", "数据库连接", connected)
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "数据库连接", False, str(e))
                return False
            
            # 3. 健康检查
            try:
                health = await db_manager.health_check()
                self.record_test("MemoryDatabaseManager", "健康检查", health)
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "健康检查", False, str(e))
            
            # 4. 创建主题
            try:
                theme = await db_manager.create_theme(
                    name="数据库测试主题",
                    description="用于测试数据库功能的主题",
                    keywords=["数据库", "测试"],
                    discovery_source="evaluation",
                    discovery_confidence=0.9
                )
                success = theme is not None and hasattr(theme, 'id')
                self.record_test("MemoryDatabaseManager", "创建主题", success)
                
                if success:
                    logger.info(f"   创建主题: {theme.name} (ID: {theme.id})")
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "创建主题", False, str(e))
            
            # 5. 查询主题
            try:
                if 'theme' in locals() and theme:
                    theme_by_id = await db_manager.get_theme(theme.id)
                    success = theme_by_id is not None
                    self.record_test("MemoryDatabaseManager", "根据ID查询主题", success)
                    
                    theme_by_name = await db_manager.get_theme_by_name("数据库测试主题")
                    success = theme_by_name is not None
                    self.record_test("MemoryDatabaseManager", "根据名称查询主题", success)
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "查询主题", False, str(e))
            
            # 6. 创建事件
            try:
                event_id = await db_manager.create_or_update_event({
                    'news_id': 'eval_event_001',
                    'title': '数据库测试事件',
                    'summary': '这是一个用于测试数据库功能的完整事件，包含详细的描述信息。',
                    'event_type': '测试事件',
                    'impact_industries': ['测试行业'],
                    'direction': '中性',
                    'confidence': 0.8
                })
                success = event_id is not None
                self.record_test("MemoryDatabaseManager", "创建事件", success)
                
                if success:
                    logger.info(f"   创建事件成功: ID={event_id}")
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "创建事件", False, str(e))
            
            # 7. 事件-主题关联
            try:
                if 'theme' in locals() and theme and 'event_id' in locals() and event_id:
                    relation = await db_manager.create_event_theme_relation(
                        event_id=event_id,
                        theme_id=theme.id,
                        confidence=0.85,
                        confidence_level='high'
                    )
                    success = relation is not None
                    self.record_test("MemoryDatabaseManager", "创建事件-主题关联", success)
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "创建事件-主题关联", False, str(e))
            
            # 8. 获取所有主题
            try:
                all_themes = await db_manager.get_all_active_themes(limit=10)
                success = isinstance(all_themes, list)
                self.record_test("MemoryDatabaseManager", "获取所有活跃主题", success)
                
                if success:
                    logger.info(f"   获取到 {len(all_themes)} 个活跃主题")
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "获取所有活跃主题", False, str(e))
            
            # 9. 获取增强主题（如果支持）
            try:
                if hasattr(db_manager, 'get_all_active_themes_with_context'):
                    enhanced_themes = await db_manager.get_all_active_themes_with_context(limit=5)
                    success = isinstance(enhanced_themes, list)
                    self.record_test("MemoryDatabaseManager", "获取增强主题列表", success)
                    
                    if success and enhanced_themes:
                        logger.info(f"   获取到 {len(enhanced_themes)} 个增强主题")
                else:
                    logger.warning("   ⚠️  数据库不支持get_all_active_themes_with_context方法")
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "获取增强主题列表", False, str(e))
            
            # 10. 清理
            try:
                await db_manager.cleanup()
                self.record_test("MemoryDatabaseManager", "清理数据库", True)
            except Exception as e:
                self.record_test("MemoryDatabaseManager", "清理数据库", False, str(e))
            
            return True
            
        except ImportError as e:
            logger.error(f"❌ 导入MemoryDatabaseManager失败: {e}")
            self.record_test("MemoryDatabaseManager", "导入模块", False, str(e))
            return False
        except Exception as e:
            logger.error(f"❌ MemoryDatabaseManager测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_pure_data_fetcher(self):
        """测试PureDataFetcher"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 PureDataFetcher")
        logger.info("="*60)
        
        try:
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.pure_data_fetcher import PureDataFetcher
            
            # 1. 创建数据库管理器
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            # 2. 创建数据获取器
            fetcher = PureDataFetcher(db_manager)
            self.record_test("PureDataFetcher", "创建实例", True)
            
            # 3. 健康检查
            try:
                health = await fetcher.health_check()
                self.record_test("PureDataFetcher", "健康检查", health)
            except Exception as e:
                self.record_test("PureDataFetcher", "健康检查", False, str(e))
            
            # 4. 获取活跃主题
            try:
                themes = await fetcher.get_all_active_themes(limit=5)
                success = isinstance(themes, list)
                self.record_test("PureDataFetcher", "获取活跃主题", success)
                
                if success:
                    logger.info(f"   获取到 {len(themes)} 个活跃主题")
            except Exception as e:
                self.record_test("PureDataFetcher", "获取活跃主题", False, str(e))
            
            # 5. 获取增强主题
            try:
                if hasattr(fetcher, 'get_all_active_themes_with_context'):
                    enhanced = await fetcher.get_all_active_themes_with_context(limit=3)
                    success = isinstance(enhanced, list)
                    self.record_test("PureDataFetcher", "获取增强主题", success)
                    
                    if success and enhanced:
                        logger.info(f"   获取到 {len(enhanced)} 个增强主题")
                        # 检查增强主题的数据结构
                        if len(enhanced) > 0:
                            first_theme = enhanced[0]
                            has_name = 'name' in first_theme or 'theme_name' in first_theme
                            has_description = 'description' in first_theme or 'ai_description' in first_theme
                            self.record_test("PureDataFetcher", "增强主题数据结构", has_name and has_description)
                else:
                    logger.warning("   ⚠️  PureDataFetcher不支持get_all_active_themes_with_context方法")
            except Exception as e:
                self.record_test("PureDataFetcher", "获取增强主题", False, str(e))
            
            # 6. 清理
            await db_manager.cleanup()
            
            return True
            
        except ImportError as e:
            logger.error(f"❌ 导入PureDataFetcher失败: {e}")
            self.record_test("PureDataFetcher", "导入模块", False, str(e))
            return False
        except Exception as e:
            logger.error(f"❌ PureDataFetcher测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_database_client(self):
        """测试DatabaseClient"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 DatabaseClient")
        logger.info("="*60)
        
        try:
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.client import DatabaseClient
            
            # 1. 创建数据库管理器
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            # 2. 创建数据库客户端
            client = DatabaseClient(db_manager)
            self.record_test("DatabaseClient", "创建实例", True)
            
            # 3. 健康检查
            try:
                health = await client.health_check()
                self.record_test("DatabaseClient", "健康检查", health)
            except Exception as e:
                self.record_test("DatabaseClient", "健康检查", False, str(e))
            
            # 4. 获取增强主题
            try:
                enriched = await client.get_enriched_themes(limit=3)
                success = isinstance(enriched, list)
                self.record_test("DatabaseClient", "获取增强主题", success)
                
                if success:
                    logger.info(f"   获取到 {len(enriched)} 个增强主题")
            except Exception as e:
                self.record_test("DatabaseClient", "获取增强主题", False, str(e))
            
            # 5. 获取相关主题
            try:
                test_event = {
                    'id': 'search_test_001',
                    'title': '主题搜索测试事件',
                    'summary': '用于测试主题搜索功能的事件',
                    'impact_industries': ['测试行业'],
                    'event_type': '测试'
                }
                related = await client.get_related_themes(test_event, limit=2)
                success = isinstance(related, list)
                self.record_test("DatabaseClient", "获取相关主题", success)
                
                if success:
                    logger.info(f"   获取到 {len(related)} 个相关主题")
            except Exception as e:
                self.record_test("DatabaseClient", "获取相关主题", False, str(e))
            
            # 6. 清理
            await db_manager.cleanup()
            
            return True
            
        except ImportError as e:
            logger.error(f"❌ 导入DatabaseClient失败: {e}")
            self.record_test("DatabaseClient", "导入模块", False, str(e))
            return False
        except Exception as e:
            logger.error(f"❌ DatabaseClient测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def save_results(self):
        """保存测试结果到文件"""
        # 计算成功率
        total = self.results["summary"]["total_tests"]
        passed = self.results["summary"]["passed"]
        if total > 0:
            self.results["summary"]["success_rate"] = passed / total
        
        # 保存到结果目录
        results_dir = project_root / "evaluate_service" / "results"
        results_dir.mkdir(exist_ok=True)
        
        # 保存JSON格式的结果
        json_file = results_dir / f"database_modules_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        # 保存文本格式的报告
        report_file = results_dir / f"database_modules_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"数据库模块功能测试报告\n")
            f.write(f"测试时间: {self.results['test_time']}\n")
            f.write(f"测试阶段: {self.results['test_phase']}\n")
            f.write("="*60 + "\n\n")
            
            f.write("📊 测试摘要\n")
            f.write(f"总测试数: {total}\n")
            f.write(f"通过数: {passed}\n")
            f.write(f"失败数: {self.results['summary']['failed']}\n")
            f.write(f"成功率: {self.results['summary']['success_rate']:.1%}\n\n")
            
            f.write("📋 模块状态\n")
            for module_name, module_data in self.results['modules'].items():
                status = module_data['status']
                passed_tests = sum(1 for test in module_data['tests'] if test['passed'])
                total_tests = len(module_data['tests'])
                f.write(f"  {module_name}: {status} ({passed_tests}/{total_tests})\n")
            
            if self.results['summary']['failed'] > 0:
                f.write("\n❌ 失败的测试:\n")
                for detail in self.results['details']:
                    if not detail['passed']:
                        f.write(f"  - {detail['module']}.{detail['test']}: {detail['error']}\n")
        
        logger.info(f"✅ 测试结果已保存到: {json_file}")
        logger.info(f"📄 测试报告已保存到: {report_file}")
        
        return json_file, report_file
    
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "="*60)
        logger.info("📊 数据库模块测试摘要")
        logger.info("="*60)
        
        total = self.results["summary"]["total_tests"]
        passed = self.results["summary"]["passed"]
        failed = self.results["summary"]["failed"]
        
        logger.info(f"总测试数: {total}")
        logger.info(f"通过数: {passed}")
        logger.info(f"失败数: {failed}")
        
        if total > 0:
            success_rate = passed / total
            logger.info(f"成功率: {success_rate:.1%}")
        
        logger.info("\n📋 模块状态:")
        for module_name, module_data in self.results['modules'].items():
            status = module_data['status']
            passed_tests = sum(1 for test in module_data['tests'] if test['passed'])
            total_tests = len(module_data['tests'])
            status_icon = "✅" if status == "PASS" else "❌"
            logger.info(f"  {status_icon} {module_name}: {status} ({passed_tests}/{total_tests})")
        
        logger.info("="*60)
        
        if failed == 0:
            logger.info("🎉 所有数据库模块测试通过！")
            return True
        else:
            logger.warning(f"⚠️  有 {failed} 个测试失败，请检查并修复")
            return False

async def main():
    """主测试函数"""
    logger.info("🚀 启动数据库模块功能完整性测试")
    logger.info("测试时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("项目目录: " + str(project_root))
    logger.info("="*60)
    
    tester = DatabaseModuleTester()
    
    try:
        # 运行各个模块测试
        await tester.test_memory_database_manager()
        await tester.test_pure_data_fetcher()
        await tester.test_database_client()
        
        # 保存结果
        tester.save_results()
        
        # 打印摘要
        all_passed = tester.print_summary()
        
        if all_passed:
            print("\n" + "="*60)
            print("🎉 数据库模块测试全部通过！")
            print("✅ 可以进入第二阶段：主题检索器测试")
            print("="*60)
            return 0
        else:
            print("\n" + "="*60)
            print("❌ 数据库模块存在未通过的测试")
            print("⚠️  请先修复数据库模块问题")
            print("="*60)
            return 1
            
    except KeyboardInterrupt:
        logger.warning("测试被用户中断")
        return 130
    except Exception as e:
        logger.error(f"测试程序异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
        exit_code = 130
    sys.exit(exit_code)