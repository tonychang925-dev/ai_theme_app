#!/usr/bin/env python3
"""
CDP 提取单个题材的完整 题材图谱 树结构（含个股入选理由 badge）。

用法:
  python extract_subject_tree_cdp.py 9026027
  python extract_subject_tree_cdp.py 9026027 --import-db
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncpg
from cdp_jyhf_collector import CDPClient


def extract_tree(cdp: CDPClient) -> list[dict]:
    """从题材图谱页面提取完整树结构。"""
    # Click all expand buttons recursively
    for _ in range(5):  # multiple rounds for deep nesting
        cdp.evaluate("""
        (function() {
            var btns = document.querySelectorAll('.btn-open');
            for (var i = 0; i < btns.length; i++) btns[i].click();
            return btns.length;
        })()
        """)
        time.sleep(0.3)

    # Full tree extraction using DOM traversal
    js = """
    (function() {
        var results = [];
        var seen = {};

        // Find the root tree container
        var rootTree = document.querySelector('.c-tree');
        if (!rootTree) { return JSON.stringify([]); }

        // Find all tree items
        var allItems = rootTree.querySelectorAll('[class*="p-tree--level"]');

        for (var i = 0; i < allItems.length; i++) {
            var el = allItems[i];

            // Get level
            var cls = el.className || '';
            var m = cls.match(/p-tree--level(\\d+)/);
            var level = m ? parseInt(m[1]) : 99;

            // Get name
            var label = el.querySelector('.tree-label__text');
            var name = label ? label.textContent.trim() : '';
            if (!name || name.length > 30) continue;

            // Get badge (入选理由)
            var badge = el.querySelector('.badge');
            var reason = badge ? badge.textContent.trim() : '';

            // Get percentage
            var pctEl = el.querySelector('.text-green, .text-red');
            var pct = pctEl ? pctEl.textContent.trim() : '';

            // Leaf node = no btn-open child
            var hasBtnOpen = el.querySelector('.btn-open') !== null;
            var isStock = !hasBtnOpen && level >= 3;

            var key = name + '|' + level;
            if (seen[key]) continue;
            seen[key] = true;

            results.push({
                name: name,
                level: level,
                reason: reason,
                pct_chg: pct,
                has_children: hasBtnOpen,
                is_stock: isStock
            });
        }

        // Build parent chain by walking sibling levels
        // Items are in DOM order, so we can track the current path
        var path = [];
        for (var i = 0; i < results.length; i++) {
            var item = results[i];
            // Pop path items that are at same or higher level
            while (path.length > 0 && path[path.length - 1].level >= item.level) {
                path.pop();
            }
            item.parent_chain = path.map(function(p) { return p.name; });
            item.parent_name = path.length > 0 ? path[path.length - 1].name : '';
            if (item.has_children) {
                path.push(item);
            }
        }

        return JSON.stringify(results);
    })()
    """
    raw = cdp.evaluate(js, timeout=20)
    if not raw:
        return []
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or [])
    except json.JSONDecodeError:
        print(f"[WARN] JSON parse failed, raw: {str(raw)[:200]}")
        return []


async def import_to_db(items: list[dict], subject_key: str) -> int:
    """Import extracted tree items to subject_child_stock_reason."""
    conn = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        # Ensure table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subject_child_stock_reason (
                id BIGSERIAL PRIMARY KEY,
                subject_key VARCHAR(80) NOT NULL,
                child_name VARCHAR(50),
                child_full_name VARCHAR(200),
                stock_id VARCHAR(10) NOT NULL,
                stock_name VARCHAR(100),
                reason TEXT,
                sort_order INTEGER DEFAULT 0,
                parent_chain TEXT,
                pct_chg VARCHAR(20),
                source_type VARCHAR(50) DEFAULT 'cdp_dom',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_child_stock UNIQUE (subject_key, child_name, stock_id)
            )
        """)

        count = 0
        stock_items = [i for i in items if i.get('is_stock')]

        # Get stock_id mapping from DB
        stock_names = list(set(i['name'] for i in stock_items if i['name']))
        name_to_id = {}
        if stock_names:
            rows = await conn.fetch("""
                SELECT DISTINCT stock_id, stock_name FROM stock_profile_ext
                WHERE stock_name = ANY($1::varchar[])
            """, stock_names)
            for r in rows:
                name_to_id[r['stock_name']] = r['stock_id']

        for item in stock_items:
            stock_name = item['name']
            stock_id = name_to_id.get(stock_name, '')
            if not stock_id:
                # Try fuzzy match
                for name, sid in name_to_id.items():
                    if name.replace(' ', '') == stock_name.replace(' ', ''):
                        stock_id = sid
                        break
            if not stock_id:
                print(f"  [SKIP] No code for: {stock_name}")
                continue

            # The first non-stock parent in the chain is the child_name
            parent_chain = item.get('parent_chain', [])
            child_name = parent_chain[-1] if parent_chain else item.get('parent_name', '')

            await conn.execute("""
                INSERT INTO subject_child_stock_reason
                    (subject_key, child_name, child_full_name, stock_id, stock_name,
                     reason, sort_order, parent_chain, pct_chg, source_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'cdp_dom')
                ON CONFLICT (subject_key, child_name, stock_id)
                DO UPDATE SET
                    reason = EXCLUDED.reason,
                    parent_chain = EXCLUDED.parent_chain,
                    pct_chg = EXCLUDED.pct_chg,
                    source_type = 'cdp_dom',
                    updated_at = NOW()
            """,
                subject_key,
                child_name,
                subject_key + '-' + child_name,
                stock_id,
                stock_name,
                item.get('reason', ''),
                count + 1,
                ' > '.join(parent_chain),
                item.get('pct_chg', ''),
            )
            count += 1

        return count
    finally:
        await conn.close()


def main():
    subject_key = sys.argv[1] if len(sys.argv) > 1 else "9026027"
    import_db = "--import-db" in sys.argv

    print(f"[EXTRACT] Subject {subject_key}")

    cdp = CDPClient()
    cdp.connect()
    print("[CDP] Connected")

    # Navigate to subject detail
    cdp.navigate(f"/subject/detail/{subject_key}")
    time.sleep(4)

    # Click 题材图谱 tab
    cdp.evaluate("""
    (function() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            if (all[i].textContent.trim() === '题材图谱') { all[i].click(); return; }
        }
    })()
    """)
    time.sleep(3)

    # Extract full tree
    items = extract_tree(cdp)
    cdp.close()

    if not items:
        print("[ERROR] No items extracted")
        return

    # Summarize
    all_nodes = [i for i in items if not i.get('is_stock')]
    stock_nodes = [i for i in items if i.get('is_stock')]
    print(f"\n=== 树结构 ({len(items)} nodes: {len(all_nodes)} branches + {len(stock_nodes)} stocks) ===")

    # Print hierarchy
    for item in items:
        indent = "  " * (item.get('level', 2) - 2)
        badge_str = f" [{item['reason']}]" if item['reason'] else ""
        stock_str = " 📈" if item['is_stock'] else ""
        print(f"{indent}{item['name']}{badge_str} {item['pct_chg']}{stock_str}")

    # Save JSON
    out_path = PROJECT_ROOT / "theme_data_complete" / "child_stock_reasons" / f"{subject_key}_tree.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] {out_path}")

    # Import to DB
    if import_db:
        count = asyncio.run(import_to_db(items, subject_key))
        print(f"[DB] Imported {count} stocks with reasons")

    print(f"\n[DONE] Branch nodes: {len(all_nodes)}, Stock nodes: {len(stock_nodes)}")


if __name__ == "__main__":
    main()
