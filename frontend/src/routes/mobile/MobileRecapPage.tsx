import { useState, useEffect, useCallback } from 'react';
import './mobile.css';

interface HotTheme {
  subject_key?: string;
  theme_name: string;
  reason: string;
  heat: number;
}

interface WatchStock {
  stock_id: string;
  stock_name: string;
  theme_name: string;
  score: number;
  reason: string;
}

interface MobileRecapData {
  trade_date: string;
  title: string;
  summary: string;
  hot_themes: HotTheme[];
  watch_stocks: WatchStock[];
  risk_notes: string[];
}

function todayString(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  } catch {
    return dateStr;
  }
}

export function MobileRecapPage() {
  const [date, setDate] = useState(todayString());
  const [data, setData] = useState<MobileRecapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initDone, setInitDone] = useState(false);

  // 启动时获取最新有数据的日期
  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch('/api/v2/mobile/defaults');
        if (resp.ok) {
          const defaults = await resp.json();
          if (defaults.latest_recap_date) {
            setDate(defaults.latest_recap_date);
          }
        }
      } catch {}
      setInitDone(true);
    })();
  }, []);

  const fetchRecap = useCallback(async (d: string) => {
    if (!initDone) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`/api/v2/mobile/recap?trade_date=${encodeURIComponent(d)}`);
      if (!resp.ok) throw new Error(`请求失败 (${resp.status})`);
      const json = await resp.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [initDone]);

  useEffect(() => {
    fetchRecap(date);
  }, [date, fetchRecap]);

  const goBack = () => {
    window.location.href = '/mobile';
  };

  const shiftDay = (delta: number) => {
    const d = new Date(date + 'T00:00:00');
    d.setDate(d.getDate() + delta);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    setDate(`${y}-${m}-${day}`);
  };

  return (
    <main className="mobile-shell" aria-label="每日复盘">
      {/* Header */}
      <header className="mobile-page-header">
        <button type="button" className="mobile-back-btn" onClick={goBack} aria-label="返回首页">
          ← 首页
        </button>
        <h1 className="mobile-page-title">每日复盘</h1>
      </header>

      {/* Date picker */}
      <div className="mobile-date-bar">
        <button type="button" className="mobile-date-arrow" onClick={() => shiftDay(-1)}>←</button>
        <span className="mobile-date-label">{formatDate(date)}</span>
        <button type="button" className="mobile-date-arrow" disabled={date >= todayString()} onClick={() => shiftDay(1)}>→</button>
      </div>

      {/* Content */}
      {loading && (
        <div className="mobile-empty">加载中...</div>
      )}
      {!loading && error && (
        <div className="mobile-empty error">{error}</div>
      )}
      {!loading && !error && data && (
        <div className="mobile-recap-body">
          {/* Summary */}
          <section className="mobile-card">
            <h2 className="mobile-card-title">{data.title}</h2>
            <p className="mobile-card-text">{data.summary}</p>
          </section>

          {/* Hot Themes */}
          {data.hot_themes.length > 0 && (
            <section className="mobile-card">
              <h2 className="mobile-card-title">热门题材</h2>
              <div className="mobile-list">
                {data.hot_themes.map((t, i) => (
                  <div className="mobile-list-item" key={i}>
                    <div className="mobile-list-item__main">
                      <strong>{t.theme_name}</strong>
                      <small>{t.reason}</small>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Watch Stocks */}
          {data.watch_stocks.length > 0 && (
            <section className="mobile-card">
              <h2 className="mobile-card-title">关注股票</h2>
              <div className="mobile-list">
                {data.watch_stocks.map((s, i) => (
                  <div className="mobile-list-item" key={i}>
                    <div className="mobile-list-item__main">
                      <strong>{s.stock_name} <span className="mobile-stock-id">{s.stock_id}</span></strong>
                      <small>{s.theme_name} · 评分 {typeof s.score === 'number' ? s.score.toFixed(1) : s.score}</small>
                      {s.reason ? <small className="mobile-reason">{s.reason}</small> : null}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Risk notes */}
          {data.risk_notes.length > 0 && (
            <section className="mobile-card mobile-card--warn">
              <h2 className="mobile-card-title">风险提示</h2>
              <ul className="mobile-risk-list">
                {data.risk_notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {/* Empty — no data and no error */}
      {!loading && !error && !data && (
        <div className="mobile-empty">复盘数据暂未生成，请先完成日采集。</div>
      )}
    </main>
  );
}
