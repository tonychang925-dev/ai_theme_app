import { useEffect, useState, Suspense } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { performanceMonitor } from "./utils/performanceMonitor";
import { resourceOptimizer } from "./utils/resourceOptimizer";
import { PerformanceDebugPanel } from "./components/PerformanceDebugPanel";
import {
  LazyIntelPage,
  LazyStrongStockWatchPage,
  LazyStrongStockWatchDetailPage,
  LazyRecapPage,
  LazyMobileHomePage,
  LazyThemeWorkspacePage,
  LazyStockWorkspacePage,
  LazyStockScreenerPage,
  LazyCollectionPage,
  LazyCollectionDebugPage,
  LazyRealtimeCollectorPage,
  LazyTestPage,
  LazySSETestPanel,
  LazyMemoryLeakTestPanel,
  LoadingFallback,
  LazyLoadErrorBoundary,
  preloadRoute
} from "./utils/codeSplitting";

export function App() {
  const [path, setPath] = useState(window.location.pathname);
  const showPerfPanel =
    process.env.NODE_ENV === 'development' &&
    new URLSearchParams(window.location.search).get('debug_perf') === '1';

  useEffect(() => {
    // 启动性能监控
    performanceMonitor.startMonitoring();

    // 初始化资源加载优化
    resourceOptimizer.initialize();

    // 监听所有URL变化
    const checkUrl = () => {
      const currentPath = window.location.pathname;
      if (currentPath !== path) {
        setPath(currentPath);
      }
    };

    // 监听popstate（用户点击后退/前进）
    const popstateHandler = () => checkUrl();
    window.addEventListener("popstate", popstateHandler);

    // 监听hashchange
    const hashchangeHandler = () => checkUrl();
    window.addEventListener("hashchange", hashchangeHandler);

    // 定期检查URL变化（用于history.replaceState）
    const intervalId = setInterval(checkUrl, 100);

    return () => {
      // 停止性能监控
      performanceMonitor.stopMonitoring();

      window.removeEventListener("popstate", popstateHandler);
      window.removeEventListener("hashchange", hashchangeHandler);
      clearInterval(intervalId);
    };
  }, [path]);


  if (path === "/mobile" || path.startsWith("/mobile/")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载移动端驾驶舱..." />}>
          <LazyMobileHomePage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/themes/")) {
    const subjectKey = path.replace("/themes/", "").trim();
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载主题工作区..." />}>
          <LazyThemeWorkspacePage subjectKey={subjectKey} />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/stocks/")) {
    const stockId = path.replace("/stocks/", "").trim();
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载股票工作区..." />}>
          <LazyStockWorkspacePage stockId={stockId} />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/recap")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载每日回顾..." />}>
          <LazyRecapPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/intel/strong-stocks/watch")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载强势股跟踪..." />}>
          <LazyStrongStockWatchPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/intel/strong-stocks/detail")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载强势股详情..." />}>
          <LazyStrongStockWatchDetailPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/screener-test")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载测试页面..." />}>
          <LazyTestPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/screener")) {
    return (
      <ErrorBoundary>
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载股票筛选器..." />}>
            <LazyStockScreenerPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      </ErrorBoundary>
    );
  }

  if (path.startsWith("/collection-debug")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载收集调试页面..." />}>
          <LazyCollectionDebugPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/realtime-collector")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载实时收集器..." />}>
          <LazyRealtimeCollectorPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/collection")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载数据收集页面..." />}>
          <LazyCollectionPage />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/test/sse")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载SSE测试面板..." />}>
          <LazySSETestPanel />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  if (path.startsWith("/test/memory-leak")) {
    return (
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载内存泄漏测试面板..." />}>
          <LazyMemoryLeakTestPanel />
        </Suspense>
      </LazyLoadErrorBoundary>
    );
  }

  return (
    <>
      <LazyLoadErrorBoundary>
        <Suspense fallback={<LoadingFallback message="加载智能分析页面..." />}>
          <LazyIntelPage />
        </Suspense>
      </LazyLoadErrorBoundary>
      {showPerfPanel && <PerformanceDebugPanel />}
    </>
  );
}
