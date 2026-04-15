/**
 * 性能调试面板组件
 * 用于开发环境查看性能指标和问题
 */

import React, { useState, useEffect } from 'react';
import { performanceMonitor } from '../utils/performanceMonitor';

interface PerformanceDebugPanelProps {
  visible?: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export const PerformanceDebugPanel: React.FC<PerformanceDebugPanelProps> = ({
  visible = true,
  autoRefresh = true,
  refreshInterval = 5000
}) => {
  const [report, setReport] = useState<any>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(autoRefresh);

  const refreshReport = () => {
    const newReport = performanceMonitor.generateReport();
    setReport(newReport);
  };

  useEffect(() => {
    if (visible) {
      refreshReport();
    }
  }, [visible]);

  useEffect(() => {
    if (visible && autoRefreshEnabled) {
      const intervalId = setInterval(refreshReport, refreshInterval);
      return () => clearInterval(intervalId);
    }
  }, [visible, autoRefreshEnabled, refreshInterval]);

  if (!visible || !report) {
    return null;
  }

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatTime = (ms: number): string => {
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'high': return 'bg-red-100 text-red-800 border-red-300';
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low': return 'bg-blue-100 text-blue-800 border-blue-300';
      default: return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getIssueTypeIcon = (type: string): string => {
    switch (type) {
      case 'memory_leak': return '🧠';
      case 'sse_leak': return '🔌';
      case 'layout_shift': return '📐';
      case 'long_task': return '⏱️';
      case 'slow_resource': return '🐌';
      default: return '⚠️';
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-h-[80vh] overflow-hidden bg-white rounded-lg shadow-xl border border-gray-200">
      {/* 面板头部 */}
      <div className="flex items-center justify-between p-4 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
          <h3 className="font-semibold text-gray-800">性能监控面板</h3>
          <span className="text-xs px-2 py-1 bg-gray-200 rounded text-gray-600">
            {report.metrics.sseConnections} SSE连接
          </span>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
            className={`text-xs px-2 py-1 rounded ${autoRefreshEnabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}
          >
            {autoRefreshEnabled ? '🔄 自动刷新' : '⏸️ 暂停刷新'}
          </button>
          <button
            onClick={refreshReport}
            className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
          >
            🔄 手动刷新
          </button>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
          >
            {isExpanded ? '📥 收起' : '📤 展开'}
          </button>
        </div>
      </div>

      {/* 面板内容 */}
      <div className="overflow-y-auto" style={{ maxHeight: isExpanded ? 'calc(80vh - 60px)' : '300px' }}>
        {/* 核心指标 */}
        <div className="p-4 border-b border-gray-100">
          <h4 className="font-medium text-gray-700 mb-2">核心性能指标</h4>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-50 p-2 rounded">
              <div className="text-xs text-gray-500">页面加载时间</div>
              <div className="font-semibold">{formatTime(report.metrics.pageLoadTime)}</div>
            </div>
            <div className="bg-gray-50 p-2 rounded">
              <div className="text-xs text-gray-500">首次内容绘制</div>
              <div className="font-semibold">{formatTime(report.metrics.firstContentfulPaint)}</div>
            </div>
            <div className="bg-gray-50 p-2 rounded">
              <div className="text-xs text-gray-500">最大内容绘制</div>
              <div className="font-semibold">{formatTime(report.metrics.largestContentfulPaint)}</div>
            </div>
            <div className="bg-gray-50 p-2 rounded">
              <div className="text-xs text-gray-500">累计布局偏移</div>
              <div className="font-semibold">{report.metrics.cumulativeLayoutShift.toFixed(3)}</div>
            </div>
          </div>
        </div>

        {/* 内存使用 */}
        {report.metrics.memoryUsage && (
          <div className="p-4 border-b border-gray-100">
            <h4 className="font-medium text-gray-700 mb-2">内存使用</h4>
            <div className="space-y-2">
              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">已使用内存</span>
                  <span className="font-medium">{formatBytes(report.metrics.memoryUsage.usedJSHeapSize)}</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-blue-600 h-2 rounded-full"
                    style={{ 
                      width: `${(report.metrics.memoryUsage.usedJSHeapSize / report.metrics.memoryUsage.jsHeapSizeLimit) * 100}%` 
                    }}
                  ></div>
                </div>
              </div>
              <div className="text-xs text-gray-500">
                总内存: {formatBytes(report.metrics.memoryUsage.totalJSHeapSize)} / 
                限制: {formatBytes(report.metrics.memoryUsage.jsHeapSizeLimit)}
              </div>
            </div>
          </div>
        )}

        {/* 问题列表 */}
        {report.issues.length > 0 && (
          <div className="p-4 border-b border-gray-100">
            <h4 className="font-medium text-gray-700 mb-2">
              检测到问题 <span className="text-red-600">({report.issues.length})</span>
            </h4>
            <div className="space-y-2">
              {report.issues.map((issue: any, index: number) => (
                <div 
                  key={index}
                  className={`p-3 rounded border ${getSeverityColor(issue.severity)}`}
                >
                  <div className="flex items-start space-x-2">
                    <span className="text-lg">{getIssueTypeIcon(issue.type)}</span>
                    <div className="flex-1">
                      <div className="font-medium">{issue.description}</div>
                      <div className="text-sm mt-1">{issue.recommendation}</div>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded ${getSeverityColor(issue.severity)}`}>
                      {issue.severity}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 资源加载 */}
        {report.metrics.resourceTiming.length > 0 && (
          <div className="p-4 border-b border-gray-100">
            <h4 className="font-medium text-gray-700 mb-2">
              资源加载 ({report.metrics.resourceTiming.length})
            </h4>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {report.metrics.resourceTiming
                .sort((a: any, b: any) => b.duration - a.duration)
                .slice(0, 5)
                .map((resource: any, index: number) => (
                  <div key={index} className="flex items-center justify-between text-sm">
                    <div className="truncate flex-1 mr-2">
                      <span className="text-gray-500 text-xs">{resource.initiatorType}:</span>
                      <span className="ml-1 truncate">{resource.name.split('/').pop()}</span>
                    </div>
                    <div className="text-gray-700 font-medium">{formatTime(resource.duration)}</div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* 长任务 */}
        {report.metrics.longTasks.length > 0 && (
          <div className="p-4">
            <h4 className="font-medium text-gray-700 mb-2">
              长任务 ({report.metrics.longTasks.length})
            </h4>
            <div className="space-y-1">
              {report.metrics.longTasks
                .sort((a: any, b: any) => b.duration - a.duration)
                .slice(0, 3)
                .map((task: any, index: number) => (
                  <div key={index} className="flex items-center justify-between text-sm">
                    <div className="text-gray-600">任务 {index + 1}</div>
                    <div className="text-red-600 font-medium">{formatTime(task.duration)}</div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* 面板底部 */}
      <div className="p-3 bg-gray-50 border-t border-gray-200">
        <div className="flex justify-between items-center">
          <div className="text-xs text-gray-500">
            最后更新: {new Date(report.timestamp).toLocaleTimeString()}
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => performanceMonitor.downloadReport()}
              className="text-xs px-3 py-1 bg-green-100 text-green-800 rounded hover:bg-green-200"
            >
              📥 下载报告
            </button>
            <button
              onClick={() => {
                console.log('性能报告:', report);
                alert('报告已输出到控制台');
              }}
              className="text-xs px-3 py-1 bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
            >
              📋 控制台输出
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// 开发环境自动显示调试面板
if (process.env.NODE_ENV === 'development') {
  // 导出全局函数用于手动控制
  (window as any).togglePerformancePanel = (visible?: boolean) => {
    const event = new CustomEvent('toggle-performance-panel', { 
      detail: { visible } 
    });
    window.dispatchEvent(event);
  };
}

export default PerformanceDebugPanel;
