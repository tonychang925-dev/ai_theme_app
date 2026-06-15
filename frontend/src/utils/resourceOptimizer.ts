/**
 * 前端资源加载优化器
 * 优化图片、字体、第三方库的加载策略
 */

import { purgeAllApiCacheEntries, purgeApiCacheForUrl, safeSetApiCache, shouldBypassApiCache } from "./apiCache";

interface ResourceOptimizationConfig {
  // 图片优化配置
  imageOptimization: {
    lazyLoading: boolean;
    placeholder: boolean;
    responsiveImages: boolean;
    webpSupport: boolean;
    quality: number; // 0-100
  };

  // 字体优化配置
  fontOptimization: {
    preloadCriticalFonts: boolean;
    fontDisplay: 'auto' | 'block' | 'swap' | 'fallback' | 'optional';
    subsetFonts: boolean;
  };

  // 第三方库优化配置
  libraryOptimization: {
    deferNonCritical: boolean;
    dynamicImport: boolean;
    preconnect: string[]; // 需要预连接的域名
  };

  // 缓存策略
  caching: {
    staticAssets: number; // 静态资源缓存时间（小时）
    apiResponses: number; // API响应缓存时间（分钟）
    localStorage: boolean; // 是否使用localStorage缓存
  };
}

class ResourceOptimizer {
  private config: ResourceOptimizationConfig;
  private fetchPatched = false;

  constructor(config?: Partial<ResourceOptimizationConfig>) {
    this.config = {
      imageOptimization: {
        lazyLoading: true,
        placeholder: true,
        responsiveImages: true,
        webpSupport: true,
        quality: 85,
        ...config?.imageOptimization
      },
      fontOptimization: {
        preloadCriticalFonts: true,
        fontDisplay: 'swap',
        subsetFonts: false,
        ...config?.fontOptimization
      },
      libraryOptimization: {
        deferNonCritical: true,
        dynamicImport: true,
        preconnect: ['fonts.googleapis.com', 'fonts.gstatic.com'],
        ...config?.libraryOptimization
      },
      caching: {
        staticAssets: 24, // 24小时
        apiResponses: 5, // 5分钟
        localStorage: true,
        ...config?.caching
      }
    };
  }

  /**
   * 初始化资源优化
   */
  initialize(): void {
    if (process.env.NODE_ENV === 'development') {
      console.log('🚀 初始化资源加载优化器');
    }

    this.setupImageOptimization();
    this.setupFontOptimization();
    this.setupLibraryOptimization();
    this.setupCaching();
    this.setupPreconnect();

    if (process.env.NODE_ENV === 'development') {
      console.log('✅ 资源加载优化器初始化完成');
    }
  }

  /**
   * 设置图片优化
   */
  private setupImageOptimization(): void {
    if (!this.config.imageOptimization.lazyLoading) return;

    // 监听图片加载
    document.addEventListener('DOMContentLoaded', () => {
      const images = document.querySelectorAll('img[data-src]');

      const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target as HTMLImageElement;
            const src = img.getAttribute('data-src');

            if (src) {
              img.src = src;
              img.removeAttribute('data-src');
            }

            imageObserver.unobserve(img);
          }
        });
      });

      images.forEach(img => imageObserver.observe(img));
    });
  }

  /**
   * 设置字体优化
   */
  private setupFontOptimization(): void {
    if (!this.config.fontOptimization.preloadCriticalFonts) return;

    // 预加载关键字体
    const preloadLinks: string[] = [
      // 可以添加需要预加载的字体
    ];

    preloadLinks.forEach(fontUrl => {
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'font';
      link.href = fontUrl;
      link.crossOrigin = 'anonymous';
      document.head.appendChild(link);
    });
  }

  /**
   * 设置第三方库优化
   */
  private setupLibraryOptimization(): void {
    if (!this.config.libraryOptimization.deferNonCritical) return;

    // 延迟加载非关键脚本
    const scripts = document.querySelectorAll('script[data-defer]');
    scripts.forEach(script => {
      script.setAttribute('defer', '');
    });
  }

  /**
   * 设置缓存策略
   */
  private setupCaching(): void {
    if (!this.config.caching.localStorage) return;
    if (process.env.NODE_ENV === 'development') return;
    if (this.fetchPatched) return;

    // 强制清理旧的 API 响应缓存，避免旧复盘快照/超大响应污染当前页面。
    try {
      purgeAllApiCacheEntries(localStorage);
    } catch {
      // ignore
    }

    // 设置API响应缓存
    const originalFetch = window.fetch.bind(window) as typeof window.fetch;
    const optimizer = this;
    const patchedFetch = (async (...args: Parameters<typeof window.fetch>) => {
      const [url, options] = args;
      const urlText =
        typeof url === "string" ? url :
        url instanceof URL ? url.toString() :
        url instanceof Request ? url.url :
        String(url);
      const cacheKey = `api_cache_${urlText}_${JSON.stringify(options || {})}`;

      if (shouldBypassApiCache(urlText)) {
        purgeApiCacheForUrl(localStorage, urlText);
        return originalFetch(...args);
      }

      // 检查是否有缓存
      if (optimizer.config.caching.apiResponses > 0) {
        try {
          const cached = localStorage.getItem(cacheKey);
          if (cached) {
            const parsed = JSON.parse(cached);
            const timestamp = Number(parsed?.timestamp);
            if (Number.isFinite(timestamp)) {
              const age = (Date.now() - timestamp) / (1000 * 60); // 分钟
              if (age < optimizer.config.caching.apiResponses) {
                return new Response(JSON.stringify(parsed.data), {
                  status: 200,
                  headers: { 'Content-Type': 'application/json' }
                });
              }
            }
          }
        } catch {
          // ignore malformed cache entries and fall through to network
        }
      }

      // 执行实际请求
      const response = await originalFetch(...args);
      const clonedResponse = response.clone();

      // 缓存响应
      if (response.ok && optimizer.config.caching.apiResponses > 0) {
        clonedResponse.json().then(data => {
          safeSetApiCache(localStorage, cacheKey, {
            data,
            timestamp: Date.now()
          });
        });
      }

      return response;
    }) as typeof window.fetch;
    window.fetch = patchedFetch;
    this.fetchPatched = true;
  }

  /**
   * 设置预连接
   */
  private setupPreconnect(): void {
    this.config.libraryOptimization.preconnect.forEach(domain => {
      const link = document.createElement('link');
      link.rel = 'preconnect';
      link.href = `https://${domain}`;
      link.crossOrigin = 'anonymous';
      document.head.appendChild(link);
    });
  }

  /**
   * 优化图片元素
   */
  optimizeImageElement(img: HTMLImageElement): void {
    const config = this.config.imageOptimization;

    // 添加懒加载属性
    if (config.lazyLoading && !img.loading) {
      img.loading = 'lazy';
    }

    // 添加占位符
    if (config.placeholder && !img.hasAttribute('data-placeholder')) {
      img.setAttribute('data-placeholder', 'true');

      // 设置低质量占位图
      const originalSrc = img.src;
      img.src = this.createPlaceholderImage(img.width, img.height);

      img.onload = () => {
        // 延迟加载原图
        setTimeout(() => {
          const tempImg = new Image();
          tempImg.onload = () => {
            img.src = originalSrc;
          };
          tempImg.src = originalSrc;
        }, 100);
      };
    }

    // 添加响应式图片支持
    if (config.responsiveImages && img.srcset) {
      img.sizes = '(max-width: 768px) 100vw, 50vw';
    }
  }

  /**
   * 创建占位图
   */
  private createPlaceholderImage(width: number, height: number): string {
    // 创建一个简单的SVG占位图
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <rect width="100%" height="100%" fill="#f0f0f0"/>
      <text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="#999" font-size="14">加载中...</text>
    </svg>`;

    return `data:image/svg+xml;base64,${btoa(svg)}`;
  }

  /**
   * 获取优化配置
   */
  getConfig(): ResourceOptimizationConfig {
    return { ...this.config };
  }

  /**
   * 更新配置
   */
  updateConfig(newConfig: Partial<ResourceOptimizationConfig>): void {
    this.config = {
      ...this.config,
      ...newConfig,
      imageOptimization: {
        ...this.config.imageOptimization,
        ...newConfig.imageOptimization
      },
      fontOptimization: {
        ...this.config.fontOptimization,
        ...newConfig.fontOptimization
      },
      libraryOptimization: {
        ...this.config.libraryOptimization,
        ...newConfig.libraryOptimization
      },
      caching: {
        ...this.config.caching,
        ...newConfig.caching
      }
    };

    if (process.env.NODE_ENV === 'development') {
      console.log('⚙️ 资源优化配置已更新', this.config);
    }
  }

  /**
   * 生成性能报告
   */
  generatePerformanceReport(): {
    imageOptimization: boolean;
    fontOptimization: boolean;
    libraryOptimization: boolean;
    cachingEnabled: boolean;
    recommendations: string[];
  } {
    const recommendations: string[] = [];

    // 检查图片优化
    const images = document.querySelectorAll('img');
    const lazyLoadedImages = Array.from(images).filter(img =>
      img.loading === 'lazy' || img.hasAttribute('data-src')
    );

    if (lazyLoadedImages.length < images.length * 0.8) {
      recommendations.push('建议为更多图片启用懒加载');
    }

    // 检查字体优化
    const fonts = document.querySelectorAll('link[rel*="font"], style[font-face]');
    if (fonts.length === 0) {
      recommendations.push('未检测到字体优化，考虑添加字体预加载');
    }

    // 检查缓存使用
    const apiCacheKeys = Object.keys(localStorage).filter(key =>
      key.startsWith('api_cache_')
    );

    if (apiCacheKeys.length === 0 && this.config.caching.apiResponses > 0) {
      recommendations.push('API缓存未使用，检查缓存配置');
    }

    return {
      imageOptimization: this.config.imageOptimization.lazyLoading,
      fontOptimization: this.config.fontOptimization.preloadCriticalFonts,
      libraryOptimization: this.config.libraryOptimization.deferNonCritical,
      cachingEnabled: this.config.caching.localStorage,
      recommendations
    };
  }
}

// 创建默认实例
const resourceOptimizer = new ResourceOptimizer();

// 开发环境自动初始化
if (process.env.NODE_ENV === 'development') {
  window.addEventListener('load', () => {
    setTimeout(() => {
      resourceOptimizer.initialize();
    }, 1000);
  });
}

export { ResourceOptimizer, resourceOptimizer };
export type { ResourceOptimizationConfig };
