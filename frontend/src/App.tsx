import { useEffect, useState, Suspense } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { performanceMonitor } from "./utils/performanceMonitor";
import { resourceOptimizer } from "./utils/resourceOptimizer";
import { PerformanceDebugPanel } from "./components/PerformanceDebugPanel";
import { AuthProvider, useAuth } from "./routes/auth/AuthProvider";
import {
  LazyIntelPage,
  LazyStrongStockWatchPage,
  LazyStrongStockWatchDetailPage,
  LazyRecapPage,
  LazyPreMarketBriefPage,
  LazyMobileHomePage,
  LazyMobileRecapPage,
  LazyMobileScreenerPage,
  LazyMobileIntelPage,
  LazyMobileNewsRecommendPage,
  LazyMobileProfilePage,
  LazyLoginPage,
  LazyAdminPage,
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
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, isAdmin } = useAuth();
  const path = window.location.pathname;

  if (loading) {
    return <LoadingFallback message="验证登录状态..." />;
  }

  // 已登录用户访问 /login → 允许查看（可切换账号或直接进入）

  // 未登录用户 → 重定向到 /login（携带 returnUrl）
  if (!user && path !== "/login") {
    const returnUrl = encodeURIComponent(path + window.location.search);
    window.location.replace(`/login?returnUrl=${returnUrl}`);
    return null;
  }

  // /admin 路由 → 要求 role=admin
  if (path === "/admin" && !isAdmin) {
    window.location.replace("/");
    return null;
  }

  return <>{children}</>;
}

function AppRoutes() {
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

  return (
    <AuthGate>
      {path === "/login" && (
        <Suspense fallback={<LoadingFallback message="加载登录..." />}>
          <LazyLoginPage />
        </Suspense>
      )}
      {path === "/admin" && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载用户管理..." />}>
            <LazyAdminPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {(path === "/mobile" || path.startsWith("/mobile/")) && (
        <>
          {path === "/mobile/recap" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载移动端复盘..." />}>
                <LazyMobileRecapPage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
          {path === "/mobile/screener" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载AI选股..." />}>
                <LazyMobileScreenerPage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
          {path === "/mobile/profile" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载账户..." />}>
                <LazyMobileProfilePage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
          {path === "/mobile/intel" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载实时情报..." />}>
                <LazyMobileIntelPage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
          {path === "/mobile/news-recommend" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载新闻荐股..." />}>
                <LazyMobileNewsRecommendPage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
          {path === "/mobile" && (
            <LazyLoadErrorBoundary>
              <Suspense fallback={<LoadingFallback message="加载移动端驾驶舱..." />}>
                <LazyMobileHomePage />
              </Suspense>
            </LazyLoadErrorBoundary>
          )}
        </>
      )}

      {path.startsWith("/themes/") && (() => {
        const subjectKey = path.replace("/themes/", "").trim();
        return (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<LoadingFallback message="加载主题工作区..." />}>
              <LazyThemeWorkspacePage subjectKey={subjectKey} />
            </Suspense>
          </LazyLoadErrorBoundary>
        );
      })()}

      {path.startsWith("/stocks/") && (() => {
        const stockId = path.replace("/stocks/", "").trim();
        return (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<LoadingFallback message="加载股票工作区..." />}>
              <LazyStockWorkspacePage stockId={stockId} />
            </Suspense>
          </LazyLoadErrorBoundary>
        );
      })()}

      {path.startsWith("/recap") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载每日回顾..." />}>
            <LazyRecapPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/pre-market-brief") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载盘前必读..." />}>
            <LazyPreMarketBriefPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/intel/strong-stocks/watch") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载强势股跟踪..." />}>
            <LazyStrongStockWatchPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/intel/strong-stocks/detail") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载强势股详情..." />}>
            <LazyStrongStockWatchDetailPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/screener-test") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载测试页面..." />}>
            <LazyTestPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/screener") && !path.startsWith("/screener-test") && (
        <ErrorBoundary>
          <LazyLoadErrorBoundary>
            <Suspense fallback={<LoadingFallback message="加载股票筛选器..." />}>
              <LazyStockScreenerPage />
            </Suspense>
          </LazyLoadErrorBoundary>
        </ErrorBoundary>
      )}

      {path.startsWith("/collection-debug") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载收集调试页面..." />}>
            <LazyCollectionDebugPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/realtime-collector") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载实时收集器..." />}>
            <LazyRealtimeCollectorPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/collection") && !path.startsWith("/collection-debug") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载数据收集页面..." />}>
            <LazyCollectionPage />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/test/sse") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载SSE测试面板..." />}>
            <LazySSETestPanel />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {path.startsWith("/test/memory-leak") && (
        <LazyLoadErrorBoundary>
          <Suspense fallback={<LoadingFallback message="加载内存泄漏测试面板..." />}>
            <LazyMemoryLeakTestPanel />
          </Suspense>
        </LazyLoadErrorBoundary>
      )}

      {/* 默认路由：Intel 首页 */}
      {(path === "/" || path === "/intel") && (
        <>
          <LazyLoadErrorBoundary>
            <Suspense fallback={<LoadingFallback message="加载智能分析页面..." />}>
              <LazyIntelPage />
            </Suspense>
          </LazyLoadErrorBoundary>
          {showPerfPanel && <PerformanceDebugPanel />}
        </>
      )}
    </AuthGate>
  );
}
