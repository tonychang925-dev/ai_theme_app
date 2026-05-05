import React from 'react';
import type { IntelFeedItem } from '../../lib/api';
import { IntelListItem } from './IntelListItem';

interface IntelListProps {
  items: IntelFeedItem[];
  loading: boolean;
  error: string | null;
  selectedItemId: string | null;
  onItemClick: (itemId: string, primaryThemeKey: string | null) => void;
}

export function IntelList({
  items,
  loading,
  error,
  selectedItemId,
  onItemClick,
}: IntelListProps) {
  // Guardrail: keep already loaded items visible even if a transient
  // loading/error state appears during stream reconnect or fallback polling.
  if (items.length > 0) {
    return (
      <section className="intel-list intel-list-dense">
        {items.map((item) => (
          <IntelListItem
            key={item.item_id}
            item={item}
            active={selectedItemId === item.item_id}
            onClick={onItemClick}
          />
        ))}
      </section>
    );
  }

  if (loading) {
    return <div className="empty-state">正在加载情报流...</div>;
  }

  if (error) {
    return <div className="empty-state error">{error}</div>;
  }

  if (!loading && !error && items.length === 0) {
    return <div className="empty-state">当日无情报项</div>;
  }

  return <div className="empty-state">当日无情报项</div>;
}
