#!/usr/bin/env python3
"""
实时数据处理服务 - 生产就绪
"""
import asyncio
import logging
import time
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data_processor.log')
    ]
)
logger = logging.getLogger(__name__)

class RealTimeDataProcessor:
    """实时数据处理服务"""
    
    def __init__(self):
        """初始化"""
        # 添加路径
        sys.path.insert(0, '.')
        
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        self.config = settings
        self.db = ThemeDatabase(settings.DATABASE_URL)
        
        # 处理状态
        self.processed_events = set()
        self.theme_cache = {}  # 主题名称 -> ID 缓存
        self.stats = {
            "start_time": datetime.now(),
            "total_events_processed": 0,
            "total_themes_created": 0,
            "total_mappings_created": 0,
            "last_processed_time": None,
            "avg_processing_time": 0.0
        }
        
        # 主题关键词映射
        self.theme_keywords = {
            "人工智能": ["ai", "人工智能", "大模型", "gpt", "llm", "机器学习", "深度学习", "神经网络"],
            "新能源汽车": ["新能源", "电动车", "特斯拉", "蔚来", "理想", "小鹏", "电池", "充电", "锂电", "电动车"],
            "半导体芯片": ["芯片", "半导体", "集成电路", "中芯国际", "光刻机", "算力", "处理器", "存储器"],
            "医药医疗": ["医药", "医疗", "生物", "疫苗", "创新药", "医院", "健康", "医疗器械", "基因"],
            "消费电子": ["苹果", "华为", "小米", "手机", "消费电子", "智能家居", "穿戴", "耳机", "平板"],
            "数字经济": ["数据", "数字", "云计算", "大数据", "区块链", "数字货币", "web3", "元宇宙"],
            "军工国防": ["军工", "国防", "军事", "航空航天", "卫星", "航母", "导弹", "无人机"],
            "新能源发电": ["光伏", "风电", "储能", "绿色能源", "碳中和", "太阳能", "可再生能源"],
            "传媒娱乐": ["游戏", "传媒", "影视", "娱乐", "短视频", "直播", "动漫", "版权"],
            "金融": ["银行", "保险", "证券", "金融", "支付", "理财", "投资", "券商"],
        }
        
        logger.info("实时数据处理服务初始化完成")
    
    async def initialize(self) -> bool:
        """初始化服务"""
        print("="*70)
        print("🚀 AI题材引擎 - 实时数据处理服务")
        print("="*70)
        
        try:
            # 初始化数据库
            print("🔌 连接数据库...")
            if not await self.db.initialize():
                print("❌ 数据库初始化失败")
                return False
            
            if not await self.db.health_check():
                print("❌ 数据库健康检查失败")
                return False
            
            print("✅ 数据库连接正常")
            
            # 显示当前数据
            stats = await self.db.get_table_stats()
            print("\n📊 数据概览:")
            for table, count in stats.items():
                print(f"  {table}: {count}")
            
            # 加载主题缓存
            await self._load_theme_cache()
            
            print(f"\n📚 主题缓存: {len(self.theme_cache)} 个主题")
            
            return True
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _load_theme_cache(self):
        """加载主题缓存"""
        try:
            themes = await self.db.get_themes_by_status("active", limit=200)
            for theme in themes:
                name = theme.get('name')
                if name:
                    self.theme_cache[name] = theme.get('id')
            
            logger.info(f"加载 {len(self.theme_cache)} 个主题到缓存")
        except Exception as e:
            logger.error(f"加载主题缓存失败: {e}")
    
    async def _analyze_event(self, event: Dict[str, Any]) -> List[tuple]:
        """分析事件，返回(主题名称, 置信度)列表"""
        title = (event.get("title") or event.get("news_title", "")).lower()
        summary = event.get("summary", "").lower()
        content = title + " " + summary
        
        found_themes = []
        
        # 基于关键词匹配
        for theme_name, keywords in self.theme_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    # 计算置信度
                    confidence = 0.7  # 基础置信度
                    
                    # 标题中出现关键词，置信度更高
                    if keyword in title:
                        confidence = 0.9
                    # 事件类型匹配
                    event_type = event.get("event_type", "").lower()
                    if "产品" in event_type or "发布" in event_type:
                        confidence += 0.1
                    if "合作" in event_type or "签约" in event_type:
                        confidence += 0.05
                    
                    found_themes.append((theme_name, min(confidence, 1.0)))
                    break  # 每个主题只匹配一次
        
        # 去重并保留最高置信度
        theme_confidences = {}
        for theme_name, confidence in found_themes:
            if theme_name not in theme_confidences or confidence > theme_confidences[theme_name]:
                theme_confidences[theme_name] = confidence
        
        return [(name, conf) for name, conf in theme_confidences.items()]
    
    async def _get_or_create_theme(self, theme_name: str, confidence: float) -> int:
        """获取或创建主题"""
        # 检查缓存
        if theme_name in self.theme_cache:
            return self.theme_cache[theme_name]
        
        # 检查数据库
        try:
            conn = await self.db.acquire_connection()
            try:
                # 查询主题
                result = await conn.fetchrow(
                    "SELECT id FROM theme_master WHERE name = $1",
                    theme_name
                )
                
                if result:
                    theme_id = result['id']
                    self.theme_cache[theme_name] = theme_id
                    return theme_id
                
                # 创建新主题
                result = await conn.fetchrow("""
                    INSERT INTO theme_master 
                    (name, keywords, status, discovery_source, discovery_confidence, heat_score)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                """,
                    theme_name,
                    [theme_name],
                    "active",
                    "ai_discovery",
                    confidence,
                    50  # 初始热度
                )
                
                theme_id = result['id']
                self.theme_cache[theme_name] = theme_id
                
                logger.info(f"创建新主题: {theme_name} (ID: {theme_id})")
                self.stats["total_themes_created"] += 1
                
                return theme_id
                
            finally:
                await self.db.release_connection(conn)
                
        except Exception as e:
            logger.error(f"获取/创建主题失败: {theme_name}, {e}")
            return 0
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个事件"""
        event_id = event.get("id")
        if not event_id:
            return {"success": False, "error": "事件ID缺失"}
        
        if event_id in self.processed_events:
            return {"success": False, "error": "事件已处理"}
        
        start_time = time.time()
        title = event.get("title") or event.get("news_title", "无标题")
        
        try:
            logger.info(f"处理事件 #{event_id}: {title[:50]}...")
            
            # 分析主题
            theme_results = await self._analyze_event(event)
            
            if not theme_results:
                logger.info(f"事件 #{event_id} 未发现相关主题")
                self.processed_events.add(event_id)
                return {"success": True, "themes_found": 0}
            
            # 处理每个主题
            mappings_created = 0
            for theme_name, confidence in theme_results:
                # 获取或创建主题
                theme_id = await self._get_or_create_theme(theme_name, confidence)
                
                if theme_id:
                    # 保存映射
                    success = await self.db.save_event_theme_mapping(
                        event_id, theme_id, confidence
                    )
                    
                    if success:
                        mappings_created += 1
                        logger.debug(f"  映射: 事件#{event_id} -> {theme_name} ({confidence:.2f})")
            
            # 更新统计
            self.processed_events.add(event_id)
            self.stats["total_events_processed"] += 1
            self.stats["total_mappings_created"] += mappings_created
            
            processing_time = time.time() - start_time
            
            # 更新平均处理时间
            if self.stats["avg_processing_time"] == 0:
                self.stats["avg_processing_time"] = processing_time
            else:
                self.stats["avg_processing_time"] = (
                    self.stats["avg_processing_time"] * 0.7 + processing_time * 0.3
                )
            
            self.stats["last_processed_time"] = datetime.now()
            
            logger.info(
                f"事件 #{event_id} 处理完成: "
                f"发现 {len(theme_results)} 个主题, "
                f"创建 {mappings_created} 个映射, "
                f"耗时 {processing_time:.3f}s"
            )
            
            return {
                "success": True,
                "event_id": event_id,
                "themes_found": len(theme_results),
                "mappings_created": mappings_created,
                "processing_time": processing_time
            }
            
        except Exception as e:
            logger.error(f"处理事件 #{event_id} 失败: {e}")
            return {"success": False, "error": str(e), "event_id": event_id}
    
    async def process_new_events_batch(self, batch_size: int = 10) -> Dict[str, Any]:
        """处理新事件批次"""
        logger.info(f"开始处理新事件批次，大小: {batch_size}")
        
        start_time = time.time()
        
        try:
            # 获取新事件
            events = await self.db.get_recent_events(limit=batch_size * 2)
            
            if not events:
                return {
                    "status": "no_events",
                    "processed": 0,
                    "duration": 0
                }
            
            # 过滤已处理的事件
            new_events = [
                event for event in events 
                if event.get("id") not in self.processed_events
            ][:batch_size]
            
            if not new_events:
                return {
                    "status": "no_new_events",
                    "processed": 0,
                    "duration": time.time() - start_time
                }
            
            logger.info(f"发现 {len(new_events)} 个新事件需要处理")
            
            # 处理每个事件
            results = []
            for event in new_events:
                result = await self.process_single_event(event)
                results.append(result)
            
            # 统计
            successful = sum(1 for r in results if r.get("success"))
            themes_found = sum(r.get("themes_found", 0) for r in results)
            
            duration = time.time() - start_time
            
            logger.info(
                f"批次处理完成: "
                f"{successful}/{len(new_events)} 成功, "
                f"发现 {themes_found} 个主题, "
                f"耗时 {duration:.2f}s"
            )
            
            return {
                "status": "success",
                "processed": len(new_events),
                "successful": successful,
                "themes_found": themes_found,
                "duration": duration,
                "total_events": self.stats["total_events_processed"],
                "total_themes": self.stats["total_themes_created"],
                "total_mappings": self.stats["total_mappings_created"]
            }
            
        except Exception as e:
            logger.error(f"批次处理失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "duration": time.time() - start_time
            }
    
    async def run_continuous(self, interval_seconds: int = 30):
        """持续运行处理"""
        logger.info(f"启动持续处理，间隔: {interval_seconds} 秒")
        print(f"\n⏰ 处理间隔: {interval_seconds} 秒")
        print("按 Ctrl+C 停止运行")
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                
                print(f"\n{'='*70}")
                print(f"处理周期 #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*70}")
                
                # 处理批次
                result = await self.process_new_events_batch(batch_size=10)
                
                # 显示结果
                if result["status"] == "success":
                    print(f"📊 本周期结果:")
                    print(f"  处理事件: {result['processed']} 个")
                    print(f"  成功处理: {result['successful']} 个")
                    print(f"  发现主题: {result['themes_found']} 个")
                    print(f"  处理时间: {result['duration']:.2f} 秒")
                elif result["status"] == "no_events":
                    print("📭 没有新事件可处理")
                elif result["status"] == "no_new_events":
                    print("📭 所有事件都已处理过")
                
                # 显示累计统计
                uptime = datetime.now() - self.stats["start_time"]
                print(f"\n📈 累计统计:")
                print(f"  运行时间: {str(uptime).split('.')[0]}")
                print(f"  处理事件: {self.stats['total_events_processed']}")
                print(f"  创建主题: {self.stats['total_themes_created']}")
                print(f"  创建映射: {self.stats['total_mappings_created']}")
                print(f"  平均耗时: {self.stats['avg_processing_time']:.3f} 秒/事件")
                
                # 等待下一个周期
                if iteration % 10 == 0:  # 每10次显示等待信息
                    print(f"\n⏳ 等待 {interval_seconds} 秒后继续...")
                
                await asyncio.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断操作")
        except Exception as e:
            print(f"\n❌ 运行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 最终统计
            print(f"\n{'='*70}")
            print("📊 最终运行统计:")
            print(f"{'='*70}")
            
            uptime = datetime.now() - self.stats["start_time"]
            print(f"  总运行时间: {str(uptime).split('.')[0]}")
            print(f"  总处理事件: {self.stats['total_events_processed']}")
            print(f"  总创建主题: {self.stats['total_themes_created']}")
            print(f"  总创建映射: {self.stats['total_mappings_created']}")
            print(f"  平均处理时间: {self.stats['avg_processing_time']:.3f} 秒/事件")
            
            # 关闭数据库
            await self.db.close()
            print("\n🔌 数据库连接已关闭")
            print("\n🎯 数据处理服务已停止")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI题材引擎 - 实时数据处理')
    parser.add_argument('--interval', type=int, default=30,
                       help='处理间隔（秒），默认30秒')
    parser.add_argument('--once', action='store_true',
                       help='只运行一次处理')
    parser.add_argument('--batch', type=int, default=10,
                       help='每批处理数量，默认10')
    
    args = parser.parse_args()
    
    # 创建处理器
    processor = RealTimeDataProcessor()
    
    # 初始化
    if not await processor.initialize():
        print("❌ 初始化失败，服务无法启动")
        return
    
    if args.once:
        # 只运行一次
        result = await processor.process_new_events_batch(batch_size=args.batch)
        print(f"\n单次处理结果: {result}")
    else:
        # 持续运行
        await processor.run_continuous(interval_seconds=args.interval)

if __name__ == "__main__":
    print("🚀 AI题材引擎 - 启动实时数据处理")
    print("-"*70)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()
