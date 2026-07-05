import { Alert, Button } from "antd";
import type { PostMarketDailyReviewV2 } from "../../../lib/api";

interface Props {
  dailyReviewV2?: PostMarketDailyReviewV2 | null;
  onRetry: () => void;
}

function getMissingParts(dailyReviewV2?: PostMarketDailyReviewV2 | null) {
  if (!dailyReviewV2) {
    return ["遗留引擎(DailyReviewV2)未生成 — 上方题材强度面板已使用M4g证据融合引擎"];
  }

  const missing: string[] = [];
  if (!dailyReviewV2.engine_summary) missing.push("engine_summary");
  if (!dailyReviewV2.market_regime_review) missing.push("market_regime_review");
  if ((dailyReviewV2.mainline_daily_states?.length ?? 0) === 0) missing.push("mainline_daily_states");
  if (!dailyReviewV2.post_market_decision_v2) missing.push("post_market_decision_v2");
  return missing.length > 0 ? missing : ["引擎报告字段不完整"];
}

export default function EngineMissingState({ dailyReviewV2, onRetry }: Props) {
  const missing = getMissingParts(dailyReviewV2);

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 8, padding: 16, marginBottom: 14 }}>
      <Alert
        type="info"
        showIcon
        message="复盘引擎报告尚未生成或字段不完整"
        description={`缺失项：${missing.join("、")}。请点击“重新复盘”生成 DailyReviewV2 engine report。`}
        style={{ marginBottom: 12 }}
      />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button type="primary" onClick={onRetry}>重新复盘</Button>
      </div>
    </div>
  );
}
