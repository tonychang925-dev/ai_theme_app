#!/usr/bin/env python3
"""
evaluate_service/scripts/convert_with_ai.py
最简单的AI数据转换脚本
"""

import json
import os
import asyncio
import sys
import hashlib
from datetime import datetime
from typing import List, Dict, Any
import aiohttp

# ============================================================
# 🔥 最简单的路径设置
# ============================================================

# 1. 获取当前脚本的绝对路径
current_file = os.path.abspath(__file__)
print(f"📄 当前文件: {current_file}")

# 2. 找到项目根目录 (ai_theme_app)
# 方法：当前脚本在 evaluate_service/scripts/，往上找两次
script_dir = os.path.dirname(current_file)  # evaluate_service/scripts/
evaluate_dir = os.path.dirname(script_dir)  # evaluate_service/
project_root = os.path.dirname(evaluate_dir)  # ai_theme_app/

print(f"📁 项目根目录: {project_root}")

# 3. 只添加这一个路径
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"✅ 添加路径: {project_root}")

# ============================================================
# 现在导入模块
# ============================================================

print("\n🔍 导入模块...")
try:
    # 现在应该能找到了
    from model_service.llm_parser.deepseek_parser import DeepSeekParser
    print("✅ 成功导入DeepSeekParser")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    
    # 如果还是失败，显示可能的路径
    print("\n🔎 查找模块...")
    
    # 检查模块是否存在
    module_path = os.path.join(project_root, "model_service", "llm_parser", "deepseek_parser.py")
    print(f"   检查路径: {module_path}")
    print(f"   文件存在: {os.path.exists(module_path)}")
    
    if os.path.exists(module_path):
        print("   文件存在但无法导入，可能是语法错误")
        # 尝试直接读取文件
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                first_lines = f.readlines()[:5]
            print(f"   文件内容前几行: {first_lines}")
        except:
            print("   无法读取文件")
    else:
        print("   文件不存在")
    
    sys.exit(1)

# ============================================================
# 转换器类
# ============================================================

class NewsConverter:
    """新闻转换器"""
    
    def __init__(self):
        self.llm_parser = None
        self.converted_count = 0
        self.failed_count = 0
    
    async def initialize(self):
        """初始化AI解析器"""
        print("🔧 初始化AI解析器...")
        
        # 检查API密钥
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("请先设置环境变量: export DEEPSEEK_API_KEY='your-api-key'")
        
        try:
            self.llm_parser = DeepSeekParser()
            print("✅ AI解析器创建成功")
        except Exception as e:
            raise ValueError(f"创建AI解析器失败: {e}")
    
    def generate_event_id(self, news_id: str) -> str:
        """生成事件ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_str = hashlib.md5(news_id.encode()).hexdigest()[:6]
        return f"event_{timestamp}_{hash_str}"
    
    async def convert_single_news(self, news: Dict[str, Any], index: int) -> Dict[str, Any]:
        """转换单条新闻"""
        news_id = news.get("news_id", f"news_{index}")
        title = news.get("title", "").strip()
        content = news.get("content", "").strip()
        
        if not title or not content:
            print(f"  [{index+1}] ❌ 跳过，标题或内容为空")
            self.failed_count += 1
            return None
        
        print(f"  [{index+1}] 处理: {title[:40]}...")
        
        try:
            # 调用AI解析
            ai_result = await self.llm_parser.parse_news(title, content[:2000])
            
            if not ai_result:
                print(f"    ❌ AI解析返回空结果")
                self.failed_count += 1
                return None
            
            # 从AI结果提取信息
            ai_analysis = ai_result.get("ai_analysis", {})
            directive = ai_result.get("theme_discovery_directive", {})
            
            # 构建事件数据
            event_data = {
                "event_id": self.generate_event_id(news_id),
                "event_type": "major" if directive.get("action") == "MAJOR" else "normal",
                "title": title,
                "content": content[:2000],
                "source": news.get("source", "未知"),
                "publish_time": news.get("publish_time", datetime.now().isoformat()),
                "ai_analysis": {
                    "core_concept": ai_analysis.get("core_concept", title[:30]),
                    "industry_keywords": ai_analysis.get("industry_keywords", ["科技", "市场"]),
                    "summary": ai_analysis.get("summary", f"关于{title}的报道"),
                    "sentiment": ai_analysis.get("sentiment", "neutral"),
                    "concept_confidence": ai_analysis.get("concept_confidence", 0.8),
                    "impact_level": ai_analysis.get("impact_level", "medium")
                },
                "raw_data": {
                    "original_id": news_id,
                    "url": news.get("url", ""),
                    "category": news.get("category", "")
                },
                "metadata": {
                    "test_flag": True,
                    "converted_at": datetime.now().isoformat()
                }
            }
            
            self.converted_count += 1
            print(f"    ✅ 转换成功")
            return event_data
            
        except Exception as e:
            print(f"    ❌ 转换失败: {e}")
            self.failed_count += 1
            return None
    
    async def convert_batch(self, news_list: List[Dict]) -> List[Dict]:
        """批量转换"""
        converted_events = []
        
        # 限制并发数
        semaphore = asyncio.Semaphore(3)
        
        async def process_with_limit(news, index):
            async with semaphore:
                return await self.convert_single_news(news, index)
        
        # 创建任务
        tasks = []
        for i, news in enumerate(news_list):
            task = asyncio.create_task(process_with_limit(news, i))
            tasks.append(task)
        
        # 处理结果
        for i, task in enumerate(asyncio.as_completed(tasks)):
            try:
                result = await task
                if result:
                    converted_events.append(result)
                
                # 显示进度
                if (i + 1) % 5 == 0:
                    print(f"    📊 进度: {i+1}/{len(tasks)}")
                    
            except Exception as e:
                print(f"    ❌ 任务失败: {e}")
        
        return converted_events
    
    async def close(self):
        """关闭资源"""
        if self.llm_parser:
            await self.llm_parser.close()

# ============================================================
# 主函数
# ============================================================

async def main():
    print("=" * 60)
    print("🤖 AI数据转换器")
    print("=" * 60)
    
    # 文件路径
    current_dir = os.path.dirname(__file__)  # scripts目录
    evaluate_dir = os.path.dirname(current_dir)  # evaluate_service目录
    input_file = os.path.join(evaluate_dir, "data", "raw", "validation_dataset.json")
    output_file = os.path.join(evaluate_dir, "data", "raw", "ai_processed_events.json")
    
    print(f"📂 输入文件: {input_file}")
    print(f"📂 输出文件: {output_file}")
    
    # 检查文件
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在")
        return
    
    # 读取数据
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
        print(f"📊 读取到 {len(dataset)} 条新闻")
    except Exception as e:
        print(f"❌ 读取数据失败: {e}")
        return
    
    # 转换
    converter = NewsConverter()
    
    try:
        await converter.initialize()
        
        print(f"\n🚀 开始转换...")
        start_time = datetime.now()
        
        events = await converter.convert_batch(dataset)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✅ 转换完成!")
        print(f"   耗时: {duration:.1f}秒")
        print(f"   成功: {converter.converted_count}条")
        print(f"   失败: {converter.failed_count}条")
        
        if events:
            # 保存
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 已保存到: {output_file}")
            
            # 显示示例
            print(f"\n📋 示例数据:")
            for i in range(min(2, len(events))):
                event = events[i]
                ai = event.get("ai_analysis", {})
                print(f"\n  [{i+1}] {event['event_id']}")
                print(f"      标题: {event['title'][:40]}...")
                print(f"      类型: {event['event_type']}")
                print(f"      核心: {ai.get('core_concept')}")
                print(f"      关键词: {', '.join(ai.get('industry_keywords', [])[:3])}")
        
    except Exception as e:
        print(f"\n❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await converter.close()

if __name__ == "__main__":
    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 请先设置环境变量:")
        print("   export DEEPSEEK_API_KEY='your-api-key'")
        sys.exit(1)
    
    # 运行
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")