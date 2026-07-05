/**
 * 增强的SSE（Server-Sent Events）连接管理器
 *
 * 提供SSE连接管理、自动重试、智能退避和状态监控功能。
 * 作为主要实时数据通道的核心组件。
 */

import type { IntelItemType, IntelSession, IntelFeedEvent } from '../api';

export interface SSEManagerOptions {
  /** 基础URL路径，默认为'/api/v2/intel/stream' */
  endpoint?: string;

  /** 最大重试次数，默认3次 */
  maxRetries?: number;

  /** 初始重试延迟（毫秒），默认1000ms */
  retryDelay?: number;

  /** 重试延迟倍增因子，默认2.0 */
  retryBackoffFactor?: number;

  /** 最大重试延迟（毫秒），默认10000ms */
  maxRetryDelay?: number;

  /** 心跳超时时间（毫秒），默认45000ms（45秒） */
  heartbeatTimeout?: number;

  /** 连接超时时间（毫秒），默认10000ms（10秒） */
  connectTimeout?: number;
}

export interface SSEConnectionState {
  /** 连接状态 */
  status: 'disconnected' | 'connecting' | 'connected' | 'retrying' | 'error' | 'closed';

  /** 当前重试次数 */
  retryCount: number;

  /** 最后错误信息 */
  lastError?: string;

  /** 连接开始时间 */
  connectedAt?: Date;

  /** 最后心跳时间 */
  lastHeartbeat?: Date;

  /** 连接持续时间（毫秒） */
  connectionDuration: number;
}

export interface SSEEventHandlers {
  /** 接收到intel_item事件 */
  onIntelItem?: (event: IntelFeedEvent) => void;

  /** 接收到heartbeat事件 */
  onHeartbeat?: () => void;

  /** 连接状态变化 */
  onStateChange?: (state: SSEConnectionState) => void;

  /** 连接错误 */
  onError?: (error: Error) => void;

  /** 连接关闭 */
  onClose?: () => void;
}

export class SSEManager {
  private eventSource: EventSource | null = null;
  private state: SSEConnectionState = {
    status: 'disconnected',
    retryCount: 0,
    connectionDuration: 0
  };

  private options: Required<SSEManagerOptions>;
  private eventHandlers: SSEEventHandlers;

  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private connectionTimer: number | null = null;
  private stateUpdateTimer: number | null = null;

  private params: {
    date?: string;
    type?: IntelItemType;
    session?: IntelSession;
  };

  // 内存泄漏防护：跟踪所有事件监听器以便清理
  private eventListeners: Map<string, EventListener> = new Map();
  private isDisposed: boolean = false;
  private lastEventId: string = '';

  constructor(
    params: {
      date?: string;
      type?: IntelItemType;
      session?: IntelSession;
    },
    eventHandlers: SSEEventHandlers = {},
    options: SSEManagerOptions = {}
  ) {
    this.params = params;
    this.eventHandlers = eventHandlers;

    // 设置默认选项
    this.options = {
      endpoint: '/api/v2/intel/stream',
      maxRetries: 3,
      retryDelay: 1000,
      retryBackoffFactor: 2.0,
      maxRetryDelay: 10000,
      heartbeatTimeout: 45000, // 45秒
      connectTimeout: 10000, // 10秒
      ...options
    };
  }

  /**
   * 连接SSE服务器
   */
  connect(): void {
    if (this.eventSource) {
      this.disconnect();
    }

    this.updateState({
      status: 'connecting',
      retryCount: 0,
      lastError: undefined,
      connectedAt: new Date()
    });

    // 构建URL
    const url = this.buildUrl();

    try {
      this.eventSource = new EventSource(url);
      this.setupEventListeners();
      const activeConnection = this.eventSource;

      // 设置连接超时
      this.connectionTimer = window.setTimeout(() => {
        if (this.eventSource === activeConnection && this.state.status === 'connecting') {
          this.handleError(new Error('SSE连接超时'));
        }
      }, this.options.connectTimeout);

    } catch (error) {
      this.handleError(error instanceof Error ? error : new Error(String(error)));
    }
  }

  /**
   * 断开SSE连接
   */
  disconnect(): void {
    if (this.isDisposed) {
      return;
    }

    this.clearTimers();
    this.removeEventListeners();

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.updateState({
      status: 'closed',
      connectionDuration: this.calculateConnectionDuration()
    });

    if (this.eventHandlers.onClose) {
      this.eventHandlers.onClose();
    }

    this.isDisposed = true;
  }

  /**
   * 完全清理管理器（用于组件卸载）
   */
  dispose(): void {
    this.disconnect();

    // 清理所有引用
    this.eventHandlers = {};
    this.params = {};
    this.eventListeners.clear();
  }

  /**
   * 获取当前连接状态
   */
  getState(): SSEConnectionState {
    return { ...this.state };
  }

  /**
   * 检查是否已连接
   */
  isConnected(): boolean {
    return this.state.status === 'connected';
  }

  /**
   * 手动重试连接
   */
  retry(): void {
    if (this.state.status === 'retrying' || this.state.status === 'connecting') {
      return;
    }

    if (this.state.retryCount >= this.options.maxRetries) {
      this.updateState({
        status: 'error',
        lastError: `已达到最大重试次数 (${this.options.maxRetries})`
      });
      return;
    }

    const retryCount = this.state.retryCount + 1;
    const delay = this.calculateRetryDelay(retryCount);

    this.updateState({
      status: 'retrying',
      retryCount
    });

    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * 构建SSE URL
   */
  private buildUrl(): string {
    const query = new URLSearchParams();
    if (this.params.date) query.set('date', this.params.date);
    if (this.params.type) query.set('type', this.params.type);
    if (this.params.session) query.set('session', this.params.session);
    query.set('limit', '20');
    if (this.lastEventId) query.set('last_event_id', this.lastEventId);

    return `${this.options.endpoint}?${query.toString()}`;
  }

  /**
   * 设置事件监听器
   */
  private setupEventListeners(): void {
    if (!this.eventSource || this.isDisposed) return;

    // intel_item 事件
    const intelItemHandler = (event: Event) => {
      try {
        const messageEvent = event as MessageEvent;
        const payload = JSON.parse(messageEvent.data) as IntelFeedEvent;
        if (this.isValidIntelEvent(payload)) {
          if (messageEvent.lastEventId) {
            this.lastEventId = messageEvent.lastEventId;
          }
          if (this.eventHandlers.onIntelItem) {
            this.eventHandlers.onIntelItem(payload);
          }
        }
        this.resetHeartbeatTimer();
      } catch (error) {
        console.error('解析intel_item事件失败:', error);
      }
    };
    this.eventSource.addEventListener('intel_item', intelItemHandler as EventListener);
    this.eventListeners.set('intel_item', intelItemHandler as EventListener);

    // heartbeat 事件
    const heartbeatHandler = () => {
      if (this.eventHandlers.onHeartbeat) {
        this.eventHandlers.onHeartbeat();
      }
      this.resetHeartbeatTimer();
    };
    this.eventSource.addEventListener('heartbeat', heartbeatHandler);
    this.eventListeners.set('heartbeat', heartbeatHandler);

    // 打开连接
    this.eventSource.onopen = () => {
      this.clearTimers(); // 清除连接超时定时器
      this.updateState({
        status: 'connected',
        retryCount: 0,
        lastError: undefined,
        connectedAt: new Date()
      });

      this.resetHeartbeatTimer();
      this.startStateUpdateTimer();
    };

    // 错误处理
    this.eventSource.onerror = (event: Event) => {
      console.error('SSE连接错误:', event);
      this.handleError(new Error('SSE连接错误'));
    };

    // 监听标准错误事件
    const errorHandler = (event: Event) => {
      try {
        const messageEvent = event as MessageEvent;
        const data = JSON.parse(messageEvent.data);
        if (data.message) {
          this.handleError(new Error(data.message));
        }
      } catch {
        // 忽略解析错误
      }
    };
    this.eventSource.addEventListener('error', errorHandler as EventListener);
    this.eventListeners.set('error', errorHandler as EventListener);
  }

  /**
   * 处理错误
   */
  private handleError(error: Error): void {
    console.error('SSE管理器错误:', error);

    this.updateState({
      status: 'error',
      lastError: error.message
    });

    if (this.eventHandlers.onError) {
      this.eventHandlers.onError(error);
    }

    // 清理现有连接
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.clearTimers();
    this.removeEventListeners();

    // 自动重试
    if (this.state.retryCount < this.options.maxRetries) {
      this.retry();
    }
  }

  /**
   * 重置心跳定时器
   */
  private resetHeartbeatTimer(): void {
    if (this.heartbeatTimer) {
      window.clearTimeout(this.heartbeatTimer);
    }

    this.heartbeatTimer = window.setTimeout(() => {
      this.handleError(new Error(`心跳超时 (${this.options.heartbeatTimeout}ms)`));
    }, this.options.heartbeatTimeout);

    this.updateState({
      lastHeartbeat: new Date()
    });
  }

  /**
   * 启动状态更新定时器
   */
  private startStateUpdateTimer(): void {
    this.stateUpdateTimer = window.setInterval(() => {
      this.updateState({
        connectionDuration: this.calculateConnectionDuration()
      });
    }, 30000); // 30秒更新一次（仅用于展示连接时长）
  }

  /**
   * 清除所有定时器
   */
  private clearTimers(): void {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.heartbeatTimer) {
      window.clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.connectionTimer) {
      window.clearTimeout(this.connectionTimer);
      this.connectionTimer = null;
    }

    if (this.stateUpdateTimer) {
      window.clearInterval(this.stateUpdateTimer);
      this.stateUpdateTimer = null;
    }
  }

  /**
   * 移除所有事件监听器
   */
  private removeEventListeners(): void {
    if (!this.eventSource) return;

    this.eventListeners.forEach((handler, eventType) => {
      this.eventSource!.removeEventListener(eventType, handler);
    });

    this.eventListeners.clear();

    // 清理onopen和onerror引用
    this.eventSource.onopen = null;
    this.eventSource.onerror = null;
  }

  /**
   * 更新状态
   */
  private updateState(updates: Partial<SSEConnectionState>): void {
    const oldState = this.state;
    this.state = {
      ...oldState,
      ...updates
    };

    // 触发状态变化回调
    if (this.eventHandlers.onStateChange && (
      oldState.status !== this.state.status ||
      oldState.retryCount !== this.state.retryCount ||
      oldState.lastError !== this.state.lastError
    )) {
      this.eventHandlers.onStateChange(this.state);
    }
  }

  /**
   * 计算重试延迟
   */
  private calculateRetryDelay(retryCount: number): number {
    const delay = this.options.retryDelay * Math.pow(this.options.retryBackoffFactor, retryCount - 1);
    return Math.min(delay, this.options.maxRetryDelay);
  }

  /**
   * 计算连接持续时间
   */
  private calculateConnectionDuration(): number {
    if (!this.state.connectedAt) return 0;
    return Date.now() - this.state.connectedAt.getTime();
  }

  private isValidIntelEvent(payload: IntelFeedEvent | null | undefined): payload is IntelFeedEvent {
    if (!payload || typeof payload !== 'object') return false;
    if (!payload.item || typeof payload.item !== 'object') return false;
    const item = payload.item as unknown as Record<string, unknown>;
    return (
      typeof payload.event_id === 'string' &&
      typeof payload.occurred_at === 'string' &&
      typeof payload.event_type === 'string' &&
      typeof item.item_id === 'string' &&
      typeof item.item_type === 'string' &&
      typeof item.occurred_at === 'string'
    );
  }
}

/**
 * 创建SSE管理器实例的便捷函数
 */
export function createSSEManager(
  params: {
    date?: string;
    type?: IntelItemType;
    session?: IntelSession;
  },
  eventHandlers: SSEEventHandlers = {},
  options: SSEManagerOptions = {}
): SSEManager {
  return new SSEManager(params, eventHandlers, options);
}
