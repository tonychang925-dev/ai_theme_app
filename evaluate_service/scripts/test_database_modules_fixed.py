#!/usr/bin/env python3
"""
数据库模块功能完整性测试 - 修复版
修复get_all_active_themes方法导致的卡顿问题
"""
import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

print(f"项目根目录: {project_root}")
print(f"当前工作目录: {os.getcwd()}")

# 配置日志
log_dir = project_root / "evaluate_service" / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"database_test_fixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

async def test_memory_database_manager_fixed():
    """测试MemoryDatabaseManager基本功能 - 修复版"""
    logger.info("🧪 测试 MemoryDatabaseManager (修复版)")
    
    try:
        # 导入模块
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        
        # 1. 创建实例
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        logger.info("✅ 创建MemoryDatabaseManager实例成功")
        
        # 2. 连接测试
        connected = await db_manager.connect()
        if connected:
            logger.info("✅ 数据库连接成功")
        else:
            logger.error("❌ 数据库连接失败")
            return False
        
        # 3. 健康检查
        health = await db_manager.health_check()
        if health:
            logger.info("✅ 数据库健康检查通过")
        else:
            logger.warning("⚠️ 数据库健康检查失败")
        
        # 4. 创建主题
        try:
            theme = await db_manager.create_theme(
                name="测试主题",
                description="用于功能测试的主题",
                keywords=["测试", "验证"],
                discovery_source="test",
                discovery_confidence=0.9
            )
            if theme and hasattr(theme, 'id'):
                logger.info(f"✅ 创建主题成功: {theme.name} (ID: {theme.id})")
            else:
                logger.error("❌ 创建主题失败")
                return False
        except Exception as e:
            logger.error(f"❌ 创建主题异常: {e}")
            return False
        
        # 5. 查询主题
        theme_by_id = await db_manager.get_theme(theme.id)
        if theme_by_id:
            logger.info(f"✅ 根据ID查询主题成功: {theme_by_id.name}")
        else:
            logger.error("❌ 根据ID查询主题失败")
            return False
        
        theme_by_name = await db_manager.get_theme_by_name("测试主题")
        if theme_by_name:
            logger.info(f"✅ 根据名称查询主题成功: {theme_by_name.name}")
        else:
            logger.error("❌ 根据名称查询主题失败")
            return False
        
        # 6. 创建事件
        try:
            event_id = await db_manager.create_or_update_event({
                'news_id': 'test_event_001',
                'title': '数据库测试事件',
                'summary': '这是一个用于测试数据库功能的完整事件描述。',
                'event_type': '测试',
                'impact_industries': ['测试行业'],
                'direction': '中性',
                'confidence': 0.8
            })
            if event_id:
                logger.info(f"✅ 创建事件成功: ID={event_id}")
            else:
                logger.error("❌ 创建事件失败")
        except Exception as e:
            logger.error(f"❌ 创建事件异常: {e}")
        
        # 7. 创建关联
        try:
            relation = await db_manager.create_event_theme_relation(
                event_id=event_id,
                theme_id=theme.id,
                confidence=0.85,
                confidence_level='high'
            )
            if relation:
                logger.info("✅ 创建事件-主题关联成功")
            else:
                logger.error("❌ 创建事件-主题关联失败")
        except Exception as e:
            logger.error(f"❌ 创建关联异常: {e}")
        
        # 8. 获取所有主题 - 使用超时保护
        logger.info("尝试获取所有活跃主题...")
        try:
            # 设置超时
            all_themes = await asyncio.wait_for(
                db_manager.get_all_active_themes(limit=10),
                timeout=5.0  # 5秒超时
            )
            if isinstance(all_themes, list):
                logger.info(f"✅ 获取所有活跃主题成功: {len(all_themes)}个")
            else:
                logger.error("❌ 获取所有活跃主题失败，返回的不是列表")
        except asyncio.TimeoutError:
            logger.error("❌ 获取所有活跃主题超时，可能方法有无限循环")
            return False
        except Exception as e:
            logger.error(f"❌ 获取所有活跃主题异常: {e}")
        
        # 9. 测试其他关键方法
        logger.info("测试其他关键方法...")
        
        # 测试获取事件
        try:
            event = await db_manager.get_event(event_id)
            if event and isinstance(event, dict):
                logger.info(f"✅ 获取事件成功: {event.get('title', '无标题')}")
            else:
                logger.warning("⚠️ 获取事件失败")
        except Exception as e:
            logger.warning(f"⚠️ 获取事件异常: {e}")
        
        # 测试获取关联
        try:
            event_themes = await db_manager.get_event_themes(event_id)
            if isinstance(event_themes, list):
                logger.info(f"✅ 获取事件主题关联成功: {len(event_themes)}个")
        except Exception as e:
            logger.warning(f"⚠️ 获取事件主题关联异常: {e}")
        
        # 10. 清理
        await db_manager.cleanup()
        logger.info("✅ 数据库清理完成")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ 导入MemoryDatabaseManager失败: {e}")
        logger.error(f"当前Python路径: {sys.path}")
        return False
    except Exception as e:
        logger.error(f"❌ MemoryDatabaseManager测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_pure_data_fetcher_fixed():
    """测试PureDataFetcher - 修复版"""
    logger.info("\n🧪 测试 PureDataFetcher (修复版)")
    
    try:
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        
        # 创建数据库管理器
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 创建测试数据
        theme = await db_manager.create_theme(
            name="数据获取测试主题",
            description="用于测试数据获取器",
            keywords=["数据", "测试"],
            discovery_source="test"
        )
        
        # 创建数据获取器
        fetcher = PureDataFetcher(db_manager)
        logger.info("✅ 创建PureDataFetcher实例成功")
        
        # 测试获取所有主题
        try:
            # 设置超时
            themes = await asyncio.wait_for(
                fetcher.get_all_active_themes(limit=5),
                timeout=5.0
            )
            if isinstance(themes, list):
                logger.info(f"✅ 获取活跃主题成功: {len(themes)}个")
            else:
                logger.error("❌ 获取活跃主题失败")
                return False
        except asyncio.TimeoutError:
            logger.error("❌ 获取活跃主题超时")
            return False
        except Exception as e:
            logger.error(f"❌ 获取活跃主题异常: {e}")
            return False
        
        # 清理
        await db_manager.cleanup()
        return True
        
    except ImportError as e:
        logger.error(f"❌ 导入PureDataFetcher失败: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ PureDataFetcher测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_database_client_fixed():
    """测试DatabaseClient - 修复版"""
    logger.info("\n🧪 测试 DatabaseClient (修复版)")
    
    try:
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        
        # 创建数据库管理器
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 创建测试数据
        theme = await db_manager.create_theme(
            name="客户端测试主题",
            description="用于测试数据库客户端",
            keywords=["客户端", "测试"],
            discovery_source="test"
        )
        
        # 创建数据库客户端
        client = DatabaseClient(db_manager)
        logger.info("✅ 创建DatabaseClient实例成功")
        
        # 测试获取增强主题
        try:
            # 设置超时
            enriched = await asyncio.wait_for(
                client.get_enriched_themes(limit=3),
                timeout=5.0
            )
            if isinstance(enriched, list):
                logger.info(f"✅ 获取增强主题成功: {len(enriched)}个")
            else:
                logger.error("❌ 获取增强主题失败")
                return False
        except asyncio.TimeoutError:
            logger.error("❌ 获取增强主题超时")
            return False
        except Exception as e:
            logger.error(f"❌ 获取增强主题异常: {e}")
            return False
        
        # 清理
        await db_manager.cleanup()
        return True
        
    except ImportError as e:
        logger.error(f"❌ 导入DatabaseClient失败: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ DatabaseClient测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    print("🚀 启动数据库模块功能测试 (修复版)")
    print("="*60)
    
    results = {
        'test_time': datetime.now().isoformat(),
        'modules': {},
        'total_tests': 3,
        'passed': 0,
        'failed': 0,
        'errors': []
    }
    
    # 测试MemoryDatabaseManager
    print("\n1. 测试MemoryDatabaseManager...")
    try:
        db_manager_passed = await asyncio.wait_for(
            test_memory_database_manager_fixed(),
            timeout=30.0
        )
        if db_manager_passed:
            results['modules']['MemoryDatabaseManager'] = 'PASS'
            results['passed'] += 1
            print("✅ MemoryDatabaseManager测试通过")
        else:
            results['modules']['MemoryDatabaseManager'] = 'FAIL'
            results['failed'] += 1
            results['errors'].append('MemoryDatabaseManager测试失败')
            print("❌ MemoryDatabaseManager测试失败")
    except asyncio.TimeoutError:
        results['modules']['MemoryDatabaseManager'] = 'TIMEOUT'
        results['failed'] += 1
        results['errors'].append('MemoryDatabaseManager测试超时')
        print("⏰ MemoryDatabaseManager测试超时")
    except Exception as e:
        results['modules']['MemoryDatabaseManager'] = 'ERROR'
        results['failed'] += 1
        results['errors'].append(f'MemoryDatabaseManager测试异常: {e}')
        print(f"💥 MemoryDatabaseManager测试异常: {e}")
    
    # 测试PureDataFetcher
    print("\n2. 测试PureDataFetcher...")
    try:
        fetcher_passed = await asyncio.wait_for(
            test_pure_data_fetcher_fixed(),
            timeout=15.0
        )
        if fetcher_passed:
            results['modules']['PureDataFetcher'] = 'PASS'
            results['passed'] += 1
            print("✅ PureDataFetcher测试通过")
        else:
            results['modules']['PureDataFetcher'] = 'FAIL'
            results['failed'] += 1
            results['errors'].append('PureDataFetcher测试失败')
            print("❌ PureDataFetcher测试失败")
    except asyncio.TimeoutError:
        results['modules']['PureDataFetcher'] = 'TIMEOUT'
        results['failed'] += 1
        results['errors'].append('PureDataFetcher测试超时')
        print("⏰ PureDataFetcher测试超时")
    except Exception as e:
        results['modules']['PureDataFetcher'] = 'ERROR'
        results['failed'] += 1
        results['errors'].append(f'PureDataFetcher测试异常: {e}')
        print(f"💥 PureDataFetcher测试异常: {e}")
    
    # 测试DatabaseClient
    print("\n3. 测试DatabaseClient...")
    try:
        client_passed = await asyncio.wait_for(
            test_database_client_fixed(),
            timeout=15.0
        )
        if client_passed:
            results['modules']['DatabaseClient'] = 'PASS'
            results['passed'] += 1
            print("✅ DatabaseClient测试通过")
        else:
            results['modules']['DatabaseClient'] = 'FAIL'
            results['failed'] += 1
            results['errors'].append('DatabaseClient测试失败')
            print("❌ DatabaseClient测试失败")
    except asyncio.TimeoutError:
        results['modules']['DatabaseClient'] = 'TIMEOUT'
        results['failed'] += 1
        results['errors'].append('DatabaseClient测试超时')
        print("⏰ DatabaseClient测试超时")
    except Exception as e:
        results['modules']['DatabaseClient'] = 'ERROR'
        results['failed'] += 1
        results['errors'].append(f'DatabaseClient测试异常: {e}')
        print(f"💥 DatabaseClient测试异常: {e}")
    
    # 保存结果
    save_test_results(results, "database_modules_fixed")
    
    # 打印总结
    print("\n" + "="*60)
    print("📊 数据库模块测试完成")
    print(f"测试模块: {results['total_tests']}")
    print(f"通过: {results['passed']}")
    print(f"失败: {results['failed']}")
    
    if results['total_tests'] > 0:
        success_rate = results['passed'] / results['total_tests']
        print(f"成功率: {success_rate:.1%}")
    
    if results['failed'] == 0:
        print("🎉 所有数据库模块测试通过！")
        print("可以进入第二阶段：主题检索器测试")
        return 0
    else:
        print("❌ 数据库模块存在未通过的测试")
        print("请先修复数据库模块问题")
        return 1

def save_test_results(results, test_type="database"):
    """保存测试结果"""
    results_dir = project_root / "evaluate_service" / "results"
    results_dir.mkdir(exist_ok=True)
    
    # 保存JSON格式
    json_file = results_dir / f"{test_type}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 保存文本报告
    report_file = results_dir / f"{test_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"{test_type.upper()}模块测试报告\n")
        f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*60 + "\n\n")
        
        total = results.get('total_tests', 0)
        passed = results.get('passed', 0)
        failed = results.get('failed', 0)
        
        f.write("📊 测试摘要\n")
        f.write(f"总测试模块: {total}\n")
        f.write(f"通过模块: {passed}\n")
        f.write(f"失败模块: {failed}\n")
        
        if total > 0:
            success_rate = passed / total
            f.write(f"成功率: {success_rate:.1%}\n\n")
        
        f.write("📋 模块详情:\n")
        for module, status in results.get('modules', {}).items():
            f.write(f"  {module}: {status}\n")
        
        if results.get('errors'):
            f.write("\n❌ 错误详情:\n")
            for error in results['errors']:
                f.write(f"  - {error}\n")
    
    print(f"✅ 测试结果已保存到: {json_file}")
    print(f"📄 测试报告已保存到: {report_file}")

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        exit_code = 130
    except Exception as e:
        print(f"测试程序异常: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    
    sys.exit(exit_code)
