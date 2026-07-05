import { useEffect, useRef, useState } from 'react';
import { navigateTo } from '../../lib/navigation';
import { fetchSubjectSearch, type ThemeRadarItem } from '../../lib/api';

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    start: '\u542f\u52a8',
    fermentation: '\u53d1\u919b',
    divergence: '\u5206\u6b67',
    rebound: '\u5f31\u8f6c\u5f3a',
    climax: '\u9ad8\u6f6e',
    fade: '\u9000\u6f6e',
    fade_watch: '\u9000\u6f6e\u89c2\u5bdf',
    fade_confirmed: '\u9000\u6f6e\u786e\u8ba4',
    repair: '\u4fee\u590d',
  };
  return map[stage] ?? stage;
}

function stageClass(stage: string): string {
  const map: Record<string, string> = {
    start: 'is-theme-start',
    fermentation: 'is-theme-fermentation',
    divergence: 'is-theme-divergence',
    rebound: 'is-theme-rebound',
    climax: 'is-theme-climax',
    fade: 'is-theme-fade',
  };
  return map[stage] ?? '';
}

interface Props {
  onThemeClick?: (themeId: string) => void;
}

export function ThemeSearchTab({ onThemeClick }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ThemeRadarItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    return () => { clearTimeout(timer.current); };
  }, []);

  const doSearch = (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setHasSearched(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchSubjectSearch(q.trim(), 30)
      .then((res) => {
        setResults(res.themes || []);
        setHasSearched(true);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : '\u641c\u7d22\u5931\u8d25');
        setResults([]);
        setHasSearched(true);
        setLoading(false);
      });
  };

  const handleInput = (value: string) => {
    setQuery(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => doSearch(value), 300);
  };

  const maxHeat = Math.max(1, ...results.map((t) => t.heat));

  return (
    <div className="theme-search-container">
      <div className="theme-search-input-wrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4a5568" strokeWidth="2">
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          className="theme-search-input"
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder={'\u8f93\u5165\u9898\u6750\u5173\u952e\u5b57...'}
          autoFocus
        />
      </div>

      {loading && <div className="empty-state compact">{'\u641c\u7d22\u4e2d...'}</div>}
      {error && <div className="empty-state compact error">{error}</div>}

      {!loading && !error && hasSearched && results.length === 0 && (
        <div className="empty-state compact">{'\u672a\u627e\u5230\u5339\u914d\u7684\u9898\u6750\uff0c\u8bf7\u5c1d\u8bd5\u5176\u4ed6\u5173\u952e\u5b57'}</div>
      )}

      {!loading && !error && !hasSearched && query.length === 0 && (
        <div className="empty-state compact">{'\u8f93\u5165\u5173\u952e\u5b57\u641c\u7d22\u9898\u6750'}</div>
      )}

      {results.length > 0 && (
        <div className="theme-radar-list">
          {results.map((item) => (
            <button
              key={item.theme_id}
              type="button"
              className="theme-radar-item"
              onClick={() => {
                if (onThemeClick) onThemeClick(item.theme_id);
                navigateTo(`/themes/${encodeURIComponent(item.theme_id)}`);
              }}
            >
              <div className="theme-radar-item-head">
                <strong>{item.theme_name}</strong>
                <span className="recap-chip is-status">{item.heat}</span>
              </div>
              <div className="theme-radar-heat-track">
                <div
                  className="theme-radar-heat-fill"
                  style={{ width: `${Math.round((item.heat / maxHeat) * 100)}%` }}
                />
              </div>
              <div className="theme-radar-item-meta">
                {item.stage && item.stage !== 'UNKNOWN' && stageLabel(item.stage) && (
                  <span className={`recap-chip ${stageClass(item.stage)}`}>
                    {stageLabel(item.stage)}
                  </span>
                )}
                {item.stock_count > 0 && (
                  <span className="recap-chip">{item.stock_count} \u80a1</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
