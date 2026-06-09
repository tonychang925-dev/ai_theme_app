import { Button } from "antd";
import type { PostMarketDailyReviewV2 } from "../../../lib/api";
import LayerCStrongPoolPanel from "./LayerCStrongPoolPanel";
import MainlineStateBoard from "./MainlineStateBoard";
import MainlineNarrativePanel from "./MainlineNarrativePanel";
import MarketOverviewNarrativePanel from "./MarketOverviewNarrativePanel";
import MarketHotspotOverviewPanel from "./MarketHotspotOverviewPanel";
import MarketOverviewPanel from "./MarketOverviewPanel";
import MarketRegimePanel from "./MarketRegimePanel";
import D1NarrativePanel from "./D1NarrativePanel";
import EvidenceLayerPanel from "./EvidenceLayerPanel";
import RecapDataQualityBar from "./RecapDataQualityBar";
import D1NextDayWatchPanel from "./D1NextDayWatchPanel";

interface Props {
  dailyReviewV2: PostMarketDailyReviewV2;
  tradeDate?: string;
  onShowLegacy: () => void;
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
      <div className="recap-engine-groups">
        <section className="workspace-card recap-engine-group">
          <h3 className="section-title recap-panel-title">市场概览</h3>
          <div className="recap-engine-group-stack">
            <MarketOverviewNarrativePanel
              narrative={dailyReviewV2.market_overview_narrative ?? null}
              engineSummary={dailyReviewV2.engine_summary ?? null}
              marketRegime={dailyReviewV2.market_regime_review ?? null}
            />
            <div className="recap-full-width">
              <MarketRegimePanel
                marketRegime={dailyReviewV2.market_regime_review}
                indexReviews={dailyReviewV2.index_technical_reviews}
                tradeDate={tradeDate}
              />
            </div>
          </div>
        </section>

        <section className="workspace-card recap-engine-group">
          <h3 className="section-title recap-panel-title">热点概览</h3>
          <div className="recap-engine-group-stack">
            <MarketHotspotOverviewPanel
              marketHotspotOverview={dailyReviewV2.market_hotspot_overview ?? null}
              tradeDate={tradeDate}
            />
            {dailyReviewV2.market_overview_review && (
              <MarketOverviewPanel
                marketOverview={dailyReviewV2.market_overview_review}
                tradeDate={tradeDate}
              />
            )}
          </div>
        </section>

        <section className="workspace-card recap-engine-group">
          <h3 className="section-title recap-panel-title">主线概览</h3>
          <div className="recap-engine-group-stack">
            <MainlineNarrativePanel narrative={dailyReviewV2.mainline_narrative ?? null} />
            {(dailyReviewV2.mainline_daily_states?.length ?? 0) > 0 && (
              <MainlineStateBoard rows={dailyReviewV2.mainline_daily_states!} tradeDate={tradeDate} />
            )}
          </div>
        </section>

        <section className="workspace-card recap-engine-group">
          <h3 className="section-title recap-panel-title">强股与证据</h3>
          <div className="recap-engine-group-stack">
            <LayerCStrongPoolPanel review={review} tradeDate={tradeDate} />
            <EvidenceLayerPanel evidenceLayerReview={dailyReviewV2.evidence_layer_review ?? null} />
          </div>
        </section>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
        <Button onClick={onShowLegacy}>查看旧版 sections</Button>
      </div>
    </>
  );
}
