interface ResultItem {
  result_id: string;
  stock_name: string;
  composite_score: number;
}

interface ResultsChartProps {
  results: ResultItem[];
  chartType: "radar" | "scatter" | "bar" | "pie";
  dimensions: ("mainline" | "cycle" | "leader" | "technical")[];
  onDataPointClick?: (resultId: string) => void;
}

export function ResultsChart({ results, chartType, onDataPointClick }: ResultsChartProps) {
  const top = results.slice(0, 8);
  const max = Math.max(...top.map((x) => x.composite_score), 1);

  if (chartType === "pie") {
    const buckets = [
      { key: "ge90", label: ">= 90", color: "#8ee0a1", count: results.filter((x) => x.composite_score >= 90).length },
      { key: "80_89", label: "80-89", color: "#9cc0ff", count: results.filter((x) => x.composite_score >= 80 && x.composite_score < 90).length },
      { key: "70_79", label: "70-79", color: "#f7d45a", count: results.filter((x) => x.composite_score >= 70 && x.composite_score < 80).length },
      { key: "lt70", label: "< 70", color: "#ffb0b0", count: results.filter((x) => x.composite_score < 70).length },
    ];
    const total = Math.max(results.length, 1);
    let start = 0;
    const segments = buckets.map((b) => {
      const ratio = b.count / total;
      const end = start + ratio * 360;
      const seg = `${b.color} ${start}deg ${end}deg`;
      start = end;
      return seg;
    });
    const gradient = `conic-gradient(${segments.join(", ")})`;

    return (
      <div className="screener-pie-layout">
        <div className="screener-pie" style={{ background: gradient }} aria-label="得分分布饼图" />
        <div className="screener-pie-legend">
          {buckets.map((b) => (
            <div key={b.key} className="screener-pie-item">
              <span className="screener-pie-dot" style={{ background: b.color }} />
              <span>{b.label}</span>
              <strong>{b.count}</strong>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {top.map((item) => (
        <button
          key={item.result_id}
          type="button"
          onClick={() => onDataPointClick?.(item.result_id)}
          className="block w-full text-left"
        >
          <div className="mb-1 flex items-center justify-between text-xs text-gray-600">
            <span>{item.stock_name || item.result_id}</span>
            <span>{item.composite_score.toFixed(1)}</span>
          </div>
          <div className="h-2 rounded bg-gray-100">
            <div className="h-2 rounded bg-blue-500" style={{ width: `${(item.composite_score / max) * 100}%` }} />
          </div>
        </button>
      ))}
    </div>
  );
}
