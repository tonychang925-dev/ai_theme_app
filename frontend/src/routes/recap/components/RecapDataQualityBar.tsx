/** PR-14B: 数据质量提示条 — 提示哪些引擎模块可用/缺失。 */
import { Alert } from "antd";

interface Props {
  indexReady?: boolean;
  mainlineReady?: boolean;
  pdv2Ready?: boolean;
}

export default function RecapDataQualityBar({ indexReady, mainlineReady, pdv2Ready }: Props) {
  const missing: string[] = [];
  if (!indexReady) missing.push("指数技术分析");
  if (!mainlineReady) missing.push("主线状态");
  if (!pdv2Ready) missing.push("PDV2 决策");

  if (missing.length === 0) return null;

  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginBottom: 10 }}
      message={`复盘引擎数据不完整（缺失：${missing.join("、")}），交易结论默认偏保守。`}
    />
  );
}
