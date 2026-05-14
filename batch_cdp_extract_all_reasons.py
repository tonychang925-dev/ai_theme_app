#!/usr/bin/env python3
"""
批量 CDP 提取所有题材的个股详细入选理由。

流程:
  1. 从 DB 加载待处理 subject 队列（按 seed 股票数降序）
  2. 逐个导航到 /subject/detail/:id → 题材图谱
  3. 展开全部树节点 + 点击每只股票展开理由
  4. 提取详细入选理由文本 → 入库 subject_child_stock_reason
  5. 断点续跑 + 进度报告

用法:
  # Phase 1: ≥5只种子股票的大题材 (预计 ~350个, ~2小时)
  python batch_cdp_extract_all_reasons.py --phase 1

  # Phase 2: 3-4只 (预计 ~670个, ~3小时)
  python batch_cdp_extract_all_reasons.py --phase 2

  # Phase 3: 1-2只 (预计 ~500个, ~3小时)
  python batch_cdp_extract_all_reasons.py --phase 3

  # 全量 (预计 ~9小时)
  python batch_cdp_extract_all_reasons.py --phase all

  # 断点续跑
  python batch_cdp_extract_all_reasons.py --phase 1 --resume

  # 测试模式
  python batch_cdp_extract_all_reasons.py --phase 1 --limit 5
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg
from cdp_jyhf_collector import CDPClient, ensure_app_running

STATE_FILE = PROJECT_ROOT / "theme_data_complete" / "child_stock_reasons" / "_batch_cdp_state.json"
LOG_FILE = PROJECT_ROOT / "theme_data_complete" / "child_stock_reasons" / "_batch_cdp_log.txt"


# ═══════════════════════════════════════════════════════════
# Queue Management
# ═══════════════════════════════════════════════════════════

async def load_queue(phase: str = "1", limit: int = 0) -> list[dict]:
    """从 subject_child_stock_reason 种子数据加载待处理题材队列。"""
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        # 种子股票数 ≥ N 的题材（种子数据中的 lead_stock 只是冰山一角）
        seed_counts = {
            "1": 5,   # Phase 1: ≥5 lead_stocks → 预计实际 25+ 只股票
            "2": 3,   # Phase 2: 3-4
            "3": 1,   # Phase 3: 1-2
        }
        min_seeds = seed_counts.get(phase, 0)
        max_seeds = {"1": 999, "2": 4, "3": 2}.get(phase, 999)

        rows = await conn.fetch("""
            SELECT subject_key, concept, seed_count
            FROM (
                SELECT scsr.subject_key::varchar,
                       COALESCE(tgp.concept, 'N/A') AS concept,
                       count(*)::int AS seed_count
                FROM subject_child_stock_reason scsr
                JOIN theme_gate_profile tgp ON tgp.subject_key::varchar = scsr.subject_key::varchar
                WHERE scsr.source_type = 'seed_from_staging'
                  AND tgp.concept IS NOT NULL AND tgp.concept != ''
                GROUP BY scsr.subject_key, tgp.concept
            ) t
            WHERE seed_count >= $1::int AND seed_count <= $2::int
            ORDER BY seed_count DESC
        """, min_seeds, max_seeds)

        queue = []
        for r in rows:
            queue.append({
                "subject_key": r["subject_key"],
                "concept": r["concept"] or r["subject_key"],
                "seed_count": r["seed_count"],
            })

        if limit > 0:
            queue = queue[:limit]

        print(f"[QUEUE] Phase {phase}: {len(queue)} subjects "
              f"(seed stocks {min_seeds}-{max_seeds})")
        return queue
    finally:
        await conn.close()


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"completed": [], "errors": [], "total_processed": 0, "total_imported": 0}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════════
# CDP Extraction
# ═══════════════════════════════════════════════════════════

def extract_subject_reasons(cdp: CDPClient, subject_key: str) -> list[dict]:
    """提取单个题材的全部个股详细入选理由。"""
    # Navigate
    cdp.navigate(f"/subject/detail/{subject_key}")
    time.sleep(5)  # Increased wait

    # Click 题材图谱 tab
    cdp.evaluate("""
    (function() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            if (all[i].textContent.trim() === '题材图谱') { all[i].click(); return; }
        }
    })()
    """)
    time.sleep(4)

    # Expand all tree nodes
    for _ in range(5):
        cdp.evaluate("""
        (function() {
            var btns = document.querySelectorAll('.btn-open');
            for (var i = 0; i < btns.length; i++) btns[i].click();
            return btns.length;
        })()
        """)
        time.sleep(0.3)

    # Click on each stock item (level ≥ 3) to reveal reasons
    cdp.evaluate("""
    (function() {
        var items = document.querySelectorAll('[class*="p-tree--level"]');
        var clicked = 0;
        for (var i = 0; i < items.length; i++) {
            var cls = items[i].className || '';
            var m = cls.match(/p-tree--level(\\d+)/);
            var level = m ? parseInt(m[1]) : 0;
            if (level >= 3) {
                var label = items[i].querySelector('.tree-label');
                if (label) { label.click(); clicked++; }
            }
        }
        return clicked;
    })()
    """)
    time.sleep(3)

    # Extract reason text from body
    raw_text = cdp.evaluate("document.body.innerText", timeout=20)
    if not raw_text:
        return []

    return _parse_reasons_text(raw_text)


def _parse_reasons_text(text: str) -> list[dict]:
    """解析 innerText 中的个股入选理由。"""
    # 找到题材图谱数据区域
    start_markers = ['一键展开', '按涨幅', '题材排名']
    start_idx = 0
    for marker in start_markers:
        idx = text.find(marker)
        if idx >= 0:
            start_idx = idx
            break

    section = text[start_idx:]

    # 分割行
    lines = section.split('\n')
    results = []
    current_stock = None
    current_pct = ''
    current_reason_lines = []

    # 已知跳过词
    skip_words = {
        '返回', '一键展开', '按涨幅', '题材排名', '上一天', '下一天',
        '题材', '排名', '图谱', '介绍', '软件局限性',
        '日线', '周线', '月线', '分时', '甄选K线', '组合K线', '周期图',
        '行业', '情绪',  # badge words
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 跳过已知非数据行
        if line in skip_words or any(line.startswith(w) for w in
            ['上证指数', '深证成指', '创业板指', '深证综指', '搜索']):
            continue

        # 跳过只含数字和特殊字符的行
        if re.match(r'^[\d\s\.\+\-%\*\(\)／]+$', line):
            continue

        # 涨幅行
        if re.match(r'^[+-]?\d+\.\d+%$', line):
            if current_stock:
                current_pct = line
            continue

        # 检测是否是股票名（中文2-8字，可能含ST/*ST/数字后缀）
        is_stock_name = (
            len(line) >= 2 and len(line) <= 15 and
            not line.startswith('20') and  # 不是年份
            not re.match(r'^\d', line) and  # 不以数字开头
            re.search(r'[\u4e00-\u9fff]', line)  # 含中文
        )

        if is_stock_name and current_stock != line:
            # 保存上一个股票的理由
            if current_stock and current_reason_lines:
                reason = ''.join(current_reason_lines).strip()
                if len(reason) > 5:
                    results.append({
                        'stock_name': current_stock,
                        'pct_chg': current_pct,
                        'reason': reason,
                    })
            current_stock = line
            current_pct = ''
            current_reason_lines = []
            continue

        # 理由文本（非股票名、非涨幅的长文本）
        if current_stock and len(line) > 3:
            current_reason_lines.append(line)

    # 最后一只
    if current_stock and current_reason_lines:
        reason = ''.join(current_reason_lines).strip()
        if len(reason) > 5:
            results.append({
                'stock_name': current_stock,
                'pct_chg': current_pct,
                'reason': reason,
            })

    return results


# ═══════════════════════════════════════════════════════════
# DB Import
# ═══════════════════════════════════════════════════════════

async def import_reasons(subject_key: str, items: list[dict]) -> int:
    """将提取的详细理由导入 subject_child_stock_reason。"""
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        # Get stock_id mapping
        stock_names = list(set(i['stock_name'] for i in items))
        name_to_id = {}
        if stock_names:
            rows = await conn.fetch("""
                SELECT DISTINCT stock_id, stock_name FROM stock_profile_ext
                WHERE stock_name = ANY($1::varchar[])
            """, stock_names)
            for r in rows:
                name_to_id[r['stock_name']] = r['stock_id']

        count = 0
        for item in items:
            name = item['stock_name']
            sid = name_to_id.get(name, '')
            if not sid:
                for n, i in name_to_id.items():
                    if n.replace(' ', '') == name.replace(' ', ''):
                        sid = i
                        break
            if not sid:
                continue

            # 先尝试 UPDATE 已有种子记录
            result = await conn.execute("""
                UPDATE subject_child_stock_reason
                SET reason = $1::text, pct_chg = $2::varchar,
                    source_type = 'cdp_dom_detailed',
                    updated_at = NOW()
                WHERE subject_key = $3::varchar AND stock_id = $4::varchar
            """, item['reason'], item.get('pct_chg', ''), subject_key, sid)

            # 解析 UPDATE 影响行数（asyncpg execute 返回 "UPDATE N"）
            updated = 0
            try:
                updated = int(result.split()[-1]) if result else 0
            except (ValueError, IndexError):
                pass

            if updated == 0:
                await conn.execute("""
                    INSERT INTO subject_child_stock_reason
                        (subject_key, child_name, stock_id, stock_name, reason, pct_chg, source_type)
                    VALUES ($1::varchar, 'cdp_extracted', $2::varchar, $3::varchar, $4::text, $5::varchar, 'cdp_dom_detailed')
                    ON CONFLICT DO NOTHING
                """, subject_key, sid, name, item['reason'], item.get('pct_chg', ''))

            count += 1

        return count
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch CDP extract JYHF detailed stock reasons")
    parser.add_argument("--phase", default="1", choices=["1", "2", "3", "all"],
                        help="Phase: 1(≥5 seeds), 2(3-4), 3(1-2), all")
    parser.add_argument("--limit", type=int, default=0, help="Limit subjects (test mode)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--skip-launch", action="store_true", help="App already running")
    args = parser.parse_args()

    # Load queue
    queue = await load_queue(args.phase, args.limit)

    # Resume: skip completed
    state = load_state()
    completed_set = set(state.get("completed", []))
    queue = [s for s in queue if s["subject_key"] not in completed_set]

    if not queue:
        log("[DONE] All subjects already processed")
        return

    log(f"[START] {len(queue)} subjects to process "
        f"(already done: {len(completed_set)})")

    # Launch app
    if not args.skip_launch:
        ensure_app_running()

    # Connect CDP
    def connect_cdp():
        try:
            c = CDPClient()
            c.connect()
            return c
        except Exception as e:
            log(f"[CDP] Connection failed: {e}, retrying in 5s...")
            time.sleep(5)
            c = CDPClient()
            c.connect()
            return c

    cdp = connect_cdp()
    log("[CDP] Connected")

    # Process
    start_time = time.time()
    total_imported = state.get("total_imported", 0)

    try:
        for i, subj in enumerate(queue):
            sk = subj["subject_key"]
            concept = subj["concept"]
            elapsed = time.time() - start_time
            rate = (i + 1) / (elapsed / 60) if elapsed > 0 else 0
            eta = (len(queue) - i - 1) / rate if rate > 0 else 0

            log(f"\n[{i+1}/{len(queue)}] {sk} {concept} "
                f"(seeds={subj['seed_count']}) "
                f"rate={rate:.1f}/min ETA={eta:.0f}min")

            try:
                items = extract_subject_reasons(cdp, sk)

                if items:
                    imported = await import_reasons(sk, items)
                    total_imported += imported
                    log(f"  [OK] {len(items)} items extracted, {imported} imported to DB")
                else:
                    log(f"  [EMPTY] No reasons extracted")

                state["completed"].append(sk)
                state["total_processed"] = i + 1 + len(completed_set)
                state["total_imported"] = total_imported

            except Exception as e:
                log(f"  [ERROR] {e}")
                state["errors"].append({"subject_key": sk, "error": str(e)[:200]})
                # CDP 断连时重新连接
                if "Broken pipe" in str(e) or "Connection" in str(e):
                    try:
                        cdp.close()
                    except:
                        pass
                    time.sleep(3)
                    try:
                        cdp = connect_cdp()
                        log(f"  [RECONNECT] CDP reconnected")
                        # Retry this subject once
                        items = extract_subject_reasons(cdp, sk)
                        if items:
                            imported = await import_reasons(sk, items)
                            total_imported += imported
                            log(f"  [RETRY OK] {len(items)} items, {imported} imported")
                            state["completed"].append(sk)
                            state["total_processed"] = i + 1 + len(completed_set)
                            state["total_imported"] = total_imported
                            # Remove from errors
                            state["errors"] = [e2 for e2 in state["errors"] if e2["subject_key"] != sk]
                    except Exception as e2:
                        log(f"  [RETRY FAIL] {e2}")

            # Save state every 10 subjects
            if (i + 1) % 10 == 0:
                save_state(state)
                total_elapsed = (time.time() - start_time) / 60
                log(f"\n[CHECKPOINT @ {total_elapsed:.0f}min] "
                    f"{state['total_processed']} done, "
                    f"{total_imported} total imported, "
                    f"{len(state['errors'])} errors")

            # Brief pause between subjects
            time.sleep(0.5)

    except KeyboardInterrupt:
        log("\n[INTERRUPT] Saving state...")
    finally:
        cdp.close()
        save_state(state)

    total_min = (time.time() - start_time) / 60
    log(f"\n{'='*60}")
    log(f"[DONE] {state['total_processed']} subjects in {total_min:.0f}min")
    log(f"       {total_imported} total reasons imported")
    log(f"       {len(state['errors'])} errors")
    log(f"       State saved to {STATE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
