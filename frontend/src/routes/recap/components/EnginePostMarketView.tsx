import { Button, Table, Tag } from "antd";
import type {
  EvidenceAlignment,
  EvidenceAlignmentIndex,
  PostMarketDailyReviewV2,
  PostMarketDecisionV2Review,
} from "../../../lib/api";
import EvidenceGroupWrapper from "./EvidenceGroupWrapper";
import EvidenceTags from "./EvidenceTags";
import EngineDecisionHeader from "./EngineDecisionHeader";
import LayerCStrongPoolPanel from "./LayerCStrongPoolPanel";
import MainlineStateBoard from "./MainlineStateBoard";
import MarketOverviewNarrativePanel from "./MarketOverviewNarrativePanel";
import MarketHotspotOverviewPanel from "./MarketHotspotOverviewPanel";
import MarketOverviewPanel from "./MarketOverviewPanel";
import MarketRegimePanel from "./MarketRegimePanel";
import RecapDataQualityBar from "./RecapDataQualityBar";
import D1NextDayWatchPanel from "./D1NextDayWatchPanel";

interface Props {
  dailyReviewV2: PostMarketDailyReviewV2;
  tradeDate?: string;
  onShowLegacy: () => void;
}

function toAlignmentRows(review: PostMarketDecisionV2Review) {
  return (review.strong_stock_pool_reviews ?? []).filter((row) => row && typeof row === "object") as Record<string, unknown>[];
}

function displayThemeName(row: Record<string, unknown>) {
  return String(row.mainline_name || row.theme_name || "其他").trim() || "其他";
}

function EngineEvidencePanel({ review, alignmentIndex }: { review: PostMarketDecisionV2Review; alignmentIndex?: EvidenceAlignmentIndex | null }) {
  const rows = toAlignmentRows(review);
  if (rows.length === 0) return null;

  const columns = [
    { title: "股票", dataIndex: "stock_name", key: "stock", width: 84 },
    { title: "题材", dataIndex: "theme_name", key: "theme", width: 112, ellipsis: true, render: (_: unknown, row: Record<string, unknown>) => displayThemeName(row) },
    { title: "角色", dataIndex: "relay_role", key: "role", width: 60, ellipsis: true },
    { title: "评分", dataIndex: "watch_score", key: "score", width: 60, render: (v: number | null | undefined) => (v != null ? Number(v).toFixed(0) : "-") },
    {
      title: "证据",
      key: "evidence",
      width: 180,
      render: (_: unknown, row: Record<string, unknown>) => {
        const alignment = row.stock_id ? (alignmentIndex?.by_stock?.[String(row.stock_id)] as EvidenceAlignment | undefined) : undefined;
        return <EvidenceTags alignment={alignment ?? null} />;
      },
    },
  ];

  const groups = [
    {
      key: "focus",
      label: "重点关注",
      type: "success" as const,
      filter: (alignment: Record<string, unknown>) => Boolean(alignment.is_focus_stock),
    },
    {
      key: "layer_c",
      label: "强势股池",
      type: "warning" as const,
      filter: (alignment: Record<string, unknown>) => Boolean(alignment.in_layer_c && !alignment.is_focus_stock),
    },
    {
      key: "d1",
      label: "次日观察",
      type: "info" as const,
      filter: (alignment: Record<string, unknown>) => Boolean(alignment.is_d1_candidate && !alignment.in_layer_c && !alignment.is_focus_stock),
    },
  ];

  return (
    <EvidenceGroupWrapper
    title="证据层"
    rows={rows}
    alignmentIndex={alignmentIndex ?? null}
    groups={groups}
  >
      {(groupRows, groupKey) => (
        <div className="recap-table-shell">
          <Table
            dataSource={groupRows.map((row, index) => ({ ...row, key: String(row.stock_id || index) }))}
            columns={columns}
            size="small"
            pagination={false}
            rowClassName={() => (groupKey === "non_mainline" ? "recap-row-muted" : "")}
          />
        </div>
      )}
    </EvidenceGroupWrapper>
  );
}

export default function EnginePostMarketView({ dailyReviewV2, tradeDate, onShowLegacy }: Props) {
  const review = dailyReviewV2.post_market_decision_v2;
  if (!review || !dailyReviewV2.engine_summary || !dailyReviewV2.market_regime_review) return null;

  return (
    <>
      <RecapDataQualityBar
        indexReady={(dailyReviewV2.index_technical_reviews?.length ?? 0) > 0}
        mainlineReady={(dailyReviewV2.mainline_daily_states?.length ?? 0) > 0}
        pdv2Ready={!!dailyReviewV2.post_market_decision_v2}
      />
      <EngineDecisionHeader
        engineSummary={dailyReviewV2.engine_summary}
        marketRegime={dailyReviewV2.market_regime_review ?? null}
      />
      <MarketOverviewNarrativePanel
        narrative={dailyReviewV2.market_overview_narrative ?? null}
        engineSummary={dailyReviewV2.engine_summary ?? null}
        marketRegime={dailyReviewV2.market_regime_review ?? null}
      />
      <MarketHotspotOverviewPanel
        marketHotspotOverview={dailyReviewV2.market_hotspot_overview ?? null}
        tradeDate={tradeDate}
      />
      <MarketRegimePanel
        marketRegime={dailyReviewV2.market_regime_review}
        indexReviews={dailyReviewV2.index_technical_reviews}
        tradeDate={tradeDate}
      />
      {dailyReviewV2.market_overview_review && (
        <MarketOverviewPanel
          marketOverview={dailyReviewV2.market_overview_review}
          tradeDate={tradeDate}
        />
      )}
      {(dailyReviewV2.mainline_daily_states?.length ?? 0) > 0 && (
        <MainlineStateBoard rows={dailyReviewV2.mainline_daily_states!} tradeDate={tradeDate} />
      )}
      <D1NextDayWatchPanel review={review} />
      <LayerCStrongPoolPanel review={review} />
      <EngineEvidencePanel review={review} alignmentIndex={dailyReviewV2.evidence_alignment_index ?? null} />
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
        <Button onClick={onShowLegacy}>查看旧版 sections</Button>
      </div>
    </>
  );
}
