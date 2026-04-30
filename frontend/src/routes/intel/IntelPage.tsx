import { useEffect, useMemo, useState } from 'react';
import { navigateTo } from '../../lib/navigation';
import { useIntelFeed } from '../../hooks/useIntelFeed';
import { IntelHeader } from '../../components/intel/IntelHeader';
import { IntelFilters } from '../../components/intel/IntelFilters';
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
  const {
    // Filter state
    date,
    setDate,
    type,
    setType,
    session,
    setSession,

    // Data state
    payload,
    loading,
    error,

    // UI state
    selectedItemId,
    setSelectedItemId,

    // Real-time state
    liveStatus,
    liveNewCount,
    sseConnectionState,
    recapDates,
  } = useIntelFeed({ limit: 50, subjectKey: selectedTheme });
  const [themeRadar, setThemeRadar] = useState<ThemeRadarItem[]>([]);
  const [marketValidation, setMarketValidation] = useState<MarketValidationView | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  const sourceSummary = useMemo(() => {
    const sources = payload?.diagnostics?.sources?.join(' / ') || '--';
    const channels = payload?.diagnostics?.source_channels?.join(' / ');
    return channels ? `${sources} | ${channels}` : sources;
  }, [payload]);

  const handleItemClick = (itemId: string, primaryThemeKey: string | null) => {
    setSelectedItemId(itemId);
    if (primaryThemeKey) setSelectedTheme(primaryThemeKey);
  };

  useEffect(() => {
    let active = true;
    fetchWorkspaceThemeRadar({ date, session, limit: 20 })
      .then((res) => {
        if (!active) return;
        setThemeRadar(res.themes || []);
        if (!selectedTheme && res.themes?.length) {
          setSelectedTheme(res.themes[0].theme_id);
        }
      })
      .catch((e) => {
        if (!active) return;
        setWorkspaceError(e instanceof Error ? e.message : "theme radar failed");
      });
    return () => {
      active = false;
    };
  }, [date, session, selectedTheme]);

  useEffect(() => {
    let active = true;
    const selectedItem = (payload?.items || []).find((it) => it.item_id === selectedItemId) || null;
    const stockId = selectedItem?.stock_ids?.[0];
    fetchWorkspaceMarketValidation({
      tradeDate: date,
      subjectKey: selectedTheme || undefined,
      stockId,
    })
      .then((res) => {
        if (!active) return;
        setMarketValidation(res);
      })
      .catch((e) => {
        if (!active) return;
        setWorkspaceError(e instanceof Error ? e.message : "market validation failed");
      });
    return () => {
      active = false;
    };
  }, [date, payload, selectedItemId, selectedTheme]);

  const leftPanel = (
    <section className="workspace-card">
      <h3>主题雷达</h3>
      <ul className="workspace-list">
        {themeRadar.map((row) => (
          <li key={row.theme_id}>
            <button type="button" className="link-button" onClick={() => setSelectedTheme(row.theme_id)}>
              {row.theme_name}
            </button>
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
      {!!marketValidation?.reject_reasons?.length && (
        <ul className="workspace-list">
          {marketValidation.reject_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {workspaceError && <p className="workspace-note">{workspaceError}</p>}
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
      />

      <IntelFilters
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
        minHeight="calc(100vh - 140px)"
      />
    </div>
  );
}
