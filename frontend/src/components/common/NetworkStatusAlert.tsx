import React, { useState, useEffect } from 'react';

interface NetworkStatusAlertProps {
  onRetry?: () => void;
  suppress?: boolean;
}

export function NetworkStatusAlert({ onRetry, suppress = false }: NetworkStatusAlertProps) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [showAlert, setShowAlert] = useState(false);
  const [lastErrorTime, setLastErrorTime] = useState<number | null>(null);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setShowAlert(false);
      setConsecutiveFailures(0);
    };

    const handleOffline = () => {
      setIsOnline(false);
      setShowAlert(true);
    };

    // 监听网络状态变化
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // 定期检查API连接
    const checkApiConnection = async () => {
      if (document.visibilityState !== 'visible') return;
      if (suppress) return;

      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch('/api/v2/stock-screener/strategies', {
          method: 'GET',
          cache: 'no-store',
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          throw new Error(`API响应状态: ${response.status}`);
        }
        setConsecutiveFailures(0);
        setShowAlert(false);
        setLastErrorTime(null);
      } catch (error) {
        if (error instanceof Error) {
          if (error.name === 'AbortError') {
            // 健康检查超时通常是临时拥塞，不直接弹告警
            return;
          }
          console.warn('API连接检查失败:', error.message);
        }
        setConsecutiveFailures((prev) => {
          const next = prev + 1;
          if (next >= 2) {
            setShowAlert(true);
            setLastErrorTime(Date.now());
          }
          return next;
        });
      }
    };

    // 每90秒检查一次，避免干扰用户操作
    const intervalId = setInterval(checkApiConnection, 90000);

    // 延迟初始检查，避免首屏加载期间误报
    const initialCheckTimeout = setTimeout(checkApiConnection, 12000);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      clearInterval(intervalId);
      clearTimeout(initialCheckTimeout);
    };
  }, [suppress]);

  useEffect(() => {
    if (suppress) {
      setShowAlert(false);
    }
  }, [suppress]);

  if (!showAlert) return null;

  const handleRetry = () => {
    if (onRetry) {
      onRetry();
    } else {
      window.location.reload();
    }
  };

  const getErrorMessage = () => {
    if (!isOnline) {
      return '网络连接已断开，请检查网络设置';
    }

    if (lastErrorTime) {
      const minutesAgo = Math.floor((Date.now() - lastErrorTime) / 60000);
      if (minutesAgo > 0) {
        return `服务器连接异常（${minutesAgo}分钟前开始），请检查服务器状态`;
      }
    }

    return '服务器连接异常，请检查网络连接或稍后重试';
  };

  return (
    <div className="fixed top-4 right-4 z-50 max-w-md">
      <div className="workspace-card collection-modal" style={{ borderColor: '#d96b6b', background: '#1a0f0f' }}>
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-6 w-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.502 0L4.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <h3 className="text-sm font-medium text-red-300">连接问题</h3>
            <div className="mt-1 text-sm text-red-200">
              <p>{getErrorMessage()}</p>
            </div>
            <div className="mt-3 flex space-x-3">
              <button
                type="button"
                onClick={handleRetry}
                className="tag tag-button tag-active"
              >
                重试连接
              </button>
              <button
                type="button"
                onClick={() => setShowAlert(false)}
                className="tag tag-button"
              >
                忽略
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
