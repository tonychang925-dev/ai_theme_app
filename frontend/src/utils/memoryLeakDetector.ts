/**
 * 内存泄漏检测工具
 * 用于检测和监控前端应用中的内存泄漏问题
 */

import React from 'react';

export interface MemoryLeakDetectionConfig {
  /** 检测间隔（毫秒），默认30秒 */
  checkInterval?: number;

  /** 内存增长阈值（MB），默认10MB */
  memoryGrowthThreshold?: number;

  /** 检测次数，默认10次 */
  detectionCount?: number;

  /** 启用EventSource泄漏检测 */
  enableSSELeakDetection?: boolean;

  /** 启用定时器泄漏检测 */
  enableTimerLeakDetection?: boolean;

  /** 启用DOM节点泄漏检测 */
  enableDOMLeakDetection?: boolean;
}

export interface MemoryLeakReport {
  /** 报告时间戳 */
  timestamp: Date;

  /** 检测到的泄漏类型 */
  leakTypes: string[];

  /** 内存使用情况 */
  memoryUsage: {
    /** 当前内存使用量（MB） */
    currentMB: number;

    /** 初始内存使用量（MB） */
    initialMB: number;

    /** 内存增长量（MB） */
    growthMB: number;

    /** 内存增长率 */
    growthRate: number;
  };

  /** EventSource泄漏详情 */
  sseLeaks?: {
    /** 活跃的EventSource连接数 */
    activeConnections: number;

    /** 未正确关闭的连接数 */
    unclosedConnections: number;

    /** 连接详情 */
    connections: Array<{
      url: string;
      status: number;
      createdAt: Date;
    }>;
  };

  /** 定时器泄漏详情 */
  timerLeaks?: {
    /** 活跃定时器数量 */
    activeTimers: number;

    /** 定时器详情 */
    timers: Array<{
      type: 'timeout' | 'interval';
      id: number;
      duration?: number;
    }>;
  };

  /** DOM节点泄漏详情 */
  domLeaks?: {
    /** DOM节点总数 */
    totalNodes: number;

    /** 疑似泄漏的节点数 */
    leakedNodes: number;

    /** 节点类型分布 */
    nodeTypes: Record<string, number>;
  };

  /** 优化建议 */
  recommendations: string[];
}

export class MemoryLeakDetector {
  private config: Required<MemoryLeakDetectionConfig>;
  private checkIntervalId: number | null = null;
  private initialMemoryUsage: number = 0;
  private memoryReadings: number[] = [];
  private sseConnections: Map<string, any> = new Map();
  private activeTimers: Map<number, any> = new Map();
  private detectionStartTime: Date = new Date();

  constructor(config: MemoryLeakDetectionConfig = {}) {
    this.config = {
      checkInterval: 30000, // 30秒
      memoryGrowthThreshold: 10, // 10MB
      detectionCount: 10,
      enableSSELeakDetection: true,
      enableTimerLeakDetection: true,
      enableDOMLeakDetection: true,
      ...config
    };
  }

  /**
   * 开始内存泄漏检测
   */
  start(): void {
    if (process.env.NODE_ENV === 'development') {
      console.log('🔍 启动内存泄漏检测');
    }

    // 记录初始内存使用
    this.initialMemoryUsage = this.getCurrentMemoryUsage();
    this.memoryReadings.push(this.initialMemoryUsage);

    // 开始定期检测
    this.checkIntervalId = window.setInterval(() => {
      this.performLeakCheck();
    }, this.config.checkInterval);

    // 拦截定时器创建
    if (this.config.enableTimerLeakDetection) {
      this.interceptTimers();
    }

    // 拦截EventSource创建
    if (this.config.enableSSELeakDetection) {
      this.interceptEventSources();
    }
  }

  /**
   * 停止内存泄漏检测
   */
  stop(): void {
    if (this.checkIntervalId) {
      window.clearInterval(this.checkIntervalId);
      this.checkIntervalId = null;
    }

    // 清理拦截器
    this.cleanupInterceptors();

    if (process.env.NODE_ENV === 'development') {
      console.log('🛑 停止内存泄漏检测');
    }
  }

  /**
   * 执行泄漏检查
   */
  private performLeakCheck(): void {
    const report = this.generateLeakReport();

    // 检查是否有严重泄漏
    const hasSeriousLeak = this.checkForSeriousLeaks(report);

    if (hasSeriousLeak) {
      if (process.env.NODE_ENV === 'development') {
        console.warn('⚠️ 检测到潜在内存泄漏', report);
      }

      // 触发泄漏警告事件
      this.triggerLeakWarning(report);
    }

    // 记录内存读数
    this.memoryReadings.push(report.memoryUsage.currentMB);

    // 限制记录数量
    if (this.memoryReadings.length > this.config.detectionCount * 2) {
      this.memoryReadings = this.memoryReadings.slice(-this.config.detectionCount);
    }
  }

  /**
   * 生成泄漏报告
   */
  generateLeakReport(): MemoryLeakReport {
    const currentMemory = this.getCurrentMemoryUsage();
    const growth = currentMemory - this.initialMemoryUsage;
    const growthRate = this.initialMemoryUsage > 0 ? (growth / this.initialMemoryUsage) * 100 : 0;

    const leakTypes: string[] = [];
    const recommendations: string[] = [];

    // 检查内存增长
    if (growth > this.config.memoryGrowthThreshold) {
      leakTypes.push('memory_growth');
      recommendations.push(`内存增长 ${growth.toFixed(2)}MB，检查组件卸载时的资源清理`);
    }

    // 检查EventSource泄漏
    let sseLeaks;
    if (this.config.enableSSELeakDetection) {
      sseLeaks = this.checkSSELeaks();
      if (sseLeaks && sseLeaks.unclosedConnections > 0) {
        leakTypes.push('sse_leak');
        recommendations.push(`发现 ${sseLeaks.unclosedConnections} 个未关闭的SSE连接，确保组件卸载时调用disconnect()`);
      }
    }

    // 检查定时器泄漏
    let timerLeaks;
    if (this.config.enableTimerLeakDetection) {
      timerLeaks = this.checkTimerLeaks();
      if (timerLeaks && timerLeaks.activeTimers > 20) { // 阈值
        leakTypes.push('timer_leak');
        recommendations.push(`发现 ${timerLeaks.activeTimers} 个活跃定时器，检查组件卸载时是否清理定时器`);
      }
    }

    // 检查DOM节点泄漏
    let domLeaks;
    if (this.config.enableDOMLeakDetection) {
      domLeaks = this.checkDOMLeaks();
      if (domLeaks && domLeaks.leakedNodes > 100) { // 阈值
        leakTypes.push('dom_leak');
        recommendations.push(`发现 ${domLeaks.leakedNodes} 个疑似泄漏的DOM节点，检查组件卸载时的DOM清理`);
      }
    }

    return {
      timestamp: new Date(),
      leakTypes,
      memoryUsage: {
        currentMB: currentMemory,
        initialMB: this.initialMemoryUsage,
        growthMB: growth,
        growthRate
      },
      sseLeaks,
      timerLeaks,
      domLeaks,
      recommendations
    };
  }

  /**
   * 检查严重泄漏
   */
  private checkForSeriousLeaks(report: MemoryLeakReport): boolean {
    // 内存增长超过阈值
    if (report.memoryUsage.growthMB > this.config.memoryGrowthThreshold) {
      return true;
    }

    // 有未关闭的SSE连接
    if (report.sseLeaks && report.sseLeaks.unclosedConnections > 0) {
      return true;
    }

    // 定时器数量过多
    if (report.timerLeaks && report.timerLeaks.activeTimers > 50) {
      return true;
    }

    return false;
  }

  /**
   * 获取当前内存使用量（MB）
   */
  private getCurrentMemoryUsage(): number {
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      return memory.usedJSHeapSize / (1024 * 1024); // 转换为MB
    }

    // 备用方法：估算内存使用
    return 0;
  }

  /**
   * 检查SSE泄漏
   */
  private checkSSELeaks(): MemoryLeakReport['sseLeaks'] {
    const connections: Array<{ url: string; status: number; createdAt: Date }> = [];

    this.sseConnections.forEach((connection, url) => {
      connections.push({
        url,
        status: connection.readyState || 0,
        createdAt: connection.createdAt || new Date()
      });
    });

    const unclosedConnections = connections.filter(c => c.status !== 2).length; // 2 = CLOSED

    return {
      activeConnections: connections.length,
      unclosedConnections,
      connections
    };
  }

  /**
   * 检查定时器泄漏
   */
  private checkTimerLeaks(): MemoryLeakReport['timerLeaks'] {
    const timers: Array<{ type: 'timeout' | 'interval'; id: number; duration?: number }> = [];

    this.activeTimers.forEach((timer, id) => {
      timers.push({
        type: timer.type,
        id,
        duration: timer.duration
      });
    });

    return {
      activeTimers: timers.length,
      timers
    };
  }

  /**
   * 检查DOM节点泄漏
   */
  private checkDOMLeaks(): MemoryLeakReport['domLeaks'] {
    const allElements = document.getElementsByTagName('*');
    const nodeTypes: Record<string, number> = {};

    // 统计节点类型
    for (let i = 0; i < allElements.length; i++) {
      const nodeName = allElements[i].nodeName.toLowerCase();
      nodeTypes[nodeName] = (nodeTypes[nodeName] || 0) + 1;
    }

    // 简单泄漏检测：检查是否有大量隐藏或未使用的节点
    const hiddenElements = document.querySelectorAll('[style*="display: none"], [style*="visibility: hidden"]');
    const detachedElements = this.findDetachedElements();

    return {
      totalNodes: allElements.length,
      leakedNodes: hiddenElements.length + detachedElements.length,
      nodeTypes
    };
  }

  /**
   * 查找分离的DOM元素
   */
  private findDetachedElements(): Element[] {
    const detached: Element[] = [];

    // 这里可以实现更复杂的分离元素检测逻辑
    // 例如：检查是否有元素不在文档流中但仍有引用

    return detached;
  }

  /**
   * 拦截定时器创建
   */
  private interceptTimers(): void {
    const originalSetTimeout = window.setTimeout;
    const originalSetInterval = window.setInterval;
    const originalClearTimeout = window.clearTimeout;
    const originalClearInterval = window.clearInterval;

    // 包装handler函数，确保它是函数类型
    const wrapHandler = (handler: TimerHandler, ...args: any[]): (() => void) => {
      if (typeof handler === 'function') {
        return () => handler(...args);
      } else if (typeof handler === 'string') {
        // 对于字符串handler，创建函数来执行它
        return () => {
          // eslint-disable-next-line no-eval
          eval(handler);
        };
      } else {
        return () => {};
      }
    };

    // 使用类型断言解决TypeScript类型问题
    (window as any).setTimeout = (handler: TimerHandler, timeout?: number, ...args: any[]): number => {
      const wrappedHandler = wrapHandler(handler, ...args);
      const timerId = originalSetTimeout.call(window, wrappedHandler, timeout) as unknown as number;

      this.activeTimers.set(timerId, {
        type: 'timeout',
        duration: timeout,
        createdAt: new Date(),
        stack: new Error().stack // 记录调用栈
      });

      return timerId;
    };

    (window as any).setInterval = (handler: TimerHandler, timeout?: number, ...args: any[]): number => {
      const wrappedHandler = wrapHandler(handler, ...args);
      const timerId = originalSetInterval.call(window, wrappedHandler, timeout) as unknown as number;

      this.activeTimers.set(timerId, {
        type: 'interval',
        duration: timeout,
        createdAt: new Date(),
        stack: new Error().stack
      });

      return timerId;
    };

    (window as any).clearTimeout = (id: number): void => {
      this.activeTimers.delete(id);
      originalClearTimeout.call(window, id);
    };

    (window as any).clearInterval = (id: number): void => {
      this.activeTimers.delete(id);
      originalClearInterval.call(window, id);
    };
  }

  /**
   * 拦截EventSource创建
   */
  private interceptEventSources(): void {
    const originalEventSource = window.EventSource;

    // 使用类型断言解决TypeScript类型问题
    (window as any).EventSource = class PatchedEventSource extends originalEventSource {
      constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
        super(url, eventSourceInitDict);

        const detector = (window as any).__memoryLeakDetector as MemoryLeakDetector;
        if (detector) {
          detector.sseConnections.set(url.toString(), {
            instance: this,
            readyState: this.readyState,
            createdAt: new Date()
          });

          // 监听关闭事件
          this.addEventListener('close', () => {
            detector.sseConnections.delete(url.toString());
          });
        }
      }
    };
  }

  /**
   * 清理拦截器
   */
  private cleanupInterceptors(): void {
    // 恢复原始函数
    // 注意：在实际应用中需要更复杂的恢复逻辑
  }

  /**
   * 触发泄漏警告事件
   */
  private triggerLeakWarning(report: MemoryLeakReport): void {
    // 可以发送到监控系统、显示警告等
    const event = new CustomEvent('memory-leak-warning', {
      detail: report
    });

    window.dispatchEvent(event);
  }

  /**
   * 强制垃圾回收（仅用于测试）
   */
  forceGarbageCollection(): void {
    if (window.gc) {
      window.gc();
    } else if ('gc' in window) {
      (window as any).gc();
    }
  }
}

/**
 * 创建内存泄漏检测器实例
 */
export function createMemoryLeakDetector(config?: MemoryLeakDetectionConfig): MemoryLeakDetector {
  const detector = new MemoryLeakDetector(config);

  // 将检测器挂载到window以便拦截器访问
  (window as any).__memoryLeakDetector = detector;

  return detector;
}

/**
 * React Hook：在组件中使用内存泄漏检测
 */
export function useMemoryLeakDetection(config?: MemoryLeakDetectionConfig) {
  const detectorRef = React.useRef<MemoryLeakDetector | null>(null);

  React.useEffect(() => {
    // 只在开发环境启用
    if (process.env.NODE_ENV === 'development') {
      detectorRef.current = createMemoryLeakDetector(config);
      detectorRef.current.start();

      return () => {
        if (detectorRef.current) {
          detectorRef.current.stop();
          detectorRef.current = null;
        }
      };
    }
  }, [config]);

  return detectorRef.current;
}