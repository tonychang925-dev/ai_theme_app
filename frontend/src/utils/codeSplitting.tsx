import React, { lazy, type ComponentType } from 'react';

type LazyModule<T extends ComponentType<any>> = { default: T };

interface LazyLoadConfig {
  name: unknown;
  timeout?: number;
  fallback?: ComponentType;
}

const safeText = (value: unknown, fallback = 'unknown'): string => {
  if (value == null) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  try {
    const json = JSON.stringify(value);
    if (json && json !== '{}') return json;
  } catch {
    // ignore
  }
  try {
    return String(value);
  } catch {
    return fallback;
  }
};

export function createLazyComponent<T extends ComponentType<any>>(
  importFn: () => Promise<LazyModule<T>>,
  config: LazyLoadConfig,
): React.LazyExoticComponent<T> {
  const componentName = safeText(config.name, 'component');
  const timeoutMs = Math.max(1000, config.timeout ?? 10000);
  const FallbackComponent = config.fallback;

  const wrappedImport = () =>
    Promise.race([
      importFn(),
      new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error(`组件加载超时: ${componentName}`)), timeoutMs);
      }),
    ]);

  return lazy(() =>
    wrappedImport().catch((error: unknown) => {
      const errorMessage =
        error && typeof error === 'object' && 'message' in (error as Record<string, unknown>)
          ? safeText((error as Record<string, unknown>).message, '未知错误')
          : safeText(error, '未知错误');

      console.error(`组件加载失败: ${componentName}`, error);

      if (FallbackComponent) {
        return { default: FallbackComponent as T };
      }

      const ErrorComponent: ComponentType = () => (
        <div style={{ padding: '20px', color: 'red' }}>
          <h3>{`组件加载失败: ${componentName}`}</h3>
          <p>{errorMessage}</p>
        </div>
      );

      return { default: ErrorComponent as T };
    }),
  );
}

export const LoadingFallback: React.FC<{ message?: string }> = ({ message = '加载中...' }) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '200px',
      color: '#666',
      fontSize: '14px',
    }}
  >
    <div style={{ textAlign: 'center' }}>
      <div style={{ marginBottom: '10px' }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            margin: '0 auto',
            border: '4px solid #f3f3f3',
            borderTop: '4px solid #3498db',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
      <p>{safeText(message, '加载中...')}</p>
    </div>
  </div>
);

export class LazyLoadErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean; error?: unknown }
> {
  constructor(props: { children: React.ReactNode; fallback?: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: unknown) {
    return { hasError: true, error };
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo) {
    console.error('懒加载组件错误:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const errorMessage =
        this.state.error && typeof this.state.error === 'object' && 'message' in (this.state.error as Record<string, unknown>)
          ? safeText((this.state.error as Record<string, unknown>).message, '未知错误')
          : safeText(this.state.error, '未知错误');

      return (
        <div style={{ padding: '20px', border: '1px solid #ff6b6b', borderRadius: '4px', background: '#fff5f5' }}>
          <h3 style={{ color: '#ff6b6b', marginBottom: '10px' }}>组件加载失败</h3>
          <p style={{ color: '#666', fontSize: '14px' }}>{errorMessage}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: undefined })}
            style={{
              marginTop: '10px',
              padding: '8px 16px',
              background: '#3498db',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            重试
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

const routeChunks = {
  main: {
    intel: () => import('../routes/intel/IntelPage').then((m) => ({ default: m.IntelPage })),
    recap: () => import('../routes/recap/RecapPage').then((m) => ({ default: m.RecapPage })),
  },
  theme: {
    workspace: () => import('../routes/theme/ThemeWorkspacePage').then((m) => ({ default: m.ThemeWorkspacePage })),
  },
  stock: {
    workspace: () => import('../routes/stock/StockWorkspacePage').then((m) => ({ default: m.StockWorkspacePage })),
    screener: () => import('../routes/screener/StockScreenerPage').then((m) => ({ default: m.StockScreenerPage })),
    screenerTest: () => import('../routes/screener/TestPage').then((m) => ({ default: m.TestPage })),
  },
  collection: {
    main: () => import('../routes/collection/CollectionPage').then((m) => ({ default: m.CollectionPage })),
    debug: () => import('../routes/collection/CollectionDebugPage').then((m) => ({ default: m.CollectionDebugPage })),
    realtime: () => import('../routes/collection/RealtimeCollectorPage').then((m) => ({ default: m.RealtimeCollectorPage })),
  },
  test: {
    sse: () => import('../components/SSETestPanel').then((m) => ({ default: m.SSETestPanel })),
    memoryLeak: () => import('../components/MemoryLeakTestPanel').then((m) => ({ default: m.MemoryLeakTestPanel })),
  },
} as const;

export function preloadRoute(routeKey: string): Promise<void> {
  const keys = routeKey.split('.');
  let current: unknown = routeChunks;

  for (const key of keys) {
    if (current && typeof current === 'object' && key in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[key];
    } else {
      return Promise.reject(new Error(`路由不存在: ${safeText(routeKey)}`));
    }
  }

  if (typeof current === 'function') {
    return (current as () => Promise<unknown>)().then(() => undefined);
  }

  return Promise.reject(new Error(`无效的路由配置: ${safeText(routeKey)}`));
}

export function preloadRoutes(routeKeys: string[]): Promise<void[]> {
  return Promise.all(routeKeys.map(preloadRoute));
}

export const LazyIntelPage = createLazyComponent(routeChunks.main.intel, { name: 'IntelPage', timeout: 5000 });
export const LazyRecapPage = createLazyComponent(routeChunks.main.recap, { name: 'RecapPage', timeout: 5000 });
export const LazyThemeWorkspacePage = createLazyComponent(routeChunks.theme.workspace, { name: 'ThemeWorkspacePage', timeout: 5000 });
export const LazyStockWorkspacePage = createLazyComponent(routeChunks.stock.workspace, { name: 'StockWorkspacePage', timeout: 5000 });
export const LazyStockScreenerPage = createLazyComponent(routeChunks.stock.screener, { name: 'StockScreenerPage', timeout: 5000 });
export const LazyCollectionPage = createLazyComponent(routeChunks.collection.main, { name: 'CollectionPage', timeout: 5000 });
export const LazyCollectionDebugPage = createLazyComponent(routeChunks.collection.debug, { name: 'CollectionDebugPage', timeout: 5000 });
export const LazyRealtimeCollectorPage = createLazyComponent(routeChunks.collection.realtime, { name: 'RealtimeCollectorPage', timeout: 5000 });
export const LazyTestPage = createLazyComponent(routeChunks.stock.screenerTest, { name: 'TestPage', timeout: 5000 });
export const LazySSETestPanel = createLazyComponent(routeChunks.test.sse, { name: 'SSETestPanel', timeout: 5000 });
export const LazyMemoryLeakTestPanel = createLazyComponent(routeChunks.test.memoryLeak, { name: 'MemoryLeakTestPanel', timeout: 5000 });
