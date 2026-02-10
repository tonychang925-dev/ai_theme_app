#!/usr/bin/env python3
"""
第一步：数据预处理脚本（改进版）
使用真实的DeepSeekParser处理原始新闻数据
生成带有theme_directive的结构化事件
"""
import json
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置测试模式
os.environ['TEST_MODE'] = '1'

logger = logging.getLogger(__name__)

class EnhancedDataPreprocessor:
    """增强版数据预处理器 - 使用真实的DeepSeekParser"""
    
    def __init__(self):
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "with_create_new": 0,
            "with_cluster": 0,
            "avg_confidence": 0.0
        }
        self.parser = None
        
    async def initialize_parser(self):
        """初始化DeepSeek解析器"""
        try:
            # 导入DeepSeekParser
            from model_service.llm_parser.deepseek_parser_0203 import DeepSeekParser
            self.parser = DeepSeekParser()
            print("✅ DeepSeekParser初始化成功（测试模式）")
            return True
        except ImportError as e:
            print(f"❌ 无法导入DeepSeekParser: {e}")
            print("尝试从model_service导入...")
            
            # 尝试其他导入方式
            try:
                # 添加model_service路径
                model_service_path = project_root / "model_service"
                if model_service_path.exists():
                    sys.path.insert(0, str(model_service_path))
                
                from llm_parser.deepseek_parser import DeepSeekParser
                self.parser = DeepSeekParser()
                print("✅ 从model_service导入DeepSeekParser成功")
                return True
            except ImportError as e2:
                print(f"❌ 所有导入尝试都失败: {e2}")
                return False
    
    async def load_raw_dataset(self) -> List[Dict[str, Any]]:
        """加载原始数据集"""
        raw_data_path = Path("evaluate_service/data/raw/validation_dataset.json")
        
        if not raw_data_path.exists():
            raise FileNotFoundError(f"原始数据文件不存在: {raw_data_path}")
        
        print(f"📂 加载原始数据文件: {raw_data_path}")
        
        try:
            with open(raw_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"✅ 加载成功: {len(data)} 条原始新闻数据")
            
            # 验证数据结构
            sample = data[0] if data else {}
            print(f"📋 数据结构验证:")
            print(f"  标题字段: {'title' in sample}")
            print(f"  内容字段: {'content' in sample}")
            print(f"  主题字段: {'theme' in sample}")
            
            return data
            
        except Exception as e:
            print(f"❌ 加载数据失败: {e}")
            raise
    
    async def process_news_item(self, news_item: Dict[str, Any], index: int) -> Dict[str, Any]:
        """处理单个新闻项"""
        try:
            title = news_item.get('title', '')
            content = news_item.get('content', '')
            theme = news_item.get('theme', 'unknown')
            
            if not title or not content:
                print(f"⚠️  第{index}条新闻缺少标题或内容，跳过")
                return None
            
            # 调用DeepSeekParser解析新闻
            print(f"  [{index+1:03d}] 解析: {title[:40]}...")
            ai_result = await self.parser.parse_news(title, content)
            
            if not ai_result:
                print(f"  ❌ 第{index}条新闻解析失败")
                return None
            
            # 提取event_info和theme_directive
            event_info = ai_result.get("event_info", {})
            theme_directive = ai_result.get("theme_discovery_directive", {
                "action": "CLUSTER",
                "confidence": 0.5,
                "reason": "AI解析失败"
            })
            
            # 验证数据结构
            required_fields = ['event_type', 'summary', 'impact_industries', 'direction', 'confidence']
            missing_fields = [field for field in required_fields if field not in event_info]
            
            if missing_fields:
                print(f"  ⚠️  第{index}条新闻缺少字段: {missing_fields}")
                # 填充默认值
                for field in missing_fields:
                    if field == 'impact_industries':
                        event_info[field] = []
                    elif field == 'confidence':
                        event_info[field] = 0.5
                    else:
                        event_info[field] = f"missing_{field}"
            
            # 构建结构化事件
            structured_event = {
                'news_id': f"news_{index:03d}",
                'event_type': event_info.get('event_type', 'unknown'),
                'impact_industries': event_info.get('impact_industries', []),
                'direction': event_info.get('direction', 'neutral'),
                'confidence': event_info.get('confidence', 0.5),
                'summary': event_info.get('summary', f"{title[:50]}..."),
                'theme_directive': theme_directive,
                'original_data': {
                    'title': title,
                    'theme': theme,
                    'content_preview': content[:100] + "..."
                },
                'ai_response': {
                    'raw_response': ai_result.get('raw_response', {}),
                    'parser_version': 'DeepSeekParser_v2'
                },
                'processed_at': datetime.now().isoformat()
            }
            
            # 更新统计
            self.stats["successful"] += 1
            action = theme_directive.get('action')
            confidence = theme_directive.get('confidence', 0)
            
            if action == 'CREATE_NEW':
                self.stats["with_create_new"] += 1
            elif action == 'CLUSTER':
                self.stats["with_cluster"] += 1
            
            # 累加置信度用于计算平均值
            self.stats["avg_confidence"] = (
                (self.stats["avg_confidence"] * (self.stats["successful"] - 1) + confidence) 
                / self.stats["successful"]
            )
            
            print(f"  ✅ 解析成功: {action} (置信度: {confidence:.2f})")
            
            return structured_event
            
        except Exception as e:
            print(f"❌ 处理第{index}条新闻失败: {e}")
            self.stats["failed"] += 1
            return None
    
    async def process_batch(self, raw_data: List[Dict]) -> List[Dict]:
        """批量处理原始数据"""
        print("🔄 开始批量处理原始数据（使用DeepSeekParser）...")
        
        # 初始化解析器
        if not await self.initialize_parser():
            raise Exception("无法初始化DeepSeekParser")
        
        events = []
        
        # 分批处理，避免内存问题
        batch_size = 10
        for i in range(0, len(raw_data), batch_size):
            batch = raw_data[i:i + batch_size]
            batch_events = []
            
            # 处理当前批次
            tasks = [self.process_news_item(item, i + j) for j, item in enumerate(batch)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 收集结果
            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"❌ 批次{i//batch_size}第{j}个任务异常: {result}")
                    self.stats["failed"] += 1
                elif result:
                    batch_events.append(result)
            
            events.extend(batch_events)
            
            # 进度显示
            print(f"  批次完成: {i + len(batch)}/{len(raw_data)} (成功: {len(events)}, 失败: {self.stats['failed']})")
            
            # 短暂延迟，避免API限制（如果是真实API）
            if i + batch_size < len(raw_data):
                await asyncio.sleep(0.1)
        
        self.stats["total_processed"] = len(raw_data)
        
        print(f"\n✅ 批量处理完成:")
        print(f"   总计: {self.stats['total_processed']}")
        print(f"   成功: {self.stats['successful']}")
        print(f"   失败: {self.stats['failed']}")
        print(f"   CREATE_NEW: {self.stats['with_create_new']}")
        print(f"   CLUSTER: {self.stats['with_cluster']}")
        print(f"   平均置信度: {self.stats['avg_confidence']:.3f}")
        
        return events
    
    def analyze_directive_quality(self, events: List[Dict]):
        """分析指令质量"""
        if not events:
            return
        
        print(f"\n📊 指令质量分析")
        print("=" * 50)
        
        # 按action分组
        actions = {}
        confidences_by_action = {}
        reasons = []
        
        for event in events:
            directive = event.get('theme_directive', {})
            action = directive.get('action', 'UNKNOWN')
            confidence = directive.get('confidence', 0)
            reason = directive.get('reason', '')
            
            if action not in actions:
                actions[action] = 0
                confidences_by_action[action] = []
            
            actions[action] += 1
            confidences_by_action[action].append(confidence)
            
            if reason and len(reason) < 100:  # 避免过长的原因
                reasons.append(reason)
        
        # 显示统计
        for action, count in sorted(actions.items()):
            percentage = count / len(events) * 100
            confidences = confidences_by_action.get(action, [])
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            
            print(f"  {action}:")
            print(f"    数量: {count} ({percentage:.1f}%)")
            print(f"    平均置信度: {avg_conf:.3f}")
            if confidences:
                print(f"    置信度范围: {min(confidences):.3f} - {max(confidences):.3f}")
        
        # 显示一些典型的原因
        if reasons:
            print(f"\n  🎯 典型决策理由 (采样):")
            for i, reason in enumerate(reasons[:5]):
                print(f"    {i+1}. {reason[:80]}...")
    
    def save_processed_data(self, events: List[Dict]):
        """保存处理后的数据"""
        # 确保目录存在
        processed_dir = Path("evaluate_service/data/processed")
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = processed_dir / "validation_events_enhanced_v2.json"
        
        # 准备输出数据
        output_data = {
            "metadata": {
                "processing_time": datetime.now().isoformat(),
                "script": "01_preprocess_validation_data_v2.py",
                "version": "2.0",
                "description": "使用DeepSeekParser处理原始新闻 -> 结构化事件",
                "parser_used": "DeepSeekParser (测试模式)",
                "total_news": len(events),
                "stats": self.stats
            },
            "events": events
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"\n💾 数据保存成功: {output_file}")
            print(f"   事件数量: {len(events)}")
            
            # 显示样本数据
            if events:
                print(f"\n📄 样本数据 (第一条事件):")
                sample = events[0]
                print(f"   事件ID: {sample.get('news_id')}")
                print(f"   标题: {sample.get('original_data', {}).get('title', 'N/A')}")
                print(f"   真实主题: {sample.get('original_data', {}).get('theme', 'N/A')}")
                print(f"   事件类型: {sample.get('event_type')}")
                print(f"   影响行业: {sample.get('impact_industries')}")
                print(f"   指令类型: {sample.get('theme_directive', {}).get('action')}")
                print(f"   指令置信度: {sample.get('theme_directive', {}).get('confidence')}")
                print(f"   指令理由: {sample.get('theme_directive', {}).get('reason', '')[:80]}...")
            
            return output_file
            
        except Exception as e:
            print(f"❌ 保存数据失败: {e}")
            raise
    
    async def close_resources(self):
        """关闭资源"""
        if self.parser:
            try:
                await self.parser.close()
                print("✅ 关闭DeepSeekParser资源")
            except Exception as e:
                print(f"⚠️  关闭解析器资源失败: {e}")

async def main():
    """主函数"""
    print("=" * 60)
    print("📊 第一步：数据预处理（改进版）")
    print("使用DeepSeekParser处理原始新闻 -> 结构化事件")
    print("=" * 60)
    
    preprocessor = EnhancedDataPreprocessor()
    
    try:
        # 1. 加载原始数据
        raw_data = await preprocessor.load_raw_dataset()
        
        # 2. 处理数据
        events = await preprocessor.process_batch(raw_data)
        
        if not events:
            print("❌ 没有生成任何事件，程序退出")
            return 1
        
        # 3. 分析指令质量
        preprocessor.analyze_directive_quality(events)
        
        # 4. 保存处理后的数据
        output_file = preprocessor.save_processed_data(events)
        
        # 5. 关闭资源
        await preprocessor.close_resources()
        
        print(f"\n✅ 第一步完成！")
        print(f"   输出文件: {output_file}")
        print(f"   关键统计:")
        print(f"     - CREATE_NEW指令: {preprocessor.stats['with_create_new']}")
        print(f"     - 平均置信度: {preprocessor.stats['avg_confidence']:.3f}")
        print(f"   接下来运行: evaluate_service/scripts/02_run_enhanced_evaluation.py")
        
    except Exception as e:
        print(f"❌ 预处理失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试关闭资源
        try:
            await preprocessor.close_resources()
        except:
            pass
        
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())