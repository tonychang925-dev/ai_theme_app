import asyncio
from theme_service.services.theme_mapper import map_event_to_themes

test_event = {
    "event_type": "政策",
    "impact_industries": ["半导体", "新能源"],
    "summary": "国家发布支持半导体产业的政策"
}

async def test():
    themes = await map_event_to_themes(test_event)
    print("匹配到的题材：", themes)

asyncio.run(test())
