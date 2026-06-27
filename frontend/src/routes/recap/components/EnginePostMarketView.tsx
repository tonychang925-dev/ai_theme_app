import type { PostMarketDailyReviewV2 } from "../../../lib/api";
import LayerCStrongPoolPanel from "./LayerCStrongPoolPanel";
import MainlineNarrativePanel from "./MainlineNarrativePanel";
import MarketOverviewNarrativePanel from "./MarketOverviewNarrativePanel";
import MarketRegimePanel from "./MarketRegimePanel";
import EvidenceLayerPanel from "./EvidenceLayerPanel";
import RecapDataQualityBar from "./RecapDataQualityBar";
import OneToTwoWatchPanel from "./OneToTwoWatchPanel";
import DailyRecapStoryPanel from "./DailyRecapStoryPanel";

interface Props {
  dailyReviewV2: PostMarketDailyReviewV2;
  tradeDate?: string;
  subjectKeyToThemeName?: Map<string, string>;
}

export default function EnginePostMarketView({ dailyReviewV2, tradeDate, subjectKeyToThemeName }: Props) {
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
        <DailyRecapStoryPanel
          essentials={dailyReviewV2.daily_recap_essentials ?? null}
          ladder={dailyReviewV2.limit_up_ladder ?? null}
          themeEvents={dailyReviewV2.limit_up_theme_events ?? null}
          limitUpThemeMatrix={dailyReviewV2.limit_up_theme_matrix ?? null}
          newHigh={dailyReviewV2.new_high_summary ?? null}
          seatMoney={dailyReviewV2.seat_money_summary ?? null}
          subjectKeyToThemeName={subjectKeyToThemeName}
          tradeDate={tradeDate}
        />

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

        {dailyReviewV2.mainline_narrative && (
          <section className="workspace-card recap-engine-group">
            <h3 className="section-title recap-panel-title">主线概览</h3>
            <div className="recap-engine-group-stack">
              <MainlineNarrativePanel narrative={dailyReviewV2.mainline_narrative} />
            </div>
          </section>
        )}

        <section className="workspace-card recap-engine-group">
          <h3 className="section-title recap-panel-title">强股与证据</h3>
          <div className="recap-engine-group-stack">
            <LayerCStrongPoolPanel review={review} tradeDate={tradeDate} />
            <EvidenceLayerPanel evidenceLayerReview={dailyReviewV2.evidence_layer_review ?? null} />
          </div>
        </section>

        <section className="workspace-card recap-engine-group">
          <OneToTwoWatchPanel dailyReviewV2={dailyReviewV2} tradeDate={tradeDate} />
        </section>
      </div>
    </>
  );
}
