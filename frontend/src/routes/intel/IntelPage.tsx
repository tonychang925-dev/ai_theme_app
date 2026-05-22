import { useEffect, useMemo, useState } from 'react';
import { navigateTo } from '../../lib/navigation';
import { useIntelFeed } from '../../hooks/useIntelFeed';
import { IntelHeader } from '../../components/intel/IntelHeader';
import { IntelList } from '../../components/intel/IntelList';
import { ThreeColumnLayout } from '../../components/ThreeColumnLayout';
import {
  fetchWorkspaceMarketValidation,
  fetchWorkspaceThemeRadar,
  type MarketValidationView,
  type ThemeRadarItem,
} from '../../lib/api';

export function IntelPage() {
  const [selectedTheme, setSelectedTheme] = useState<string | null>(null);
  const [themeFilterEnabled, setThemeFilterEnabled] = useState(false);
  const {
    date, setDate, type, setType, session, setSession,
    payload, loading, error,
    selectedItemId, setSelectedItemId,
    liveStatus, liveNewCount, sseConnectionState,
    streamDiagnostics, recapDates,
  } = useIntelFeed({ limit: 50, subjectKey: themeFilterEnabled ? selectedTheme : null });
  const [themeRadar, setThemeRadar] = useState<ThemeRadarItem[]>([]);
  const [marketValidation, setMarketValidation] = useState<MarketValidationView | null>(null);
  const [workspaceErrors, setWorkspaceErrors] = useState<{ themeRadar: string | null; marketValidation: string | null }>({
    themeRadar: null, marketValidation: null,
  });

  const sourceSummary = useMemo(() => {
    const sources = payload?.diagnostics?.sources?.join(' / ') || '--';
    const channels = payload?.diagnostics?.source_channels?.join(' / ');
    return channels ? `${sources} | ${channels}` : sources;
  }, [payload]);

  const handleItemClick = (itemId: string, primaryThemeKey: string | null) => {
    setSelectedItemId(itemId);
    if (primaryThemeKey) {
      setSelectedTheme(primaryThemeKey);
      navigateTo(`/themes/${encodeURIComponent(primaryThemeKey)}`);
    }
  };

  useEffect(() => {
    let active = true;
    fetchWorkspaceThemeRadar({ date, session, limit: 20 })
      .then((res) => {
        if (!active) return;
        setThemeRadar(res.themes || []);
        setWorkspaceErrors((prev) => ({ ...prev, themeRadar: null }));
        if (!selectedTheme && res.themes?.length) {
          setSelectedTheme(res.themes[0].theme_id);
        }
      })
      .catch((e) => {
        if (!active) return;
        setWorkspaceErrors((prev) => ({ ...prev, themeRadar: e instanceof Error ? e.message : "theme radar failed" }));
      });
    return () => { active = false; };
  }, [date, session, selectedTheme]);

  useEffect(() => {
    let active = true;
    const selectedItem = (payload?.items || []).find((it) => it.item_id === selectedItemId) || null;
    const stockId = selectedItem?.stock_ids?.[0];
    fetchWorkspaceMarketValidation({ tradeDate: date, subjectKey: selectedTheme || undefined, stockId })
      .then((res) => {
        if (!active) return;
        setMarketValidation(res);
        setWorkspaceErrors((prev) => ({ ...prev, marketValidation: null }));
      })
      .catch((e) => {
        if (!active) return;
        setWorkspaceErrors((prev) => ({ ...prev, marketValidation: e instanceof Error ? e.message : "market validation failed" }));
      });
    return () => { active = false; };
  }, [date, payload, selectedItemId, selectedTheme]);

  const leftPanel = (
    <section className="workspace-card">
      <h3>主题雷达</h3>
      <label className="workspace-note" style={{ display: "block", marginBottom: 8 }}>
        <input type="checkbox" checked={themeFilterEnabled}
          onChange={(e) => setThemeFilterEnabled(e.target.checked)}
          style={{ marginRight: 6 }} />
        按左栏主题过滤中栏
      </label>
      <ul className="workspace-list">
        {themeRadar.map((row) => (
          <li key={row.theme_id}>
            <button type="button" className="link-button" onClick={() => setSelectedTheme(row.theme_id)}>{row.theme_name}</button>
            <p className="workspace-note">热度 {row.heat} | 阶段 {row.stage} | 关联股 {row.stock_count}</p>
          </li>
        ))}
      </ul>
    </section>
  );

  const rightPanel = (
    <section className="workspace-card">
      <h3>市场验证</h3>
      <p className="workspace-note">候选级别: {marketValidation?.candidate_level || "--"}</p>
      <p className="workspace-note">支撑类型: {marketValidation?.support_type || "--"}</p>
      <p className="workspace-note">支撑分数: {marketValidation?.support_score ?? "--"}</p>
      <p className="workspace-note">强势池数量: {marketValidation?.strong_watch_count ?? "--"}</p>
      <p className="workspace-note">弱转强候选数量: {marketValidation?.w2s_candidate_count ?? "--"}</p>
      <p className="workspace-note">Fallback状态: {streamDiagnostics.fallbackActive ? "开启" : "关闭"}</p>
      <p className="workspace-note">Fallback原因: {streamDiagnostics.fallbackReason || "--"}</p>
      <p className="workspace-note">流恢复时间: {streamDiagnostics.streamRecoveredAt || "--"}</p>
      {!!marketValidation?.reject_reasons?.length && (
        <ul className="workspace-list">{marketValidation.reject_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      )}
      {workspaceErrors.themeRadar && <p className="workspace-note">ThemeRadar异常: {workspaceErrors.themeRadar}</p>}
      {workspaceErrors.marketValidation && <p className="workspace-note">MarketValidation异常: {workspaceErrors.marketValidation}</p>}
    </section>
  );

  return (
    <div className="intel-shell">
      <IntelHeader
        sourceSummary={sourceSummary}
        payloadCount={payload?.count ?? 0}
        liveStatus={liveStatus}
        sseConnectionState={sseConnectionState}
        liveNewCount={liveNewCount}
        date={date}
        setDate={setDate}
        session={session}
        setSession={setSession}
        type={type}
        setType={setType}
        recapDates={recapDates}
      />

      <ThreeColumnLayout
        leftPanel={leftPanel}
        centerPanel={
          <main className="intel-stream">
            <IntelList
              items={payload?.items ?? []}
              loading={loading}
              error={error}
              selectedItemId={selectedItemId}
              onItemClick={handleItemClick}
            />
          </main>
        }
        rightPanel={rightPanel}
        minHeight="calc(100vh - 80px)"
      />
    </div>
  );
}
