#!/usr/bin/env python3
"""
强制处理所有事件 - 确保处理所有未处理的事件
"""
import asyncio
import logging
import time
import sys
import os
from datetime import datetime
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class ForceProcessor:
    """强制处理器 - 确保处理所有事件"""
    
    def __init__(self):
        try:
            from config import settings
            from database import ThemeDatabase
            
            self.db = ThemeDatabase(settings.DATABASE_URL)
            self.running = True
            
            # 扩展关键词映射
            self.theme_keywords = {
                # 科技类
                "人工智能": ["人工智能", "ai", "大模型", "gpt", "机器学习", "深度学习"],
                "半导体芯片": ["芯片", "半导体", "集成电路", "中芯国际", "光刻机"],
                "数字经济": ["数字经济", "数据要素", "大数据", "云计算", "区块链"],
                "5G通信": ["5g", "通信", "华为", "中兴", "基站"],
                "物联网": ["物联网", "iot", "智能家居", "智能设备"],
                
                # 新能源
                "新能源汽车": ["新能源汽车", "电动车", "特斯拉", "蔚来", "电池", "充电桩"],
                "新能源发电": ["光伏", "风电", "储能", "太阳能", "可再生能源"],
                "锂电池": ["锂电池", "锂电", "电池材料", "正极", "负极"],
                
                # 消费类
                "消费电子": ["消费电子", "苹果", "华为", "小米", "手机", "智能穿戴"],
                "大消费": ["消费", "零售", "电商", "食品饮料", "白酒", "家电"],
                "医药医疗": ["医药", "医疗", "生物医药", "创新药", "疫苗", "医疗器械"],
                "旅游酒店": ["旅游", "酒店", "航空", "机场", "文旅"],
                
                # 金融地产
                "金融": ["金融", "银行", "保险", "证券", "券商", "支付"],
                "房地产": ["房地产", "地产", "房企", "楼市", "房价"],
                "基建": ["基建", "基础设施建设", "铁路", "公路", "桥梁"],
                
                # 其他
                "军工国防": ["军工", "国防", "军事", "航空航天", "卫星"],
                "物流运输": ["物流", "快递", "运输", "供应链", "仓储"],
                "传媒娱乐": ["传媒", "娱乐", "游戏", "影视", "短视频"],
                "农业": ["农业", "种业", "粮食", "乡村振兴"],
                "环保": ["环保", "污水处理", "固废处理", "碳中和"],
                "教育": ["教育", "培训", "在线教育", "职业教育"],
            }
            
            self.stats = {
                "start_time": datetime.now(),
                "total_processed": 0,
                "total_themes_created": 0,
                "total_mappings_created": 0
            }
            
            logger.info("强制处理器初始化完成")
            
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def initialize(self):
        """初始化"""
        print("="*70)
        print("🚀 AI题材引擎 - 强制处理所有事件")
        print("="*70)
        
        try:
            # 初始化数据库
            if not await self.db.initialize():
                print("❌ 数据库初始化失败")
                return False
            
            if not await self.db.health_check():
                print("❌ 数据库连接失败")
                return False
            
            print("✅ 数据库连接成功")
            
            # 显示当前状态
            await self.show_current_status()
            
            return True
            
        except Exception as e:
            print(f"❌ 初始化异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def show_current_status(self):
        """显示当前状态"""
        try:
            conn = await self.db.acquire_connection()
            
            # 基本统计
            total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
            total_themes = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
            total_mappings = await conn.fetchval("SELECT COUNT(*) FROM event_theme_map")
            processed_events = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
            
            print("\n📊 当前系统状态:")
            print(f"   新闻事件总数: {total_events}")
            print(f"   投资主题总数: {total_themes}")
            print(f"   事件-主题映射: {total_mappings}")
            
            if total_events > 0:
                progress = (processed_events / total_events * 100)
                print(f"   已处理事件: {processed_events}/{total_events} ({progress:.1f}%)")
                
                unprocessed = total_events - processed_events
                if unprocessed > 0:
                    print(f"   ⚠️  未处理事件: {unprocessed} 个")
            
            await self.db.release_connection(conn)
            
        except Exception as e:
            print(f"⚠️  无法获取状态: {e}")
    
    async def get_all_unprocessed_events(self):
        """获取所有未处理的事件"""
        try:
            conn = await self.db.acquire_connection()
            
            events = await conn.fetch('''
                SELECT 
                    ne.id,
                    ne.news_id,
                    COALESCE(ne.title, nr.title) as title,
                    ne.summary,
                    ne.event_type,
                    ne.created_at,
                    nr.content
                FROM news_event ne
                LEFT JOIN news_raw nr ON ne.news_id = nr.id
                WHERE ne.id NOT IN (SELECT DISTINCT event_id FROM event_theme_map)
                ORDER BY ne.created_at ASC
            ''')
            
            await self.db.release_connection(conn)
            
            # 转换为字典列表
            result = []
            for event in events:
                result.append(dict(event))
            
            return result
            
        except Exception as e:
            print(f"❌ 获取未处理事件失败: {e}")
            return []
    
    def analyze_event(self, event: dict) -> list:
        """智能分析事件主题"""
        title = event.get('title', '')
        summary = event.get('summary', '')
        event_type = event.get('event_type', '')
        content = (title + " " + summary).lower()
        
        if not content.strip():
            return []
        
        themes_found = []
        
        # 1. 关键词匹配
        for theme_name, keywords in self.theme_keywords.items():
            for keyword in keywords:
                if keyword.lower() in content:
                    themes_found.append(theme_name)
                    break
        
        # 2. 事件类型推断
        if not themes_found:
            event_type_lower = event_type.lower()
            if '政策' in event_type_lower or '利好' in event_type_lower:
                themes_found.extend(['数字经济', '基建', '新能源发电'])
            elif '产品' in event_type_lower or '发布' in event_type_lower:
                themes_found.extend(['消费电子', '新能源汽车'])
            elif '技术' in event_type_lower or '突破' in event_type_lower:
                themes_found.extend(['人工智能', '半导体芯片'])
            elif '合作' in event_type_lower or '签约' in event_type_lower:
                themes_found.extend(['金融', '物流运输'])
            elif '风险' in event_type_lower or '警示' in event_type_lower:
                themes_found.extend(['金融', '房地产'])
        
        # 3. 标题关键词补充
        title_lower = title.lower()
        title_keywords = {
            '电子': '消费电子',
            '电器': '消费电子',
            '汽车': '新能源汽车',
            '电池': '锂电池',
            '医药': '医药医疗',
            '医疗': '医药医疗',
            '银行': '金融',
            '证券': '金融',
            '保险': '金融',
            '地产': '房地产',
            '房子': '房地产',
            '光伏': '新能源发电',
            '风电': '新能源发电',
            '游戏': '传媒娱乐',
            '影视': '传媒娱乐',
            '旅游': '旅游酒店',
            '酒店': '旅游酒店',
            '物流': '物流运输',
            '快递': '物流运输',
            '农业': '农业',
            '粮食': '农业',
            '环保': '环保',
            '污水': '环保',
        }
        
        for keyword, theme in title_keywords.items():
            if keyword in title_lower and theme not in themes_found:
                themes_found.append(theme)
        
        return list(set(themes_found))
    
    async def get_or_create_theme(self, theme_name: str, confidence: float = 0.7) -> int:
        """获取或创建主题"""
        try:
            # 查询主题
            conn = await self.db.acquire_connection()
            
            theme = await conn.fetchrow(
                "SELECT id FROM theme_master WHERE name = $1",
                theme_name
            )
            
            if theme:
                theme_id = theme['id']
                await self.db.release_connection(conn)
                return theme_id
            
            # 创建新主题
            result = await conn.fetchrow('''
                INSERT INTO theme_master 
                (name, keywords, status, discovery_source, discovery_confidence, heat_score)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            ''',
                theme_name,
                [theme_name],
                'active',
                'force_processor',
                confidence,
                50  # 初始热度
            )
            
            theme_id = result['id']
            await self.db.release_connection(conn)
            
            if theme_id:
                print(f"🎯 创建新主题: {theme_name} (ID: {theme_id})")
                self.stats["total_themes_created"] += 1
            
            return theme_id
            
        except Exception as e:
            print(f"❌ 主题处理失败: {e}")
            return 0
    
    async def process_all_unprocessed(self):
        """处理所有未处理的事件"""
        print("\n" + "="*70)
        print("🔍 开始处理所有未处理事件")
        print("="*70)
        
        # 获取所有未处理事件
        unprocessed_events = await self.get_all_unprocessed_events()
        
        if not unprocessed_events:
            print("✅ 所有事件都已处理完成！")
            return
        
        print(f"📥 发现 {len(unprocessed_events)} 个未处理事件")
        print("开始处理...\n")
        
        start_time = time.time()
        processed_count = 0
        total_themes_found = 0
        
        for i, event in enumerate(unprocessed_events, 1):
            event_id = event.get('id')
            if not event_id:
                continue
            
            try:
                title = event.get('title', '无标题')
                if len(title) > 50:
                    title_display = title[:47] + "..."
                else:
                    title_display = title
                
                print(f"[{i}/{len(unprocessed_events)}] 处理事件 #{event_id}: {title_display}")
                
                # 分析主题
                themes = self.analyze_event(event)
                
                if themes:
                    print(f"   发现主题: {', '.join(themes)}")
                    
                    # 处理每个主题
                    for theme_name in themes:
                        theme_id = await self.get_or_create_theme(theme_name)
                        if theme_id:
                            # 计算置信度
                            confidence = 0.8  # 基础置信度
                            
                            # 保存映射
                            success = await self.db.save_event_theme_mapping(
                                event_id, theme_id, confidence
                            )
                            if success:
                                total_themes_found += 1
                                self.stats["total_mappings_created"] += 1
                    
                    print(f"   ✅ 成功关联 {len(themes)} 个主题")
                else:
                    print(f"   ⏳ 未发现相关主题")
                
                processed_count += 1
                self.stats["total_processed"] += 1
                
                # 每处理5个事件显示一次进度
                if i % 5 == 0 or i == len(unprocessed_events):
                    elapsed = time.time() - start_time
                    speed = i / elapsed if elapsed > 0 else 0
                    remaining = len(unprocessed_events) - i
                    eta = remaining / speed if speed > 0 else 0
                    
                    print(f"\n📊 进度: {i}/{len(unprocessed_events)} ({i/len(unprocessed_events)*100:.1f}%)")
                    print(f"   速度: {speed:.1f} 事件/秒")
                    print(f"   预计剩余时间: {eta:.0f} 秒\n")
                
            except Exception as e:
                print(f"   ❌ 处理事件 #{event_id} 失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 处理完成
        elapsed = time.time() - start_time
        
        print("\n" + "="*70)
        print("🎉 批量处理完成！")
        print("="*70)
        
        print(f"\n📊 处理结果:")
        print(f"   处理事件: {processed_count}/{len(unprocessed_events)}")
        print(f"   发现主题: {total_themes_found} 个")
        print(f"   创建映射: {self.stats['total_mappings_created']} 个")
        print(f"   总耗时: {elapsed:.2f} 秒")
        print(f"   平均速度: {processed_count/elapsed:.2f} 事件/秒")
        
        # 更新最终状态
        await self.show_current_status()
    
    async def run_continuous(self, interval=30):
        """持续运行处理器"""
        if not await self.initialize():
            return
        
        print(f"\n⏰ 启动持续处理模式")
        print("按 Ctrl+C 停止\n")
        
        iteration = 0
        
        try:
            # 首先处理所有积压的事件
            await self.process_all_unprocessed()
            
            print(f"\n🔄 启动持续监控，每 {interval} 秒检查一次新事件")
            
            while self.running:
                iteration += 1
                
                print(f"\n{'='*50}")
                print(f"监控周期 #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
                
                # 检查是否有新事件
                unprocessed_events = await self.get_all_unprocessed_events()
                
                if unprocessed_events:
                    print(f"发现 {len(unprocessed_events)} 个新事件，开始处理...")
                    await self.process_all_unprocessed()
                else:
                    print("✅ 所有事件都已处理完成")
                
                # 显示统计
                uptime = datetime.now() - self.stats["start_time"]
                print(f"\n📈 累计统计:")
                print(f"  运行时间: {str(uptime).split('.')[0]}")
                print(f"  处理事件: {self.stats['total_processed']}")
                print(f"  创建主题: {self.stats['total_themes_created']}")
                print(f"  创建映射: {self.stats['total_mappings_created']}")
                
                # 等待下一周期
                if iteration % 3 == 0:
                    print(f"\n⏳ 等待 {interval} 秒后继续检查...")
                
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断")
        except Exception as e:
            print(f"\n❌ 运行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 最终统计
            print(f"\n{'='*70}")
            print("🎯 最终统计:")
            print(f"  总运行时间: {datetime.now() - self.stats['start_time']}")
            print(f"  总处理事件: {self.stats['total_processed']}")
            print(f"  总创建主题: {self.stats['total_themes_created']}")
            print(f"  总创建映射: {self.stats['total_mappings_created']}")
            
            # 关闭数据库
            try:
                await self.db.close()
                print("\n🔌 数据库连接已关闭")
            except:
                pass

def signal_handler(signum, frame):
    print(f"\n🛑 收到停止信号")
    processor.running = False

async def main():
    """主函数"""
    try:
        processor = ForceProcessor()
        
        # 设置信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 运行处理器
        await processor.run_continuous(interval=30)
        
    except Exception as e:
        print(f"\n❌ 处理器启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 AI题材引擎 - 启动强制处理器")
    print("="*70)
    asyncio.run(main())
