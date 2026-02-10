# theme_service/data/standard_themes.py
"""
标准题材库数据结构定义
参考同花顺、东方财富，涵盖10大板块，三级分类
"""

STANDARD_THEMES_CONFIG = {
    "metadata": {
        "version": "2.0",
        "created_at": "2025-01-16",
        "source": "综合同花顺、东方财富、申万行业分类",
        "description": "金融投资AI助理标准题材库"
    },
    
    # ========== 一级分类：10大行业板块 ==========
    "primary_categories": [
        {
            "id": "tech",
            "name": "大科技",
            "description": "科技创新与数字化转型产业",
            "priority": 1
        },
        {
            "id": "new_energy", 
            "name": "大新能源",
            "description": "能源转型与碳中和相关产业",
            "priority": 2
        },
        {
            "id": "consumption",
            "name": "大消费", 
            "description": "居民消费与零售服务产业",
            "priority": 3
        },
        {
            "id": "medical",
            "name": "大医药",
            "description": "医疗健康与生物医药产业", 
            "priority": 4
        },
        {
            "id": "cyclical",
            "name": "大周期",
            "description": "经济周期敏感性基础产业",
            "priority": 5
        },
        {
            "id": "manufacturing",
            "name": "大制造",
            "description": "高端制造与工业升级产业",
            "priority": 6
        },
        {
            "id": "finance",
            "name": "大金融",
            "description": "金融服务与资本中介产业",
            "priority": 7
        },
        {
            "id": "geopolitical",
            "name": "国际关系与地缘政治",
            "description": "国际关系对经济和市场的影响",
            "priority": 8
        },
        {
            "id": "policy",
            "name": "政策主题",
            "description": "国家政策驱动的投资主题",
            "priority": 9
        },
        {
            "id": "utilities", 
            "name": "公用事业",
            "description": "公共事业与基础设施产业",
            "priority": 10
        }
    ],
    
    # ========== 二级分类：细分行业 ==========
    "secondary_categories": [
        # 大科技下的二级分类
        {
            "id": "tech_ai",
            "name": "人工智能",
            "parent_id": "tech",
            "keywords": ["AI", "人工智能", "大模型", "机器学习", "深度学习", "AIGC"],
            "description": "人工智能技术及应用全产业链"
        },
        {
            "id": "tech_semiconductor",
            "name": "半导体",
            "parent_id": "tech",
            "keywords": ["芯片", "半导体", "集成电路", "IC设计", "晶圆制造", "封装测试"],
            "description": "半导体设计、制造、封测全产业链"
        },
        {
            "id": "tech_consumer_electronics",
            "name": "消费电子", 
            "parent_id": "tech",
            "keywords": ["智能手机", "可穿戴设备", "AR/VR", "智能家居", "TWS耳机", "折叠屏"],
            "description": "智能硬件与消费电子产品"
        },
        {
            "id": "tech_5g",
            "name": "5G通信",
            "parent_id": "tech", 
            "keywords": ["5G", "基站", "光模块", "光纤光缆", "卫星互联网", "物联网"],
            "description": "5G及通信设备与技术"
        },
        
        # 大新能源下的二级分类
        {
            "id": "new_energy_ev",
            "name": "新能源汽车",
            "parent_id": "new_energy",
            "keywords": ["新能源汽车", "电动车", "锂电池", "充电桩", "智能驾驶", "特斯拉"],
            "description": "电动汽车及配套产业链"
        },
        {
            "id": "new_energy_pv",
            "name": "光伏",
            "parent_id": "new_energy",
            "keywords": ["光伏", "太阳能", "硅料", "硅片", "电池片", "组件", "逆变器"],
            "description": "太阳能光伏发电全产业链"
        },
        
        # 国际关系与地缘政治（您的核心需求）
        {
            "id": "geo_sino_japan",
            "name": "中日关系",
            "parent_id": "geopolitical",
            "keywords": ["中日关系", "日本", "靖国神社", "出口管制", "外交施压", "东海", "钓鱼岛"],
            "description": "中日双边关系及地缘政治影响",
            "merge_keywords": [
                "对日两用物项出口管制",
                "日政要参拜神社",
                "中日关系紧张升级", 
                "对日反制措施",
                "对日外交施压",
                "中日地缘政治紧张"
            ]
        },
        {
            "id": "geo_sino_us",
            "name": "中美关系",
            "parent_id": "geopolitical",
            "keywords": ["中美关系", "贸易摩擦", "技术制裁", "芯片禁令", "实体清单", "关税"],
            "description": "中美经贸与科技关系"
        }
    ]
}