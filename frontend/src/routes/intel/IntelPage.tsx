import { useMemo } from 'react';
import { navigateTo } from '../../lib/navigation';
import { useIntelFeed } from '../../hooks/useIntelFeed';
import { IntelHeader } from '../../components/intel/IntelHeader';
import { IntelFilters } from '../../components/intel/IntelFilters';
import { IntelList } from '../../components/intel/IntelList';

export function IntelPage() {
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
  } = useIntelFeed({ limit: 50 });

  const sourceSummary = useMemo(() => {
    const sources = payload?.diagnostics?.sources?.join(' / ') || '--';
    const channels = payload?.diagnostics?.source_channels?.join(' / ');
    return channels ? `${sources} | ${channels}` : sources;
  }, [payload]);

  const handleItemClick = (itemId: string, primaryThemeKey: string | null) => {
    setSelectedItemId(itemId);
    if (primaryThemeKey) {
      navigateTo(`/themes/${primaryThemeKey}`);
    }
  };

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

      <main className="intel-stream">
        <IntelList
          items={payload?.items ?? []}
          loading={loading}
          error={error}
          selectedItemId={selectedItemId}
          onItemClick={handleItemClick}
        />
      </main>
    </div>
  );
}
