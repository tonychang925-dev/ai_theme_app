import { useState, useCallback } from 'react';
import './mobile.css';

interface MatchedTheme {
  subject_key: string;
  theme_name: string;
  confidence: number;
  reason: string;
}

interface RecommendedStock {
  stock_id: string;
  stock_name: string;
  score: number;
  theme_name: string;
  reason: string;
}

interface NewsRecommendData {
  event_summary: string;
  matched_themes: MatchedTheme[];
  recommended_stocks: RecommendedStock[];
  risk_notes: string[];
}

export function MobileNewsRecommendPage() {
  const [newsText, setNewsText] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<NewsRecommendData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    const text = newsText.trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const resp = await fetch('/api/v2/mobile/news-recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ news_text: text }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(detail || `请求失败 (${resp.status})`);
      }
      setData(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [newsText]);

  return (
    <main className="mobile-shell" aria-label="新闻荐股">
      <header className="mobile-page-header">
        <button type="button" className="mobile-back-btn" onClick={() => { window.location.href = '/mobile'; }}>
          ← 首页
        </button>
        <h1 className="mobile-page-title">新闻荐股</h1>
      </header>

      {/* Input */}
      <section className="mobile-card" style={{ margin: '12px 16px' }}>
        <textarea
          className="mobile-news-input"
          placeholder="粘贴新闻、研报或公告文本...&#10;&#10;例如：工信部表示将加快推进卫星互联网规模化应用..."
          value={newsText}
          onChange={(e) => setNewsText(e.target.value)}
          rows={6}
        />
        <button
          type="button"
          className="mobile-submit-btn"
          onClick={handleSubmit}
          disabled={loading || !newsText.trim()}
        >
          {loading ? '分析中...' : '开始分析'}
        </button>
      </section>

      {error && <div className="mobile-empty error">{error}</div>}

      {/* Results */}
      {data && (
        <div className="mobile-recap-body">
          {/* Summary */}
          <section className="mobile-card">
            <h2 className="mobile-card-title">提取摘要</h2>
            <p className="mobile-card-text">{data.event_summary}</p>
          </section>

          {/* Matched Themes */}
          {data.matched_themes.length > 0 && (
            <section className="mobile-card">
              <h2 className="mobile-card-title">匹配题材 ({data.matched_themes.length})</h2>
              <div className="mobile-list">
                {data.matched_themes.map((t, i) => (
                  <div className="mobile-list-item" key={i}>
                    <div className="mobile-list-item__main">
                      <strong>{t.theme_name}</strong>
                      <small>置信度 {(t.confidence * 100).toFixed(0)}% · {t.reason}</small>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Recommended Stocks */}
          {data.recommended_stocks.length > 0 && (
            <section className="mobile-card">
              <h2 className="mobile-card-title">推荐股票 ({data.recommended_stocks.length})</h2>
              <div className="mobile-list">
                {data.recommended_stocks.map((s, i) => (
                  <div className="mobile-list-item" key={i}>
                    <div className="mobile-list-item__main">
                      <strong>
                        {s.stock_name}
                        <span className="mobile-stock-id">{s.stock_id}</span>
                      </strong>
                      <small>{s.theme_name} · 评分 {s.score.toFixed(0)}</small>
                      <small className="mobile-reason">{s.reason}</small>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Empty results */}
          {data.matched_themes.length === 0 && data.recommended_stocks.length === 0 && (
            <div className="mobile-empty">未匹配到相关题材或股票，请尝试更具体的新闻文本。</div>
          )}

          {/* Risk */}
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
    </main>
  );
}
