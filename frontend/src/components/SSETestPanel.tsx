import { useState } from 'react';
import type { SSEConnectionState, IntelFeedEvent } from '../lib/api';
import { useSSEConnection } from '../hooks/useSSEConnection';

/**
 * SSE功能测试面板
 *
 * 用于验证阶段一的SSE连接管理优化是否正常工作。
 * 显示SSE连接状态、心跳计数、收到的情报项等信息。
 */
export function SSETestPanel() {
  const [testParams, setTestParams] = useState({
    date: new Date().toISOString().slice(0, 10),
    type: 'all' as const,
    session: 'all' as const,
  });

  const {
    connectionState,
    isConnected,
    connect,
    disconnect,
    retry,
    error: errorMessage,
    receivedItems,
    heartbeatCount,
    dispose
  } = useSSEConnection(
    testParams,
    {
      onIntelItem: (event: IntelFeedEvent) => {
        console.log('收到情报项:', event);
      },
      onHeartbeat: () => {
        console.log(`收到心跳 #${heartbeatCount + 1}`);
      },
      onStateChange: (state: SSEConnectionState) => {
        console.log('连接状态变化:', state);
      },
      onError: (error: Error) => {
        console.error('SSE错误:', error);
      },
      onClose: () => {
        console.log('SSE连接关闭');
      }
    },
    {
      autoConnect: false,
      autoDisconnect: true,
      enableLeakDetection: true,
      maxRetries: 3,
      retryDelay: 1000,
      heartbeatTimeout: 45000,
      connectTimeout: 10000
    }
  );

  // 格式化连接状态显示
  const formatConnectionState = (state: SSEConnectionState | null) => {
    if (!state) return '未连接';

    const statusMap: Record<string, string> = {
      'disconnected': '已断开',
      'connecting': '连接中',
      'connected': '已连接',
      'retrying': `重试中 (${state.retryCount})`,
      'error': `错误: ${state.lastError || '未知错误'}`,
      'closed': '已关闭',
    };

    return `${statusMap[state.status]} - 持续时间: ${Math.floor(state.connectionDuration / 1000)}秒`;
  };

  // 重置计数
  const resetCounts = () => {
    // 注意：receivedItems和heartbeatCount由Hook管理
    // 这里可以添加额外的重置逻辑
    console.log('重置计数');
  };

  return (
    <div className="sse-test-panel" style={{ padding: '20px', fontFamily: 'monospace' }}>
      <h2>SSE功能测试 - 阶段一验证</h2>
      <p>测试增强的SSE管理器功能，包括自动重试、心跳监控和连接状态管理。</p>

      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '5px' }}>
        <h3>测试参数</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '15px' }}>
          <div>
            <label>日期:</label>
            <input
              type="date"
              value={testParams.date}
              onChange={(e) => setTestParams({ ...testParams, date: e.target.value })}
              style={{ width: '100%', padding: '5px' }}
            />
          </div>
          <div>
            <label>类型:</label>
            <select
              value={testParams.type}
              onChange={(e) => setTestParams({ ...testParams, type: e.target.value as 'all' })}
              style={{ width: '100%', padding: '5px' }}
            >
              <option value="all">全部</option>
              <option value="event">新事件</option>
              <option value="new_theme">新题材</option>
              <option value="stock_move">异动</option>
            </select>
          </div>
          <div>
            <label>时段:</label>
            <select
              value={testParams.session}
              onChange={(e) => setTestParams({ ...testParams, session: e.target.value as 'all' })}
              style={{ width: '100%', padding: '5px' }}
            >
              <option value="all">全部</option>
              <option value="pre">盘前</option>
              <option value="intra">盘中</option>
              <option value="post">盘后</option>
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={connect}
            disabled={isConnected}
            style={{
              padding: '10px 20px',
              backgroundColor: isConnected ? '#ccc' : '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isConnected ? 'not-allowed' : 'pointer',
            }}
          >
            {isConnected ? '已连接' : '连接SSE'}
          </button>
          <button
            onClick={disconnect}
            disabled={!isConnected}
            style={{
              padding: '10px 20px',
              backgroundColor: !isConnected ? '#ccc' : '#dc3545',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: !isConnected ? 'not-allowed' : 'pointer',
            }}
          >
            断开连接
          </button>
          <button
            onClick={retry}
            disabled={!connectionState}
            style={{
              padding: '10px 20px',
              backgroundColor: !connectionState ? '#ccc' : '#ffc107',
              color: '#333',
              border: 'none',
              borderRadius: '4px',
              cursor: !connectionState ? 'not-allowed' : 'pointer',
            }}
          >
            手动重试
          </button>
          <button
            onClick={resetCounts}
            style={{
              padding: '10px 20px',
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            重置计数
          </button>
          <button
            onClick={dispose}
            style={{
              padding: '10px 20px',
              backgroundColor: '#28a745',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            完全清理
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
        <div style={{ padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '5px' }}>
          <h3>连接状态</h3>
          <div style={{ marginBottom: '10px' }}>
            <strong>状态:</strong> {formatConnectionState(connectionState)}
          </div>
          {connectionState && (
            <div style={{ fontSize: '12px', color: '#666' }}>
              <div>重试次数: {connectionState.retryCount}</div>
              {connectionState.connectedAt && (
                <div>连接时间: {new Date(connectionState.connectedAt).toLocaleString()}</div>
              )}
              {connectionState.lastHeartbeat && (
                <div>最后心跳: {new Date(connectionState.lastHeartbeat).toLocaleString()}</div>
              )}
              {connectionState.lastError && (
                <div style={{ color: '#dc3545' }}>错误: {connectionState.lastError}</div>
              )}
            </div>
          )}
        </div>

        <div style={{ padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '5px' }}>
          <h3>统计信息</h3>
          <div style={{ marginBottom: '10px' }}>
            <div>心跳计数: {heartbeatCount}</div>
            <div>收到情报项: {receivedItems.length}</div>
            <div>连接状态: {isConnected ? '✅ 已连接' : '❌ 未连接'}</div>
          </div>
          {errorMessage && (
            <div style={{ padding: '10px', backgroundColor: '#f8d7da', color: '#721c24', borderRadius: '4px' }}>
              <strong>错误:</strong> {errorMessage}
            </div>
          )}
        </div>
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h3>收到的情报项（最近20条）</h3>
        {receivedItems.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#6c757d' }}>
            尚未收到情报项，请连接SSE...
          </div>
        ) : (
          <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            {receivedItems.map((item, index) => (
              <div
                key={index}
                style={{
                  padding: '10px',
                  borderBottom: '1px solid #eee',
                  backgroundColor: index % 2 === 0 ? '#fff' : '#f8f9fa',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                  <strong>{item.event_type}</strong>
                  <span style={{ fontSize: '12px', color: '#6c757d' }}>
                    {new Date(item.occurred_at).toLocaleString()}
                  </span>
                </div>
                <div style={{ fontSize: '14px' }}>
                  {item.item.summary || item.item.title || '无描述'}
                </div>
                {item.item.theme_names.length > 0 && (
                  <div style={{ fontSize: '12px', color: '#007bff', marginTop: '5px' }}>
                    主题: {item.item.theme_names.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ padding: '15px', backgroundColor: '#e8f4fd', borderRadius: '5px', fontSize: '14px' }}>
        <h4>测试说明</h4>
        <ul>
          <li>点击"连接SSE"按钮启动SSE连接</li>
          <li>观察连接状态变化：连接中 → 已连接</li>
          <li>查看心跳计数：服务器每15秒发送一次心跳</li>
          <li>如果有新情报项，会显示在下方列表中</li>
          <li>测试断开连接和手动重试功能</li>
          <li>检查网络断开时自动重试是否工作</li>
        </ul>
        <p style={{ marginTop: '10px', fontStyle: 'italic' }}>
          注意：确保后端服务(frontend_bff)正在运行，端口8000可用。
        </p>
      </div>
    </div>
  );
}
