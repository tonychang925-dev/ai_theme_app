import tushare as ts
import pandas as pd
import asyncio
import asyncpg
from datetime import datetime

# ========== 配置区 ==========
# 替换为你自己的Tushare Pro Token
TUSHARE_TOKEN = '55fbe131c105b584daaff3e4f86681ad6e74ed8a5df1e9401edc0a7e'
# 你的数据库连接字符串
DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
# 申万行业版本 (SW2021 或最新版，如SW2023，可在Tushare文档查看)
SW_VERSION = 'SW2021'
# ===========================

# 设置Token
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

import time  # 新增导入

def fetch_sw_all_levels():
    """获取申万行业完整三级分类数据（带频率控制）"""
    print("🔄 开始从Tushare获取申万行业分类数据...")
    
    try:
        # 1. 获取一级分类（行业门类）
        print("  正在获取一级行业门类...")
        df_l1 = pro.index_classify(level='L1', src='SW2021')
        print(f"  获取到 {len(df_l1)} 个一级行业")
        
        # 2. 获取二级分类（行业大类）
        print("  正在获取二级行业大类...")
        all_l2 = []
        for idx, row in df_l1.iterrows():
            df_l2 = pro.index_classify(level='L2', src='SW2021', parent_code=row['industry_code'])
            all_l2.append(df_l2)
            time.sleep(0.1)  # 轻微延迟避免触发限制
        df_l2_all = pd.concat(all_l2, ignore_index=True)
        print(f"  获取到 {len(df_l2_all)} 个二级行业")
        
        # 3. 获取三级分类（行业中类 - 关键修改部分）
        print("  正在获取三级行业中类（此步骤较慢，请耐心等待）...")
        all_l3 = []
        total_l2 = len(df_l2_all)
        
        for idx, row in df_l2_all.iterrows():
            try:
                df_l3 = pro.index_classify(level='L3', src='SW2021', parent_code=row['industry_code'])
                all_l3.append(df_l3)
                
                # 进度显示
                if (idx + 1) % 10 == 0 or (idx + 1) == total_l2:
                    print(f"    进度: {idx + 1}/{total_l2}，已获取 {len(pd.concat(all_l3, ignore_index=True))} 个三级行业")
                
                # 关键：每次请求后暂停1.5秒，确保不超过频率限制
                # 每分钟50次 = 每次间隔至少1.2秒，这里用1.5秒更安全
                time.sleep(1.5)
                
            except Exception as e:
                print(f"    ⚠️ 获取失败 {row['industry_code']}: {e}")
                print(f"    等待5秒后继续...")
                time.sleep(5)  # 遇到错误等待更久
                continue
        
        if all_l3:
            df_l3_all = pd.concat(all_l3, ignore_index=True)
            print(f"  成功获取到 {len(df_l3_all)} 个三级行业")
        else:
            df_l3_all = pd.DataFrame()
            print("  ⚠️ 未获取到任何三级行业数据")
        
        print("✅ 数据获取完成")
        return df_l1, df_l2_all, df_l3_all
        
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return None, None, None

def fetch_sw_constituents(industry_code):
    """
    获取单个三级行业的成分股列表
    """
    try:
        df = pro.index_member(index_code=industry_code)
        return df[['con_code', 'con_name']] if not df.empty else pd.DataFrame()
    except Exception as e:
        print(f"  获取成分股失败 {industry_code}: {e}")
        return pd.DataFrame()

async def save_sw_to_database(df_l1, df_l2, df_l3):
    """
    将申万行业数据保存到数据库
    """
    if df_l1 is None:
        print("❌ 无有效数据，跳过数据库保存")
        return False
    
    conn = None
    try:
        print("\n💾 正在连接数据库并保存数据...")
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 开始事务
        async with conn.transaction():
            # 1. 保存到 financial_categories 表（专业分类表）
            print("  保存到 financial_categories 表...")
            
            # 清空旧的申万数据（可选，注意备份）
            await conn.execute("DELETE FROM financial_categories WHERE source_system = 'shenwan_tushare'")
            
            # 插入一级
            for _, row in df_l1.iterrows():
                await conn.execute("""
                    INSERT INTO financial_categories 
                    (category_code, category_name, category_level, parent_code, 
                     category_type, source_system, description)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, 
                    row['industry_code'], 
                    row['industry_name'], 
                    1, 
                    None,
                    'industry', 
                    'shenwan_tushare', 
                    f"申万一级行业[{SW_VERSION}]：{row['industry_name']}"
                )
            
            # 插入二级
            for _, row in df_l2.iterrows():
                await conn.execute("""
                    INSERT INTO financial_categories 
                    (category_code, category_name, category_level, parent_code,
                     category_type, source_system)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    row['industry_code'], 
                    row['industry_name'], 
                    2, 
                    row['parent_code'],
                    'industry', 
                    'shenwan_tushare'
                )
            
            # 插入三级
            for _, row in df_l3.iterrows():
                # 查询父级信息用于构建路径
                parent_info = await conn.fetchrow(
                    "SELECT category_name, parent_code FROM financial_categories WHERE category_code = $1",
                    row['parent_code']
                )
                
                if parent_info:
                    l2_name = parent_info['category_name']
                    l1_code = parent_info['parent_code']
                    l1_info = await conn.fetchrow(
                        "SELECT category_name FROM financial_categories WHERE category_code = $1",
                        l1_code
                    )
                    l1_name = l1_info['category_name'] if l1_info else ''
                    
                    full_path = [l1_name, l2_name, row['industry_name']]
                    
                    await conn.execute("""
                        INSERT INTO financial_categories 
                        (category_code, category_name, category_level, parent_code,
                         full_path, category_type, source_system)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                        row['industry_code'], 
                        row['industry_name'], 
                        3, 
                        row['parent_code'],
                        full_path, 
                        'industry', 
                        'shenwan_tushare'
                    )
            
            # 2. 保存到 theme_master 表（你的题材主表）
            print("  保存到 theme_master 表...")
            for _, row in df_l3.iterrows():
                # 获取完整分类信息
                cat_info = await conn.fetchrow("""
                    SELECT fc1.category_name as l1_name, fc1.category_code as l1_code,
                           fc2.category_name as l2_name, fc2.category_code as l2_code,
                           fc3.full_path
                    FROM financial_categories fc3
                    LEFT JOIN financial_categories fc2 ON fc3.parent_code = fc2.category_code
                    LEFT JOIN financial_categories fc1 ON fc2.parent_code = fc1.category_code
                    WHERE fc3.category_code = $1 AND fc3.source_system = 'shenwan_tushare'
                """, row['industry_code'])
                
                if cat_info:
                    # 获取该行业的成分股
                    constituents = fetch_sw_constituents(row['industry_code'])
                    stock_codes = constituents['con_code'].tolist()[:20] if not constituents.empty else []  # 限制前20只，避免数组过大
                    
                    theme_code = f"SW_{row['industry_code']}"
                    
                    # 插入或更新题材
                    await conn.execute("""
                        INSERT INTO theme_master 
                        (name, code, description, level1_category, level2_category, 
                         level3_category, category_path, theme_type, heat_score, 
                         category1_code, category2_code, category3_code,
                         related_stocks, source_system, source_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                        ON CONFLICT (code) DO UPDATE SET
                        name = EXCLUDED.name,
                        level1_category = EXCLUDED.level1_category,
                        level2_category = EXCLUDED.level2_category,
                        level3_category = EXCLUDED.level3_category,
                        category_path = EXCLUDED.category_path,
                        related_stocks = EXCLUDED.related_stocks,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                        row['industry_name'],          # name
                        theme_code,                    # code
                        f"申万行业分类[{SW_VERSION}]：{row['industry_name']}",  # description
                        cat_info['l1_name'],           # level1_category
                        cat_info['l2_name'],           # level2_category
                        row['industry_name'],          # level3_category
                        cat_info['full_path'],         # category_path
                        'industry',                    # theme_type
                        65,                            # heat_score (行业默认65)
                        cat_info['l1_code'],           # category1_code
                        cat_info['l2_code'],           # category2_code
                        row['industry_code'],          # category3_code
                        stock_codes,                   # related_stocks
                        'tushare',                     # source_system
                        row['industry_code']           # source_id
                    )
        
        print("✅ 申万行业数据已成功保存到数据库！")
        return True
        
    except Exception as e:
        print(f"❌ 数据库保存失败: {e}")
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    """主函数"""
    print("="*60)
    print("📊 申万行业分类数据获取与入库程序")
    print("="*60)
    
    # 1. 获取数据
    df_l1, df_l2, df_l3 = fetch_sw_all_levels()
    
    if df_l1 is not None and len(df_l3) > 0:
        # 2. 显示预览
        print(f"\n📋 数据预览:")
        print(f"  一级行业示例: {df_l1['industry_name'].tolist()[:3]}")
        print(f"  三级行业总数: {len(df_l3)} 个")
        print(f"  三级行业示例:")
        for i, row in df_l3.head(3).iterrows():
            print(f"    • {row['industry_name']} ({row['industry_code']})")
        
        # 3. 保存到数据库
        success = await save_sw_to_database(df_l1, df_l2, df_l3)
        
        if success:
            print(f"\n🎉 程序执行成功！")
            print(f"   已获取 {len(df_l3)} 个申万三级行业（题材）")
            print(f"   数据已保存到 theme_master 和 financial_categories 表")
        else:
            print(f"\n⚠️  程序执行完成，但数据库保存可能存在问题")
    else:
        print("❌ 未能获取有效数据，请检查Token权限或网络连接")

if __name__ == "__main__":
    # 运行主程序
    asyncio.run(main())