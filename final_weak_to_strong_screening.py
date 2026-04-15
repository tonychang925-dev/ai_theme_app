#!/usr/bin/env python3
"""
最终弱转强筛选报告
基于真实数据库4/10日数据的弱转强筛选
使用简单涨跌幅逻辑识别弱转强候选
"""
import asyncio
import asyncpg
from datetime import date, timedelta
from typing import List, Dict, Any
import json

async def main():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("=" * 80)
    print("真实数据库弱转强筛选最终报告")
    print("基于2026-04-10日股票数据")
    print("=" * 80)

    # 连接数据库
    print("\n连接数据库...")
    conn = await asyncpg.connect(**config)

    try:
        trade_date = date(2026, 4, 10)
        prev_date = trade_date - timedelta(days=1)

        print(f"交易日期: {trade_date}")
        print(f"前一日日期: {prev_date}")

        # 1. 获取有前一日数据的股票
        print(f"\n1. 获取有前一日数据的股票...")

        query = """
        SELECT
            t1.stock_id,
            t1.stock_name,
            t1.subject_key,
            t1.pct_chg as today_pct_chg,
            t1.is_leader as today_is_leader,
            t1.rank_order,
            t2.pct_chg as prev_pct_chg,
            t2.is_leader as prev_is_leader
        FROM subject_stock_daily_snapshot t1
        INNER JOIN subject_stock_daily_snapshot t2
            ON t1.stock_id = t2.stock_id
            AND t2.trade_date = $2
        WHERE t1.trade_date = $1
        ORDER BY t1.rank_order NULLS LAST
        LIMIT 200
        """

        stocks = await conn.fetch(query, trade_date, prev_date)
        print(f"   获取到 {len(stocks)} 只有前一日数据的股票")

        # 2. 识别弱转强候选
        print(f"\n2. 识别弱转强候选...")

        candidates = []
        for stock in stocks:
            stock_dict = dict(stock)
            stock_id = stock_dict['stock_id']
            stock_name = stock_dict['stock_name']
            subject_key = stock_dict['subject_key']

            today_pct_chg = float(stock_dict['today_pct_chg']) if stock_dict['today_pct_chg'] is not None else None
            prev_pct_chg = float(stock_dict['prev_pct_chg']) if stock_dict['prev_pct_chg'] is not None else None

            if today_pct_chg is None or prev_pct_chg is None:
                continue

            # 弱转强判断逻辑
            is_weak_to_strong = False
            reason = ""
            score = 0

            # 条件1: 前一日弱势 (跌幅 > 2%)
            prev_day_weak = prev_pct_chg < -2.0

            # 条件2: 今日转强
            today_strong = False
            if prev_day_weak:
                # 今日上涨且比前一日表现好
                if today_pct_chg > 0 and today_pct_chg > prev_pct_chg + 3.0:
                    today_strong = True
                    reason = f"前一日跌{prev_pct_chg:.2f}%，今日涨{today_pct_chg:.2f}%"
                    score = 70 + min(30, today_pct_chg * 2)  # 基础分70 + 今日涨幅加权
                # 或者前一日大跌，今日止跌
                elif prev_pct_chg < -5.0 and today_pct_chg > -1.0:
                    today_strong = True
                    reason = f"前一日大跌{prev_pct_chg:.2f}%，今日止跌{today_pct_chg:.2f}%"
                    score = 65 + min(35, (today_pct_chg - prev_pct_chg) * 3)  # 反弹幅度加权

            if prev_day_weak and today_strong:
                # 获取主题信息
                theme_name = f"主题_{subject_key}"
                try:
                    theme_query = """
                    SELECT name, heat_score
                    FROM theme_master
                    WHERE code = $1
                    LIMIT 1
                    """
                    theme_row = await conn.fetch(theme_query, subject_key)
                    if theme_row:
                        theme_name = theme_row[0]['name']
                        heat_score = theme_row[0]['heat_score']
                        # 热度加权
                        if heat_score > 80:
                            score += 10
                        elif heat_score > 60:
                            score += 5
                    else:
                        heat_score = 50
                except:
                    heat_score = 50

                # 龙头股加权
                if stock_dict['today_is_leader']:
                    score += 10
                    reason += " (龙头股)"

                # 限制分数在0-100之间
                score = max(0, min(100, score))

                candidates.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'subject_key': subject_key,
                    'theme_name': theme_name,
                    'heat_score': heat_score,
                    'prev_pct_chg': prev_pct_chg,
                    'today_pct_chg': today_pct_chg,
                    'reason': reason,
                    'score': score,
                    'is_leader': stock_dict['today_is_leader'],
                    'rank_order': stock_dict['rank_order']
                })

        print(f"   识别到 {len(candidates)} 个弱转强候选")

        # 3. 按评分排序
        candidates.sort(key=lambda x: x['score'], reverse=True)

        # 4. 显示结果
        print(f"\n3. 弱转强候选列表 (前20名):")
        print("-" * 80)

        if candidates:
            for i, cand in enumerate(candidates[:20], 1):
                print(f"{i:2d}. {cand['stock_name']} ({cand['stock_id']})")
                print(f"    主题: {cand['theme_name']} (热度: {cand['heat_score']})")
                print(f"    评分: {cand['score']:.1f}/100 | 排名: {cand['rank_order']} | 龙头: {cand['is_leader']}")
                print(f"    前一日: {cand['prev_pct_chg']:6.2f}% → 今日: {cand['today_pct_chg']:6.2f}%")
                print(f"    理由: {cand['reason']}")
                print()
        else:
            print("    未找到弱转强候选股票")

        # 5. 统计信息
        print(f"\n4. 统计信息:")
        print(f"   分析股票数量: {len(stocks)}")
        print(f"   弱转强候选数量: {len(candidates)}")

        if candidates:
            avg_score = sum(c['score'] for c in candidates) / len(candidates)
            high_score_count = len([c for c in candidates if c['score'] >= 70])
            leader_count = len([c for c in candidates if c['is_leader']])

            print(f"   平均评分: {avg_score:.1f}/100")
            print(f"   高评分候选 (≥70): {high_score_count} 个")
            print(f"   龙头股: {leader_count} 个")

            # 主题分布
            theme_counts = {}
            for cand in candidates:
                theme = cand['theme_name']
                theme_counts[theme] = theme_counts.get(theme, 0) + 1

            print(f"   主题分布:")
            for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"     - {theme}: {count} 只股票")

        # 6. 检查神剑股份
        print(f"\n5. 神剑股份检查:")
        shenjian_found = False
        for cand in candidates:
            if cand['stock_id'] == '002361.SZ':
                shenjian_found = True
                print(f"   ✅ 神剑股份 (002361.SZ) 在候选列表中")
                print(f"      排名: {cand['rank_order']}, 评分: {cand['score']:.1f}")
                print(f"      前一日: {cand['prev_pct_chg']:.2f}%, 今日: {cand['today_pct_chg']:.2f}%")
                break

        if not shenjian_found:
            print(f"   ❌ 神剑股份未在候选列表中")

            # 检查神剑股份是否在数据库中
            shenjian_query = """
            SELECT stock_id, stock_name, trade_date, pct_chg
            FROM subject_stock_daily_snapshot
            WHERE stock_id = '002361.SZ'
            ORDER BY trade_date DESC
            LIMIT 5
            """
            shenjian_rows = await conn.fetch(shenjian_query)

            if shenjian_rows:
                print(f"   神剑股份在数据库中的最新记录:")
                for row in shenjian_rows:
                    print(f"     {row['trade_date']}: {row['pct_chg']}%")
            else:
                print(f"   数据库中未找到神剑股份记录")

        # 7. 推荐重点关注
        print(f"\n6. 推荐重点关注:")
        if candidates:
            top_candidates = candidates[:3]
            for i, cand in enumerate(top_candidates, 1):
                print(f"   {i}. {cand['stock_name']} ({cand['stock_id']})")
                print(f"      评分: {cand['score']:.1f}/100, 理由: {cand['reason']}")

            print(f"\n   操作建议:")
            print(f"   1. 重点关注前3名弱转强候选")
            print(f"   2. 结合主题热度分析主线题材")
            print(f"   3. 检查龙头股在主题中的表现")
            print(f"   4. 观察次日集合竞价表现")
        else:
            print(f"   无弱转强候选，建议观望")

        # 8. 数据质量评估
        print(f"\n7. 数据质量评估:")

        # 检查主题映射
        theme_map_query = """
        SELECT COUNT(DISTINCT subject_key) as distinct_subjects
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1
        """
        distinct_subjects = await conn.fetch(theme_map_query, trade_date)

        theme_match_query = """
        SELECT COUNT(DISTINCT tm.code) as matched_themes
        FROM subject_stock_daily_snapshot ss
        JOIN theme_master tm ON ss.subject_key = tm.code
        WHERE ss.trade_date = $1
        """
        matched_themes = await conn.fetch(theme_match_query, trade_date)

        print(f"   独特主题键: {distinct_subjects[0]['distinct_subjects']}")
        print(f"   匹配的主题: {matched_themes[0]['matched_themes']}")

        if matched_themes[0]['matched_themes'] == 0:
            print(f"   ⚠️  主题映射不匹配: subject_key与theme_master.code不一致")

        # 检查前一日数据覆盖率
        coverage_query = """
        SELECT
            COUNT(DISTINCT t1.stock_id) as today_stocks,
            COUNT(DISTINCT t2.stock_id) as prev_day_stocks,
            ROUND(COUNT(DISTINCT t2.stock_id) * 100.0 / NULLIF(COUNT(DISTINCT t1.stock_id), 0), 1) as coverage_rate
        FROM subject_stock_daily_snapshot t1
        LEFT JOIN subject_stock_daily_snapshot t2
            ON t1.stock_id = t2.stock_id
            AND t2.trade_date = $2
        WHERE t1.trade_date = $1
        """
        coverage = await conn.fetch(coverage_query, trade_date, prev_date)

        print(f"   今日股票数: {coverage[0]['today_stocks']}")
        print(f"   有前一日数据的股票: {coverage[0]['prev_day_stocks']}")
        print(f"   前一日数据覆盖率: {coverage[0]['coverage_rate']}%")

        print(f"\n{'='*80}")
        print(f"弱转强筛选完成!")
        print(f"{'='*80}")

    finally:
        await conn.close()
        print("数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())