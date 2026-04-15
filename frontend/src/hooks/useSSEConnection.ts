/**
 * SSE连接管理Hook
 * 提供安全的SSE连接管理，防止内存泄漏
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import type { IntelItemType, IntelSession, IntelFeedEvent } from '../lib/api';
import type { SSEConnectionState, SSEEventHandlers, SSEManagerOptions } from '../lib/realtime/sseManager';
import { createIntelStreamManager } from '../lib/api';

export interface UseSSEConnectionOptions extends SSEManagerOptions {
  /** 是否自动连接，默认false */
  autoConnect?: boolean;

  /** 组件卸载时是否自动断开连接，默认true */
  autoDisconnect?: boolean;

  /** 启用内存泄漏检测，默认true（开发环境） */
  enableLeakDetection?: boolean;
}

export interface UseSSEConnectionReturn {
  /** 连接状态 */
  connectionState: SSEConnectionState | null;

  /** 是否已连接 */
  isConnected: boolean;

  /** 连接SSE */
  connect: () => void;

  /** 断开连接 */
  disconnect: () => void;

  /** 手动重试 */
  retry: () => void;

  /** 错误信息 */
  error: string | null;

  /** 收到的情报项 */
  receivedItems: IntelFeedEvent[];

  /** 心跳计数 */
  heartbeatCount: number;

  /** 清理所有资源 */
  dispose: () => void;
}

/**
 * 安全的SSE连接Hook
 * 提供内存泄漏防护的连接管理
 */
export function useSSEConnection(
  params: {
    date?: string;
    type?: IntelItemType;
    session?: IntelSession;
  },
  eventHandlers?: SSEEventHandlers,
  options: UseSSEConnectionOptions = {}
): UseSSEConnectionReturn {
  const {
    autoConnect = false,
    autoDisconnect = true,
    enableLeakDetection = process.env.NODE_ENV === 'development',
    ...sseOptions
  } = options;

  const sseManagerRef = useRef<import('../lib/realtime/sseManager').SSEManager | null>(null);
  const [connectionState, setConnectionState] = useState<SSEConnectionState | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receivedItems, setReceivedItems] = useState<IntelFeedEvent[]>([]);
  const [heartbeatCount, setHeartbeatCount] = useState(0);

  // 内存泄漏检测
  const leakDetectionRef = useRef<{
    connectionCount: number;
    lastCleanupTime: Date | null;
    cleanupAttempts: number;
  }>({
    connectionCount: 0,
    lastCleanupTime: null,
    cleanupAttempts: 0
  });

  // 包装事件处理器，确保在组件卸载时不会调用
  const wrappedEventHandlers = useRef<SSEEventHandlers>({});

  useEffect(() => {
    // 使用简单的挂载检查，不依赖私有属性
    let isComponentMounted = true;

    const isMounted = () => isComponentMounted;

    wrappedEventHandlers.current = {
      onIntelItem: (event: IntelFeedEvent) => {
        if (isMounted() && eventHandlers?.onIntelItem) {
          eventHandlers.onIntelItem(event);
        }
        if (isMounted()) {
          setReceivedItems(prev => [event, ...prev].slice(0, 50)); // 限制数量防止内存增长
        }
      },
      onHeartbeat: () => {
        if (isMounted() && eventHandlers?.onHeartbeat) {
          eventHandlers.onHeartbeat();
        }
        if (isMounted()) {
          setHeartbeatCount(prev => prev + 1);
        }
      },
      onStateChange: (state: SSEConnectionState) => {
        if (isMounted() && eventHandlers?.onStateChange) {
          eventHandlers.onStateChange(state);
        }
        if (isMounted()) {
          setConnectionState(state);
          setIsConnected(state.status === 'connected');
        }
      },
      onError: (error: Error) => {
        if (isMounted() && eventHandlers?.onError) {
          eventHandlers.onError(error);
        }
        if (isMounted()) {
          setError(error.message);
        }
      },
      onClose: () => {
        if (isMounted() && eventHandlers?.onClose) {
          eventHandlers.onClose();
        }
        if (isMounted()) {
          setIsConnected(false);
        }
      }
    };

    return () => {
      isComponentMounted = false;
    };
  }, [eventHandlers]);

  // 连接SSE
  const connect = useCallback(() => {
    // 清理现有连接
    if (sseManagerRef.current) {
      sseManagerRef.current.disconnect();
      sseManagerRef.current = null;
    }

    setError(null);
    leakDetectionRef.current.connectionCount++;

    try {
      const manager = createIntelStreamManager(
        params,
        wrappedEventHandlers.current,
        sseOptions
      );

      sseManagerRef.current = manager;
      manager.connect();

      if (enableLeakDetection && process.env.NODE_ENV === 'development') {
        console.log(`🔗 SSE连接 #${leakDetectionRef.current.connectionCount} 已启动`);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '未知错误';
      setError(errorMessage);
      if (process.env.NODE_ENV === 'development') {
        console.error('SSE连接失败:', err);
      }
    }
  }, [params, sseOptions, enableLeakDetection]);

  // 断开连接
  const disconnect = useCallback(() => {
    if (sseManagerRef.current) {
      sseManagerRef.current.disconnect();
      sseManagerRef.current = null;

      if (enableLeakDetection && process.env.NODE_ENV === 'development') {
        leakDetectionRef.current.lastCleanupTime = new Date();
        console.log('🔌 SSE连接已断开');
      }
    }

    setIsConnected(false);
    setError(null);
  }, [enableLeakDetection]);

  // 手动重试
  const retry = useCallback(() => {
    if (sseManagerRef.current) {
      sseManagerRef.current.retry();
    }
  }, []);

  // 完全清理
  const dispose = useCallback(() => {
    if (sseManagerRef.current) {
      // 直接调用disconnect方法
      const manager = sseManagerRef.current;
      manager.disconnect();
      sseManagerRef.current = null;
    }

    // 清理状态
    setConnectionState(null);
    setIsConnected(false);
    setError(null);
    setReceivedItems([]);
    setHeartbeatCount(0);

    if (enableLeakDetection && process.env.NODE_ENV === 'development') {
      leakDetectionRef.current.cleanupAttempts++;
      console.log(`🧹 SSE连接已完全清理 (尝试次数: ${leakDetectionRef.current.cleanupAttempts})`);
    }
  }, [enableLeakDetection]);

  // 自动连接
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      if (autoDisconnect) {
        dispose();
      }
    };
  }, [autoConnect, autoDisconnect, connect, dispose]);

  // 内存泄漏检测
  useEffect(() => {
    if (!enableLeakDetection) return;

    const checkForLeaks = () => {
      const { connectionCount, lastCleanupTime, cleanupAttempts } = leakDetectionRef.current;

      // 检查是否有未清理的连接
      if (sseManagerRef.current && !isConnected && lastCleanupTime) {
        const timeSinceCleanup = Date.now() - lastCleanupTime.getTime();
        if (timeSinceCleanup > 10000 && process.env.NODE_ENV === 'development') { // 10秒后仍有连接
          console.warn('⚠️ 检测到潜在的SSE连接泄漏', {
            connectionCount,
            cleanupAttempts,
            timeSinceCleanup
          });
        }
      }
    };

    const intervalId = setInterval(checkForLeaks, 30000); // 每30秒检查一次

    return () => {
      clearInterval(intervalId);
    };
  }, [enableLeakDetection, isConnected]);

  return {
    connectionState,
    isConnected,
    connect,
    disconnect,
    retry,
    error,
    receivedItems,
    heartbeatCount,
    dispose
  };
}

/**
 * 简化的SSE连接Hook（推荐使用）
 */
export function useIntelStream(
  params: {
    date?: string;
    type?: IntelItemType;
    session?: IntelSession;
  },
  onIntelItem?: (event: IntelFeedEvent) => void,
  options: UseSSEConnectionOptions = {}
) {
  const eventHandlers = onIntelItem ? { onIntelItem } : undefined;

  return useSSEConnection(params, eventHandlers, options);
}

/**
 * 测试Hook：模拟SSE连接泄漏
 */
export function useSSELeakTest() {
  const [leakCount, setLeakCount] = useState(0);
  const leakConnectionsRef = useRef<Array<{ id: number; dispose: () => void }>>([]);

  const createLeak = useCallback(() => {
    const id = Date.now();
    const { dispose } = useSSEConnection(
      { date: new Date().toISOString().slice(0, 10) },
      {},
      { autoConnect: true, autoDisconnect: false }
    );

    leakConnectionsRef.current.push({ id, dispose });
    setLeakCount(prev => prev + 1);

    if (process.env.NODE_ENV === 'development') {
      console.warn(`💥 故意创建SSE泄漏 #${id}`);
    }
  }, []);

  const cleanupLeaks = useCallback(() => {
    leakConnectionsRef.current.forEach(({ dispose }) => {
      try {
        dispose();
      } catch (err) {
        if (process.env.NODE_ENV === 'development') {
          console.error('清理泄漏时出错:', err);
        }
      }
    });

    leakConnectionsRef.current = [];
    setLeakCount(0);

    if (process.env.NODE_ENV === 'development') {
      console.log(`🧹 清理了所有SSE泄漏`);
    }
  }, []);

  return {
    leakCount,
    createLeak,
    cleanupLeaks
  };
}