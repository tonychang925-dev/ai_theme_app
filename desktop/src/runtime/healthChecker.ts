import http from 'http';

export interface HealthResult {
  ok: boolean;
  statusCode: number;
  body: string;
}

export interface ReadyzResult {
  status: string; // 'ok' | 'degraded' | 'failed'
  checks: Record<string, string>;
  fatal: string[];
  degraded: string[];
}

function httpGet(url: string, timeoutMs: number): Promise<HealthResult> {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = '';
      res.on('data', (chunk: Buffer) => { body += chunk.toString(); });
      res.on('end', () => {
        resolve({ ok: res.statusCode === 200, statusCode: res.statusCode || 0, body });
      });
    });
    req.on('error', (err: Error) => {
      resolve({ ok: false, statusCode: 0, body: err.message });
    });
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, statusCode: 0, body: 'timeout' });
    });
  });
}

export async function waitForHealthz(
  port: number,
  host: string = '127.0.0.1',
  timeoutMs: number = 30000,
  intervalMs: number = 1000,
): Promise<boolean> {
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

export async function waitForReadyz(
  port: number,
  host: string = '127.0.0.1',
  timeoutMs: number = 45000,
  intervalMs: number = 2000,
): Promise<ReadyzResult | null> {
  const url = `http://${host}:${port}/readyz`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await httpGet(url, 5000);
    if (result.ok) {
      try {
        const parsed: ReadyzResult = JSON.parse(result.body);
        if (parsed.status && parsed.checks) {
          return parsed;
        }
      } catch {
        // Continue polling
      }
    }
    await new Promise(r => setTimeout(r, intervalMs));
  }
  return null;
}

export async function verifyE2E(port: number, host: string = '127.0.0.1'): Promise<boolean> {
  // Verify intel feed endpoint
  const url = `http://${host}:${port}/api/v2/recap/defaults`;
  const result = await httpGet(url, 10000);
  return result.ok;
}
