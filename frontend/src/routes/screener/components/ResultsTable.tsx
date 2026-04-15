interface ResultItem {
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  dimension_scores: {
    mainline: number;
    cycle: number;
    leader: number;
    technical: number;
  };
  rank_position: number;
  screening_reason: string;
  theme_info?: {
    subject_key: string;
    theme_name: string;
  };
  llm_review?: {
    decision: string;
    confidence?: number;
    reasoning?: string;
  };
}

interface ResultsTableProps {
  results: ResultItem[];
  isLoading: boolean;
  onRowClick: (resultId: string) => void;
  onAddFavorite: (resultId: string) => void;
  sortBy: keyof ResultItem;
  sortDirection: "asc" | "desc";
  onSortChange: (field: keyof ResultItem) => void;
  onNavigateToStock?: (stockId: string) => void;
  onNavigateToTheme?: (subjectKey: string) => void;
}

export function ResultsTable(props: ResultsTableProps) {
  const { results, isLoading, onRowClick, onAddFavorite, onNavigateToStock, onNavigateToTheme } = props;

  if (isLoading) {
    return <div className="p-4 text-sm text-gray-500">加载中...</div>;
  }

  return (
    <table className="min-w-full divide-y divide-gray-200 text-sm">
      <thead className="bg-gray-50">
        <tr>
          <th className="px-3 py-2 text-left">排名</th>
          <th className="px-3 py-2 text-left">股票</th>
          <th className="px-3 py-2 text-left">题材</th>
          <th className="px-3 py-2 text-left">综合分</th>
          <th className="px-3 py-2 text-left">维度分</th>
          <th className="px-3 py-2 text-left">LLM复核</th>
          <th className="px-3 py-2 text-left">操作</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {results.map((item) => (
          <tr key={item.result_id} className="hover:bg-gray-50">
            <td className="px-3 py-2">{item.rank_position ?? "-"}</td>
            <td className="px-3 py-2">
              <button type="button" className="text-blue-600 hover:underline" onClick={() => onNavigateToStock?.(item.stock_id)}>
                {item.stock_name || item.stock_id}
              </button>
            </td>
            <td className="px-3 py-2">
              {item.theme_info?.subject_key ? (
                <button
                  type="button"
                  className="text-indigo-600 hover:underline"
                  onClick={() => onNavigateToTheme?.(item.theme_info!.subject_key)}
                >
                  {item.theme_info?.theme_name || item.theme_info?.subject_key}
                </button>
              ) : (
                "-"
              )}
            </td>
            <td className="px-3 py-2 font-medium">{item.composite_score.toFixed(2)}</td>
            <td className="px-3 py-2">
              <div className="space-y-1">
                <div className="flex items-center text-xs">
                  <span className="w-16 text-gray-500">主线:</span>
                  <span className="font-medium">{item.dimension_scores.mainline.toFixed(1)}</span>
                </div>
                <div className="flex items-center text-xs">
                  <span className="w-16 text-gray-500">周期:</span>
                  <span className="font-medium">{item.dimension_scores.cycle.toFixed(1)}</span>
                </div>
                <div className="flex items-center text-xs">
                  <span className="w-16 text-gray-500">龙头:</span>
                  <span className="font-medium">{item.dimension_scores.leader.toFixed(1)}</span>
                </div>
                <div className="flex items-center text-xs">
                  <span className="w-16 text-gray-500">技术:</span>
                  <span className="font-medium">{item.dimension_scores.technical.toFixed(1)}</span>
                </div>
              </div>
            </td>
            <td className="px-3 py-2">
              {item.llm_review ? (
                <div className="space-y-1">
                  <span className={`inline-block px-2 py-1 text-xs rounded-full ${
                    item.llm_review.decision === 'pass' ? 'bg-green-100 text-green-800' :
                    item.llm_review.decision === 'watch' ? 'bg-yellow-100 text-yellow-800' :
                    item.llm_review.decision === 'reject' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {item.llm_review.decision}
                  </span>
                  {item.llm_review.confidence && (
                    <div className="text-xs text-gray-500">
                      置信度: {(item.llm_review.confidence * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              ) : (
                <span className="text-xs text-gray-400">未复核</span>
              )}
            </td>
            <td className="px-3 py-2">
              <div className="flex items-center gap-2">
                <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => onRowClick(item.result_id)}>
                  详情
                </button>
                <button type="button" className="text-xs text-green-600 hover:underline" onClick={() => onAddFavorite(item.result_id)}>
                  收藏
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
