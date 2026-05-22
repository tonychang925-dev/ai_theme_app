import React from 'react';
import { useAuth } from '../../routes/auth/AuthProvider';
import { navigateTo } from '../../lib/navigation';
import type { SSEConnectionState } from '../../lib/api';
import logoImg from '../../assets/intel-icons/logo.png';
import realtimeIcon from '../../assets/intel-icons/实时采集.png';
import collectionIcon from '../../assets/intel-icons/采集控制台.png';
import recapIcon from '../../assets/intel-icons/当日复盘.png';
import premarketIcon from '../../assets/intel-icons/盘前必读.png';
import screenerIcon from '../../assets/intel-icons/AI选股.png';
import strongwatchIcon from '../../assets/intel-icons/强势股跟踪.png';

interface IntelHeaderProps {
  sourceSummary: string;
  payloadCount: number;
  liveStatus: 'connecting' | 'live' | 'fallback';
  sseConnectionState: SSEConnectionState | null;
  liveNewCount: number;
  date: string;
  setDate: (d: string) => void;
  session: string;
  setSession: (s: string) => void;
  type: string;
  setType: (t: string) => void;
  recapDates: { postMarket: string; preMarket: string };
}

export function IntelHeader({
  sourceSummary, payloadCount, liveStatus, liveNewCount,
  date, setDate, session, setSession, type, setType, recapDates,
}: IntelHeaderProps) {
  const liveStatusText = { 'live': '在线', 'connecting': '连接中', 'fallback': '兜底模式' }[liveStatus];
  const { user, logout } = useAuth();

  return (
    <header className="intel-toolbar">
      {/* Logo + Title */}
      <div className="intel-brand">
        <img src={logoImg} alt="Logo" className="intel-logo" />
        <h1 className="intel-title">AI投资助理</h1>
      </div>

      {/* Quick Actions */}
      <nav className="intel-quick-actions">
        <button type="button" className="quick-action-card" onClick={() => navigateTo('/realtime-collector')}>
          <img src={realtimeIcon} alt="实时采集" className="quick-action-icon" />
          <span className="quick-action-tooltip">实时采集</span>
        </button>
        <button type="button" className="quick-action-card" onClick={() => navigateTo('/collection')}>
          <img src={collectionIcon} alt="采集控制台" className="quick-action-icon" />
          <span className="quick-action-tooltip">采集控制台</span>
        </button>
        <button type="button" className="quick-action-card" onClick={() => navigateTo(`/recap?date=${recapDates.postMarket || ''}&report_type=post_market`)}>
          <img src={recapIcon} alt="当日复盘" className="quick-action-icon" />
          <span className="quick-action-tooltip">当日复盘</span>
        </button>
        <button type="button" className="quick-action-card" onClick={() => navigateTo(`/pre-market-brief?trade_date=${recapDates.preMarket || ''}`)}>
          <img src={premarketIcon} alt="盘前必读" className="quick-action-icon" />
          <span className="quick-action-tooltip">盘前必读</span>
        </button>
        <button type="button" className="quick-action-card" onClick={() => navigateTo('/screener')}>
          <img src={screenerIcon} alt="AI选股" className="quick-action-icon" />
          <span className="quick-action-tooltip">AI选股</span>
        </button>
        <button type="button" className="quick-action-card" onClick={() => navigateTo(`/intel/strong-stocks/watch?date=${date}&window_days=7`)}>
          <img src={strongwatchIcon} alt="强势股跟踪" className="quick-action-icon" />
          <span className="quick-action-tooltip">强势股跟踪</span>
        </button>
      </nav>

      {/* Filters */}
      <div className="intel-filters">
        <select value={session} onChange={(e) => setSession(e.target.value)} className="intel-filter-select">
          <option value="all">全部时段</option>
          <option value="pre">盘前</option>
          <option value="intra">盘中</option>
          <option value="post">盘后</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} className="intel-filter-select">
          <option value="all">全部类型</option>
          <option value="recap">复盘</option>
          <option value="weak_to_strong">弱转强</option>
          <option value="theme_cycle">题材周期</option>
          <option value="stock_signal">强势股</option>
          <option value="event_review">待复核</option>
          <option value="event">新事件</option>
          <option value="stock_move">异动</option>
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="intel-filter-select" />
      </div>

      {/* Connection Status */}
      <span className={`intel-status-dot ${liveStatus}`} title={liveStatusText}>
        {liveNewCount > 0 && <span className="intel-live-badge">{liveNewCount}</span>}
      </span>

      {/* User */}
      {user && (
        <div className="intel-user-bar">
          {user.role === 'admin' && <a href="/admin" className="intel-admin-link" title="用户管理">⚙</a>}
          <button className="intel-user-btn" onClick={logout} title="退出登录">
            <span className="intel-user-avatar">{user.email?.[0]?.toUpperCase() || 'U'}</span>
          </button>
        </div>
      )}
    </header>
  );
}
