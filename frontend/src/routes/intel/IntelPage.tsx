import { useEffect, useMemo, useState } from "react";
import type {
  IntelFeedEvent,
  IntelFeedItem,
  IntelFeedView,
  IntelItemType,
  IntelSession,
} from "../../lib/api";
import { fetchIntelFeed, fetchRecapDefaults, openIntelStream } from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

function todayString() {
  return new Date().toISOString().slice(0, 10);
}

function readInitialState() {
  const params = new URLSearchParams(window.location.search);
  return {
    date: params.get("date") || todayString(),
    type: (params.get("type") as IntelItemType | null) || "all",
    session: (params.get("session") as IntelSession | null) || "all",
    selectedItemId: params.get("item"),
  };
}

function formatTime(value: string) {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function confidenceText(item: IntelFeedItem) {
  if (item.confidence == null) return "--";
  return Number(item.confidence).toFixed(2);
}

function impactText(item: IntelFeedItem) {
  if (item.impact_score == null) return "--";
  return Number(item.impact_score).toFixed(0);
}

function itemTone(item: IntelFeedItem) {
  if (item.item_type === "new_theme") return "spark";
  if (item.item_type === "theme_move" || item.item_type === "stock_move") return "heat";
  return "signal";
}

function itemTypeLabel(item: IntelFeedItem) {
  if (item.item_type === "event") return "新事件";
  if (item.item_type === "new_theme") return "新题材";
  return "情报";
}

function sourceLabel(sourceType: string) {
  if (sourceType === "event_theme_map") return "题材匹配事件";
  if (sourceType === "jyhf_history" || sourceType === "jyhf_rank_daily") return "久赢题材事件";
  if (sourceType === "jyhf_stock_daily") return "久赢股票异动";
  if (sourceType === "jyhf_full_theme_list") return "久赢题材列表";
  return sourceType;
}

export function IntelPage() {
  const initialState = useMemo(() => readInitialState(), []);
  const [date, setDate] = useState(initialState.date);
  const [type, setType] = useState<IntelItemType>(initialState.type);
  const [session, setSession] = useState<IntelSession>(initialState.session);
  const [payload, setPayload] = useState<IntelFeedView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(initialState.selectedItemId);
  const [liveStatus, setLiveStatus] = useState<"connecting" | "live" | "fallback">("connecting");
  const [liveNewCount, setLiveNewCount] = useState(0);
  const [recapDates, setRecapDates] = useState<{ postMarket: string; preMarket: string }>({
    postMarket: initialState.date,
    preMarket: initialState.date,
  });

  function applyFeedData(data: IntelFeedView) {
    setPayload(data);
    if (selectedItemId && !data.items.some((item) => item.item_id === selectedItemId)) {
      setSelectedItemId(null);
    }
  }

  function mergeIncomingItems(incomingItems: IntelFeedItem[]) {
    if (incomingItems.length === 0) return;
    setPayload((current) => {
      const currentItems = current?.items ?? [];
      const existingIds = new Set(currentItems.map((item) => item.item_id));
      const freshItems = incomingItems.filter((item) => !existingIds.has(item.item_id));
      if (freshItems.length === 0) return current;

      setLiveNewCount((value) => value + freshItems.length);

      return {
        items: [...freshItems, ...currentItems].slice(0, 50),
        count: Math.min(currentItems.length + freshItems.length, 50),
        date: current?.date ?? date,
        session: current?.session ?? session,
        type: current?.type ?? type,
        diagnostics: current?.diagnostics,
      };
    });
  }

  useEffect(() => {
    let active = true;
    fetchRecapDefaults()
      .then((data) => {
        if (!active) return;
        setRecapDates({
          postMarket: data.latest_post_market_date || initialState.date,
          preMarket: data.latest_pre_market_date || initialState.date,
        });
      })
      .catch(() => {
        if (!active) return;
        setRecapDates({
          postMarket: initialState.date,
          preMarket: initialState.date,
        });
      });
    return () => {
      active = false;
    };
  }, [initialState.date]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setLiveNewCount(0);
    fetchIntelFeed({ date, type, session, limit: 50 })
      .then((data) => {
        if (!active) return;
        applyFeedData(data);
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message);
        setPayload(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [date, type, session]);

  useEffect(() => {
    const stream = openIntelStream({ date, type, session });
    setLiveStatus("connecting");

    stream.addEventListener("intel_item", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as IntelFeedEvent;
        if (payload?.item) {
          mergeIncomingItems([payload.item]);
          setLiveStatus("live");
        }
      } catch {
        setLiveStatus("fallback");
      }
    });

    stream.addEventListener("heartbeat", () => {
      setLiveStatus("live");
    });

    stream.onerror = () => {
      setLiveStatus("fallback");
    };

    return () => {
      stream.close();
    };
  }, [date, type, session]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchIntelFeed({ date, type, session, limit: 50 })
        .then((data) => {
          const currentIds = new Set((payload?.items ?? []).map((item) => item.item_id));
          const freshItems = data.items.filter((item) => !currentIds.has(item.item_id));
          if (freshItems.length > 0) {
            mergeIncomingItems(freshItems);
          }
        })
        .catch(() => {
          setLiveStatus("fallback");
        });
    }, 30000);

    return () => {
      window.clearInterval(timer);
    };
  }, [date, type, session, payload]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("date", date);
    params.set("type", type);
    params.set("session", session);
    if (selectedItemId) {
      params.set("item", selectedItemId);
    }
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, "", next);
  }, [date, type, session, selectedItemId]);

  const sourceSummary = useMemo(() => payload?.diagnostics?.sources?.join(" / ") || "--", [payload]);
  return (
    <div className="intel-shell">
      <header className="intel-topbar">
        <div>
          <p className="eyebrow">AI Investment Assistant</p>
          <h1>情报台</h1>
          <p className="subtle">按时间顺序展示归属到题材的事件流，点击任一事件直接进入题材详情</p>
        </div>
        <div className="topbar-meta">
          <span>来源: {sourceSummary}</span>
          <span>条目: {payload?.count ?? 0}</span>
          <span>实时: {liveStatus === "live" ? "在线" : liveStatus === "connecting" ? "连接中" : "兜底模式"}</span>
          {liveNewCount > 0 && <span>新增: {liveNewCount}</span>}
        </div>
      </header>

      <section className="intel-filters">
        <label>
          <span>日期</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          <span>时段</span>
          <select value={session} onChange={(e) => setSession(e.target.value as IntelSession)}>
            <option value="all">全部</option>
            <option value="pre">盘前</option>
            <option value="intra">盘中</option>
            <option value="post">盘后</option>
          </select>
        </label>
        <label>
          <span>类型</span>
          <select value={type} onChange={(e) => setType(e.target.value as IntelItemType)}>
            <option value="all">情报</option>
            <option value="event">新事件</option>
            <option value="new_theme">新题材</option>
          </select>
        </label>
        <button
          type="button"
          className="recap-filter-button"
          onClick={() => navigateTo(`/recap?date=${recapDates.postMarket}&report_type=post_market`)}
        >
          当日复盘
        </button>
        <button
          type="button"
          className="recap-filter-button"
          onClick={() => navigateTo(`/recap?date=${recapDates.preMarket}&report_type=pre_market`)}
        >
          盘前必读
        </button>
      </section>

      <main className="intel-stream">
        <section className="intel-list intel-list-dense">
          {loading && <div className="empty-state">正在加载情报流...</div>}
          {error && <div className="empty-state error">{error}</div>}
          {!loading && !error && payload?.items.length === 0 && <div className="empty-state">当日无情报项</div>}

          {payload?.items.map((item) => {
            const active = selectedItemId === item.item_id;
            const primaryThemeKey = item.theme_subject_keys[0] ?? null;
            const primaryThemeName = item.theme_names[0] ?? primaryThemeKey ?? "--";
            return (
              <button
                key={item.item_id}
                type="button"
                className={`intel-row intel-row-${itemTone(item)} ${active ? "active" : ""}`}
                onClick={() => {
                  setSelectedItemId(item.item_id);
                  if (primaryThemeKey) {
                    navigateTo(`/themes/${primaryThemeKey}`);
                  }
                }}
              >
                <div className="intel-row-time">
                  <span className="intel-row-date">{formatTime(item.occurred_at)}</span>
                </div>
                <div className="intel-row-body">
                  <div className="intel-row-head">
                    <span className={`pill pill-${item.item_type}`}>{itemTypeLabel(item)}</span>
                    <span className="intel-row-source">{sourceLabel(item.source_type)}</span>
                  </div>
                  <div className="intel-row-theme">
                    <strong className="intel-row-theme-name">{primaryThemeName}</strong>
                  </div>
                  <h3 className="intel-row-title">{item.summary || item.title || "无事件描述"}</h3>
                  {item.title && item.summary && item.title !== item.summary && (
                    <p className="intel-row-summary">{item.title}</p>
                  )}
                  <div className="intel-row-meta">
                    <span className="metric-chip">热度 {impactText(item)}</span>
                    <span className="metric-chip">置信 {confidenceText(item)}</span>
                    {item.stock_names.length > 0 && (
                      <span className="intel-row-stocks">{item.stock_names.slice(0, 4).join(" / ")}</span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </section>
      </main>
    </div>
  );
}
