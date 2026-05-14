from __future__ import annotations

import json
import time

from services.jyhf_cdp_service.cdp_client import CDPClient


class NewEventExtractor:
    def prepare(self, cdp: CDPClient) -> None:
        # Step 1: 强制导航到首页
        route_result = cdp.evaluate(
            """
            (function() {
                try {
                    var app = document.querySelector('#app');
                    if (app && app.__vue_app__) {
                        app.__vue_app__.config.globalProperties.$router.push('/');
                        return 'router_push';
                    }
                } catch (e) {}
                window.location.hash = '#/';
                return 'hash_push';
            })()
            """,
            timeout=8.0,
        )
        time.sleep(5)
        # Step 2: 点击所有可能的导航元素确保在正确的页面
        result = cdp.evaluate(
            """
            (function() {
                // 先尝试关闭可能的弹窗/详情页（点击返回按钮或遮罩）
                var backBtn = document.querySelector('[class*=\"back\"]') || document.querySelector('[class*=\"Back\"]');
                if (backBtn) { backBtn.click(); }
                // 策略1：精确匹配 '新事件' 文本节点
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var txt = (el.textContent || '').trim();
                    if (txt === '新事件' && el.children.length <= 1) {
                        el.click();
                        return 'clicked_exact';
                    }
                }
                // 策略2：遍历所有包含'新事件'的元素，点击最具体的那个
                var best = null;
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var txt = (el.textContent || '').trim();
                    if (txt.indexOf('新事件') >= 0 && txt.length <= 10) {
                        if (!best || el.children.length < best.children.length) {
                            best = el;
                        }
                    }
                }
                if (best) { best.click(); return 'clicked_best'; }
                return 'not_found';
            })()
            """,
            timeout=8.0,
        )
        time.sleep(3)
        if not str(result).startswith("clicked"):
            raise RuntimeError(f"new event tab not found: route={route_result} click={result}")
        # Step 3: 等待页面渲染完成
        time.sleep(2)

    def read(self, cdp: CDPClient) -> tuple[list[dict], str, str]:
        raw = cdp.evaluate(
            """
            (function() {
                var text = document.body.innerText;
                var searchIdx = text.indexOf('搜索');
                if (searchIdx < 0) searchIdx = 0;
                var section = text.substring(searchIdx);
                var dateMatch = section.match(/\\d{4}-\\d{1,2}-\\d{1,2}/);
                // 搜索后无日期，回退到全文搜索
                if (!dateMatch) {
                    dateMatch = text.match(/\\d{4}-\\d{1,2}-\\d{1,2}/);
                }
                if (!dateMatch) return JSON.stringify({events: [], feed_date: '', body_text: text});
                var feedText = text.substring(dateMatch.index);
                // 修复 innerText 将 driver_desc 与 新闻来源 合并到同一行的问题
                feedText = feedText.replace(/（新闻来源[：:]/g, '\\n（新闻来源：');
                var lines = feedText.split('\\n');
                var results = [];
                var feedDate = '';
                var current = null;
                var currentRaw = [];
                var SKIP_KEYWORDS = ['连板复盘','热门题材复盘','龙虎榜','盘前必读','涨停榜','题材挖掘榜','题材轮动','题材掘金','题材排名','涨停复盘'];
                function pushCurrent() {
                    if (current && current.subject_name) {
                        var skip = false;
                        for (var k = 0; k < SKIP_KEYWORDS.length; k++) {
                            if (current.subject_name.indexOf(SKIP_KEYWORDS[k]) >= 0) { skip = true; break; }
                        }
                        if (!skip) {
                            current.raw_text = currentRaw.join('\\n').trim();
                            results.push(current);
                        }
                    }
                }
                var seenDate = false;
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (!line) continue;
                    var dateHit = line.match(/\\d{4}-\\d{1,2}-\\d{1,2}/);
                    if (dateHit) {
                        if (!feedDate) { feedDate = dateHit[0]; seenDate = true; }
                        else if (seenDate) { break; }  // 第二个日期分栏 → 停，只采当日
                        continue;
                    }
                    if (!feedDate) continue;
                    if (/^\\d{2}:\\d{2}$/.test(line)) {
                        pushCurrent();
                        current = {event_time: line};
                        currentRaw = [line];
                    } else if (current) {
                        currentRaw.push(line);
                        if (!current.subject_name && line.length > 1 && !line.includes('%') && !line.includes('驱动') && !/\\d{4}-\\d{1,2}-\\d{1,2}/.test(line)) {
                            current.subject_name = line;
                        } else if (current.subject_name && !current.pct_chg_text && /^[+-]?\\d+\\.?\\d*%$/.test(line)) {
                            current.pct_chg_text = line;
                        } else if (current.subject_name && (line.startsWith('【驱动事件：') || line.startsWith('【新题材更新：'))) {
                            current.driver_title = line.replace('【驱动事件：', '').replace('【新题材更新：', '').replace('】', '');
                            current.event_type = line.startsWith('【新题材更新：') ? '新题材更新' : '驱动事件';
                        } else if (current.driver_title && !current.driver_desc && line.length > 20 && !line.startsWith('【') && !line.includes('新闻来源')) {
                            current.driver_desc = line;
                        } else if (current.driver_title && line.startsWith('（新闻来源：')) {
                            current.news_source = line.replace('（新闻来源：', '').replace('）', '');
                        }
                    }
                }
                pushCurrent();
                // 标准化日期 YYYY-M-D → YYYY-MM-DD
                if (feedDate) {
                    var parts = feedDate.match(/(\\d{4})-(\\d{1,2})-(\\d{1,2})/);
                    if (parts) {
                        feedDate = parts[1] + '-' + parts[2].padStart(2, '0') + '-' + parts[3].padStart(2, '0');
                    }
                }
                return JSON.stringify({events: results, feed_date: feedDate, body_text: text.substring(0, 12000)});
            })()
            """,
            timeout=8.0,
        )
        payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return payload.get("events") or [], str(payload.get("feed_date") or ""), str(payload.get("body_text") or "")
