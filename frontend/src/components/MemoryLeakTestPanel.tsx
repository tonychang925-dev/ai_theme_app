/**
 * 内存泄漏测试面板
 * 用于测试和验证SSE连接内存泄漏修复效果
 */

import { useState, useEffect } from 'react';
import { useSSELeakTest } from '../hooks/useSSEConnection';
import { createMemoryLeakDetector } from '../utils/memoryLeakDetector';

export function MemoryLeakTestPanel() {
  const [testResults, setTestResults] = useState<Array<{
    id: number;
    type: string;
    timestamp: Date;
    status: 'created' | 'cleaned' | 'leaked';
    details?: string;
  }>>([]);

  const [memoryStats, setMemoryStats] = useState<{
    currentMB: number;
    initialMB: number;
    growthMB: number;
    growthRate: number;
  }>({
    currentMB: 0,
    initialMB: 0,
    growthMB: 0,
    growthRate: 0
  });

  const [detector, setDetector] = useState<ReturnType<typeof createMemoryLeakDetector> | null>(null);
  const { leakCount, createLeak, cleanupLeaks } = useSSELeakTest();

  // 初始化内存泄漏检测器
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      const leakDetector = createMemoryLeakDetector({
        checkInterval: 10000, // 10秒检查一次
        memoryGrowthThreshold: 5, // 5MB阈值
        enableSSELeakDetection: true,
        enableTimerLeakDetection: true,
        enableDOMLeakDetection: true
      });

      leakDetector.start();
      setDetector(leakDetector);

      // 监听内存泄漏警告
      const handleLeakWarning = (event: CustomEvent) => {
        const report = event.detail;
        console.warn('内存泄漏警告:', report);

        setTestResults(prev => [...prev, {
          id: Date.now(),
          type: 'memory_leak',
          timestamp: new Date(),
          status: 'leaked',
          details: `内存增长 ${report.memoryUsage.growthMB.toFixed(2)}MB`
        }]);

        setMemoryStats(report.memoryUsage);
      };

      window.addEventListener('memory-leak-warning', handleLeakWarning as EventListener);

      return () => {
        window.removeEventListener('memory-leak-warning', handleLeakWarning as EventListener);
        leakDetector.stop();
      };
    }
  }, []);

  // 手动检查内存使用
  const checkMemoryUsage = () => {
    if (detector) {
      const report = detector.generateLeakReport();
      setMemoryStats(report.memoryUsage);

      setTestResults(prev => [...prev, {
        id: Date.now(),
        type: 'memory_check',
        timestamp: new Date(),
        status: 'created',
        details: `内存使用: ${report.memoryUsage.currentMB.toFixed(2)}MB`
      }]);

      return report;
    }
    return null;
  };

  // 运行SSE泄漏测试
  const runSSELeakTest = () => {
    // 创建多个SSE连接但不清理
    for (let i = 0; i < 5; i++) {
      setTimeout(() => {
        createLeak();
      }, i * 1000);
    }

    setTestResults(prev => [...prev, {
      id: Date.now(),
      type: 'sse_leak_test',
      timestamp: new Date(),
      status: 'created',
      details: '创建5个SSE泄漏连接'
    }]);
  };

  // 运行定时器泄漏测试
  const runTimerLeakTest = () => {
    // 创建多个定时器但不清理
    const timerIds: NodeJS.Timeout[] = [];
    for (let i = 0; i < 10; i++) {
      const timerId = setTimeout(() => {
        console.log(`定时器 ${i} 执行`);
      }, 30000); // 30秒后执行
      timerIds.push(timerId);
    }

    setTestResults(prev => [...prev, {
      id: Date.now(),
      type: 'timer_leak_test',
      timestamp: new Date(),
      status: 'created',
      details: `创建10个定时器 (ID: ${timerIds.join(', ')})`
    }]);

    // 存储定时器ID以便后续清理
    (window as any).__testTimers = timerIds;
  };

  // 清理所有测试资源
  const cleanupAllTests = () => {
    // 清理SSE泄漏
    cleanupLeaks();

    // 清理定时器
    if ((window as any).__testTimers) {
      (window as any).__testTimers.forEach((timerId: NodeJS.Timeout) => {
        clearTimeout(timerId);
      });
      (window as any).__testTimers = [];
    }

    // 强制垃圾回收（如果可用）
    if (detector) {
      detector.forceGarbageCollection();
    }

    setTestResults(prev => [...prev, {
      id: Date.now(),
      type: 'cleanup',
      timestamp: new Date(),
      status: 'cleaned',
      details: '清理所有测试资源'
    }]);

    // 重新检查内存
    setTimeout(() => {
      checkMemoryUsage();
    }, 1000);
  };

  // 导出测试结果
  const exportTestResults = () => {
    const data = {
      timestamp: new Date().toISOString(),
      memoryStats,
      testResults,
      leakCount,
      userAgent: navigator.userAgent
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `memory-leak-test-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="memory-leak-test-panel" style={{ padding: '20px', fontFamily: 'monospace' }}>
      <h2>内存泄漏测试面板</h2>
      <p>测试SSE连接内存泄漏修复效果，验证资源清理机制。</p>

      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '5px' }}>
        <h3>内存使用情况</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '15px' }}>
          <div style={{ padding: '10px', backgroundColor: '#fff', borderRadius: '4px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>当前内存</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
              {memoryStats.currentMB.toFixed(2)} MB
            </div>
          </div>
          <div style={{ padding: '10px', backgroundColor: '#fff', borderRadius: '4px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>内存增长</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: memoryStats.growthMB > 10 ? '#dc3545' : '#28a745' }}>
              {memoryStats.growthMB.toFixed(2)} MB
            </div>
          </div>
          <div style={{ padding: '10px', backgroundColor: '#fff', borderRadius: '4px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>增长率</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: memoryStats.growthRate > 20 ? '#dc3545' : '#28a745' }}>
              {memoryStats.growthRate.toFixed(1)}%
            </div>
          </div>
          <div style={{ padding: '10px', backgroundColor: '#fff', borderRadius: '4px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>SSE泄漏数</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: leakCount > 0 ? '#dc3545' : '#28a745' }}>
              {leakCount}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={checkMemoryUsage}
            style={{
              padding: '8px 16px',
              backgroundColor: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            检查内存
          </button>
          <button
            onClick={runSSELeakTest}
            style={{
              padding: '8px 16px',
              backgroundColor: '#ffc107',
              color: '#333',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            SSE泄漏测试
          </button>
          <button
            onClick={runTimerLeakTest}
            style={{
              padding: '8px 16px',
              backgroundColor: '#17a2b8',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            定时器泄漏测试
          </button>
          <button
            onClick={cleanupAllTests}
            style={{
              padding: '8px 16px',
              backgroundColor: '#28a745',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            清理所有测试
          </button>
          <button
            onClick={exportTestResults}
            style={{
              padding: '8px 16px',
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            导出结果
          </button>
        </div>
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h3>测试结果</h3>
        {testResults.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#6c757d' }}>
            暂无测试结果，请运行测试...
          </div>
        ) : (
          <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa' }}>
                  <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>时间</th>
                  <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>类型</th>
                  <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>状态</th>
                  <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>详情</th>
                </tr>
              </thead>
              <tbody>
                {testResults.slice().reverse().map((result) => (
                  <tr
                    key={result.id}
                    style={{
                      borderBottom: '1px solid #eee',
                      backgroundColor: result.status === 'leaked' ? '#f8d7da' :
                        result.status === 'cleaned' ? '#d4edda' : '#fff'
                    }}
                  >
                    <td style={{ padding: '10px', fontSize: '12px' }}>
                      {result.timestamp.toLocaleTimeString()}
                    </td>
                    <td style={{ padding: '10px' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: '3px',
                        fontSize: '12px',
                        backgroundColor: result.type.includes('leak') ? '#dc3545' : '#007bff',
                        color: 'white'
                      }}>
                        {result.type}
                      </span>
                    </td>
                    <td style={{ padding: '10px' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: '3px',
                        fontSize: '12px',
                        backgroundColor: result.status === 'leaked' ? '#dc3545' :
                          result.status === 'cleaned' ? '#28a745' : '#ffc107',
                        color: 'white'
                      }}>
                        {result.status === 'leaked' ? '泄漏' :
                          result.status === 'cleaned' ? '已清理' : '已创建'}
                      </span>
                    </td>
                    <td style={{ padding: '10px', fontSize: '14px' }}>
                      {result.details}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={{ padding: '15px', backgroundColor: '#e8f4fd', borderRadius: '5px', fontSize: '14px' }}>
        <h4>测试说明</h4>
        <ul>
          <li><strong>检查内存</strong>: 手动检查当前内存使用情况和增长趋势</li>
          <li><strong>SSE泄漏测试</strong>: 故意创建SSE连接但不清理，测试泄漏检测机制</li>
          <li><strong>定时器泄漏测试</strong>: 创建定时器但不清理，测试定时器泄漏检测</li>
          <li><strong>清理所有测试</strong>: 清理所有测试资源，强制垃圾回收</li>
          <li><strong>导出结果</strong>: 导出测试结果为JSON文件</li>
        </ul>
        <p style={{ marginTop: '10px', fontStyle: 'italic' }}>
          注意：这些测试会故意创建内存泄漏，请在测试完成后务必点击"清理所有测试"按钮。
        </p>
        <p style={{ marginTop: '10px', color: '#666' }}>
          内存泄漏检测器每10秒自动检查一次，检测到泄漏会在控制台输出警告。
        </p>
      </div>

      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fff3cd', borderRadius: '5px', fontSize: '14px' }}>
        <h4 style={{ color: '#856404' }}>修复验证</h4>
        <p>验证SSE内存泄漏修复效果：</p>
        <ol>
          <li>运行SSE泄漏测试创建多个连接</li>
          <li>观察内存增长情况</li>
          <li>点击"清理所有测试"</li>
          <li>检查内存是否回落</li>
          <li>重复测试验证稳定性</li>
        </ol>
        <p style={{ marginTop: '10px', color: '#856404' }}>
          预期结果：清理后内存应回落，SSE连接数归零，无持续内存增长。
        </p>
      </div>
    </div>
  );
}