from __future__ import annotations

import json

from services.jyhf_cdp_service.cdp_client import CDPClient


class NewEventExtractor:
    def prepare(self, cdp: CDPClient) -> None:
        cdp.evaluate(
            "document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/')",
            timeout=8.0,
        )
        result = cdp.evaluate(
            """
            (function() {
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].textContent.trim() === '新事件' && all[i].children.length === 0) {
                        all[i].click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            })()
            """,
            timeout=8.0,
        )
        if result != "clicked":
            raise RuntimeError(f"new event tab not found: {result}")

    def read(self, cdp: CDPClient) -> tuple[list[dict], str, str]:
        raw = cdp.evaluate(
            """
            (function() {
                var text = document.body.innerText;
                var searchIdx = text.indexOf('搜索');
                if (searchIdx < 0) searchIdx = 0;
                var section = text.substring(searchIdx);
                var dateMatch = section.match(/\\d{4}-\\d{2}-\\d{2}/);
                if (!dateMatch) return JSON.stringify({events: [], feed_date: '', body_text: text});
                var feedText = section.substring(dateMatch.index);
                var lines = feedText.split('\\n');
                var results = [];
                var feedDate = '';
                var current = null;
                var currentRaw = [];
                function pushCurrent() {
                    if (current && current.subject_name) {
                        current.raw_text = currentRaw.join('\\n').trim();
                        results.push(current);
                    }
                }
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (!line) continue;
                    if (!feedDate && /\\d{4}-\\d{2}-\\d{2}/.test(line)) feedDate = line;
                    if (/^\\d{2}:\\d{2}$/.test(line)) {
                        pushCurrent();
                        current = {event_time: line};
                        currentRaw = [line];
                    } else if (current) {
                        currentRaw.push(line);
                        if (!current.subject_name && line.length > 1 && !line.includes('%') && !line.includes('驱动') && !/^\\d{4}-\\d{2}-\\d{2}/.test(line)) {
                            current.subject_name = line;
                        } else if (current.subject_name && !current.pct_chg_text && /^[+-]?\\d+\\.?\\d*%$/.test(line)) {
                            current.pct_chg_text = line;
                        } else if (current.subject_name && line.startsWith('【驱动事件：')) {
                            current.driver_title = line.replace('【驱动事件：', '').replace('】', '');
                        } else if (current.driver_title && !current.driver_desc && line.length > 20 && !line.startsWith('【') && !line.includes('新闻来源')) {
                            current.driver_desc = line;
                        } else if (current.driver_title && line.startsWith('（新闻来源：')) {
                            current.news_source = line.replace('（新闻来源：', '').replace('）', '');
                        }
                    }
                }
                pushCurrent();
                return JSON.stringify({events: results, feed_date: feedDate, body_text: text.substring(0, 12000)});
            })()
            """,
            timeout=8.0,
        )
        payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return payload.get("events") or [], str(payload.get("feed_date") or ""), str(payload.get("body_text") or "")
