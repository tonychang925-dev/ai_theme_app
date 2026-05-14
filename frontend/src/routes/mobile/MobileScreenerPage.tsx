import { useState, useEffect, useCallback } from 'react';
import './mobile.css';

interface StockItem {
  stock_id: string;
  stock_name: string;
  score: number;
  theme_name: string;
  level: string;
  reason: string;
  risk: string;
  source: string;
}

interface ScreenerData {
  trade_date: string;
  strategy: string;
  count: number;
  items: StockItem[];
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

function levelBadge(level: string): string {
  const upper = (level || '').toUpperCase();
  if (upper.startsWith('A') || upper.includes('FORMAL')) return 'A';
  if (upper.startsWith('B') || upper.includes('OBSERVE')) return 'B';
  if (upper.startsWith('C')) return 'C';
  return level.slice(0, 2);
}

function sourceLabel(src: string): string {
  return src === 'weak_to_strong' ? '弱转强' : '强势追踪';
}

export function MobileScreenerPage() {
  const [date, setDate] = useState(todayString());
  const [data, setData] = useState<ScreenerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (d: string) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `/api/v2/mobile/screener/latest?trade_date=${encodeURIComponent(d)}&strategy=weak_to_strong`,
      );
      if (!resp.ok) throw new Error(`请求失败 (${resp.status})`);
      setData(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(date); }, [date, fetchData]);

  const shiftDay = (delta: number) => {
    const d = new Date(date + 'T00:00:00');
    d.setDate(d.getDate() + delta);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    setDate(`${y}-${m}-${day}`);
  };

  return (
    <main className="mobile-shell" aria-label="AI选股">
      <header className="mobile-page-header">
        <button type="button" className="mobile-back-btn" onClick={() => { window.location.href = '/mobile'; }}>
          ← 首页
        </button>
        <h1 className="mobile-page-title">AI选股</h1>
      </header>

      <div className="mobile-date-bar">
        <button type="button" className="mobile-date-arrow"
          onTouchStart={(e) => { e.preventDefault(); shiftDay(-1); }}
          onClick={() => shiftDay(-1)}>←</button>
        <span className="mobile-date-label">{formatDate(date)}</span>
        <button type="button" className="mobile-date-arrow"
          disabled={date >= todayString()}
          onClick={() => shiftDay(1)}>→</button>
      </div>

      {loading && <div className="mobile-empty">加载中...</div>}
      {!loading && error && <div className="mobile-empty error">{error}</div>}
      {!loading && !error && data && data.items.length === 0 && (
        <div className="mobile-empty">当前日期暂无选股结果，请先完成日采集。</div>
      )}
      {!loading && !error && data && data.items.length > 0 && (
        <div className="mobile-recap-body">
          <section className="mobile-card">
            <h2 className="mobile-card-title">
              共 {data.items.length} 只 · {data.strategy === 'weak_to_strong' ? '弱转强 + 强势追踪' : data.strategy}
            </h2>
          </section>
          {data.items.map((item) => (
            <section className="mobile-card mobile-screener-card" key={item.stock_id}>
              <div className="mobile-screener-head">
                <strong className="mobile-screener-name">
                  {item.stock_name}
                  <span className="mobile-stock-id">{item.stock_id}</span>
                </strong>
                <span className={`mobile-level-badge level-${levelBadge(item.level)}`}>
                  {levelBadge(item.level)}
                </span>
              </div>
              <div className="mobile-screener-meta">
                <span className="mobile-screener-score">{item.score.toFixed(1)} 分</span>
                <span className="mobile-screener-source">{sourceLabel(item.source)}</span>
              </div>
              <div className="mobile-screener-info">
                <p><small>题材</small> {item.theme_name}</p>
                {item.reason ? <p><small>理由</small> {item.reason}</p> : null}
                <p><small>风险</small> {item.risk}</p>
              </div>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
