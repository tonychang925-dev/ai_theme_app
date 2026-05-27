import { useEffect, useMemo, useState } from 'react';
import { navigateTo } from '../../lib/navigation';
import { useIntelFeed } from '../../hooks/useIntelFeed';
import { IntelHeader } from '../../components/intel/IntelHeader';
import { IntelList } from '../../components/intel/IntelList';
import { ThemeRadarPanel } from '../../components/intel/ThemeRadarPanel';
import { MarketValidationPanel } from '../../components/intel/MarketValidationPanel';
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
    realtimeHealth,
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
    <ThemeRadarPanel
      themes={themeRadar}
      loading={false}
      error={workspaceErrors.themeRadar}
      selectedTheme={selectedTheme}
      onThemeClick={setSelectedTheme}
      themeFilterEnabled={themeFilterEnabled}
      onToggleFilter={setThemeFilterEnabled}
    />
  );

  const rightPanel = (
    <MarketValidationPanel
      data={marketValidation}
      loading={false}
      error={workspaceErrors.marketValidation}
    />
  );

  return (
    <div className="intel-shell">
      <IntelHeader
        sourceSummary={sourceSummary}
        payloadCount={payload?.count ?? 0}
        liveStatus={liveStatus}
        sseConnectionState={sseConnectionState}
        liveNewCount={liveNewCount}
        realtimeHealth={realtimeHealth}
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
