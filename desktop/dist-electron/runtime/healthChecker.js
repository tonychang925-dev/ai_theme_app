"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.waitForHealthz = waitForHealthz;
exports.waitForReadyz = waitForReadyz;
exports.verifyE2E = verifyE2E;
const http_1 = __importDefault(require("http"));
function httpGet(url, timeoutMs) {
    return new Promise((resolve) => {
        const req = http_1.default.get(url, { timeout: timeoutMs }, (res) => {
            let body = '';
            res.on('data', (chunk) => { body += chunk.toString(); });
            res.on('end', () => {
                resolve({ ok: res.statusCode === 200, statusCode: res.statusCode || 0, body });
            });
        });
        req.on('error', (err) => {
            resolve({ ok: false, statusCode: 0, body: err.message });
        });
        req.on('timeout', () => {
            req.destroy();
            resolve({ ok: false, statusCode: 0, body: 'timeout' });
        });
    });
}
async function waitForHealthz(port, host = '127.0.0.1', timeoutMs = 30000, intervalMs = 1000) {
    const url = `http://${host}:${port}/healthz`;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const result = await httpGet(url, 3000);
        if (result.ok && result.body.includes('ok')) {
            return true;
        }
        await new Promise(r => setTimeout(r, intervalMs));
    }
    return false;
}
async function waitForReadyz(port, host = '127.0.0.1', timeoutMs = 45000, intervalMs = 2000) {
    const url = `http://${host}:${port}/readyz`;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const result = await httpGet(url, 5000);
        if (result.ok) {
            try {
                const parsed = JSON.parse(result.body);
                if (parsed.status && parsed.checks) {
                    return parsed;
                }
            }
            catch {
                // Continue polling
            }
        }
        await new Promise(r => setTimeout(r, intervalMs));
    }
    return null;
}
async function verifyE2E(port, host = '127.0.0.1') {
    // Verify intel feed endpoint
    const url = `http://${host}:${port}/api/v2/recap/defaults`;
    const result = await httpGet(url, 10000);
    return result.ok;
}
//# sourceMappingURL=healthChecker.js.map