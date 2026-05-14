import React from 'react';
import { navigateTo } from '../../lib/navigation';
import { useAuth } from '../../routes/auth/AuthProvider';
import type { SSEConnectionState } from '../../lib/api';

interface IntelHeaderProps {
  sourceSummary: string;
  payloadCount: number;
  liveStatus: 'connecting' | 'live' | 'fallback';
  sseConnectionState: SSEConnectionState | null;
  liveNewCount: number;
}

export function IntelHeader({
  sourceSummary,
  payloadCount,
  liveStatus,
  sseConnectionState,
  liveNewCount,
}: IntelHeaderProps) {
  const liveStatusText = {
    'live': '在线',
    'connecting': '连接中',
    'fallback': '兜底模式',
  }[liveStatus];

  const { user, logout } = useAuth();

  return (
    <header className="intel-topbar" style={{ flexWrap: 'wrap' }}>
      <div style={{ flex: 1 }}>
        <p className="eyebrow">AI Investment Assistant</p>
        <h1>情报台</h1>
        <p className="subtle">按时间顺序展示归属到题材的事件流，点击任一事件直接进入题材详情</p>
      </div>
      {user && (
        <div className="auth-user-bar" style={{ marginRight: 12 }}>
          <strong>{user.email}</strong> ({user.role})
          {user.role === 'admin' && <a href="/admin" style={{ color: '#ffd700', fontSize: 12, marginLeft: 8 }}>用户管理</a>}
          <a href="/mobile" style={{ color: '#5dade2', fontSize: 12, marginLeft: 6 }}>移动端</a>
          <button className="auth-logout-btn" onClick={logout}>退出</button>
        </div>
      )}
      <div className="topbar-meta">
        <span>来源: {sourceSummary}</span>
        <span>条目: {payloadCount}</span>
        <span>
          实时: {liveStatusText}
          {sseConnectionState && sseConnectionState.status !== 'connected' && (
            <span className="connection-detail">
              ({sseConnectionState.status === 'retrying' ? `重试 ${sseConnectionState.retryCount}` : sseConnectionState.status})
            </span>
          )}
        </span>
        {liveNewCount > 0 && <span>新增: {liveNewCount}</span>}
      </div>
    </header>
  );
}