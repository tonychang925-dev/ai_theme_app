interface FavoriteItem {
  favorite_id: string;
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
}

interface FavoritePanelProps {
  favorites: FavoriteItem[];
  onRemoveFavorite: (favoriteId: string) => void;
  onViewDetail: (resultId: string) => void;
  onNavigateToStock: (stockId: string) => void;
}

export function FavoritePanel({ favorites, onRemoveFavorite, onViewDetail, onNavigateToStock }: FavoritePanelProps) {
  if (!favorites.length) {
    return <p className="workspace-note">暂无收藏</p>;
  }

  return (
    <ul className="screener-fav-list">
      {favorites.slice(0, 10).map((item) => (
        <li key={item.favorite_id} className="screener-fav-item">
          <div className="screener-fav-head">
            <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => onNavigateToStock(item.stock_id)}>
              {item.stock_name || item.stock_id}
            </button>
            <span className="metric-label">{item.composite_score?.toFixed?.(1) ?? '-'}</span>
          </div>
          <div className="screener-fav-actions">
            <button type="button" className="recap-theme-link" onClick={() => onViewDetail(item.result_id)}>
              查看
            </button>
            <button type="button" className="recap-theme-link" onClick={() => onRemoveFavorite(item.favorite_id)}>
              移除
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
