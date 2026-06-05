import { useEffect, useMemo, useState } from "react";
import { fetchStrongStockWatch, type StrongStockWatchItem } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { navigateTo } from "../../lib/navigation";
import strongwatchIcon from "../../assets/intel-icons/强势股跟踪.png";

function todayString() {
  return new Date().toISOString().slice(0, 10);
}

function formatPct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  return `${num > 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function normalizeStockCode(stockId?: string | null): string {
  return String(stockId || "").split(".")[0] || "";
}

function isDisallowed(item: StrongStockWatchItem): boolean {
  const code = normalizeStockCode(item.stock_id);
  const name = String(item.stock_name || "").toUpperCase();
  return code.startsWith("688") || name.startsWith("ST") || name.startsWith("*ST");
}

function weekdayLabel(dateText: string): string {
  const d = new Date(`${dateText}T00:00:00`);
  const mapping = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  if (Number.isNaN(d.getTime())) return "";
  return mapping[d.getDay()] || "";
}

function headerDate(dateText: string): string {
  const compact = dateText.replace(/-/g, "");
  const wd = weekdayLabel(dateText);
  return wd ? `${compact}(${wd})` : compact;
}

function toneClass(item: StrongStockWatchItem): string {
  if (item.watch_status === "active") return "is-active";
  if (item.watch_status === "weakening") return "is-weakening";
  return "is-removed";
}

function parseBoardLevel(item: StrongStockWatchItem): number {
  const anyItem = item as unknown as { labels_json?: Record<string, unknown>; recent_limit_up_count?: number };
  const fromLabels = Number(anyItem?.labels_json?.recent_limit_up_count ?? NaN);
  const fromFlat = Number(anyItem?.recent_limit_up_count ?? NaN);
  const fromFlag = Number(item.current_flag ?? NaN);
  const lv = Number.isFinite(fromLabels) ? fromLabels : Number.isFinite(fromFlat) ? fromFlat : fromFlag;
  return Number.isFinite(lv) ? Math.max(0, Math.floor(lv)) : 0;
}

function parsePctChg(item: StrongStockWatchItem): number | null {
  const anyItem = item as unknown as { labels_json?: Record<string, unknown>; pct_chg?: number };
  const fromItem = Number(anyItem?.pct_chg ?? NaN);
  if (Number.isFinite(fromItem)) return fromItem;
  const fromLabels = Number(anyItem?.labels_json?.pct_chg ?? NaN);
  if (Number.isFinite(fromLabels)) return fromLabels;
  return null;
}

function boardLabel(level: number): string {
  if (level >= 2) return `${level}板`;
  if (level === 1) return "1板";
  return "--";
}


/**
 * 展示契约（禁止随意变更）:
 * 1) 页面保持“多日看板分列”样式。
 * 2) 主口径仅展示“在池强势股”：watch_status in ('active','weakening')。
 * 3) 每个交易日内去重：同日同股只保留最优一条。
 * 4) 7 日窗口内同一只股票只展示一次，并挂到“首次入选”的日期列。
 * 5) 禁止用 promoted_to_candidate 参与 C 层强势池统计。
 */
function dedupByDate(rows: StrongStockWatchItem[]): StrongStockWatchItem[] {
  const bestByDateCode = new Map<string, StrongStockWatchItem>();
  for (const row of rows) {
    const code = normalizeStockCode(row.stock_id);
    const d = String(row.trade_date || "");
    if (!code || !d) continue;
    const k = `${d}#${code}`;
    const prev = bestByDateCode.get(k);
    if (!prev) {
      bestByDateCode.set(k, row);
      continue;
    }
    const prevFlag = Number(prev.current_flag || 0);
    const curFlag = Number(row.current_flag || 0);
    const prevScore = Number(prev.watch_score || 0);
    const curScore = Number(row.watch_score || 0);
    if (curFlag > prevFlag || (curFlag === prevFlag && curScore > prevScore)) {
      bestByDateCode.set(k, row);
    }
  }
  return [...bestByDateCode.values()];
}

function pickBetterSameDayRow(a: StrongStockWatchItem, b: StrongStockWatchItem): StrongStockWatchItem {
  const aFlag = Number(a.current_flag || 0);
  const bFlag = Number(b.current_flag || 0);
  if (bFlag > aFlag) return b;
  if (bFlag < aFlag) return a;
  return Number(b.watch_score || 0) > Number(a.watch_score || 0) ? b : a;
}

function dedupByStockEntryDate(rows: StrongStockWatchItem[]): StrongStockWatchItem[] {
  const firstByCode = new Map<string, StrongStockWatchItem>();
  for (const row of rows) {
    const code = normalizeStockCode(row.stock_id);
    if (!code) continue;
    const prev = firstByCode.get(code);
    if (!prev) {
      firstByCode.set(code, row);
      continue;
    }
    const prevDate = String(prev.watch_start_date || prev.trade_date || "");
    const currDate = String(row.watch_start_date || row.trade_date || "");
    if (currDate < prevDate) {
      firstByCode.set(code, row);
      continue;
    }
    if (currDate > prevDate) continue;
    if (String(row.trade_date || "") < String(prev.trade_date || "")) {
      firstByCode.set(code, row);
      continue;
    }
    if (String(row.trade_date || "") > String(prev.trade_date || "")) continue;
    firstByCode.set(code, pickBetterSameDayRow(prev, row));
  }
  return [...firstByCode.values()];
}

export function StrongStockWatchPage() {
  const initialParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const initialDate = initialParams?.get("date") || todayString();
  const initialWindowDaysRaw = Number(initialParams?.get("window_days") || "7");
  const initialWindowDays = [7, 10, 15, 20].includes(initialWindowDaysRaw) ? initialWindowDaysRaw : 7;

  const [date, setDate] = useState<string>(initialDate);
  const [windowDays, setWindowDays] = useState<number>(initialWindowDays);

  const fetcher = useMemo(
    () => () =>
      fetchStrongStockWatch({
        date,
        windowDays,
        limit: 5000,
        latestPerStock: false,
        includeRemoved: false,
      }),
    [date, windowDays],
  );

  const { data, loading, error } = useApi(fetcher, {
    immediate: true,
    deps: [date, windowDays],
  });

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("date", date);
    params.set("window_days", String(windowDays));
    window.history.replaceState({}, "", `/intel/strong-stocks/watch?${params.toString()}`);
  }, [date, windowDays]);

  const dedupStats = useMemo(() => {
    const rawRows = data?.items ?? [];
    const filteredRows = rawRows.filter(
      (item) =>
        !isDisallowed(item) &&
        (String(item.watch_status || "") === "active" || String(item.watch_status || "") === "weakening"),
    );
    const uniqueByDateRows = dedupByDate(filteredRows);
    const uniqueEntryRows = dedupByStockEntryDate(uniqueByDateRows);
    const latestByCode = new Map<string, StrongStockWatchItem>();
    for (const row of uniqueByDateRows) {
      const code = normalizeStockCode(row.stock_id);
      if (!code) continue;
      const prev = latestByCode.get(code);
      if (!prev) {
        latestByCode.set(code, row);
        continue;
      }
      const d0 = String(prev.trade_date || "");
      const d1 = String(row.trade_date || "");
      if (d1 > d0) {
        latestByCode.set(code, row);
      } else if (d1 === d0) {
        const pLv = parseBoardLevel(prev);
        const cLv = parseBoardLevel(row);
        if (cLv > pLv || (cLv === pLv && Number(row.watch_score || 0) > Number(prev.watch_score || 0))) {
          latestByCode.set(code, row);
        }
      }
    }
    const tradeDates = [...new Set(filteredRows.map((x) => String(x.trade_date || "")).filter(Boolean))]
      .sort((a, b) => b.localeCompare(a, "zh-CN"))
      .slice(0, 7);
    return {
      rawCount: rawRows.length,
      filteredCount: filteredRows.length,
      dedupedCount: uniqueEntryRows.length,
      removedCount: Math.max(0, uniqueByDateRows.length - uniqueEntryRows.length),
      tradeDates,
      uniqueRows: uniqueEntryRows,
      uniqueStockCount: uniqueEntryRows.length,
      latestByCode,
    };
  }, [data?.items]);

  const groupedItems = useMemo(() => {
    const uniqueRows = dedupStats.uniqueRows;
    const byDate = new Map<string, StrongStockWatchItem[]>();
    for (const row of uniqueRows) {
      const d = String(row.trade_date || "");
      if (!d) continue;
      const list = byDate.get(d) ?? [];
      list.push(row);
      byDate.set(d, list);
    }
    const keys = dedupStats.tradeDates;
    return keys.map((key) => {
      const items = [...(byDate.get(key) ?? [])].sort((a, b) => {
        const codeA = normalizeStockCode(a.stock_id);
        const codeB = normalizeStockCode(b.stock_id);
        const latestA = dedupStats.latestByCode.get(codeA) ?? a;
        const latestB = dedupStats.latestByCode.get(codeB) ?? b;
        const lvA = parseBoardLevel(latestA);
        const lvB = parseBoardLevel(latestB);
        if (lvB !== lvA) return lvB - lvA;
        return Number(latestB.watch_score || 0) - Number(latestA.watch_score || 0);
      });
      return { key, items };
    });
  }, [dedupStats.uniqueRows, dedupStats.tradeDates, dedupStats.latestByCode]);

  const detailCount = groupedItems.reduce((sum, g) => sum + g.items.length, 0);
  const totalCount = dedupStats.uniqueStockCount;

  return (
    <div className="workspace-page strong-watch-page">
      <section className="strong-watch-toolbar">
        <img src={strongwatchIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">强势股跟踪</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#9f9f9f" }}>截至日期</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              style={{ border: "1px solid #2a2a2a", borderRadius: 6, background: "#1a1a1a", color: "#f5f5f5", padding: "4px 8px" }} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#9f9f9f" }}>窗口天数</span>
            <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}
              style={{ border: "1px solid #2a2a2a", borderRadius: 6, background: "#1a1a1a", color: "#f5f5f5", padding: "4px 8px" }}>
              <option value={7}>7日</option>
              <option value={10}>10日</option>
              <option value={15}>15日</option>
              <option value={20}>20日</option>
            </select>
          </label>
        </div>
        <button type="button" className="back-button" onClick={() => navigateTo("/")}>
          返回
        </button>
      </section>

      {loading && <div className="empty-state">加载强势股跟踪中...</div>}
      {!loading && error && <div className="empty-state error">加载失败: {error}</div>}

      {!loading && !error && groupedItems.length === 0 && <div className="empty-state">当前{windowDays}日窗口无强势股记录</div>}

      {!loading && !error && groupedItems.length > 0 && (
        <section className="strong-watch-board strong-watch-board-quote">
          {groupedItems.map((group) => (
            <article key={group.key} className="strong-watch-board-col strong-watch-board-market-col">
              <header className="strong-watch-board-col-head strong-watch-market-head">
                <h3>{headerDate(group.key)}</h3>
                <span>共{group.items.length}只</span>
              </header>
              <div className="strong-watch-board-col-body strong-watch-market-body">
                {group.items.length === 0 ? (
                  <div className="strong-watch-level-row">
                    <div className="strong-watch-level-tag">--</div>
                    <div className="strong-watch-level-content">
                      <div className="strong-watch-level-empty">--</div>
                    </div>
                  </div>
                ) : (
                  group.items.map((item) => {
                    const lv = parseBoardLevel(dedupStats.latestByCode.get(normalizeStockCode(item.stock_id)) ?? item);
                    const displayName = item.stock_name || item.stock_id || "--";
                    return (
                      <div className="strong-watch-level-row" key={`${group.key}-${item.stock_id}`}>
                        <div className="strong-watch-level-tag">{boardLabel(lv)}</div>
                        <div className="strong-watch-level-content">
                          <button
                            type="button"
                            className={`strong-watch-market-item ${toneClass(item)}`}
                            onClick={() =>
                              navigateTo(
                                `/intel/strong-stocks/detail?stock_id=${encodeURIComponent(item.stock_id)}&date=${encodeURIComponent(
                                  date,
                                )}&window_days=${windowDays}`,
                              )
                            }
                          >
                            <strong>{displayName}</strong>
                            <span className="strong-watch-pct">{formatPct(parsePctChg(item))}</span>
                            <em>{item.theme_name || item.subject_key || "--"}</em>
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </article>
          ))}
        </section>
      )}

      <div className="strong-watch-summary">
        <strong>{totalCount}</strong>
        <span>{windowDays}个交易日在池强势股展示（明细 {detailCount} 条）</span>
        <span>原始 {dedupStats.rawCount} / 去重后 {dedupStats.dedupedCount}</span>
      </div>
    </div>
  );
}
