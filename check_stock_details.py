#!/usr/bin/env python3
"""
检查股票详细信息
"""
import asyncio
import asyncpg
from datetime import date

async def main():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("连接数据库...")
    conn = await asyncpg.connect(**config)

    try:
        today_date = date(2026, 4, 10)
        prev_date = date(2026, 4, 9)

        # 获取2026-04-10日所有股票
        print(f"\n获取{today_date}日所有股票:")
        all_stocks = await conn.fetch("""
            SELECT stock_id, stock_name, subject_key, pct_chg, is_leader, rank_order
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            ORDER BY rank_order NULLS LAST
        """, today_date)

        print(f"   共找到{len(all_stocks)}条记录")

        # 显示前20条
        print(f"\n前20条记录:")
        for i, stock in enumerate(all_stocks[:20], 1):
            print(f"   {i}. {stock['stock_id']} - {stock['stock_name']}")
            print(f"      主题: {stock['subject_key']}, 排名: {stock['rank_order']}")
            print(f"      涨跌幅: {stock['pct_chg']}%, 是否龙头: {stock['is_leader']}")

        # 检查主题映射
        print(f"\n检查主题映射:")

        # 获取独特的subject_key
        unique_subjects = await conn.fetch("""
            SELECT DISTINCT subject_key
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            LIMIT 10
        """, today_date)

        print(f"   独特的subject_key值:")
        for i, subj in enumerate(unique_subjects, 1):
            subject_key = subj['subject_key']

            # 尝试在theme_master中查找
            theme_match = await conn.fetch("""
                SELECT name, code, heat_score
                FROM theme_master
                WHERE code = $1
                LIMIT 1
            """, subject_key)

            if theme_match:
                theme = theme_match[0]
                print(f"   {i}. {subject_key} -> {theme['name']} (热度: {theme['heat_score']})")
            else:
                # 尝试查找相似的
                similar_themes = await conn.fetch("""
                    SELECT name, code, heat_score
                    FROM theme_master
                    WHERE code LIKE $1 || '%'
                    LIMIT 3
                """, str(subject_key)[:3])

                if similar_themes:
                    print(f"   {i}. {subject_key} -> 未直接匹配，相似主题:")
                    for sim in similar_themes:
                        print(f"       可能: {sim['code']} - {sim['name']} (热度: {sim['heat_score']})")
                else:
                    print(f"   {i}. {subject_key} -> 无匹配主题")

        # 检查弱转强候选
        print(f"\n检查潜在弱转强候选:")
        candidates = []

        for stock in all_stocks[:30]:  # 检查前30只
            stock_id = stock['stock_id']

            # 获取前一日数据
            prev_data = await conn.fetch("""
                SELECT pct_chg, is_leader
                FROM subject_stock_daily_snapshot
                WHERE trade_date = $1
                AND stock_id = $2
            """, prev_date, stock_id)

            if prev_data:
                prev_pct_chg = prev_data[0]['pct_chg']
                today_pct_chg = stock['pct_chg']

                # 简单弱转强判断
                is_weak_to_strong = False
                reason = ""

                if prev_pct_chg and today_pct_chg:
                    if prev_pct_chg < -2.0 and today_pct_chg > 0:
                        is_weak_to_strong = True
                        reason = f"前一日跌{prev_pct_chg:.2f}%，今日涨{today_pct_chg:.2f}%"
                    elif prev_pct_chg < -5.0 and today_pct_chg > -1.0:
                        is_weak_to_strong = True
                        reason = f"前一日大跌{prev_pct_chg:.2f}%，今日止跌{today_pct_chg:.2f}%"

                if is_weak_to_strong:
                    candidates.append({
                        'stock_id': stock_id,
                        'stock_name': stock['stock_name'],
                        'prev_pct_chg': prev_pct_chg,
                        'today_pct_chg': today_pct_chg,
                        'reason': reason
                    })

        print(f"   找到{len(candidates)}个潜在弱转强候选:")
        for i, cand in enumerate(candidates, 1):
            print(f"   {i}. {cand['stock_id']} - {cand['stock_name']}")
            print(f"      前一日: {cand['prev_pct_chg']:.2f}%, 今日: {cand['today_pct_chg']:.2f}%")
            print(f"      理由: {cand['reason']}")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())