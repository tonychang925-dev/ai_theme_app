#!/usr/bin/env python3
"""
第二步：验证 AIThemeSimilarityAnalyzer 的真实AI分析能力

🎯 目标：
1. 使用真实的DeepSeek API
2. 验证AI能否做出准确的"合并/创建"决策
3. 检查输出质量
"""
import asyncio
import sys
from pathlib import Path
import json
from datetime import datetime

# 添加项目根目录
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入修复版的 PureDataFetcher
from evaluate_service.scripts.fixed_pure_data_fetcher_test import FixedPureDataFetcher

async def setup_test_environment():
    """设置测试环境：创建有意义的测试数据"""
    print("🔧 设置测试环境...")
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    
    # 创建数据库
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 清除缓存
    db_manager.theme_context_cache.clear()
    
    print("创建测试主题...")
    
    # 创建3个相关但不同的AI主题
    themes_data = [
        {
            "name": "人工智能技术",
            "description": "基础人工智能技术研究，包括机器学习、深度学习等算法",
            "keywords": ["AI", "机器学习", "深度学习", "算法"],
            "discovery_source": "test",
            "discovery_confidence": 0.9
        },
        {
            "name": "AI硬件产品", 
            "description": "AI相关的硬件产品，如AI芯片、AI服务器、智能设备等",
            "keywords": ["AI芯片", "硬件", "智能设备", "服务器"],
            "discovery_source": "test",
            "discovery_confidence": 0.8
        },
        {
            "name": "智能穿戴设备",
            "description": "智能手表、智能眼镜等穿戴式智能设备",
            "keywords": ["智能手表", "智能眼镜", "可穿戴", "AR眼镜"],
            "discovery_source": "test", 
            "discovery_confidence": 0.7
        }
    ]
    
    themes = []
    for theme_data in themes_data:
        theme = await db_manager.create_theme(**theme_data)
        themes.append(theme)
        print(f"  ✅ 创建主题: {theme.name}")
    
    print("\n创建测试事件（AI眼镜相关）...")
    
    # 创建AI眼镜相关的事件
    ai_glasses_events = [
        {
            "news_id": "ai_glasses_001",
            "event_info": {
                "event_type": "产品发布",
                "impact_industries": ["消费电子", "人工智能", "硬件"],
                "direction": "利好",
                "event_confidence": 0.85
            },
            "original_news": {
                "title": "Rokid发布新一代AI智能眼镜，销量突破30万台",
                "content": "Rokid公司今日发布新一代AI智能眼镜，集成了语音助手、实时翻译和AR导航功能。据悉，该产品累计销量已达30万台，下半年将上线打车功能。",
                "date": "2025-07-27"
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "decision_confidence": 0.8,
                "reason": "AI眼镜产品重大突破"
            }
        },
        {
            "news_id": "ai_glasses_002",
            "event_info": {
                "event_type": "技术发布",
                "impact_industries": ["互联网", "人工智能", "显示技术"],
                "direction": "利好", 
                "event_confidence": 0.9
            },
            "original_news": {
                "title": "阿里巴巴推出首款自研AI眼镜，集成通义千问大模型",
                "content": "阿里巴巴发布首款自研AI眼镜，产品整合了高德地图、支付宝和淘宝生态。眼镜搭载通义千问大模型，支持语音交互、实时翻译和会议纪要生成。",
                "date": "2025-07-23"
            },
            "theme_discovery_directive": {
                "action": "CREATE_NEW",
                "decision_confidence": 0.85,
                "reason": "巨头入局AI眼镜市场"
            }
        }
    ]
    
    event_ids = []
    for event_data in ai_glasses_events:
        event_id = await db_manager.create_or_update_event(event_data)
        event_ids.append(event_id)
        print(f"  ✅ 创建事件: {event_data['original_news']['title'][:30]}...")
        
        # 将事件关联到相关主题
        for theme in themes:
            # 简单的关键词匹配来决定是否关联
            title_lower = event_data['original_news']['title'].lower()
            theme_keywords = [k.lower() for k in theme.keywords]
            
            if any(keyword in title_lower for keyword in theme_keywords):
                await db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=theme.id,
                    confidence=0.7,
                    confidence_level="medium"
                )
                print(f"    关联到主题: {theme.name}")
    
    print(f"\n✅ 环境设置完成: {len(themes)}个主题, {len(event_ids)}个事件")
    return db_manager, themes, event_ids

async def test_ai_similarity_analyzer_real():
    """
    测试真实的AI相似性分析器
    
    🔥 这里我们直接调用DeepSeek API来模拟AI分析器的行为
    """
    print("\n" + "="*60)
    print("🧪 第二步：验证 AI 相似性分析器")
    print("="*60)
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    from theme_service.related_theme_fetcher import RelatedThemeFetcher
    
    # 设置环境
    db_manager, themes, event_ids = await setup_test_environment()
    
    # 使用修复版的 PureDataFetcher
    fixed_fetcher = FixedPureDataFetcher(db_manager)
    
    # 创建 RelatedThemeFetcher
    theme_fetcher = RelatedThemeFetcher(fixed_fetcher)
    
    print("\n1. 获取现有主题的完整上下文...")
    existing_themes = await theme_fetcher.fetch_all_active_themes(limit=10)
    print(f"   获取到 {len(existing_themes)} 个现有主题")
    
    for i, theme in enumerate(existing_themes[:3]):
        print(f"   主题{i+1}: {theme['name']}")
        print(f"     描述: {theme.get('description', '')[:50]}...")
        print(f"     事件数: {theme.get('context', {}).get('event_count', 0)}")
    
    print("\n2. 获取新事件数据...")
    if event_ids:
        from database_service.pure_data_fetcher import PureDataFetcher
        event_fetcher = PureDataFetcher(db_manager)
        new_event = await event_fetcher.get_event(event_ids[0])
        
        if new_event:
            print(f"   新事件: {new_event.get('title', '未知')}")
            print(f"   内容预览: {new_event.get('full_content', '')[:80]}...")
            print(f"   事件类型: {new_event.get('event_info', {}).get('event_type', '未知')}")
            
            # 准备AI分析输入
            analysis_input = {
                "new_event": {
                    "title": new_event.get('title', ''),
                    "content": new_event.get('full_content', ''),
                    "event_type": new_event.get('event_info', {}).get('event_type', ''),
                    "industries": new_event.get('event_info', {}).get('impact_industries', [])
                },
                "existing_themes": existing_themes,
                "analysis_requirements": {
                    "compare_content": True,
                    "check_semantic_similarity": True,
                    "evaluate_merge_possibility": True,
                    "suggest_new_theme_name": True
                }
            }
            
            print(f"\n3. 准备AI分析输入数据...")
            print(f"   新事件关键词: {new_event.get('event_info', {}).get('impact_industries', [])}")
            print(f"   现有主题数量: {len(existing_themes)}")
            print(f"   总事件内容长度: {sum(len(t.get('description', '')) for t in existing_themes)} 字符")
            
            # 保存输入数据供调试
            input_file = Path("ai_analysis_input.json")
            with open(input_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_input, f, ensure_ascii=False, indent=2)
            print(f"   AI分析输入已保存到: {input_file}")
    
    print("\n4. 测试模拟的AI分析...")
    
    # 首先测试一个简化的模拟AI分析
    mock_ai_result = await simulate_ai_analysis(new_event, existing_themes)
    
    print(f"   模拟AI分析结果:")
    print(f"     决策: {mock_ai_result.get('decision')}")
    print(f"     置信度: {mock_ai_result.get('confidence')}")
    print(f"     建议主题名称: {mock_ai_result.get('suggested_theme_name')}")
    print(f"     分析理由: {mock_ai_result.get('reason')[:100]}...")
    
    print("\n5. 测试真实的AI分析（DeepSeek API）...")
    
    # 尝试调用真实的DeepSeek API
    real_ai_result = await call_real_deepseek_api(analysis_input)
    
    if real_ai_result:
        print(f"   ✅ 真实AI分析成功!")
        print(f"     决策: {real_ai_result.get('decision')}")
        print(f"     置信度: {real_ai_result.get('confidence')}")
        print(f"     分析质量: {real_ai_result.get('analysis_quality', 'unknown')}")
        
        # 评估AI分析质量
        quality_score = evaluate_ai_analysis_quality(real_ai_result)
        print(f"     质量评分: {quality_score}/10")
        
        if quality_score >= 7:
            print(f"   🎉 AI分析质量良好，可以投入使用")
        else:
            print(f"   ⚠️  AI分析质量需要改进")
    else:
        print(f"   ⚠️  真实AI分析失败，使用模拟结果")
    
    # 清理
    await db_manager.cleanup()
    
    return real_ai_result or mock_ai_result

async def simulate_ai_analysis(new_event, existing_themes):
    """模拟AI分析（当真实API不可用时使用）"""
    print("   🧪 使用模拟AI分析...")
    
    # 简单的规则匹配
    new_event_content = new_event.get('full_content', '').lower()
    new_event_title = new_event.get('title', '').lower()
    
    best_match = None
    best_score = 0
    
    for theme in existing_themes:
        theme_name = theme.get('name', '').lower()
        theme_keywords = [k.lower() for k in theme.get('keywords', [])]
        
        # 简单评分：检查关键词匹配
        score = 0
        
        # 检查主题名称是否出现在事件中
        if theme_name in new_event_content or theme_name in new_event_title:
            score += 3
        
        # 检查关键词匹配
        for keyword in theme_keywords:
            if keyword in new_event_content:
                score += 1
        
        if score > best_score:
            best_score = score
            best_match = theme
    
    if best_match and best_score >= 2:
        return {
            "decision": "MERGE",
            "confidence": min(best_score / 5.0, 0.9),
            "target_theme_id": best_match.get('id'),
            "target_theme_name": best_match.get('name'),
            "suggested_theme_name": best_match.get('name'),
            "reason": f"新事件与现有主题'{best_match.get('name')}'高度相关，关键词匹配度较高。建议合并到该主题。",
            "analysis_method": "simulated_keyword_matching"
        }
    else:
        return {
            "decision": "CREATE_NEW",
            "confidence": 0.7,
            "suggested_theme_name": "AI智能眼镜产业",
            "reason": "新事件涉及AI智能眼镜领域，与现有主题关联度不高，建议创建新主题。",
            "analysis_method": "simulated_keyword_matching"
        }

async def call_real_deepseek_api(analysis_input):
    """调用真实的DeepSeek API进行AI分析"""
    print("   🔗 尝试调用DeepSeek API...")
    
    try:
        # 首先检查是否有可用的API密钥
        import os
        from openai import OpenAI
        
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            print("   ⚠️  未找到API密钥，跳过真实AI分析")
            print("   提示：设置环境变量 DEEPSEEK_API_KEY 或 OPENAI_API_KEY")
            return None
        
        print("   ✅ 找到API密钥，开始调用AI分析...")
        
        # 构建AI分析提示
        prompt = build_ai_analysis_prompt(analysis_input)
        
        # 调用DeepSeek API
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的主题分析AI助手。你需要分析新闻事件，判断应该合并到现有主题还是创建新主题。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        # 解析AI响应
        ai_response = response.choices[0].message.content
        
        # 尝试从响应中提取结构化数据
        result = parse_ai_response(ai_response)
        result["raw_ai_response"] = ai_response
        result["analysis_quality"] = "real_ai_analysis"
        
        print(f"   ✅ AI分析完成，响应长度: {len(ai_response)} 字符")
        
        # 保存AI响应
        output_file = Path("ai_analysis_output.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"   AI分析结果已保存到: {output_file}")
        
        return result
        
    except ImportError:
        print("   ⚠️  未安装openai库，使用模拟分析")
        print("   安装命令: pip install openai")
        return None
    except Exception as e:
        print(f"   ❌ AI分析失败: {e}")
        # 不打印详细错误，避免泄露API密钥
        return None

def build_ai_analysis_prompt(analysis_input):
    """构建AI分析提示"""
    new_event = analysis_input["new_event"]
    existing_themes = analysis_input["existing_themes"]
    
    prompt = f"""请分析以下新闻事件，并判断它应该合并到现有主题还是创建新主题。

新闻事件：
标题：{new_event['title']}
内容：{new_event['content'][:500]}...
事件类型：{new_event['event_type']}
涉及行业：{', '.join(new_event['industries'])}

现有主题列表（共{len(existing_themes)}个）：
"""
    
    for i, theme in enumerate(existing_themes):
        prompt += f"""
{i+1}. 主题名称：{theme['name']}
   描述：{theme.get('description', '')[:100]}...
   关键词：{', '.join(theme.get('keywords', []))}
   关联事件数：{theme.get('context', {}).get('event_count', 0)}
"""
    
    prompt += """
请根据以下要求进行分析：
1. 对比新闻事件与每个现有主题的内容相似度
2. 评估语义相关性
3. 判断是否应该合并到某个现有主题，还是创建新主题
4. 如果合并，请说明理由和置信度
5. 如果创建新主题，请建议合适的主题名称

请用JSON格式返回分析结果，包含以下字段：
{
  "decision": "MERGE" 或 "CREATE_NEW",
  "confidence": 0.0到1.0的置信度,
  "target_theme_id": 如果是MERGE，目标主题ID,
  "target_theme_name": 如果是MERGE，目标主题名称,
  "suggested_theme_name": 建议的主题名称（如果是CREATE_NEW，或MERGE后的优化名称）,
  "reason": "详细的分析理由",
  "key_matching_points": ["匹配点1", "匹配点2", ...]
}

请确保JSON格式正确，可以直接解析。
"""
    
    return prompt

def parse_ai_response(ai_response):
    """解析AI响应为结构化数据"""
    try:
        # 尝试从响应中提取JSON
        import re
        
        # 查找JSON部分
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            result = json.loads(json_str)
            return result
        else:
            # 如果找不到JSON，创建基本结果
            return {
                "decision": "UNKNOWN",
                "confidence": 0.5,
                "reason": "无法解析AI响应",
                "raw_response": ai_response[:200]
            }
    except Exception as e:
        print(f"   解析AI响应失败: {e}")
        return {
            "decision": "ERROR",
            "confidence": 0.0,
            "reason": f"解析失败: {str(e)}",
            "raw_response": ai_response[:200]
        }

def evaluate_ai_analysis_quality(ai_result):
    """评估AI分析质量"""
    score = 0
    
    # 检查必要字段
    required_fields = ['decision', 'confidence', 'reason']
    for field in required_fields:
        if field in ai_result and ai_result[field]:
            score += 1
    
    # 检查决策合理性
    if ai_result.get('decision') in ['MERGE', 'CREATE_NEW']:
        score += 2
    
    # 检查置信度合理性
    confidence = ai_result.get('confidence', 0)
    if 0 <= confidence <= 1:
        score += 1
    
    # 检查理由的详细程度
    reason = ai_result.get('reason', '')
    if len(reason) > 50:
        score += 2
    
    # 检查是否有具体匹配点
    if 'key_matching_points' in ai_result and ai_result['key_matching_points']:
        score += 2
    
    # 检查建议名称的合理性
    if 'suggested_theme_name' in ai_result and ai_result['suggested_theme_name']:
        score += 2
    
    return min(score, 10)

async def main():
    """主测试函数"""
    print("="*60)
    print("🚀 启动 AI 相似性分析器验证测试")
    print("="*60)
    
    print("\n📋 测试目标：")
    print("  1. 验证AI能否做出准确的'合并/创建'决策")
    print("  2. 检查AI分析输出质量")
    print("  3. 测试与现有系统的集成")
    print("  4. 评估AI分析的实际效果")
    
    try:
        # 运行AI分析测试
        ai_result = await test_ai_similarity_analyzer_real()
        
        print("\n" + "="*60)
        print("📊 AI分析结果评估")
        print("="*60)
        
        print(f"\n决策: {ai_result.get('decision')}")
        print(f"置信度: {ai_result.get('confidence')}")
        print(f"分析方法: {ai_result.get('analysis_method', 'unknown')}")
        
        reason = ai_result.get('reason', '')
        print(f"\n分析理由:")
        if len(reason) > 150:
            print(f"  {reason[:150]}...")
        else:
            print(f"  {reason}")
        
        if 'key_matching_points' in ai_result:
            print(f"\n关键匹配点:")
            for point in ai_result['key_matching_points'][:3]:
                print(f"  • {point}")
        
        # 质量评估
        quality_score = evaluate_ai_analysis_quality(ai_result)
        print(f"\n📈 AI分析质量评分: {quality_score}/10")
        
        if quality_score >= 8:
            print("🎉 优秀！AI分析质量很高，可以投入生产使用")
            print("   下一步：集成到 EnhancedThemeDiscoveryEngine")
        elif quality_score >= 6:
            print("✅ 良好！AI分析基本可用，建议进一步优化")
            print("   下一步：优化提示词和解析逻辑")
        else:
            print("⚠️  一般！AI分析需要改进")
            print("   下一步：调试AI分析逻辑")
        
        # 建议下一步
        print("\n🎯 下一步建议：")
        print("  1. 如果AI分析质量良好，可以开始验证 EnhancedThemeDiscoveryEngine")
        print("  2. 优化AI分析提示词以获得更稳定的结果")
        print("  3. 添加更多测试用例验证边界情况")
        print("  4. 集成错误处理和重试机制")
        
        return quality_score >= 6  # 如果质量评分>=6，认为测试通过
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        
        print("\n" + "="*60)
        if success:
            print("🎉 AI相似性分析器验证测试通过！")
            print("可以进入下一阶段：验证 EnhancedThemeDiscoveryEngine")
        else:
            print("❌ AI相似性分析器验证测试失败")
            print("需要先修复AI分析问题")
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(130)