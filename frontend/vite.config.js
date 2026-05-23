import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
    plugins: [react()],
    server: {
        host: "0.0.0.0", port: 5173,
        proxy: {
            "/api/v1/realtime": {
                target: "http://127.0.0.1:8090",
                changeOrigin: true,
                configure: function (proxy) {
                    proxy.on("proxyReq", function (proxyReq, req) {
                        console.log("[proxy]", req.method, req.url, "->", proxyReq.path);
                    });
                },
            },
            "/api/v1/theme": "http://127.0.0.1:8090",
            "/api/v1/stock": "http://127.0.0.1:8090",
            "/api/v1/pre_market_brief": "http://127.0.0.1:8090",
            "/api/v1/intel": "http://127.0.0.1:8090",
            "/api/v1/db": "http://127.0.0.1:8090",
            "/api/v2": "http://127.0.0.1:8000",
        },
    },
    build: { target: "es2020" },
});
