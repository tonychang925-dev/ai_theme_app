/**
 * 前端性能监控工具
 * 用于分析前端性能瓶颈，检测内存泄漏，优化用户体验
 */

interface PerformanceMetrics {
  pageLoadTime: number;
  firstContentfulPaint: number;
  largestContentfulPaint: number;
  cumulativeLayoutShift: number;
  totalBlockingTime: number;
  timeToInteractive: number;
  memoryUsage?: {
    usedJSHeapSize: number;
    totalJSHeapSize: number;
    jsHeapSizeLimit: number;
  };
  resourceTiming: Array<{
    name: string;
    duration: number;
    transferSize: number;
    initiatorType: string;
  }>;
  sseConnections: number;
  longTasks: Array<{
    duration: number;
    startTime: number;
    name?: string;
  }>;
}

interface PerformanceReport {
  timestamp: string;
  url: string;
  metrics: PerformanceMetrics;
  issues: Array<{
    type: 'memory_leak' | 'slow_resource' | 'layout_shift' | 'long_task' | 'sse_leak';
    severity: 'low' | 'medium' | 'high';
    description: string;
    recommendation: string;
  }>;
  recommendations: string[];
}

class PerformanceMonitor {
  private metrics: PerformanceMetrics;
  // Observer-only: never close or recreate business-owned resources.
  private trackedEventSources: WeakMap<EventSource, {
    url: string;
    createdAt: number;
    openedAt?: number;
    lastErrorAt?: number;
    readyState: number;
    finalized: boolean;
  }> = new WeakMap();
  private trackedEventSourceCount = 0;
  private longTaskObserver: PerformanceObserver | null = null;
  private resourceObserver: PerformanceObserver | null = null;
  private layoutShiftObserver: PerformanceObserver | null = null;
  private memoryMonitorTimer: number | null = null;
  private originalEventSource: typeof EventSource | null = null;
  private eventSourcePatched = false;
  private isMonitoring: boolean = false;

  constructor() {
    this.metrics = {
      pageLoadTime: 0,
      firstContentfulPaint: 0,
      largestContentfulPaint: 0,
      cumulativeLayoutShift: 0,
      totalBlockingTime: 0,
      timeToInteractive: 0,
      resourceTiming: [],
      sseConnections: 0,
      longTasks: []
    };
  }

  /**
   * 开始性能监控
   */
  startMonitoring(): void {
    if (this.isMonitoring) {
      if (process.env.NODE_ENV === 'development') {
        console.warn('性能监控已启动');
      }
      return;
    }

    if (process.env.NODE_ENV === 'development') {
      console.log('🚀 启动前端性能监控');
    }
    this.isMonitoring = true;

    // 监听长任务
    this.setupLongTaskObserver();

    // 监听资源加载
    this.setupResourceObserver();

    // 监听布局偏移
    this.setupLayoutShiftObserver();

    // 监听SSE连接
    this.setupSSEMonitoring();

    // 收集初始性能指标
    this.collectInitialMetrics();

    // 定期检查内存使用
    this.startMemoryMonitoring();
  }

  /**
   * 停止性能监控
   */
  stopMonitoring(): void {
    if (!this.isMonitoring) {
      return;
    }

    if (process.env.NODE_ENV === 'development') {
      console.log('🛑 停止前端性能监控');
    }
    this.isMonitoring = false;

    this.longTaskObserver?.disconnect();
    this.resourceObserver?.disconnect();
    this.layoutShiftObserver?.disconnect();

    if (this.memoryMonitorTimer !== null) {
      window.clearInterval(this.memoryMonitorTimer);
      this.memoryMonitorTimer = null;
    }

    this.restoreEventSource();
    this.trackedEventSources = new WeakMap();
    this.trackedEventSourceCount = 0;
    this.metrics.sseConnections = 0;
  }

  /**
   * 生成性能报告
   */
  generateReport(): PerformanceReport {
    const issues = this.analyzeIssues();
    const recommendations = this.generateRecommendations(issues);

    return {
      timestamp: new Date().toISOString(),
      url: window.location.href,
      metrics: { ...this.metrics },
      issues,
      recommendations
    };
  }

  /**
   * 导出报告为JSON
   */
  exportReport(): string {
    const report = this.generateReport();
    return JSON.stringify(report, null, 2);
  }

  /**
   * 下载报告
   */
  downloadReport(filename: string = 'performance_report.json'): void {
    const report = this.exportReport();
    const blob = new Blob([report], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * 获取当前SSE连接数
   */
  getSSEConnectionCount(): number {
    return this.trackedEventSourceCount;
  }

  /**
   * 手动添加SSE连接监控
   */
  monitorSSEConnection(eventSource: EventSource): void {
    if (this.trackedEventSources.has(eventSource)) {
      return;
    }

    this.trackedEventSources.set(eventSource, {
      url: '',
      createdAt: Date.now(),
      readyState: eventSource.readyState,
      finalized: false
    });
    this.trackedEventSourceCount += 1;
    this.metrics.sseConnections = this.trackedEventSourceCount;

    const finalize = () => {
      this.finalizeTrackedEventSource(eventSource);
    };

    eventSource.addEventListener('open', () => {
      const info = this.trackedEventSources.get(eventSource);
      if (!info || info.finalized) {
        return;
      }
      info.openedAt = Date.now();
      info.readyState = eventSource.readyState;
    });

    eventSource.addEventListener('error', () => {
      const info = this.trackedEventSources.get(eventSource);
      if (!info || info.finalized) {
        return;
      }
      info.lastErrorAt = Date.now();
      info.readyState = eventSource.readyState;
      if (eventSource.readyState === EventSource.CLOSED) {
        finalize();
      }
    });

    eventSource.addEventListener('close', finalize);
  }

  private setupLongTaskObserver(): void {
    if ('PerformanceObserver' in window) {
      this.longTaskObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          if (entry.duration > 50) { // 超过50ms的任务视为长任务
            this.metrics.longTasks.push({
              duration: entry.duration,
              startTime: entry.startTime,
              name: entry.name
            });
          }
        });
      });

      try {
        this.longTaskObserver.observe({ entryTypes: ['longtask'] });
      } catch (e) {
        if (process.env.NODE_ENV === 'development') {
          console.warn('长任务监控不支持:', e);
        }
      }
    }
  }

  private setupResourceObserver(): void {
    if ('PerformanceObserver' in window) {
      this.resourceObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          const resourceEntry = entry as PerformanceResourceTiming;
          this.metrics.resourceTiming.push({
            name: resourceEntry.name,
            duration: resourceEntry.duration,
            transferSize: resourceEntry.transferSize,
            initiatorType: resourceEntry.initiatorType
          });
        });
      });

      try {
        this.resourceObserver.observe({ entryTypes: ['resource'] });
      } catch (e) {
        if (process.env.NODE_ENV === 'development') {
          console.warn('资源监控不支持:', e);
        }
      }
    }
  }

  private setupLayoutShiftObserver(): void {
    if ('PerformanceObserver' in window) {
      this.layoutShiftObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          const layoutShiftEntry = entry as any;
          if (!layoutShiftEntry.hadRecentInput) {
            this.metrics.cumulativeLayoutShift += layoutShiftEntry.value;
          }
        });
      });

      try {
        this.layoutShiftObserver.observe({ entryTypes: ['layout-shift'] });
      } catch (e) {
        if (process.env.NODE_ENV === 'development') {
          console.warn('布局偏移监控不支持:', e);
        }
      }
    }
  }

  private setupSSEMonitoring(): void {
    if (this.eventSourcePatched) {
      return;
    }

    // 仅拦截 EventSource 构造函数做观察，不接管业务资源生命周期。
    const originalEventSource = window.EventSource;
    this.originalEventSource = originalEventSource;
    const self = this;

    const MonitoredEventSource = function(url: string, eventSourceInitDict?: EventSourceInit) {
      const eventSource = new originalEventSource(url, eventSourceInitDict);
      self.monitorSSEConnection(eventSource);
      return eventSource;
    } as any;

    MonitoredEventSource.prototype = originalEventSource.prototype;
    window.EventSource = MonitoredEventSource;
    this.eventSourcePatched = true;
  }

  private restoreEventSource(): void {
    if (this.eventSourcePatched && this.originalEventSource) {
      window.EventSource = this.originalEventSource;
    }

    this.originalEventSource = null;
    this.eventSourcePatched = false;
  }

  private collectInitialMetrics(): void {
    // 使用Performance API收集核心Web Vitals
    if ('performance' in window) {
      const perf = window.performance;
      const navEntry = perf.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
      
      if (navEntry) {
        this.metrics.pageLoadTime = navEntry.loadEventEnd - navEntry.startTime;
        this.metrics.timeToInteractive = this.calculateTimeToInteractive();
      }

      // 收集Paint Timing
      const paintEntries = perf.getEntriesByType('paint');
      paintEntries.forEach((entry) => {
        if (entry.name === 'first-contentful-paint') {
          this.metrics.firstContentfulPaint = entry.startTime;
        }
      });

      // 收集Largest Contentful Paint
      const lcpEntries = perf.getEntriesByType('largest-contentful-paint');
      if (lcpEntries.length > 0) {
        this.metrics.largestContentfulPaint = lcpEntries[lcpEntries.length - 1].startTime;
      }

      // 收集Total Blocking Time
      this.metrics.totalBlockingTime = this.calculateTotalBlockingTime();
    }
  }

  private startMemoryMonitoring(): void {
    if ('memory' in (performance as any)) {
      const memory = (performance as any).memory;
      this.metrics.memoryUsage = {
        usedJSHeapSize: memory.usedJSHeapSize,
        totalJSHeapSize: memory.totalJSHeapSize,
        jsHeapSizeLimit: memory.jsHeapSizeLimit
      };

      // 定期检查内存使用
      this.memoryMonitorTimer = window.setInterval(() => {
        if (this.isMonitoring) {
          this.metrics.memoryUsage = {
            usedJSHeapSize: memory.usedJSHeapSize,
            totalJSHeapSize: memory.totalJSHeapSize,
            jsHeapSizeLimit: memory.jsHeapSizeLimit
          };
        }
      }, 10000); // 每10秒检查一次
    }
  }

  private calculateTimeToInteractive(): number {
    // 简化版的TTI计算
    const longTasks = this.metrics.longTasks.filter(task => task.duration > 50);
    if (longTasks.length === 0) {
      return this.metrics.firstContentfulPaint + 100; // 假设FCP后100ms可交互
    }
    
    const lastLongTask = longTasks[longTasks.length - 1];
    return lastLongTask.startTime + lastLongTask.duration + 50;
  }

  private calculateTotalBlockingTime(): number {
    return this.metrics.longTasks
      .filter(task => task.duration > 50)
      .reduce((total, task) => total + (task.duration - 50), 0);
  }

  private analyzeIssues(): PerformanceReport['issues'] {
    const issues: PerformanceReport['issues'] = [];

    // 检查内存泄漏
    if (this.metrics.memoryUsage) {
      const memoryUsageRatio = this.metrics.memoryUsage.usedJSHeapSize / this.metrics.memoryUsage.jsHeapSizeLimit;
      if (memoryUsageRatio > 0.8) {
        issues.push({
          type: 'memory_leak',
          severity: 'high',
          description: `内存使用率过高: ${(memoryUsageRatio * 100).toFixed(1)}%`,
          recommendation: '检查内存泄漏，优化组件卸载，减少全局变量'
        });
      }
    }

    // 检查SSE连接泄漏
    if (this.metrics.sseConnections > 5) {
      issues.push({
        type: 'sse_leak',
        severity: 'medium',
        description: `SSE连接数过多: ${this.metrics.sseConnections}个`,
        recommendation: '确保SSE连接在组件卸载时正确关闭，实现连接池管理'
      });
    }

    // 检查布局偏移
    if (this.metrics.cumulativeLayoutShift > 0.1) {
      issues.push({
        type: 'layout_shift',
        severity: 'medium',
        description: `累计布局偏移过高: ${this.metrics.cumulativeLayoutShift.toFixed(3)}`,
        recommendation: '为图片和广告预留空间，避免动态内容插入导致布局变化'
      });
    }

    // 检查长任务
    const longTasks = this.metrics.longTasks.filter(task => task.duration > 100);
    if (longTasks.length > 3) {
      issues.push({
        type: 'long_task',
        severity: 'medium',
        description: `检测到${longTasks.length}个长任务(>100ms)`,
        recommendation: '优化JavaScript执行，将长任务拆分为多个小任务，使用Web Workers'
      });
    }

    // 检查慢资源
    const slowResources = this.metrics.resourceTiming.filter(resource => resource.duration > 1000);
    if (slowResources.length > 0) {
      issues.push({
        type: 'slow_resource',
        severity: 'low',
        description: `检测到${slowResources.length}个慢资源加载(>1s)`,
        recommendation: '优化资源加载，使用CDN，压缩资源，实现懒加载'
      });
    }

    return issues;
  }

  private generateRecommendations(issues: PerformanceReport['issues']): string[] {
    const recommendations: string[] = [];

    // 基于问题生成建议
    if (issues.some(issue => issue.type === 'memory_leak')) {
      recommendations.push('实施内存泄漏检测：使用Chrome DevTools Memory面板定期检查');
      recommendations.push('优化组件生命周期：确保useEffect清理函数正确执行');
      recommendations.push('减少全局状态：使用局部状态替代全局状态管理');
    }

    if (issues.some(issue => issue.type === 'sse_leak')) {
      recommendations.push('实现SSE连接管理器：统一管理所有SSE连接的生命周期');
      recommendations.push('添加连接数限制：限制同时打开的SSE连接数量');
      recommendations.push('优化连接复用：实现SSE连接池，避免重复创建连接');
    }

    if (issues.some(issue => issue.type === 'layout_shift')) {
      recommendations.push('优化图片加载：为所有图片设置width和height属性');
      recommendations.push('预留广告空间：为动态广告内容预留固定尺寸容器');
      recommendations.push('避免动态内容插入：使用CSS动画替代直接DOM操作');
    }

    if (issues.some(issue => issue.type === 'long_task')) {
      recommendations.push('代码分割：使用React.lazy和Suspense实现路由级代码分割');
      recommendations.push('优化渲染：使用React.memo和useMemo减少不必要的重新渲染');
      recommendations.push('异步处理：将计算密集型任务移到Web Workers中执行');
    }

    if (issues.some(issue => issue.type === 'slow_resource')) {
      recommendations.push('资源优化：压缩图片，使用WebP格式，实现图片懒加载');
      recommendations.push('CDN加速：将静态资源部署到CDN');
      recommendations.push('预加载关键资源：使用<link rel="preload">预加载关键CSS和字体');
    }

    // 通用建议
    recommendations.push('实施性能预算：为关键指标设置性能预算并监控');
    recommendations.push('定期性能审计：每周执行一次完整的性能测试');
    recommendations.push('用户体验监控：监控真实用户性能指标(RUM)');

    return recommendations;
  }

  private finalizeTrackedEventSource(eventSource: EventSource): void {
    const info = this.trackedEventSources.get(eventSource);
    if (!info || info.finalized) {
      return;
    }

    info.finalized = true;
    this.trackedEventSourceCount = Math.max(0, this.trackedEventSourceCount - 1);
    this.metrics.sseConnections = this.trackedEventSourceCount;
  }
}

// 导出单例实例
export const performanceMonitor = new PerformanceMonitor();

// 开发环境自动启动监控
if (process.env.NODE_ENV === 'development') {
  window.addEventListener('load', () => {
    setTimeout(() => {
      performanceMonitor.startMonitoring();
      console.log('🔍 开发环境性能监控已启动');
    }, 1000);
  });
}

export default PerformanceMonitor;
