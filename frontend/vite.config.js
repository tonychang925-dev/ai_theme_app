import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { splitVendorChunkPlugin } from "vite";
export default defineConfig({
    plugins: [react(), splitVendorChunkPlugin()],
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8003",
                changeOrigin: true
            }
        }
    },
    build: {
        // 代码分割配置
        rollupOptions: {
            output: {
                // 手动配置代码分割策略
                manualChunks: function (id) {
                    // 将node_modules中的依赖分组
                    if (id.includes("node_modules")) {
                        // React相关
                        if (id.includes("react") || id.includes("react-dom")) {
                            return "vendor-react";
                        }
                        // 状态管理
                        if (id.includes("zustand")) {
                            return "vendor-state";
                        }
                        // 其他第三方库
                        return "vendor-other";
                    }
                    // 按业务模块分组
                    if (id.includes("src/routes/intel")) {
                        return "chunk-intel";
                    }
                    if (id.includes("src/routes/theme")) {
                        return "chunk-theme";
                    }
                    if (id.includes("src/routes/stock")) {
                        return "chunk-stock";
                    }
                    if (id.includes("src/routes/screener")) {
                        return "chunk-screener";
                    }
                    if (id.includes("src/routes/collection")) {
                        return "chunk-collection";
                    }
                    if (id.includes("src/routes/recap")) {
                        return "chunk-recap";
                    }
                    // 工具和组件
                    if (id.includes("src/utils/") || id.includes("src/components/")) {
                        return "chunk-utils";
                    }
                },
                // 文件命名策略
                chunkFileNames: "assets/[name]-[hash].js",
                entryFileNames: "assets/[name]-[hash].js",
                assetFileNames: "assets/[name]-[hash].[ext]",
            },
        },
        // 构建优化
        target: "es2020",
        minify: "terser",
        terserOptions: {
            compress: {
                drop_console: true,
                drop_debugger: true,
            },
        },
        // 资源优化
        assetsInlineLimit: 4096, // 4kb以下的资源内联
        chunkSizeWarningLimit: 1000, // 块大小警告限制
        reportCompressedSize: false, // 不报告压缩大小
    },
    // 预加载优化
    optimizeDeps: {
        include: ["react", "react-dom", "zustand"],
        exclude: [],
    },
});
