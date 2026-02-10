# theme_service/database/complete_theme_data.py
"""
补全完整的题材数据库数据
包含完整的分类体系和题材
"""
import asyncio
import asyncpg
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def complete_theme_data():
    """补全完整的题材数据库"""
    db_url = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(db_url)
    
    try:
        print("="*60)
        print("📚 补全完整的题材数据库数据")
        print("="*60)
        
        # 首先检查当前数据
        count = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        print(f"当前已有 {count} 个题材")
        
        # 如果数据较少，建议清空重新开始
        if count < 50:
            choice = input(f"当前只有 {count} 个题材，是否清空并重新构建完整数据库？(y/N): ")
            if choice.lower() == 'y':
                await conn.execute("DELETE FROM theme_master")
                print("🗑️ 已清空现有数据")
            else:
                print("⏹️ 保留现有数据")
        
        # 定义完整的分类体系和题材
        theme_hierarchy = {
            # ========== 一级分类 ==========
            "国际关系与地缘政治": {
                "二级分类": {
                    "中日关系": [
                        {
                            "name": "对日出口管制题材",
                            "code": "THEME_SJ_EXPORT",
                            "description": "中国对日本两用物项出口管制相关政策及市场影响",
                            "keywords": ["出口管制", "两用物项", "日本", "制裁", "贸易限制", "半导体材料", "技术封锁", "贸易战", "禁运"],
                            "aliases": ["对日贸易限制", "出口禁令", "技术封锁题材", "半导体管制"],
                            "merge_candidates": ["贸易制裁", "技术出口管制", "国际贸易争端"],
                            "industries": ["半导体", "化工", "材料科学"],
                            "concepts": ["国家安全", "产业保护", "技术自主"],
                            "heat_score": 88,
                            "theme_type": "relation",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "中日外交会谈题材",
                            "code": "THEME_SJ_DIPLOMACY",
                            "description": "中日高层外交会谈及双边关系动态对市场的影响",
                            "keywords": ["外交会谈", "双边关系", "高层会晤", "外交磋商", "中日外交", "首脑会议", "外交渠道", "战略对话"],
                            "aliases": ["外交对话", "双边会谈", "外交往来", "高层对话"],
                            "merge_candidates": ["外交关系", "国际对话", "多边会谈"],
                            "industries": ["外交", "国际贸易", "文化交流"],
                            "concepts": ["软实力", "国际影响力", "外交政策"],
                            "heat_score": 82,
                            "theme_type": "relation",
                            "confidence_score": 0.8
                        },
                        {
                            "name": "东海争端题材",
                            "code": "THEME_SJ_EAST_CHINA_SEA",
                            "description": "东海领土争端及相关地缘政治对能源和航运的影响",
                            "keywords": ["东海", "钓鱼岛", "领土争端", "海警", "主权", "海洋权益", "油气资源", "渔业资源", "海上安全"],
                            "aliases": ["钓鱼岛争端", "东海主权", "海洋争端", "东海油气"],
                            "merge_candidates": ["领土争议", "海洋权益争端", "资源开发"],
                            "industries": ["海洋工程", "油气勘探", "航运物流", "渔业"],
                            "concepts": ["海洋强国", "资源安全", "主权完整"],
                            "heat_score": 79,
                            "theme_type": "relation",
                            "confidence_score": 0.75
                        },
                        {
                            "name": "日企在华投资题材",
                            "code": "THEME_SJ_INVESTMENT",
                            "description": "日本企业在华投资布局调整及产业转移",
                            "keywords": ["日本投资", "产业转移", "日企", "制造业回流", "供应链调整", "对华投资", "产业政策"],
                            "aliases": ["日资题材", "日本制造业", "供应链重构"],
                            "merge_candidates": ["外资投资", "产业转移", "供应链安全"],
                            "industries": ["汽车制造", "电子设备", "精密仪器"],
                            "concepts": ["外商投资", "产业升级", "技术合作"],
                            "heat_score": 75,
                            "theme_type": "relation",
                            "confidence_score": 0.8
                        }
                    ],
                    "中美关系": [
                        {
                            "name": "中美贸易摩擦题材",
                            "code": "THEME_SU_TRADE",
                            "description": "中美贸易关税、技术封锁等经贸摩擦相关影响",
                            "keywords": ["贸易战", "关税", "301调查", "技术封锁", "芯片禁令", "实体清单", "出口管制", "供应链安全"],
                            "aliases": ["中美贸易战", "关税摩擦", "技术冷战"],
                            "merge_candidates": ["国际贸易争端", "技术脱钩", "全球化重构"],
                            "industries": ["半导体", "消费电子", "机械设备"],
                            "concepts": ["自主可控", "国产替代", "双循环"],
                            "heat_score": 85,
                            "theme_type": "relation",
                            "confidence_score": 0.9
                        },
                        {
                            "name": "中美科技竞争题材",
                            "code": "THEME_SU_TECH",
                            "description": "中美在人工智能、芯片、量子计算等领域的竞争",
                            "keywords": ["科技竞争", "芯片战争", "AI竞赛", "量子计算", "技术标准", "专利竞争", "研发投入"],
                            "aliases": ["技术竞争", "创新竞赛", "高科技博弈"],
                            "merge_candidates": ["科技强国", "创新驱动", "技术自主"],
                            "industries": ["半导体", "人工智能", "量子技术", "航空航天"],
                            "concepts": ["科技自立", "原始创新", "前沿技术"],
                            "heat_score": 88,
                            "theme_type": "relation",
                            "confidence_score": 0.85
                        }
                    ],
                    "中欧关系": [
                        {
                            "name": "中欧投资协定题材",
                            "code": "THEME_SE_INVESTMENT",
                            "description": "中欧全面投资协定谈判及实施相关影响",
                            "keywords": ["中欧投资", "CAI", "市场准入", "公平竞争", "可持续发展", "绿色转型", "数字经济"],
                            "aliases": ["欧中协定", "投资协议", "经济合作"],
                            "merge_candidates": ["多边合作", "经济一体化", "国际协议"],
                            "industries": ["新能源汽车", "可再生能源", "金融服务"],
                            "concepts": ["开放合作", "规则对接", "互惠互利"],
                            "heat_score": 78,
                            "theme_type": "relation",
                            "confidence_score": 0.8
                        }
                    ]
                }
            },
            # ========== 大科技 ==========
            "大科技": {
                "二级分类": {
                    "人工智能": [
                        {
                            "name": "ChatGPT概念",
                            "code": "THEME_AI_CHATGPT",
                            "description": "OpenAI ChatGPT及相关大语言模型技术产业链",
                            "keywords": ["ChatGPT", "大语言模型", "对话AI", "文本生成", "OpenAI", "GPT-4", "自然语言处理", "智能对话", "内容生成"],
                            "aliases": ["对话式AI", "语言模型", "生成式AI", "文本AI"],
                            "merge_candidates": ["自然语言处理", "文本AI", "AI聊天", "智能客服"],
                            "industries": ["软件服务", "云计算", "互联网内容"],
                            "concepts": ["数字经济", "智能化转型", "内容革命"],
                            "heat_score": 92,
                            "theme_type": "concept",
                            "confidence_score": 0.9
                        },
                        {
                            "name": "AIGC应用",
                            "code": "THEME_AI_AIGC",
                            "description": "AI生成内容在各行业的应用场景",
                            "keywords": ["AIGC", "文生图", "代码生成", "AI创作", "Midjourney", "Stable Diffusion", "AI绘画", "智能设计", "创意生成"],
                            "aliases": ["AI生成内容", "生成式AI应用", "AI创作工具", "创意AI"],
                            "merge_candidates": ["内容生成", "创意AI", "AI设计", "智能媒体"],
                            "industries": ["媒体娱乐", "广告营销", "游戏开发", "建筑设计"],
                            "concepts": ["内容创新", "创作效率", "个性化定制"],
                            "heat_score": 88,
                            "theme_type": "concept",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "智能驾驶",
                            "code": "THEME_AI_AUTODRIVE",
                            "description": "自动驾驶与智能交通系统",
                            "keywords": ["自动驾驶", "ADAS", "车路协同", "高精地图", "激光雷达", "毫米波雷达", "智能座舱", "无人驾驶", "车联网"],
                            "aliases": ["无人驾驶", "自动驾驶技术", "智能交通", "智慧出行"],
                            "merge_candidates": ["辅助驾驶", "车联网", "智慧交通", "汽车电子"],
                            "industries": ["汽车制造", "汽车电子", "物联网", "地图导航"],
                            "concepts": ["智慧城市", "出行革命", "交通安全"],
                            "heat_score": 85,
                            "theme_type": "concept",
                            "confidence_score": 0.88
                        },
                        {
                            "name": "机器人与智能制造",
                            "code": "THEME_AI_ROBOT",
                            "description": "工业机器人、服务机器人及智能制造系统",
                            "keywords": ["工业机器人", "服务机器人", "协作机器人", "智能制造", "工业4.0", "机器视觉", "运动控制", "自动化"],
                            "aliases": ["工业自动化", "智能装备", "机器人技术", "无人工厂"],
                            "merge_candidates": ["自动化设备", "智能工厂", "高端装备"],
                            "industries": ["机械设备", "自动化", "电子制造"],
                            "concepts": ["制造强国", "产业升级", "生产效率"],
                            "heat_score": 82,
                            "theme_type": "concept",
                            "confidence_score": 0.8
                        }
                    ],
                    "半导体": [
                        {
                            "name": "芯片设计题材",
                            "code": "THEME_SEMI_DESIGN",
                            "description": "集成电路设计及相关EDA软件",
                            "keywords": ["芯片设计", "EDA", "集成电路", "IP核", "SoC", "IC设计", "设计软件", "模拟芯片", "数字芯片"],
                            "aliases": ["IC设计", "半导体设计", "芯片研发", "电路设计"],
                            "merge_candidates": ["芯片研发", "设计软件", "知识产权核"],
                            "industries": ["半导体设计", "软件服务", "集成电路"],
                            "concepts": ["自主可控", "技术创新", "高端芯片"],
                            "heat_score": 85,
                            "theme_type": "concept",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "晶圆制造题材",
                            "code": "THEME_SEMI_FAB",
                            "description": "晶圆制造及半导体设备",
                            "keywords": ["晶圆制造", "半导体设备", "光刻机", "刻蚀", "薄膜沉积", "清洗设备", "测试设备", "封装测试", "中芯国际"],
                            "aliases": ["芯片制造", "半导体生产", "制造设备", "晶圆代工"],
                            "merge_candidates": ["制造工艺", "生产设备", "先进制程"],
                            "industries": ["半导体制造", "设备制造", "材料科学"],
                            "concepts": ["制造能力", "产业链安全", "技术突破"],
                            "heat_score": 80,
                            "theme_type": "concept",
                            "confidence_score": 0.8
                        },
                        {
                            "name": "半导体材料题材",
                            "code": "THEME_SEMI_MATERIAL",
                            "description": "半导体制造所需关键材料",
                            "keywords": ["硅片", "光刻胶", "电子气体", "溅射靶材", "CMP材料", "封装材料", "高纯试剂", "化合物半导体"],
                            "aliases": ["芯片材料", "半导体化学品", "电子材料", "先进材料"],
                            "merge_candidates": ["新材料", "关键材料", "电子化学品"],
                            "industries": ["化工材料", "有色金属", "精细化工"],
                            "concepts": ["材料突破", "供应链安全", "国产替代"],
                            "heat_score": 78,
                            "theme_type": "concept",
                            "confidence_score": 0.75
                        }
                    ],
                    "5G通信": [
                        {
                            "name": "5G基站建设题材",
                            "code": "THEME_5G_BASE",
                            "description": "5G网络基础设施建设及设备",
                            "keywords": ["5G基站", "网络建设", "天线射频", "光模块", "光纤光缆", "网络设备", "通信设备", "小基站"],
                            "aliases": ["网络建设", "通信基建", "5G设备", "基站设备"],
                            "merge_candidates": ["通信网络", "新基建", "数字基建"],
                            "industries": ["通信设备", "光通信", "网络建设"],
                            "concepts": ["新基建", "数字经济", "网络强国"],
                            "heat_score": 80,
                            "theme_type": "concept",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "5G应用场景题材",
                            "code": "THEME_5G_APP",
                            "description": "5G在工业互联网、车联网等场景的应用",
                            "keywords": ["工业互联网", "车联网", "智慧医疗", "云游戏", "AR/VR", "远程控制", "物联网", "边缘计算"],
                            "aliases": ["5G应用", "行业应用", "场景落地", "万物互联"],
                            "merge_candidates": ["物联网应用", "行业数字化", "智能场景"],
                            "industries": ["工业软件", "医疗信息", "游戏娱乐"],
                            "concepts": ["数字化转型", "产业融合", "应用创新"],
                            "heat_score": 78,
                            "theme_type": "concept",
                            "confidence_score": 0.8
                        }
                    ]
                }
            },
            # ========== 大新能源 ==========
            "大新能源": {
                "二级分类": {
                    "新能源汽车": [
                        {
                            "name": "电动汽车整车题材",
                            "code": "THEME_EV_VEHICLE",
                            "description": "电动汽车整车制造及品牌",
                            "keywords": ["电动汽车", "新能源汽车", "电动车", "造车新势力", "特斯拉", "比亚迪", "蔚来", "理想", "小鹏"],
                            "aliases": ["新能源车", "电动车制造", "智能汽车", "电动化"],
                            "merge_candidates": ["汽车制造", "智能出行", "低碳交通"],
                            "industries": ["汽车制造", "汽车零部件", "电池电机"],
                            "concepts": ["绿色出行", "能源转型", "产业升级"],
                            "heat_score": 86,
                            "theme_type": "industry",
                            "confidence_score": 0.9
                        },
                        {
                            "name": "动力电池题材",
                            "code": "THEME_EV_BATTERY",
                            "description": "锂电池、固态电池等动力电池技术",
                            "keywords": ["锂电池", "动力电池", "宁德时代", "比亚迪电池", "固态电池", "钠离子电池", "电池材料", "电池回收", "电池管理"],
                            "aliases": ["电池技术", "储能电池", "电池制造", "电池产业链"],
                            "merge_candidates": ["储能技术", "电池材料", "新能源存储"],
                            "industries": ["电池制造", "材料科学", "化工"],
                            "concepts": ["能源存储", "技术进步", "循环经济"],
                            "heat_score": 85,
                            "theme_type": "industry",
                            "confidence_score": 0.88
                        },
                        {
                            "name": "充电设施题材",
                            "code": "THEME_EV_CHARGING",
                            "description": "充电桩、换电站等基础设施",
                            "keywords": ["充电桩", "充电站", "换电站", "充电网络", "超级充电", "无线充电", "充电运营", "能源服务"],
                            "aliases": ["充电设施", "充电基建", "换电模式", "充电服务"],
                            "merge_candidates": ["能源基建", "公共服务", "智慧能源"],
                            "industries": ["电力设备", "工程建设", "能源服务"],
                            "concepts": ["新基建", "能源网络", "便利出行"],
                            "heat_score": 82,
                            "theme_type": "industry",
                            "confidence_score": 0.85
                        }
                    ],
                    "光伏": [
                        {
                            "name": "光伏组件题材",
                            "code": "THEME_PV_MODULE",
                            "description": "光伏组件制造及高效电池技术",
                            "keywords": ["光伏组件", "太阳能电池", "PERC", "TOPCon", "HJT", "IBC", "钙钛矿", "光伏制造", "太阳能"],
                            "aliases": ["太阳能组件", "光伏电池", "光伏生产", "光伏技术"],
                            "merge_candidates": ["太阳能技术", "可再生能源", "清洁能源"],
                            "industries": ["光伏设备", "新能源", "材料科学"],
                            "concepts": ["绿色能源", "技术迭代", "成本下降"],
                            "heat_score": 81,
                            "theme_type": "industry",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "光伏逆变器题材",
                            "code": "THEME_PV_INVERTER",
                            "description": "光伏逆变器及储能变流器",
                            "keywords": ["光伏逆变器", "储能变流器", "组串式", "集中式", "微型逆变器", "华为逆变器", "阳光电源", "锦浪科技"],
                            "aliases": ["逆变器", "电力电子", "电能转换", "光伏电气"],
                            "merge_candidates": ["电力设备", "电能质量", "智能电网"],
                            "industries": ["电力设备", "电子制造", "新能源"],
                            "concepts": ["电能转换", "智能控制", "系统集成"],
                            "heat_score": 80,
                            "theme_type": "industry",
                            "confidence_score": 0.85
                        }
                    ],
                    "风电": [
                        {
                            "name": "风电设备题材",
                            "code": "THEME_WIND_EQUIP",
                            "description": "风电机组及核心零部件制造",
                            "keywords": ["风电机组", "风力发电", "叶片", "齿轮箱", "发电机", "塔筒", "海上风电", "陆上风电", "风机设备"],
                            "aliases": ["风力设备", "风电制造", "风机部件", "风电技术"],
                            "merge_candidates": ["新能源设备", "发电设备", "大型装备"],
                            "industries": ["电力设备", "重型机械", "复合材料"],
                            "concepts": ["清洁能源", "大型装备", "海洋经济"],
                            "heat_score": 78,
                            "theme_type": "industry",
                            "confidence_score": 0.8
                        }
                    ]
                }
            },
            # ========== 大消费 ==========
            "大消费": {
                "二级分类": {
                    "食品饮料": [
                        {
                            "name": "白酒题材",
                            "code": "THEME_FOOD_LIQUOR",
                            "description": "高端白酒品牌及消费升级",
                            "keywords": ["白酒", "茅台", "五粮液", "高端白酒", "酱香型", "浓香型", "次高端", "白酒消费", "酒文化"],
                            "aliases": ["白酒板块", "酒类投资", "高端酒", "饮酒消费"],
                            "merge_candidates": ["消费升级", "文化消费", "奢侈品消费"],
                            "industries": ["食品饮料", "酿造", "零售"],
                            "concepts": ["文化传承", "品牌价值", "消费分级"],
                            "heat_score": 84,
                            "theme_type": "industry",
                            "confidence_score": 0.9
                        },
                        {
                            "name": "调味品题材",
                            "code": "THEME_FOOD_SEASONING",
                            "description": "酱油、醋等调味品及复合调味料",
                            "keywords": ["酱油", "醋", "蚝油", "调味品", "复合调味", "海天味业", "千禾味业", "中炬高新", "厨邦"],
                            "aliases": ["调味板块", "厨房经济", "餐桌消费"],
                            "merge_candidates": ["食品制造", "家庭消费", "餐饮产业链"],
                            "industries": ["食品制造", "餐饮", "零售"],
                            "concepts": ["日常消费", "家庭经济", "品质生活"],
                            "heat_score": 78,
                            "theme_type": "industry",
                            "confidence_score": 0.85
                        }
                    ],
                    "家用电器": [
                        {
                            "name": "智能家电题材",
                            "code": "THEME_HOME_SMART",
                            "description": "智能家居及小家电创新",
                            "keywords": ["智能家居", "扫地机器人", "智能音箱", "小家电", "物联网家电", "智能控制", "家庭机器人", "清洁电器"],
                            "aliases": ["智慧家庭", "智能设备", "家电创新", "生活电器"],
                            "merge_candidates": ["物联网应用", "家庭科技", "消费电子"],
                            "industries": ["家电制造", "电子设备", "物联网"],
                            "concepts": ["智慧生活", "便利生活", "科技消费"],
                            "heat_score": 82,
                            "theme_type": "industry",
                            "confidence_score": 0.85
                        },
                        {
                            "name": "白色家电题材",
                            "code": "THEME_HOME_WHITE",
                            "description": "空调、冰箱、洗衣机等传统家电",
                            "keywords": ["空调", "冰箱", "洗衣机", "白色家电", "格力", "美的", "海尔", "家电下乡", "家电更新"],
                            "aliases": ["传统家电", "大家电", "家电消费", "耐用品消费"],
                            "merge_candidates": ["耐用消费品", "家庭设备", "更新换代"],
                            "industries": ["家电制造", "零售", "售后服务"],
                            "concepts": ["消费升级", "更新需求", "家庭投资"],
                            "heat_score": 76,
                            "theme_type": "industry",
                            "confidence_score": 0.8
                        }
                    ]
                }
            }
        }
        
        # 插入数据
        total_inserted = 0
        
        print("\n📝 开始插入数据...")
        for level1, level1_data in theme_hierarchy.items():
            print(f"\n🌟 一级分类: {level1}")
            
            for level2, themes in level1_data["二级分类"].items():
                print(f"  📍 二级分类: {level2}")
                
                for theme_data in themes:
                    # 检查是否已存在
                    exists = await conn.fetchval(
                        "SELECT COUNT(*) FROM theme_master WHERE code = $1",
                        theme_data["code"]
                    )
                    
                    if exists > 0:
                        print(f"    ⏭️  已存在: {theme_data['name']}")
                        continue
                    
                    # 准备tags数据
                    tags = {
                        "keywords": theme_data["keywords"],
                        "aliases": theme_data["aliases"],
                        "merge_candidates": theme_data.get("merge_candidates", []),
                        "industries": theme_data.get("industries", []),
                        "concepts": theme_data.get("concepts", []),
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    await conn.execute("""
                        INSERT INTO theme_master 
                        (name, code, description, level1_category, level2_category, 
                         level3_category, category_path, tags, theme_type, 
                         heat_score, confidence_score, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                        theme_data["name"],
                        theme_data["code"],
                        theme_data["description"],
                        level1,
                        level2,
                        theme_data["name"],
                        [level1, level2, theme_data["name"]],
                        json.dumps(tags, ensure_ascii=False),
                        theme_data["theme_type"],
                        theme_data["heat_score"],
                        theme_data.get("confidence_score", 0.8),
                        "active"
                    )
                    
                    total_inserted += 1
                    print(f"    ✅ 新增: {theme_data['name']} (热度: {theme_data['heat_score']})")
        
        # 统计结果
        print("\n" + "="*60)
        print("📊 数据插入完成")
        print("="*60)
        
        # 总体统计
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT level1_category) as level1_count,
                COUNT(DISTINCT level2_category) as level2_count,
                COUNT(DISTINCT theme_type) as type_count,
                AVG(heat_score) as avg_heat
            FROM theme_master
            WHERE status = 'active'
        """)
        
        print(f"总体统计:")
        print(f"  总题材数: {stats['total']}")
        print(f"  一级分类数: {stats['level1_count']}")
        print(f"  二级分类数: {stats['level2_count']}")
        print(f"  题材类型数: {stats['type_count']}")
        print(f"  平均热度: {stats['avg_heat']:.1f}")
        
        # 分类统计
        category_stats = await conn.fetch("""
            SELECT level1_category, level2_category, COUNT(*) as theme_count
            FROM theme_master
            WHERE status = 'active'
            GROUP BY level1_category, level2_category
            ORDER BY level1_category, theme_count DESC
        """)
        
        print(f"\n📁 分类统计:")
        current_level1 = None
        for stat in category_stats:
            if stat['level1_category'] != current_level1:
                current_level1 = stat['level1_category']
                print(f"\n  🌟 {current_level1}:")
            print(f"    📍 {stat['level2_category']}: {stat['theme_count']} 个题材")
        
        # 热门题材TOP10
        hot_themes = await conn.fetch("""
            SELECT name, level1_category, level2_category, heat_score, theme_type
            FROM theme_master
            WHERE status = 'active'
            ORDER BY heat_score DESC
            LIMIT 10
        """)
        
        print(f"\n🔥 热门题材TOP10:")
        for i, theme in enumerate(hot_themes, 1):
            print(f"  {i:2d}. {theme['name']} (热度: {theme['heat_score']})")
            print(f"      分类: {theme['level1_category']} → {theme['level2_category']}")
            print(f"      类型: {theme['theme_type']}")
        
        print(f"\n🎉 数据补全完成！新增 {total_inserted} 个题材")
        
    except Exception as e:
        logger.error(f"❌ 数据插入失败: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(complete_theme_data())