import logging
from typing import List, Dict
from theme_service.models.theme import fetch_all_themes

logger = logging.getLogger(__name__)

# 假设这是你的映射规则示范：
# 事件类型和影响行业匹配对应主题ID的简单字典
RULES = {
    "资本": {
        "金融": 10,
        "证券": 11,
    },
    "其他": {
        "国防安全": 20,
        "地缘政治": 21,
        "航空运输": 22,
        "政府": 23,
        "公共管理": 24,
        "旅游业": 25,
        "娱乐业": 26,
    },
    "产业": {
        "交通运输": 30,
        "旅游": 31,
        "零售": 32,
        "餐饮": 33,
        "电影": 34,
        "文化传媒": 35,
    },
    "政策": {
        "交通建设": 40,
        "城市规划": 41,
        "房地产": 42,
    }
    # 根据日志继续添加
}

async def map_event_to_themes(event):
    """
    示例映射函数，基于 event_type 和 impact_industries 简单匹配。
    会打印详细日志，帮助调试。
    """
    logger.info(f"Mapping event: {event}")

    matched_themes = []

    event_type = event.get("event_type", "").strip()
    industries = event.get("impact_industries", [])

    if not event_type or not industries:
        logger.warning("Event missing event_type or impact_industries, skipping mapping.")
        return matched_themes

    logger.info(f"Event type: {event_type}, industries: {industries}")

    # 逐行业匹配
    for industry in industries:
        industry = industry.strip()
        theme_id = RULES.get(event_type, {}).get(industry)
        if theme_id:
            confidence = 0.9  # 你可以自定义置信度
            logger.info(f"Matched theme_id {theme_id} for event_type '{event_type}' and industry '{industry}'")
            matched_themes.append({"theme_id": theme_id, "confidence": confidence})
        else:
            logger.info(f"No match for industry '{industry}' under event_type '{event_type}'")

    logger.info(f"Total matched themes: {len(matched_themes)}")

    return matched_themes