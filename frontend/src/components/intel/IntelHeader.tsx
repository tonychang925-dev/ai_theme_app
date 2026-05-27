import React from 'react';
import { useAuth } from '../../routes/auth/AuthProvider';
import { navigateTo } from '../../lib/navigation';
import type { IntelItemType, IntelSession, SSEConnectionState } from '../../lib/api';
import logoImg from '../../assets/intel-icons/logo_1.png';
import logo2Img from '../../assets/intel-icons/logo_2.png';
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
  realtimeHealth: {
    serviceOnline: boolean | null;
    pipelineRunning: boolean | null;
    jyhfCollectorRunning: boolean | null;
    jyhfCdpConnected: boolean | null;
    todayCount: number;
  };
  date: string;
  setDate: (d: string) => void;
  session: IntelSession;
  setSession: (s: IntelSession) => void;
  type: IntelItemType;
  setType: (t: IntelItemType) => void;
  recapDates: { postMarket: string; preMarket: string };
}

export function IntelHeader({
  sourceSummary, payloadCount, liveStatus, liveNewCount,
  realtimeHealth, date, setDate, session, setSession, type, setType, recapDates,
}: IntelHeaderProps) {
  const liveStatusText = { 'live': '在线', 'connecting': '连接中', 'fallback': '兜底模式' }[liveStatus];
  const { user, logout } = useAuth();
  const statusText = (value: boolean | null, ok: string, fail: string, unknown = '检查中') =>
    value === null ? unknown : value ? ok : fail;

  return (
    <header className="intel-toolbar">
      {/* Logo + Title */}
      <div className="intel-brand">
        <img src={logoImg} alt="Logo" className="intel-logo" />
        <img src={logo2Img} alt="AI投资助理" style={{ height: 88, width: "auto", flexShrink: 0 }} />
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
        {user && user.role === 'admin' && (
          <button type="button" className="quick-action-card" onClick={() => navigateTo('/admin')} title="用户管理">
            <span className="quick-action-icon" style={{ fontSize: 48, lineHeight: "64px", width: 128, textAlign: "center", display: "inline-block" }}>⚙</span>
            <span className="quick-action-tooltip">用户管理</span>
          </button>
        )}
      </nav>

      {/* Right-aligned: Filters + Status + User */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
        <select value={session} onChange={(e) => setSession(e.target.value as IntelSession)} className="intel-filter-select">
          <option value="all">全部时段</option>
          <option value="pre">盘前</option>
          <option value="intra">盘中</option>
          <option value="post">盘后</option>
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="intel-filter-select" />
        <select value={type} onChange={(e) => setType(e.target.value as IntelItemType)} className="intel-filter-select">
          <option value="all">全部类型</option>
          <option value="recap">复盘</option>
          <option value="weak_to_strong">弱转强</option>
          <option value="theme_cycle">题材周期</option>
          <option value="stock_signal">强势股</option>
          <option value="event_review">待复核</option>
          <option value="event">新事件</option>
          <option value="stock_move">异动</option>
        </select>
        <span style={{ fontSize: 14, color: "#9f9f9f", whiteSpace: "nowrap" }}>连结状态</span>
        <span className={`intel-status-dot ${liveStatus}`} title={liveStatusText} />
        <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12, color: "#9f9f9f", whiteSpace: "nowrap" }}>
          <span>服务：{statusText(realtimeHealth.serviceOnline, '在线', '离线')}</span>
          <span>管线：{statusText(realtimeHealth.pipelineRunning, '运行中', '未运行')}</span>
          <span>JYHF：{statusText(realtimeHealth.jyhfCollectorRunning && realtimeHealth.jyhfCdpConnected, '采集有效', '未采集')}</span>
          <span>今日情报：{realtimeHealth.todayCount}</span>
        </div>
        {user && (
          <div className="intel-user-bar">
            <button className="intel-user-btn" onClick={logout} title="退出登录">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#9f9f9f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
