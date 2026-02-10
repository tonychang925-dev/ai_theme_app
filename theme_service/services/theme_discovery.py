"""
主题发现引擎 - 基于AI分析发现新投资主题
这是 theme_service 的核心模块
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

class ThemeDiscoveryEngine:
    """主题发现引擎 - 实现AI驱动的题材发现"""
    
    def __init__(self, ai_client, db_manager=None):
        """
        初始化主题发现引擎
        
        Args:
            ai_client: AI分析客户端 (AIThemeClient)
            db_manager: 数据库管理器 (可选)
        """
        self.ai_client = ai_client
        self.db = db_manager
        
        # 配置参数
        self.min_events_for_theme = 2
        self.theme_confidence_threshold = 0.6
        self.cluster_similarity_threshold = 0.5
        
        logger.info("ThemeDiscoveryEngine 初始化完成")
    
    async def discover_from_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        从事件列表中自动发现新主题
        
        Args:
            events: 事件数据列表
            
        Returns:
            发现的主题列表
        """
        if not events:
            logger.info("没有事件需要分析")
            return []
        
        logger.info(f"开始主题发现: {len(events)} 个事件")
        
        # 步骤1: AI深度分析每个事件
        analyzed_events = []
        for i, event in enumerate(events, 1):
            try:
                logger.debug(f"分析事件 {i}/{len(events)}: {event.get('title', '无标题')[:30]}...")
                
                # 调用AI分析
                ai_result = await self.ai_client.analyze_event_for_themes(event)
                
                analyzed_events.append({
                    "event": event,
                    "analysis": ai_result,
                    "analyzed_at": datetime.now()
                })
                
            except Exception as e:
                logger.error(f"事件分析失败: {e}")
        
        if not analyzed_events:
            logger.warning("所有事件分析都失败")
            return []
        
        # 步骤2: 聚类相似事件
        clusters = self._cluster_events(analyzed_events)
        logger.info(f"形成 {len(clusters)} 个事件簇")
        
        # 步骤3: 从每个簇中提取主题候选
        new_themes = []
        for cluster_id, cluster in enumerate(clusters):
            if len(cluster["events"]) >= self.min_events_for_theme:
                theme_candidate = await self._extract_theme_from_cluster(cluster)
                
                if theme_candidate and theme_candidate["confidence"] >= self.theme_confidence_threshold:
                    new_themes.append(theme_candidate)
                    logger.info(f"发现主题候选: {theme_candidate['name']} (置信度: {theme_candidate['confidence']:.2f})")
        
        logger.info(f"主题发现完成: 发现 {len(new_themes)} 个新主题")
        return new_themes
    
    def _cluster_events(self, analyzed_events: List[Dict]) -> List[Dict]:
        """基于AI分析结果聚类相似事件"""
        clusters = []
        
        for event_data in analyzed_events:
            event = event_data["event"]
            analysis = event_data["analysis"]
            
            # 提取关键信息用于聚类
            themes = analysis.get("potential_themes", [])
            industries = analysis.get("related_industries", [])
            
            # 寻找匹配的簇
            matched_cluster = None
            for cluster in clusters:
                similarity = self._calculate_cluster_similarity(
                    themes, industries,
                    cluster["themes"], cluster["industries"]
                )
                
                if similarity >= self.cluster_similarity_threshold:
                    matched_cluster = cluster
                    break
            
            if matched_cluster:
                # 添加到现有簇
                matched_cluster["events"].append(event_data)
                matched_cluster["themes"].extend(themes)
                matched_cluster["industries"].extend(industries)
                matched_cluster["themes"] = list(set(matched_cluster["themes"]))
                matched_cluster["industries"] = list(set(matched_cluster["industries"]))
            else:
                # 创建新簇
                clusters.append({
                    "events": [event_data],
                    "themes": themes,
                    "industries": industries,
                    "first_seen": datetime.now()
                })
        
        return clusters
    
    def _calculate_cluster_similarity(self, themes1, industries1, themes2, industries2):
        """计算两个事件簇的相似度"""
        if not themes1 and not themes2:
            return 0.0
        
        # 主题相似度
        themes_set1 = set(themes1)
        themes_set2 = set(themes2)
        theme_similarity = len(themes_set1 & themes_set2) / max(len(themes_set1 | themes_set2), 1)
        
        # 行业相似度
        industries_set1 = set(industries1)
        industries_set2 = set(industries2)
        industry_similarity = len(industries_set1 & industries_set2) / max(len(industries_set1 | industries_set2), 1)
        
        # 综合相似度（主题权重更高）
        return theme_similarity * 0.7 + industry_similarity * 0.3
    
    async def _extract_theme_from_cluster(self, cluster: Dict) -> Optional[Dict[str, Any]]:
        """从事件簇中提取主题候选"""
        events_data = cluster["events"]
        
        if len(events_data) < self.min_events_for_theme:
            return None
        
        # 统计主题出现频率
        theme_counter = Counter()
        for event_data in events_data:
            themes = event_data["analysis"].get("potential_themes", [])
            theme_counter.update(themes)
        
        if not theme_counter:
            return None
        
        # 选择最常出现的主题
        theme_name, frequency = theme_counter.most_common(1)[0]
        
        # 计算置信度
        total_events = len(events_data)
        frequency_score = frequency / total_events
        
        # 平均确定性
        avg_certainty = sum(
            event_data["analysis"].get("certainty", 0.5)
            for event_data in events_data
        ) / total_events
        
        # 平均主题强度
        avg_strength = sum(
            event_data["analysis"].get("theme_strength", {}).get("score", 5)
            for event_data in events_data
        ) / total_events
        
        # 综合置信度
        confidence = (
            frequency_score * 0.4 +      # 频率权重 40%
            avg_certainty * 0.3 +        # 确定性权重 30%
            (avg_strength / 10) * 0.3    # 强度权重 30%
        )
        
        # 提取支持事件
        supporting_events = [ed["event"]["id"] for ed in events_data if "id" in ed["event"]]
        
        return {
            "name": theme_name,
            "confidence": min(confidence, 1.0),
            "supporting_events": supporting_events,
            "event_count": total_events,
            "first_seen": min(ed.get("analyzed_at", datetime.now()) for ed in events_data),
            "avg_certainty": avg_certainty,
            "avg_strength": avg_strength,
            "status": "candidate"
        }
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件并返回相关主题
        
        Args:
            event: 单个事件数据
            
        Returns:
            处理结果
        """
        result = {
            "event_id": event.get("id"),
            "processed_at": datetime.now(),
            "themes_found": []
        }
        
        try:
            # AI分析事件
            ai_analysis = await self.ai_client.analyze_event_for_themes(event)
            
            # 提取发现的主题
            themes = ai_analysis.get("potential_themes", [])
            
            if themes:
                result["themes_found"] = themes
                result["confidence"] = ai_analysis.get("certainty", 0.5)
                
                logger.info(f"事件 {event.get('id')} 发现主题: {themes}")
            else:
                logger.debug(f"事件 {event.get('id')} 未发现主题")
            
        except Exception as e:
            logger.error(f"处理事件失败: {e}")
            result["error"] = str(e)
        
        return result

# 测试函数
async def test_theme_discovery():
    """测试主题发现引擎"""
    print("🧪 测试主题发现引擎...")
    
    # 创建模拟AI客户端
    class MockAIClient:
        async def analyze_event_for_themes(self, event_data):
            # 模拟AI分析结果
            return {
                "potential_themes": ["AI眼镜", "智能穿戴"],
                "certainty": 0.85,
                "theme_strength": {"score": 8, "reason": "产品已量产"}
            }
    
    # 创建测试事件
    test_events = [
        {
            "id": 1001,
            "title": "Rokid智能眼镜销量突破30万台",
            "summary": "Rokid创始人透露智能眼镜销量已达30万台",
            "event_type": "产品突破",
            "impact_industries": ["消费电子", "人工智能"]
        },
        {
            "id": 1002,
            "title": "苹果Vision Pro二代即将发布",
            "summary": "供应链消息称Vision Pro二代已开始试产",
            "event_type": "产品发布",
            "impact_industries": ["消费电子", "XR设备"]
        }
    ]
    
    # 创建引擎并测试
    ai_client = MockAIClient()
    engine = ThemeDiscoveryEngine(ai_client)
    
    themes = await engine.discover_from_events(test_events)
    
    print(f"✅ 测试完成: 发现 {len(themes)} 个主题")
    for theme in themes:
        print(f"   主题: {theme['name']}, 置信度: {theme['confidence']:.2f}")
    
    return len(themes) > 0

if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(test_theme_discovery())
    
    if success:
        print("\n🎉 主题发现引擎测试通过！")
        print("   可以开始下一步开发")
    else:
        print("\n⚠️  测试存在问题")
