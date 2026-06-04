/**
 * 性能监控工具测试
 */

import { performanceMonitor } from './performanceMonitor';

describe('PerformanceMonitor', () => {
  let monitor: typeof performanceMonitor;

  beforeEach(() => {
    monitor = performanceMonitor;
  });

  afterEach(() => {
    monitor.stopMonitoring();
  });

  test('应该正确初始化', () => {
    expect(monitor).toBeDefined();
  });

  test('应该能够启动和停止监控', () => {
    const startSpy = (jest as any).spyOn(monitor, 'startMonitoring') as any;
    const stopSpy = (jest as any).spyOn(monitor, 'stopMonitoring') as any;

    monitor.startMonitoring();
    expect(startSpy).toHaveBeenCalled();

    monitor.stopMonitoring();
    expect(stopSpy).toHaveBeenCalled();
  });

  test('应该生成性能报告', () => {
    monitor.startMonitoring();
    const report = monitor.generateReport();

    expect(report).toHaveProperty('timestamp');
    expect(report).toHaveProperty('url');
    expect(report).toHaveProperty('metrics');
    expect(report).toHaveProperty('issues');
    expect(report).toHaveProperty('recommendations');

    expect(report.metrics).toHaveProperty('pageLoadTime');
    expect(report.metrics).toHaveProperty('firstContentfulPaint');
    expect(report.metrics).toHaveProperty('largestContentfulPaint');
    expect(report.metrics).toHaveProperty('cumulativeLayoutShift');
    expect(report.metrics).toHaveProperty('totalBlockingTime');
    expect(report.metrics).toHaveProperty('timeToInteractive');
    expect(report.metrics).toHaveProperty('resourceTiming');
    expect(report.metrics).toHaveProperty('sseConnections');
    expect(report.metrics).toHaveProperty('longTasks');
  });

  test('应该导出报告为JSON', () => {
    monitor.startMonitoring();
    const json = monitor.exportReport();

    expect(typeof json).toBe('string');
    
    const parsed = JSON.parse(json);
    expect(parsed).toHaveProperty('timestamp');
    expect(parsed).toHaveProperty('metrics');
  });

  test('应该能够下载报告', () => {
    // 模拟DOM方法
    const createElementSpy = (jest as any).spyOn(document, 'createElement');
    const appendChildSpy = (jest as any).spyOn(document.body, 'appendChild');
    const removeChildSpy = (jest as any).spyOn(document.body, 'removeChild');
    
    const mockClick = (jest as any).fn();
    const mockAnchor = {
      href: '',
      download: '',
      click: mockClick
    } as any;
    
    createElementSpy.mockReturnValue(mockAnchor);

    monitor.startMonitoring();
    monitor.downloadReport();

    expect(createElementSpy).toHaveBeenCalledWith('a');
    expect(appendChildSpy).toHaveBeenCalledWith(mockAnchor);
    expect(mockClick).toHaveBeenCalled();
    expect(removeChildSpy).toHaveBeenCalledWith(mockAnchor);
  });

  test('应该能够监控SSE连接', () => {
    const addEventListener = (jest as any).fn();
    const mockEventSource = {
      addEventListener,
      close: (jest as any).fn()
    } as any;

    monitor.startMonitoring();
    monitor.monitorSSEConnection(mockEventSource);

    expect(monitor.getSSEConnectionCount()).toBe(1);
    expect(addEventListener).toHaveBeenCalledWith('open', expect.any(Function));
    expect(addEventListener).toHaveBeenCalledWith('error', expect.any(Function));
    expect(addEventListener).toHaveBeenCalledWith('close', expect.any(Function));
  });

  test('停止监控时不应该关闭业务EventSource', () => {
    const mockEventSource = {
      readyState: 1,
      addEventListener: (jest as any).fn(),
      close: (jest as any).fn()
    } as any;

    monitor.startMonitoring();
    monitor.monitorSSEConnection(mockEventSource);
    monitor.stopMonitoring();

    expect(mockEventSource.close).not.toHaveBeenCalled();
    expect(monitor.getSSEConnectionCount()).toBe(0);
  });

  test('EventSource补丁应该可恢复', () => {
    const originalEventSource = window.EventSource;

    monitor.startMonitoring();
    expect(window.EventSource).not.toBe(originalEventSource);

    monitor.stopMonitoring();
    expect(window.EventSource).toBe(originalEventSource);
  });

  test('应该分析性能问题', () => {
    // 模拟有问题的指标
    monitor['metrics'] = {
      pageLoadTime: 5000,
      firstContentfulPaint: 3000,
      largestContentfulPaint: 4000,
      cumulativeLayoutShift: 0.15,
      totalBlockingTime: 300,
      timeToInteractive: 5000,
      memoryUsage: {
        usedJSHeapSize: 800 * 1024 * 1024, // 800MB
        totalJSHeapSize: 900 * 1024 * 1024,
        jsHeapSizeLimit: 1000 * 1024 * 1024
      },
      resourceTiming: [
        { name: 'slow-resource.js', duration: 2000, transferSize: 1000000, initiatorType: 'script' }
      ],
      sseConnections: 10,
      longTasks: [
        { duration: 150, startTime: 1000, name: 'long-task-1' },
        { duration: 200, startTime: 2000, name: 'long-task-2' },
        { duration: 180, startTime: 3000, name: 'long-task-3' },
        { duration: 120, startTime: 4000, name: 'long-task-4' }
      ]
    };

    const issues = (monitor as any)['analyzeIssues']();
    
    // 应该检测到多个问题
    expect(issues.length).toBeGreaterThan(0);
    
    // 检查问题类型
    const issueTypes = issues.map((issue: any) => issue.type);
    expect(issueTypes).toContain('memory_leak');
    expect(issueTypes).toContain('sse_leak');
    expect(issueTypes).toContain('layout_shift');
    expect(issueTypes).toContain('long_task');
    expect(issueTypes).toContain('slow_resource');
  });

  test('应该生成优化建议', () => {
    const mockIssues = [
      { type: 'memory_leak', severity: 'high', description: '内存泄漏', recommendation: '修复内存泄漏' },
      { type: 'sse_leak', severity: 'medium', description: 'SSE连接泄漏', recommendation: '修复SSE连接' }
    ];

    const recommendations = (monitor as any)['generateRecommendations'](mockIssues);
    
    expect(recommendations.length).toBeGreaterThan(0);
    expect(recommendations).toEqual(expect.arrayContaining([
      expect.stringContaining('内存泄漏'),
      expect.stringContaining('SSE连接')
    ]));
  });

  test('单例实例应该可用', () => {
    expect(performanceMonitor).toBeDefined();
    expect(performanceMonitor.startMonitoring).toBeDefined();
    expect(performanceMonitor.stopMonitoring).toBeDefined();
    expect((performanceMonitor as any).generateReport).toBeDefined();
  });
});

// 测试环境设置
beforeAll(() => {
  // 模拟Performance API
  Object.defineProperty(window, 'performance', {
    value: {
      getEntriesByType: (jest as any).fn((type: string) => {
        if (type === 'navigation') {
          return [{
            loadEventEnd: 2000,
            startTime: 0
          }];
        }
        if (type === 'paint') {
          return [
            { name: 'first-contentful-paint', startTime: 1000 }
          ];
        }
        if (type === 'largest-contentful-paint') {
          return [
            { startTime: 1500 }
          ];
        }
        return [];
      }),
      memory: {
        usedJSHeapSize: 100 * 1024 * 1024,
        totalJSHeapSize: 200 * 1024 * 1024,
        jsHeapSizeLimit: 1000 * 1024 * 1024
      }
    },
    writable: true
  });

  // 模拟PerformanceObserver
  (window as any).PerformanceObserver = class MockPerformanceObserver {
    observe = (jest as any).fn();
    disconnect = (jest as any).fn();
    static supportedEntryTypes = ['longtask', 'resource', 'layout-shift'];
  };

  // 模拟EventSource
  (window as any).EventSource = class MockEventSource {
    readyState = 0;
    addEventListener = (jest as any).fn();
    close = (jest as any).fn();
  };
});

afterAll(() => {
  (jest as any).restoreAllMocks();
});
