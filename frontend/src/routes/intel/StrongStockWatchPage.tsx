import { useEffect, useMemo, useState } from "react";
import { fetchStrongStockWatch, type StrongStockWatchItem } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { navigateTo } from "../../lib/navigation";

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

type DateBucket = {
  key: string;
  items: StrongStockWatchItem[];
  levelMap: Map<number | "break", StrongStockWatchItem[]>;
};

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
        limit: 500,
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

  const groupedItems = useMemo<DateBucket[]>(() => {
    const rows = (data?.items ?? [])
      .filter((item) => !isDisallowed(item))
      .filter((item) => item.watch_status === "active" || item.watch_status === "weakening");

    const byDate = new Map<string, StrongStockWatchItem[]>();
    for (const row of rows) {
      const key = row.trade_date;
      const list = byDate.get(key) ?? [];
      list.push(row);
      byDate.set(key, list);
    }

    const keys = [...byDate.keys()].sort((a, b) => b.localeCompare(a, "zh-CN"));

    return keys.map((key) => {
      const dayRows = byDate.get(key) ?? [];
      const dedup = new Map<string, StrongStockWatchItem>();
      for (const row of dayRows) {
        const code = normalizeStockCode(row.stock_id);
        if (!code) continue;
        const prev = dedup.get(code);
        if (!prev) {
          dedup.set(code, row);
          continue;
        }
        const prevFlag = Number(prev.current_flag || 0);
        const curFlag = Number(row.current_flag || 0);
        const prevScore = Number(prev.watch_score || 0);
        const curScore = Number(row.watch_score || 0);
        if (curFlag > prevFlag || (curFlag === prevFlag && curScore > prevScore)) {
          dedup.set(code, row);
        }
      }

      const items = [...dedup.values()].sort((a, b) => {
        const aFlag = Number(a.current_flag || 0);
        const bFlag = Number(b.current_flag || 0);
        if (bFlag !== aFlag) return bFlag - aFlag;
        return Number(b.watch_score || 0) - Number(a.watch_score || 0);
      });

      const levelMap = new Map<number | "break", StrongStockWatchItem[]>();
      const localLevels = new Set<number | "break">();
      for (const item of items) {
        const flag = Number(item.current_flag || 0);
        localLevels.add(flag < 2 ? "break" : flag);
      }
      for (const lv of localLevels) {
        levelMap.set(
          lv,
          items.filter((x) =>
            lv === "break" ? Number(x.current_flag || 0) < 2 : Number(x.current_flag || 0) === lv,
          ),
        );
      }

      return { key, items, levelMap };
    });
  }, [data?.items]);

  const globalLevels = useMemo<Array<number | "break">>(() => {
    const maxFlag = Math.max(
      2,
      ...groupedItems.flatMap((group) => group.items.map((x) => Number(x.current_flag || 0))),
    );
    const levels: Array<number | "break"> = [];
    for (let lv = maxFlag; lv >= 2; lv -= 1) levels.push(lv);
    if (groupedItems.some((group) => group.items.some((x) => Number(x.current_flag || 0) < 2))) {
      levels.push("break");
    }
    return levels;
  }, [groupedItems]);

  const detailCount = groupedItems.reduce((sum, g) => sum + g.items.length, 0);
  const totalCount = useMemo(() => {
    const codes = new Set<string>();
    for (const group of groupedItems) {
      for (const item of group.items) {
        const code = normalizeStockCode(item.stock_id);
        if (code) codes.add(code);
      }
    }
    return codes.size;
  }, [groupedItems]);

  return (
    <div className="workspace-page strong-watch-page">
      <header className="workspace-header">
        <button type="button" className="back-button" onClick={() => navigateTo("/")}>
          返回情报台
        </button>
        <h1>强势股跟踪</h1>
      </header>

      <section className="strong-watch-toolbar">
        <label>
          <span>截至日期</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          <span>窗口天数</span>
          <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
            <option value={7}>7日</option>
            <option value={10}>10日</option>
            <option value={15}>15日</option>
            <option value={20}>20日</option>
          </select>
        </label>
        <div className="strong-watch-summary">
          <strong>{totalCount}</strong>
          <span>{windowDays}日去重强势股（明细 {detailCount} 条）</span>
        </div>
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
                {globalLevels.map((level) => {
                  const items = group.levelMap.get(level) ?? [];
                  return (
                    <div key={`${group.key}-lv-${level}`} className="strong-watch-level-row">
                      <div className="strong-watch-level-tag">{level === "break" ? "断板" : `${level}板`}</div>
                      <div className="strong-watch-level-content">
                        {items.length === 0 ? (
                          <div className="strong-watch-level-empty">--</div>
                        ) : (
                          items.map((item) => (
                            <button
                              key={`${group.key}-${item.stock_id}-${level}`}
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
                              <strong>{item.stock_name}</strong>
                              <span>{formatPct(item.pct_chg)}</span>
                              <em>{item.theme_name || item.subject_key || "--"}</em>
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
