# theme_service/data/standard_themes_v2.py
"""
标准题材库数据 - 三级分类版本
"""

# 一级分类：10大行业板块
PRIMARY_CATEGORIES = [
    {"code": "P_TECH", "name": "大科技", "description": "科技创新与数字化转型产业", "priority": 1},
    {"code": "P_ENERGY", "name": "大新能源", "description": "能源转型与碳中和相关产业", "priority": 2},
    {"code": "P_CONSUME", "name": "大消费", "description": "居民消费与零售服务产业", "priority": 3},
    {"code": "P_MEDICAL", "name": "大医药", "description": "医疗健康与生物医药产业", "priority": 4},
    {"code": "P_CYCLE", "name": "大周期", "description": "经济周期敏感性基础产业", "priority": 5},
    {"code": "P_MANUFACTURE", "name": "大制造", "description": "高端制造与工业升级产业", "priority": 6},
    {"code": "P_FINANCE", "name": "大金融", "description": "金融服务与资本中介产业", "priority": 7},
    {"code": "P_GEO", "name": "国际关系与地缘政治", "description": "国际关系对经济和市场的影响", "priority": 8},
    {"code": "P_POLICY", "name": "政策主题", "description": "国家政策驱动的投资主题", "priority": 9},
    {"code": "P_UTILITY", "name": "公用事业", "description": "公共事业与基础设施产业", "priority": 10},
]

# 二级分类
SECONDARY_CATEGORIES = [
    # 大科技下的二级分类
    {
        "code": "S_AI",
        "name": "人工智能",
        "parent_code": "P_TECH",
        "description": "人工智能技术及应用全产业链",
        "tags": {
            "keywords": ["AI", "人工智能", "大模型", "机器学习", "深度学习", "AIGC"],
            "aliases": ["AI技术", "人工智能技术", "智能算法"],
            "merge_candidates": ["智能计算", "算法"],
            "industries": ["软件", "互联网"],
            "concepts": ["数字经济", "数字化转型"]
        }
    },
    {
        "code": "S_SEMI",
        "name": "半导体",
        "parent_code": "P_TECH",
        "description": "半导体设计、制造、封测全产业链",
        "tags": {
            "keywords": ["芯片", "半导体", "集成电路", "IC设计", "晶圆制造", "封装测试"],
            "aliases": ["芯片产业", "集成电路产业"],
            "merge_candidates": ["微电子", "芯片制造"],
            "industries": ["电子", "设备制造"],
            "concepts": ["自主可控", "国产替代"]
        }
    },
    {
        "code": "S_CONSUMER_ELECTRONICS",
        "name": "消费电子",
        "parent_code": "P_TECH",
        "description": "智能硬件与消费电子产品",
        "tags": {
            "keywords": ["智能手机", "可穿戴设备", "AR/VR", "智能家居", "TWS耳机", "折叠屏"],
            "aliases": ["电子消费品", "智能硬件"],
            "merge_candidates": ["智能设备", "数码产品"]
        }
    },
    
    # 国际关系与地缘政治（您的核心需求）
    {
        "code": "S_SINO_JAPAN",
        "name": "中日关系",
        "parent_code": "P_GEO",
        "description": "中日双边关系及地缘政治影响",
        "theme_type": "relation",
        "tags": {
            "keywords": ["中日关系", "日本", "靖国神社", "出口管制", "外交施压", "东海", "钓鱼岛"],
            "aliases": ["中日双边关系", "中日外交", "对日关系"],
            "merge_candidates": [
                "对日两用物项出口管制",
                "日政要参拜神社",
                "中日关系紧张升级",
                "对日反制措施",
                "对日外交施压",
                "中日地缘政治紧张"
            ],
            "entities": ["中国", "日本", "外交部", "商务部", "海关总署"],
            "events": ["出口管制政策", "外交会谈", "贸易谈判", "东海争端"],
            "geography": ["中国", "日本", "东海", "钓鱼岛"]
        }
    },
    {
        "code": "S_SINO_US",
        "name": "中美关系",
        "parent_code": "P_GEO",
        "description": "中美经贸与科技关系",
        "theme_type": "relation",
        "tags": {
            "keywords": ["中美关系", "贸易摩擦", "技术制裁", "芯片禁令", "实体清单", "关税"],
            "aliases": ["中美贸易", "中美外交", "中美科技战"],
            "merge_candidates": ["贸易战", "科技制裁", "出口管制"],
            "entities": ["美国", "中国", "商务部", "白宫"],
            "events": ["贸易谈判", "制裁措施", "高层会晤"]
        }
    },
    
    # 大新能源下的二级分类
    {
        "code": "S_EV",
        "name": "新能源汽车",
        "parent_code": "P_ENERGY",
        "description": "电动汽车及配套产业链",
        "tags": {
            "keywords": ["新能源汽车", "电动车", "锂电池", "充电桩", "智能驾驶", "特斯拉"],
            "aliases": ["电动车", "新能源车", "电动汽车"],
            "merge_candidates": ["电动车产业链", "锂电池汽车"],
            "industries": ["汽车制造", "电池"],
            "concepts": ["碳中和", "绿色出行"]
        }
    },
]

# 三级分类（示例）
TERTIARY_CATEGORIES = [
    # 人工智能下的三级分类
    {
        "code": "T_AIGC",
        "name": "AIGC应用",
        "parent_code": "S_AI",
        "description": "AI生成内容的具体应用场景",
        "tags": {
            "keywords": ["ChatGPT", "Midjourney", "文生图", "代码生成", "智能写作"],
            "aliases": ["AI生成内容", "生成式AI"],
            "merge_candidates": ["AI创作", "智能生成"],
            "industries": ["内容创作", "软件开发"],
            "concepts": ["内容科技", "创意经济"]
        }
    },
    {
        "code": "T_AUTODRIVE",
        "name": "智能驾驶",
        "parent_code": "S_AI",
        "description": "自动驾驶与智能交通系统",
        "tags": {
            "keywords": ["自动驾驶", "ADAS", "车路协同", "高精地图", "激光雷达"],
            "aliases": ["无人驾驶", "自动驾驶技术"],
            "merge_candidates": ["辅助驾驶", "智能交通"],
            "industries": ["汽车电子", "交通"],
            "concepts": ["智慧交通", "车联网"]
        }
    },
]