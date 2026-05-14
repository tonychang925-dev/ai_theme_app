import { useState, useEffect, useCallback } from 'react';
import './mobile.css';

interface IntelItem {
  item_id: string;
  item_type: string;
  occurred_at: string;
  title: string;
  summary: string;
  theme_names: string[];
}

function todayString(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}

export function MobileIntelPage() {
  const [date, setDate] = useState(todayString());
  const [items, setItems] = useState<IntelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initDone, setInitDone] = useState(true);

  const fetchItems = useCallback(async (d: string) => {
    if (!initDone) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`/api/v2/intel/feed?date=${d}&session=all&type=all&limit=50`);
      if (!resp.ok) throw new Error(`请求失败 (${resp.status})`);
      const data = await resp.json();
      setItems((data.items || []).filter((it: IntelItem) =>
        it.item_type === 'event' || it.item_type === 'new_theme'
      ));
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [initDone]);

  useEffect(() => { fetchItems(date); }, [date, fetchItems]);

  const shiftDay = (delta: number) => {
    const d = new Date(date + 'T00:00:00');
    d.setDate(d.getDate() + delta);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    setDate(`${y}-${m}-${day}`);
  };

  return (
    <main className="mobile-shell" aria-label="实时情报">
      <header className="mobile-page-header">
        <button type="button" className="mobile-back-btn" onClick={() => { window.location.href = '/mobile'; }}>
          ← 首页
        </button>
        <h1 className="mobile-page-title">实时情报</h1>
      </header>

      <div className="mobile-date-bar">
        <button type="button" className="mobile-date-arrow" onClick={() => shiftDay(-1)}>←</button>
        <span className="mobile-date-label">{date}</span>
        <button type="button" className="mobile-date-arrow" disabled={date >= todayString()} onClick={() => shiftDay(1)}>→</button>
      </div>

      {loading && <div className="mobile-empty">加载中...</div>}
      {!loading && error && <div className="mobile-empty error">{error}</div>}
      {!loading && !error && items.length === 0 && (
        <div className="mobile-empty">暂无实时情报</div>
      )}
      {!loading && items.length > 0 && (
        <div className="mobile-recap-body">
          {items.map((item) => (
            <section
              className={`mobile-card ${item.item_type === 'new_theme' ? 'mobile-intel-newtheme' : ''}`}
              key={item.item_id}
            >
              <div className="mobile-intel-head">
                <span className="mobile-intel-time">{formatTime(item.occurred_at)}</span>
                {item.item_type === 'new_theme' && (
                  <span className="mobile-newtheme-badge">新题材</span>
                )}
              </div>
              <h3 className="mobile-intel-title">{item.title}</h3>
              {item.summary && item.summary !== item.title && (
                <p className="mobile-intel-desc">{item.summary}</p>
              )}
              {item.theme_names.length > 0 && (
                <div className="mobile-intel-themes">
                  {item.theme_names.slice(0, 3).map((t, i) => (
                    <span className="mobile-theme-tag" key={i}>{t}</span>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
