from __future__ import annotations

import json
import re
import time
from urllib.parse import unquote

from services.jyhf_cdp_service.cdp_client import CDPClient


class PrepareRetryError(RuntimeError):
    """DOM element not ready — caller should retry on next capture cycle."""


class NotificationPopupExtractor:
    """Extract structured event data from JYHF push notification popups.

    The JYHF app receives push notifications for followed subjects via a
    ``#/notification?...`` route.  All event fields are carried as URL query
    parameters — no DOM parsing needed.  The popup does **not** auto-dismiss;
    it persists until the user clicks "查看详情" or navigates away.

    URL format::

        /notification?
          route=TopicView
          &extraId=9055879
          &extraName=<subject_name>
          &title=<notification_title>
          &content=<driver_event_body>
    """

    _ROUTE_MARKER = "/notification?"

    # Regex to pull structured fields out of the ``content`` param.
    _DRIVER_RE = re.compile(r"【驱动事件[：:](.*?)】")
    _SOURCE_RE = re.compile(r"（新闻来源[：:](.*?)）")

    def detect(self, cdp: CDPClient) -> bool:
        """Return True if the app is currently showing a notification popup."""
        loc = cdp.evaluate("window.location.hash", timeout=3.0)
        return isinstance(loc, str) and self._ROUTE_MARKER in loc

    def read(self, cdp: CDPClient) -> list[dict]:
        """Parse the notification URL query string into one or more event dicts.

        Return format is compatible with ``NewEventExtractor.read()``:

        * subject_name  — from ``extraName``
        * subject_key   — from ``extraId`` (BONUS: popup carries the ID directly)
        * driver_title  — parsed from ``【驱动事件：…】`` in ``content``
        * driver_desc   — body text after the driver marker, before news source
        * news_source   — from ``（新闻来源：…）``
        * event_type    — ``"驱动事件"`` (default for push notifications)
        * event_time    — ``""`` (not available in popup)
        * pct_chg_text  — ``""`` (not available in popup)
        """
        raw = cdp.evaluate(
            """
            (function() {
                var hash = window.location.hash || '';
                var idx = hash.indexOf('?');
                if (idx < 0) return JSON.stringify({error: 'no query string'});
                var qs = hash.substring(idx + 1);
                var params = {};
                var pairs = qs.split('&');
                for (var i = 0; i < pairs.length; i++) {
                    var eq = pairs[i].indexOf('=');
                    if (eq < 0) continue;
                    var key = pairs[i].substring(0, eq);
                    var val = pairs[i].substring(eq + 1);
                    try { params[key] = decodeURIComponent(val); } catch(e) { params[key] = val; }
                }
                return JSON.stringify({params: params});
            })()
            """,
            timeout=5.0,
        )
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            return []

        params = payload.get("params") if isinstance(payload, dict) else {}
        if not params:
            return []

        subject_name = unquote(str(params.get("extraName", "")).strip())
        subject_id = str(params.get("extraId", "")).strip()
        content = unquote(str(params.get("content", "")).strip())

        if not subject_name or not content:
            return []

        # Parse structured fields from content
        driver_title = ""
        driver_desc = ""
        news_source = ""

        dm = self._DRIVER_RE.search(content)
        if dm:
            driver_title = dm.group(1).strip()

        sm = self._SOURCE_RE.search(content)
        if sm:
            news_source = sm.group(1).strip()

        # Driver description: text between "】" and "（新闻来源："
        desc_start = content.find("】") + 1
        desc_end = content.find("（新闻来源：")
        if desc_end < 0:
            desc_end = len(content)
        if 0 < desc_start < desc_end:
            driver_desc = content[desc_start:desc_end].strip()
        elif desc_start > 0:
            driver_desc = content[desc_start:].strip()

        event = {
            "event_time": "",
            "subject_name": subject_name,
            "subject_key": subject_id,
            "pct_chg_text": "",
            "driver_title": driver_title,
            "driver_desc": driver_desc,
            "news_source": news_source,
            "event_type": "驱动事件",
            "raw_text": content,
        }
        return [event]


class PersistentHookInjector:
    """Inject persistent JS hooks into the JYHF renderer to capture notifications.

    Hooks are injected once and survive CDP disconnects because they live in
    the renderer's JS memory (``window.__cdp_*__``).  Subsequent connections
    only need to *read* the accumulated data.

    Three layers of capture (defense in depth):

    1. **Vue Router beforeEach** — intercepts ``$router.push('/notification?...')``
       before the component renders.  This is the primary capture path.
    2. **hashchange listener** — backup for direct ``window.location.hash`` changes.
    3. **fetch response interceptor** — captures API response bodies for
       diagnostic / future use (e.g. if encryption is removed).
    """

    _INJECTED_FLAG = "__cdp_persistent_hooks_injected__"
    _NOTIF_STORE = "__cdp_notifications__"

    def ensure_injected(self, cdp: CDPClient) -> bool:
        """Inject hooks if not already active. Returns True on first injection."""
        flag = cdp.evaluate(f"window.{self._INJECTED_FLAG}", timeout=2.0)
        if flag is True:
            return False  # Already injected

        result = cdp.evaluate(
            """
            (function() {
                if (window.__cdp_persistent_hooks_injected__) return 'already';
                window.__cdp_persistent_hooks_injected__ = true;
                window.__cdp_notifications__ = [];
                var injected = [];

                // ── Layer 1: Vue Router beforeEach ──
                try {
                    var app = document.querySelector('#app');
                    if (app && app.__vue_app__) {
                        var router = app.__vue_app__.config.globalProperties.$router;
                        if (router) {
                            router.beforeEach(function(to, from, next) {
                                var fp = to.fullPath || to.path || '';
                                if (fp.indexOf('/notification') >= 0) {
                                    var q = to.query || {};
                                    window.__cdp_notifications__.push({
                                        source: 'router',
                                        route: q.route || '',
                                        subject_id: q.extraId || '',
                                        subject_name: decodeURIComponent(q.extraName || ''),
                                        title: decodeURIComponent(q.title || ''),
                                        content: decodeURIComponent(q.content || ''),
                                        captured_at: new Date().toISOString()
                                    });
                                }
                                next();
                            });
                            injected.push('router_hook');
                        }
                    }
                } catch(e) { injected.push('router_err:' + e.message); }

                // ── Layer 2: hashchange listener ──
                try {
                    window.addEventListener('hashchange', function() {
                        var hash = window.location.hash || '';
                        var marker = '/notification?';
                        var idx = hash.indexOf(marker);
                        if (idx < 0) return;
                        var qs = hash.substring(idx + marker.length);
                        var params = {};
                        var pairs = qs.split('&');
                        for (var i = 0; i < pairs.length; i++) {
                            var eq = pairs[i].indexOf('=');
                            if (eq < 0) continue;
                            try { params[pairs[i].substring(0, eq)] = decodeURIComponent(pairs[i].substring(eq + 1)); }
                            catch(e2) {}
                        }
                        if (params.extraId || params.extraName) {
                            window.__cdp_notifications__.push({
                                source: 'hashchange',
                                route: params.route || '',
                                subject_id: params.extraId || '',
                                subject_name: params.extraName || '',
                                title: params.title || '',
                                content: params.content || '',
                                captured_at: new Date().toISOString()
                            });
                        }
                    });
                    injected.push('hashchange_listener');
                } catch(e) { injected.push('hashchange_err:' + e.message); }

                // ── Layer 3: fetch response interceptor (best-effort) ──
                try {
                    if (!window.__cdp_feed_hook_active__) {
                        window.__cdp_feed_hook_active__ = true;
                        window.__cdp_feed_responses__ = [];
                        var origFetch = window.fetch;
                        window.fetch = function(url, options) {
                            var urlStr = typeof url === 'string' ? url : (url && url.url ? url.url : '');
                            return origFetch.apply(this, arguments).then(function(response) {
                                if (urlStr.indexOf('txcfgl.com') >= 0) {
                                    var cloned = response.clone();
                                    cloned.text().then(function(body) {
                                        window.__cdp_feed_responses__.push({
                                            url: urlStr.substring(0, 250),
                                            status: response.status,
                                            body: body.substring(0, 8000)
                                        });
                                    }).catch(function() {});
                                }
                                return response;
                            });
                        };
                        injected.push('fetch_interceptor');
                    }
                } catch(e) { injected.push('fetch_err:' + e.message); }

                return JSON.stringify(injected);
            })()
            """,
            timeout=8.0,
        )
        return True  # Freshly injected

    def drain_notifications(self, cdp: CDPClient) -> list[dict]:
        """Read and clear accumulated notifications from JS memory.

        Returns list of raw notification dicts with keys:
        source, route, subject_id, subject_name, title, content, captured_at.
        """
        raw = cdp.evaluate(
            f"""
            (function() {{
                var arr = window.{self._NOTIF_STORE} || [];
                window.{self._NOTIF_STORE} = [];
                return JSON.stringify(arr);
            }})()
            """,
            timeout=3.0,
        )
        if not raw:
            return []
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or [])
        except json.JSONDecodeError:
            return []


class NewEventExtractor:
    def prepare(self, cdp: CDPClient) -> None:
        # Step 1: navigate to home page
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
        # Poll for route change instead of blind sleep
        for _ in range(10):
            time.sleep(0.3)
            try:
                loc = cdp.evaluate("window.location.hash", timeout=2.0)
                if str(loc) in ("", "#/", "#/ "):
                    break
            except Exception:
                pass

        # Step 2: find and click "新事件" tab
        result = cdp.evaluate(
            """
            (function() {
                var backBtn = document.querySelector('[class*="back"]') || document.querySelector('[class*="Back"]');
                if (backBtn) { backBtn.click(); }
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var txt = (el.textContent || '').trim();
                    if (txt === '新事件' && el.children.length <= 1) {
                        el.click();
                        return 'clicked_exact';
                    }
                }
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
        if not str(result).startswith("clicked"):
            raise PrepareRetryError(f"new event tab not found: route={route_result} click={result}")

        # Poll for page render — check full text because the event feed
        # may appear far below the ranking table (offset 750+).
        for _ in range(15):
            time.sleep(0.3)
            try:
                txt = cdp.evaluate(
                    "document.body.innerText", timeout=2.0,
                )
                if isinstance(txt, str) and len(txt) > 50:
                    # "今天" is the date header specific to the event feed.
                    # Also accept "驱动事件" / "新题材" / "搜索" as fallback.
                    if any(kw in txt for kw in ("今天", "驱动事件", "新题材")):
                        break
            except Exception:
                pass

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


class ReviewSubjectDetailExtractor:
    """Extract full DOM content from JYHF review/lising subject pages.

    When a popup or hook notification captures a review-type subject
    (e.g. 连板复盘, 热门题材复盘, 龙虎榜), the notification URL only
    carries the subject_id and name — NO driver event body.  This
    extractor navigates CDP into the subject detail page and reads the
    full rendered DOM text, which contains the stock ranking table.

    Review subjects detected by name pattern::

        REVIEW_KEYWORDS = ['连板复盘', '热门题材复盘', '龙虎榜',
                           '涨停复盘', '盘前必读', '题材掘金', '题材排名']

    Usage (after popup/hook captures a review subject)::

        extractor = ReviewSubjectDetailExtractor()
        body_text = extractor.extract(cdp, subject_key='9068870',
                                      subject_name='6月23日连板复盘')
        description = extractor.format_description(subject_name, body_text)
    """

    REVIEW_KEYWORDS = [
        "连板复盘", "热门题材复盘", "龙虎榜",
        "涨停复盘", "盘前必读", "题材掘金", "题材排名",
        "涨停榜", "题材轮动", "题材挖掘榜",
    ]

    @staticmethod
    def is_review_subject(subject_name: str) -> bool:
        """Return True if the subject is a review/listing page needing deep extraction."""
        if not subject_name:
            return False
        for kw in ReviewSubjectDetailExtractor.REVIEW_KEYWORDS:
            if kw in subject_name:
                return True
        return False

    def extract(
        self, cdp: CDPClient, *, subject_key: str, subject_name: str,
    ) -> str | None:
        """Navigate to the subject detail page and return the body innerText.

        Returns None if navigation or extraction fails.
        """
        import time as _time

        try:
            # Navigate to subject detail page via Vue Router
            result = cdp.evaluate(
                f"""(function() {{
    try {{
        var app = document.querySelector('#app');
        if (app && app.__vue_app__) {{
            app.__vue_app__.config.globalProperties.$router.push(
                '/subject/detail/{subject_key}/vip-table');
            return 'router_ok';
        }}
    }} catch(e) {{}}
    window.location.hash = '#/subject/detail/{subject_key}/vip-table';
    return 'hash_ok';
}})()""",
                timeout=8.0,
            )

            # Wait for page render (review subjects need time for stock tables)
            for _ in range(20):  # up to 10s wait
                _time.sleep(0.5)
                try:
                    loc = cdp.evaluate("window.location.hash", timeout=2.0)
                    if isinstance(loc, str) and subject_key in loc:
                        body = cdp.evaluate("document.body.innerText", timeout=3.0)
                        if isinstance(body, str) and len(body) > 100:
                            return body
                except Exception:
                    pass

            # Final attempt
            body = cdp.evaluate("document.body.innerText", timeout=5.0)
            if isinstance(body, str) and len(body) > 50:
                return body
            return None

        except Exception:
            return None

    @staticmethod
    def format_description(subject_name: str, body_text: str) -> str:
        """Format extracted DOM body text into a frontend-displayable description.

        Truncates to ~2000 chars to fit subject_history_staging.description.
        """
        if not body_text:
            return f"{subject_name}"

        # Keep only the first 2000 chars (description field is TEXT, not unlimited)
        clean = body_text.strip()
        if len(clean) > 2000:
            clean = clean[:2000] + "…"

        return f"{subject_name}\n\n{clean}"
