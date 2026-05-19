import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { splitVendorChunkPlugin } from "vite";

export default defineConfig({
  plugins: [react(), splitVendorChunkPlugin()],
  server: {
    host: '0.0.0.0', port: 5173, allowedHosts: true,
    proxy: {
      "^/api/v1/.*": {
        target: "http://127.0.0.1:8090",
        changeOrigin: true,
      },
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    strictPort: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("react") || id.includes("react-dom")) return "vendor-react";
            if (id.includes("zustand")) return "vendor-state";
            return "vendor-other";
          }
          if (id.includes("src/routes/intel")) return "chunk-intel";
          if (id.includes("src/routes/theme")) return "chunk-theme";
          if (id.includes("src/routes/stock")) return "chunk-stock";
          if (id.includes("src/routes/screener")) return "chunk-screener";
          if (id.includes("src/routes/collection")) return "chunk-collection";
          if (id.includes("src/routes/recap")) return "chunk-recap";
          if (id.includes("src/utils/") || id.includes("src/components/")) return "chunk-utils";
        },
        chunkFileNames: "assets/[name]-[hash].js",
        entryFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash].[ext]",
      },
    },
    target: "es2020", minify: "terser",
    terserOptions: { compress: { drop_console: true, drop_debugger: true } },
    assetsInlineLimit: 4096, chunkSizeWarningLimit: 1000, reportCompressedSize: false,
  },
  optimizeDeps: { include: ["react", "react-dom", "zustand"], exclude: [] },
});
