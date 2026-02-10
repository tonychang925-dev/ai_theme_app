import asyncio
import asyncpg
import logging

DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"

# 主题列表示例，包含id、name、category、keywords、description、status
themes = [
    (1, '金融', '资本市场', ['银行', '信贷', '理财'], '涵盖银行、信贷及各类金融服务的主题。', 'active'),
    (2, '证券', '资本市场', ['股票', '债券', '基金'], '证券市场相关主题，包括股票、债券、基金等。', 'active'),
    (3, '科技', '行业', ['人工智能', '半导体', '软件'], '科技行业相关主题，聚焦新技术和创新。', 'active'),
    (4, '新能源', '行业', ['风能', '太阳能', '电池'], '新能源产业相关主题，关注清洁能源发展。', 'active'),
    (5, '汽车', '行业', ['电动车', '传统汽车', '自动驾驶'], '汽车行业相关主题，包括电动汽车与自动驾驶技术。', 'active'),
    (6, '医药', '行业', ['制药', '医疗器械', '生物技术'], '医药行业主题，涵盖制药及医疗器械领域。', 'active'),
    (7, '消费', '行业', ['零售', '品牌', '电商'], '消费品和零售市场相关主题。', 'active'),
    (8, '互联网', '行业', ['电子商务', '社交媒体', '云计算'], '互联网及相关服务行业主题。', 'active'),
    (9, '房地产', '行业', ['住宅', '商业地产', '土地'], '房地产市场及开发相关主题。', 'active'),
    (10, '基建', '行业', ['交通运输', '建筑工程', '基础设施'], '基础设施建设相关主题。', 'active'),
    (11, '资本市场', '资本市场', ['股市', '融资', '并购'], '资本市场相关的宏观主题。', 'active'),
    (12, '政策', '政策法规', ['政府政策', '法规', '监管'], '政策和法规方面的主题。', 'active'),
    (13, '环保', '行业', ['环境保护', '污染治理', '可持续发展'], '环保及可持续发展相关主题。', 'active'),
    (14, '军工', '行业', ['国防', '武器制造', '军用设备'], '军工及国防产业主题。', 'active'),
    (15, '文化传媒', '行业', ['影视', '出版', '广告'], '文化及传媒产业相关主题。', 'active'),
    (16, '物流', '行业', ['仓储', '运输', '供应链'], '物流与供应链管理主题。', 'active'),
    (17, '教育', '行业', ['在线教育', '学校', '培训'], '教育产业相关主题。', 'active'),
    (18, '农业', '行业', ['种植', '养殖', '农产品'], '农业及农产品相关主题。', 'active'),
    (19, '食品饮料', '行业', ['食品加工', '饮料制造', '餐饮'], '食品与饮料产业主题。', 'active'),
    (20, '旅游', '行业', ['景区', '酒店', '旅行社'], '旅游行业及相关服务。', 'active'),
    (21, '互联网安全', '行业', ['网络安全', '信息安全', '数据保护'], '互联网安全及信息保护。', 'active'),
    (22, '半导体', '行业', ['芯片', '制造', '设计'], '半导体产业链相关主题。', 'active'),
    (23, '电子元器件', '行业', ['传感器', '电阻', '连接器'], '电子元器件产业。', 'active'),
    (24, '5G通信', '行业', ['通信设备', '基站', '网络'], '5G及通信行业。', 'active'),
    (25, '人工智能', '行业', ['机器学习', '深度学习', '自动化'], '人工智能领域相关主题。', 'active'),
    (26, '区块链', '行业', ['加密货币', '分布式账本', '智能合约'], '区块链及相关技术。', 'active'),
    (27, '电力', '行业', ['发电', '输电', '配电'], '电力行业主题。', 'active'),
    (28, '航空航天', '行业', ['航天器', '卫星', '航空制造'], '航空航天产业。', 'active'),
    (29, '医疗器械', '行业', ['诊断设备', '治疗设备'], '医疗器械产业主题。', 'active'),
    (30, '大数据', '行业', ['数据分析', '云计算', '存储'], '大数据及云计算技术。', 'active'),
    (31, '零售', '行业', ['连锁', '电商', '便利店'], '零售行业及消费品销售。', 'active'),
    (32, '餐饮', '行业', ['餐厅', '快餐', '食品加工'], '餐饮行业及食品服务。', 'active'),
]

async def init_theme_master():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for theme in themes:
            theme_id, name, category, keywords, description, status = theme
            await conn.execute("""
                INSERT INTO theme_master (id, name, category, keywords, description, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name) DO UPDATE SET
                    category = EXCLUDED.category,
                    keywords = EXCLUDED.keywords,
                    description = EXCLUDED.description,
                    status = EXCLUDED.status
            """, theme_id, name, category, keywords, description, status)
        print(f"Inserted or updated {len(themes)} themes into theme_master")
    except Exception as e:
        logging.error(f"Error inserting themes: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(init_theme_master())

