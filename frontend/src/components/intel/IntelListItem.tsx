import React from 'react';
import type { IntelFeedItem } from '../../lib/api';
import {
  formatOccurredAt,
  formatConfidence,
  formatImpactScore,
  getItemTone,
  getItemTypeLabel,
  getSourceLabel,
  getSourceChannelLabel,
} from '../../lib/utils/format';

interface IntelListItemProps {
  item: IntelFeedItem;
  active: boolean;
  onClick: (itemId: string, primaryThemeKey: string | null) => void;
}

export function IntelListItem({ item, active, onClick }: IntelListItemProps) {
  const primaryThemeKey = item.theme_subject_keys[0] ?? null;
  const primaryThemeName = item.theme_names[0] ?? primaryThemeKey ?? '--';

  const handleClick = () => {
    onClick(item.item_id, primaryThemeKey);
  };

  return (
    <button
      type="button"
      className={`intel-row intel-row-${getItemTone(item.item_type)} ${active ? 'active' : ''}`}
      onClick={handleClick}
    >
      <div className="intel-row-time">
        <span className="intel-row-date">{formatOccurredAt(item.occurred_at, item.item_type)}</span>
      </div>
      <div className="intel-row-body">
        <div className="intel-row-head">
          {getItemTypeLabel(item.item_type) && (
            <span className={`pill pill-${item.item_type}`}>{getItemTypeLabel(item.item_type)}</span>
          )}
          <span className="intel-row-source">{getSourceLabel(item.source_type)}</span>
          {item.source_channel && (
            <span className={`pill pill-channel pill-channel-${item.source_channel}`}>
              {getSourceChannelLabel(item.source_channel)}
            </span>
          )}
        </div>
        <div className="intel-row-theme">
          <strong className="intel-row-theme-name">{primaryThemeName}</strong>
        </div>
        <p className="intel-row-title">{item.summary || item.title || '无事件描述'}</p>
        {item.title && item.summary && item.title !== item.summary && (
          <p className="intel-row-summary">{item.title}</p>
        )}
        <div className="intel-row-meta">
          <span className="metric-chip">热度 {formatImpactScore(item.impact_score)}</span>
          <span className="metric-chip">置信 {formatConfidence(item.confidence)}</span>
          {item.stock_names.length > 0 && (
            <span className="intel-row-stocks">{item.stock_names.slice(0, 4).join(' / ')}</span>
          )}
        </div>
      </div>
    </button>
  );
}