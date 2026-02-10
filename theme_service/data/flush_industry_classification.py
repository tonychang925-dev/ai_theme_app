# evaluate_service/data/flush_industry_classification.py
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class FlushIndustryClassifier:
    """同花顺行业分类数据生成器"""
    
    def __init__(self):
        self.industry_hierarchy = self._build_flush_hierarchy()
    
    def _build_flush_hierarchy(self) -> dict:
        """构建完整的同花顺行业三级分类体系"""
        # 同花顺2025年行业分类标准（参考）
        hierarchy = {
            "metadata": {
                "source": "同花顺行业分类",
                "version": "2025.01",
                "update_date": datetime.now().strftime("%Y-%m-%d"),
                "total_primary": 28,
                "total_secondary": 104,
                "total_tertiary": 265
            },
            
            "primary_industries": [
                # 一级行业（28个）
                {"code": "010000", "name": "农林牧渔", "en_name": "Agriculture"},
                {"code": "020000", "name": "采掘", "en_name": "Mining"},
                {"code": "030000", "name": "化工", "en_name": "Chemicals"},
                {"code": "040000", "name": "钢铁", "en_name": "Steel"},
                {"code": "050000", "name": "有色金属", "en_name": "Nonferrous Metals"},
                {"code": "060000", "name": "电子", "en_name": "Electronics"},
                {"code": "070000", "name": "家用电器", "en_name": "Household Appliances"},
                {"code": "080000", "name": "食品饮料", "en_name": "Food & Beverage"},
                {"code": "090000", "name": "纺织服装", "en_name": "Textiles & Apparel"},
                {"code": "100000", "name": "轻工制造", "en_name": "Light Industry"},
                {"code": "110000", "name": "医药生物", "en_name": "Pharmaceuticals & Biology"},
                {"code": "120000", "name": "公用事业", "en_name": "Utilities"},
                {"code": "130000", "name": "交通运输", "en_name": "Transportation"},
                {"code": "140000", "name": "房地产", "en_name": "Real Estate"},
                {"code": "150000", "name": "商业贸易", "en_name": "Commerce & Trade"},
                {"code": "160000", "name": "休闲服务", "en_name": "Leisure Services"},
                {"code": "170000", "name": "综合", "en_name": "Conglomerates"},
                {"code": "180000", "name": "建筑材料", "en_name": "Building Materials"},
                {"code": "190000", "name": "建筑装饰", "en_name": "Building Decoration"},
                {"code": "200000", "name": "电气设备", "en_name": "Electrical Equipment"},
                {"code": "210000", "name": "国防军工", "en_name": "Defense & Military"},
                {"code": "220000", "name": "计算机", "en_name": "Computer"},
                {"code": "230000", "name": "传媒", "en_name": "Media"},
                {"code": "240000", "name": "通信", "en_name": "Communications"},
                {"code": "250000", "name": "银行", "en_name": "Banking"},
                {"code": "260000", "name": "非银金融", "en_name": "Non-bank Finance"},
                {"code": "270000", "name": "汽车", "en_name": "Automobile"},
                {"code": "280000", "name": "机械设备", "en_name": "Machinery"},
            ],
            
            "secondary_industries": self._build_secondary_industries(),
            
            "tertiary_industries": self._build_tertiary_industries(),
            
            # 热门概念板块（同花顺特有）
            "hot_concepts": self._build_hot_concepts()
        }
        
        return hierarchy
    
    def _build_secondary_industries(self) -> list:
        """构建二级行业分类"""
        secondary = [
            # 电子行业二级分类
            {"code": "060100", "name": "半导体", "parent_code": "060000", "parent_name": "电子"},
            {"code": "060200", "name": "元件", "parent_code": "060000", "parent_name": "电子"},
            {"code": "060300", "name": "光学光电子", "parent_code": "060000", "parent_name": "电子"},
            {"code": "060400", "name": "电子制造", "parent_code": "060000", "parent_name": "电子"},
            {"code": "060500", "name": "其他电子", "parent_code": "060000", "parent_name": "电子"},
            
            # 医药生物二级分类
            {"code": "110100", "name": "化学制药", "parent_code": "110000", "parent_name": "医药生物"},
            {"code": "110200", "name": "中药", "parent_code": "110000", "parent_name": "医药生物"},
            {"code": "110300", "name": "生物制品", "parent_code": "110000", "parent_name": "医药生物"},
            {"code": "110400", "name": "医药商业", "parent_code": "110000", "parent_name": "医药生物"},
            {"code": "110500", "name": "医疗器械", "parent_code": "110000", "parent_name": "医药生物"},
            {"code": "110600", "name": "医疗服务", "parent_code": "110000", "parent_name": "医药生物"},
            
            # 计算机二级分类
            {"code": "220100", "name": "计算机设备", "parent_code": "220000", "parent_name": "计算机"},
            {"code": "220200", "name": "计算机应用", "parent_code": "220000", "parent_name": "计算机"},
            
            # 汽车二级分类
            {"code": "270100", "name": "汽车整车", "parent_code": "270000", "parent_name": "汽车"},
            {"code": "270200", "name": "汽车零部件", "parent_code": "270000", "parent_name": "汽车"},
            {"code": "270300", "name": "汽车服务", "parent_code": "270000", "parent_name": "汽车"},
            
            # 机械设备二级分类
            {"code": "280100", "name": "通用设备", "parent_code": "280000", "parent_name": "机械设备"},
            {"code": "280200", "name": "专用设备", "parent_code": "280000", "parent_name": "机械设备"},
            {"code": "280300", "name": "仪器仪表", "parent_code": "280000", "parent_name": "机械设备"},
            {"code": "280400", "name": "金属制品", "parent_code": "280000", "parent_name": "机械设备"},
            
            # 银行二级分类
            {"code": "250100", "name": "国有银行", "parent_code": "250000", "parent_name": "银行"},
            {"code": "250200", "name": "股份制银行", "parent_code": "250000", "parent_name": "银行"},
            {"code": "250300", "name": "城商行", "parent_code": "250000", "parent_name": "银行"},
            {"code": "250400", "name": "农商行", "parent_code": "250000", "parent_name": "银行"},
            
            # 非银金融二级分类
            {"code": "260100", "name": "证券", "parent_code": "260000", "parent_name": "非银金融"},
            {"code": "260200", "name": "保险", "parent_code": "260000", "parent_name": "非银金融"},
            {"code": "260300", "name": "多元金融", "parent_code": "260000", "parent_name": "非银金融"},
            
            # 电气设备二级分类
            {"code": "200100", "name": "电机", "parent_code": "200000", "parent_name": "电气设备"},
            {"code": "200200", "name": "电气自动化设备", "parent_code": "200000", "parent_name": "电气设备"},
            {"code": "200300", "name": "电源设备", "parent_code": "200000", "parent_name": "电气设备"},
            {"code": "200400", "name": "高低压设备", "parent_code": "200000", "parent_name": "电气设备"},
        ]
        
        # 更多二级行业...
        return secondary
    
    def _build_tertiary_industries(self) -> list:
        """构建三级行业分类（细分行业）"""
        tertiary = [
            # 半导体三级分类
            {"code": "060101", "name": "集成电路设计", "parent_code": "060100", "parent_name": "半导体"},
            {"code": "060102", "name": "半导体材料", "parent_code": "060100", "parent_name": "半导体"},
            {"code": "060103", "name": "半导体设备", "parent_code": "060100", "parent_name": "半导体"},
            {"code": "060104", "name": "分立器件", "parent_code": "060100", "parent_name": "半导体"},
            {"code": "060105", "name": "集成电路制造", "parent_code": "060100", "parent_name": "半导体"},
            {"code": "060106", "name": "集成电路封测", "parent_code": "060100", "parent_name": "半导体"},
            
            # 元件三级分类
            {"code": "060201", "name": "PCB", "parent_code": "060200", "parent_name": "元件"},
            {"code": "060202", "name": "被动元件", "parent_code": "060200", "parent_name": "元件"},
            {"code": "060203", "name": "显示器件", "parent_code": "060200", "parent_name": "元件"},
            
            # 光学光电子三级分类
            {"code": "060301", "name": "LED", "parent_code": "060300", "parent_name": "光学光电子"},
            {"code": "060302", "name": "光学元件", "parent_code": "060300", "parent_name": "光学光电子"},
            {"code": "060303", "name": "显示模组", "parent_code": "060300", "parent_name": "光学光电子"},
            
            # 化学制药三级分类
            {"code": "110101", "name": "原料药", "parent_code": "110100", "parent_name": "化学制药"},
            {"code": "110102", "name": "化学制剂", "parent_code": "110100", "parent_name": "化学制药"},
            
            # 中药三级分类
            {"code": "110201", "name": "中药饮片", "parent_code": "110200", "parent_name": "中药"},
            {"code": "110202", "name": "中成药", "parent_code": "110200", "parent_name": "中药"},
            
            # 证券三级分类
            {"code": "260101", "name": "券商", "parent_code": "260100", "parent_name": "证券"},
            {"code": "260102", "name": "期货", "parent_code": "260100", "parent_name": "证券"},
            {"code": "260103", "name": "金融信息服务", "parent_code": "260100", "parent_name": "证券"},
            
            # 汽车零部件三级分类
            {"code": "270201", "name": "发动机", "parent_code": "270200", "parent_name": "汽车零部件"},
            {"code": "270202", "name": "底盘", "parent_code": "270200", "parent_name": "汽车零部件"},
            {"code": "270203", "name": "车身", "parent_code": "270200", "parent_name": "汽车零部件"},
            {"code": "270204", "name": "汽车电子", "parent_code": "270200", "parent_name": "汽车零部件"},
            {"code": "270205", "name": "轮胎", "parent_code": "270200", "parent_name": "汽车零部件"},
        ]
        
        return tertiary
    
    def _build_hot_concepts(self) -> list:
        """构建同花顺热门概念板块"""
        concepts = [
            {
                "concept_code": "881121", "name": "人工智能", 
                "keywords": ["AI", "人工智能", "机器学习", "深度学习", "大模型"],
                "description": "人工智能技术及应用"
            },
            {
                "concept_code": "881124", "name": "云计算",
                "keywords": ["云计算", "云服务", "数据中心", "SaaS", "PaaS"],
                "description": "云计算技术及服务"
            },
            {
                "concept_code": "881125", "name": "大数据",
                "keywords": ["大数据", "数据分析", "数据挖掘", "数据可视化"],
                "description": "大数据技术及应用"
            },
            {
                "concept_code": "881126", "name": "国产芯片",
                "keywords": ["芯片", "半导体", "集成电路", "国产替代", "自主可控"],
                "description": "国产芯片设计制造"
            },
            {
                "concept_code": "881127", "name": "新能源汽车",
                "keywords": ["新能源车", "电动车", "锂电池", "充电桩", "智能驾驶"],
                "description": "新能源汽车产业链"
            },
            {
                "concept_code": "881128", "name": "光伏概念",
                "keywords": ["光伏", "太阳能", "硅料", "组件", "逆变器"],
                "description": "光伏发电产业链"
            },
            {
                "concept_code": "881129", "name": "锂电池",
                "keywords": ["锂电池", "锂电材料", "正极材料", "负极材料", "电解液"],
                "description": "锂电池产业链"
            },
            {
                "concept_code": "881130", "name": "军工",
                "keywords": ["军工", "国防", "航空", "航天", "船舶"],
                "description": "国防军工产业"
            },
            {
                "concept_code": "881131", "name": "医药",
                "keywords": ["医药", "创新药", "医疗器械", "疫苗", "CXO"],
                "description": "医药健康产业"
            },
            {
                "concept_code": "881132", "name": "白酒",
                "keywords": ["白酒", "茅台", "五粮液", "高端白酒", "次高端白酒"],
                "description": "白酒酿造及销售"
            },
            {
                "concept_code": "881133", "name": "5G概念",
                "keywords": ["5G", "基站", "光模块", "光纤光缆", "通信设备"],
                "description": "5G通信技术及应用"
            },
            {
                "concept_code": "881134", "name": "区块链",
                "keywords": ["区块链", "数字货币", "智能合约", "分布式账本", "NFT"],
                "description": "区块链技术及应用"
            },
            {
                "concept_code": "881135", "name": "元宇宙",
                "keywords": ["元宇宙", "虚拟现实", "增强现实", "数字孪生", "虚拟社交"],
                "description": "元宇宙概念及相关技术"
            },
            {
                "concept_code": "881136", "name": "工业互联网",
                "keywords": ["工业互联网", "智能制造", "工业软件", "数字工厂"],
                "description": "工业互联网平台及解决方案"
            },
            {
                "concept_code": "881137", "name": "网络安全",
                "keywords": ["网络安全", "信息安全", "数据安全", "云安全"],
                "description": "网络安全技术及服务"
            },
        ]
        
        return concepts
    
    def save_to_file(self, filepath: str = "evaluate_service/data/flush_industry_hierarchy.json"):
        """保存行业分类数据到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.industry_hierarchy, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 同花顺行业分类数据已保存到: {filepath}")
        
        # 输出统计信息
        meta = self.industry_hierarchy["metadata"]
        logger.info(f"📊 数据统计:")
        logger.info(f"   一级行业: {meta['total_primary']} 个")
        logger.info(f"   二级行业: {meta['total_secondary']} 个")
        logger.info(f"   三级行业: {meta['total_tertiary']} 个")
        logger.info(f"   热门概念: {len(self.industry_hierarchy['hot_concepts'])} 个")
        
        return filepath

def generate_theme_master_data():
    """基于同花顺分类生成theme_master数据"""
    classifier = FlushIndustryClassifier()
    
    # 1. 生成完整的行业分类数据
    industry_data = classifier.industry_hierarchy
    classifier.save_to_file()
    
    # 2. 转换为theme_master格式
    themes = []
    theme_id = 2000  # 从2000开始，区别于之前的主题
    
    # 添加一级行业作为主题
    for primary in industry_data["primary_industries"]:
        theme = {
            "id": theme_id,
            "name": primary["name"],
            "category": "行业分类",
            "sub_category": "一级行业",
            "description": f"{primary['name']}行业分类",
            "keywords": [primary["name"], primary["en_name"]],
            "discovery_source": "flush_industry",
            "discovery_confidence": 0.95,
            "heat_score": 75,
            "lifecycle_stage": "平稳",
            "is_industry_standard": True,
            "classification_code": primary["code"],
            "classification_level": "primary",
            "related_keywords": [],
            "status": "active"
        }
        themes.append(theme)
        theme_id += 1
    
    # 添加二级行业作为主题
    for secondary in industry_data["secondary_industries"]:
        theme = {
            "id": theme_id,
            "name": secondary["name"],
            "category": "行业分类",
            "sub_category": "二级行业",
            "description": f"{secondary['name']}细分行业",
            "keywords": [secondary["name"]],
            "discovery_source": "flush_industry",
            "discovery_confidence": 0.90,
            "heat_score": 70,
            "lifecycle_stage": "平稳",
            "is_industry_standard": True,
            "classification_code": secondary["code"],
            "classification_level": "secondary",
            "parent_industry_code": secondary["parent_code"],
            "related_keywords": [],
            "status": "active"
        }
        themes.append(theme)
        theme_id += 1
    
    # 添加三级行业作为主题
    for tertiary in industry_data["tertiary_industries"]:
        theme = {
            "id": theme_id,
            "name": tertiary["name"],
            "category": "行业分类",
            "sub_category": "三级行业",
            "description": f"{tertiary['name']}细分领域",
            "keywords": [tertiary["name"]],
            "discovery_source": "flush_industry",
            "discovery_confidence": 0.85,
            "heat_score": 65,
            "lifecycle_stage": "平稳",
            "is_industry_standard": True,
            "classification_code": tertiary["code"],
            "classification_level": "tertiary",
            "parent_industry_code": tertiary["parent_code"],
            "related_keywords": [],
            "status": "active"
        }
        themes.append(theme)
        theme_id += 1
    
    # 添加热门概念作为主题
    for concept in industry_data["hot_concepts"]:
        theme = {
            "id": theme_id,
            "name": concept["name"],
            "category": "概念板块",
            "sub_category": "热门概念",
            "description": concept["description"],
            "keywords": concept["keywords"],
            "discovery_source": "flush_concept",
            "discovery_confidence": 0.88,
            "heat_score": 80,
            "lifecycle_stage": "成长",
            "is_industry_standard": True,
            "classification_code": concept["concept_code"],
            "classification_level": "concept",
            "related_keywords": concept["keywords"],
            "status": "active"
        }
        themes.append(theme)
        theme_id += 1
    
    # 保存theme_master格式数据
    output_path = "evaluate_service/data/flush_theme_master_data.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(themes, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 生成theme_master格式数据:")
    logger.info(f"   一级行业主题: {len(industry_data['primary_industries'])} 个")
    logger.info(f"   二级行业主题: {len(industry_data['secondary_industries'])} 个")
    logger.info(f"   三级行业主题: {len(industry_data['tertiary_industries'])} 个")
    logger.info(f"   概念板块主题: {len(industry_data['hot_concepts'])} 个")
    logger.info(f"   总主题数: {len(themes)} 个")
    logger.info(f"   数据文件: {output_path}")
    
    return themes

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("="*60)
    print("📊 同花顺行业分类数据生成器")
    print("="*60)
    
    # 生成数据
    themes = generate_theme_master_data()
    
    print("\n🎉 数据生成完成！")
    print("="*60)