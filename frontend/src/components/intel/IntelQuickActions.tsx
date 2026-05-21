import React from 'react';
import { navigateTo } from '../../lib/navigation';

// 图标资源 — 从设计稿裁切，按语义映射
import realtimeIcon from '../../assets/intel-icons/icon_12.png';
import collectionIcon from '../../assets/intel-icons/icon_09.png';
import recapIcon from '../../assets/intel-icons/icon_07.png';
import premarketIcon from '../../assets/intel-icons/icon_08.png';
import screenerIcon from '../../assets/intel-icons/icon_06.png';
import strongwatchIcon from '../../assets/intel-icons/icon_05.png';

interface QuickAction {
  label: string;
  icon: string;
  href: string;
}

interface IntelQuickActionsProps {
  date?: string;
  recapDates?: {
    postMarket: string;
    preMarket: string;
  };
}

export function IntelQuickActions({ date, recapDates }: IntelQuickActionsProps) {
  const actions: QuickAction[] = [
    {
      label: '实时采集',
      icon: realtimeIcon,
      href: '/realtime-collector',
    },
    {
      label: '采集控制台',
      icon: collectionIcon,
      href: '/collection',
    },
    {
      label: '当日复盘',
      icon: recapIcon,
      href: `/recap?date=${recapDates?.postMarket || ''}&report_type=post_market`,
    },
    {
      label: '盘前必读',
      icon: premarketIcon,
      href: `/pre-market-brief?trade_date=${recapDates?.preMarket || ''}`,
    },
    {
      label: 'AI选股',
      icon: screenerIcon,
      href: '/screener',
    },
    {
      label: '强势股',
      icon: strongwatchIcon,
      href: `/intel/strong-stocks/watch?date=${date || ''}&window_days=7`,
    },
  ];

  return (
    <nav className="intel-quick-actions">
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          className="quick-action-card"
          onClick={() => navigateTo(action.href)}
          title={action.label}
        >
          <img src={action.icon} alt={action.label} className="quick-action-icon" />
          <span className="quick-action-label">{action.label}</span>
        </button>
      ))}
    </nav>
  );
}
