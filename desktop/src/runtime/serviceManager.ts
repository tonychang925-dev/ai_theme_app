import * as fs from 'fs';
import * as path from 'path';
import http from 'http';
import { app } from 'electron';
import { loadEnv, generateJwtSecret, persistEnvLocal } from './envLoader';
import { runDoctor } from './dependencyDoctor';
import { allocatePorts, clearStalePids, savePids } from './portManager';
import { spawnCommand, killAllManaged } from './processTree';
import { waitForHealthz, waitForReadyz, verifyE2E } from './healthChecker';
import { logInfo, logError, getLogDir } from './logManager';

export interface ServiceStatus {
  name: string;
  running: boolean;
  port: number;
  pid?: number;
}

let managedProcesses: Map<string, { pid?: number; port: number }> = new Map();
let redisStartedByUs: boolean = false;
let _cdProjectRoot: string | null = null;

export async function startAll(projectRoot: string): Promise<{
  success: boolean;
  webPort: number;
  spsPort: number;
  cdpPort: number;
  doctorPassed: boolean;
  doctorChecks: import('./dependencyDoctor').CheckResult[] | null;
  readyzResult: any;
}> {
  _cdProjectRoot = projectRoot;
  const userDataDir = path.dirname(getLogDir()); // ~/Library/Application Support/AI投资助理
  logInfo('ServiceManager: ===== Starting all services =====');

  // 1. Load env
  const env = loadEnv(projectRoot);
  const logDir = getLogDir();

  // Inject desktop runtime paths
  env['DESKTOP_LOG_DIR'] = logDir;
  env['DESKTOP_USER_DATA'] = userDataDir;

  // 2. Dependency doctor
  const doctor = await runDoctor(projectRoot, env);
  logInfo(`ServiceManager: doctor passed=${doctor.pass}`);
  if (!doctor.pass) {
    logError('ServiceManager: dependency doctor failed, check diagnostics');
    return { success: false, webPort: 0, spsPort: 0, cdpPort: 0, doctorPassed: false, doctorChecks: doctor.checks, readyzResult: null };
  }

  // 3. Clear stale PIDs from previous runs
  clearStalePids();

  // 4. Ensure Redis (best effort)
  // Redis is handled in dependencyDoctor already

  // 5. Allocate ports
  const ports = allocatePorts({
    web: parseInt(env['WEB_PORT'] || '8000', 10),
    sps: parseInt(env['SPS_PORT'] || '8090', 10),
    cdp: parseInt(env['CDP_PORT'] || '8095', 10),
  });

  // 6. Determine Python paths
  const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
  const condaPython = '/opt/miniconda3/envs/theme_matcher_env/bin/python';

  // 7. Set env vars that services will read
  // CRITICAL: ensure JWT_SECRET is never empty — backend raises RuntimeError without it
  const jwtSecret = env['JWT_SECRET'] || generateJwtSecret();
  if (!env['JWT_SECRET']) {
    persistEnvLocal({ JWT_SECRET: jwtSecret });
  }
  const serviceEnv: Record<string, string> = {
    ...env,
    'JWT_SECRET': jwtSecret,
    'WEB_PORT': String(ports.web),
    'SPS_PORT': String(ports.sps),
    'CDP_PORT': String(ports.cdp),
    'STOCK_PROCESSING_READ_BASE_URL': `http://127.0.0.1:${ports.sps}`,
    'WEB_APP_READ_MODE': 'http',
    'HF_HUB_OFFLINE': '1',
    'PYTHONPATH': projectRoot,
  };

  // Set FRONTEND_DIST_DIR for web_app_service
  // V1-dev: projectRoot/frontend/dist
  // V1-app: extraResources path inside .app bundle
  if (!serviceEnv['FRONTEND_DIST_DIR']) {
    if (app.isPackaged) {
      serviceEnv['FRONTEND_DIST_DIR'] = path.join(process.resourcesPath, 'frontend', 'dist');
    } else {
      serviceEnv['FRONTEND_DIST_DIR'] = path.join(projectRoot, 'frontend', 'dist');
    }
  }

  // 8. Start SPS
  logInfo(`ServiceManager: starting stock_processing_service on port ${ports.sps}`);
  const spsProc = spawnCommand(condaPython, [
    '-m', 'uvicorn',
    'stock_processing_service.api_app:app',
    '--host', '127.0.0.1',
    '--port', String(ports.sps),
  ], {
    cwd: projectRoot,
    env: { ...serviceEnv, 'REDIS_URL': serviceEnv['REDIS_URL'] || 'redis://localhost:6379/0' },
    logName: 'stock_processing_service.log',
  });
  managedProcesses.set('sps', { pid: spsProc.pid, port: ports.sps });

  logInfo('ServiceManager: waiting for SPS healthz...');
  const spsHealthy = await waitForHealthz(ports.sps);
  if (!spsHealthy) {
    logError('ServiceManager: SPS failed to become healthy');
    await stopAll();
    return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult: null };
  }
  logInfo('ServiceManager: SPS healthy');

  // 9. Start web_app_service
  logInfo(`ServiceManager: starting web_app_service on port ${ports.web}`);
  const webProc = spawnCommand(venvPython, [
    '-m', 'uvicorn',
    'web_app_service.main:app',
    '--host', '0.0.0.0',
    '--port', String(ports.web),
  ], {
    cwd: projectRoot,
    env: {
      ...serviceEnv,
      'STOCK_PROCESSING_READ_BASE_URL': `http://127.0.0.1:${ports.sps}`,
      'FRONTEND_DIST_DIR': serviceEnv['FRONTEND_DIST_DIR'],
    },
    logName: 'web_app_service.log',
  });
  managedProcesses.set('web', { pid: webProc.pid, port: ports.web });

  logInfo('ServiceManager: waiting for web_app healthz...');
  const webHealthy = await waitForHealthz(ports.web, '127.0.0.1');
  if (!webHealthy) {
    logError('ServiceManager: web_app_service failed to become healthy');
    await stopAll();
    return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult: null };
  }
  logInfo('ServiceManager: web_app healthy');

  // 10. Wait for readyz
  logInfo('ServiceManager: waiting for readyz...');
  const readyzResult = await waitForReadyz(ports.web);
  if (!readyzResult || readyzResult.status === 'failed') {
    logError(`ServiceManager: readyz failed status=${readyzResult?.status}`);
    // Don't stop — degraded still allows the app to show
    if (readyzResult?.status === 'failed') {
      await stopAll();
      return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult };
    }
  }

  // 11. Optional: CDP service (default off)
  let cdpStarted = false;
  const enableCdp = env['ENABLE_CDP'] === '1' || env['ENABLE_CDP'] === 'true';
  if (enableCdp) {
    logInfo(`ServiceManager: starting jyhf_cdp_service on port ${ports.cdp}`);
    const cdpProc = spawnCommand(venvPython, [
      '-m', 'uvicorn',
      'services.jyhf_cdp_service.app:app',
      '--host', '127.0.0.1',
      '--port', String(ports.cdp),
    ], {
      cwd: projectRoot,
      env: serviceEnv,
      logName: 'jyhf_cdp_service.log',
    });
    managedProcesses.set('cdp', { pid: cdpProc.pid, port: ports.cdp });
    cdpStarted = true;
  }

  // 12. Verify e2e
  const e2eOk = await verifyE2E(ports.web);
  logInfo(`ServiceManager: e2e verification ${e2eOk ? 'OK' : 'FAILED'}`);

  // Save PIDs
  const pidRecords = Array.from(managedProcesses.entries())
    .filter(([, v]) => v.pid)
    .map(([k, v]) => ({
      serviceName: k,
      pid: v.pid!,
      port: v.port,
      startedAt: new Date().toISOString(),
    }));
  savePids(pidRecords);

  logInfo('ServiceManager: ===== All services started =====');
  return {
    success: true,
    webPort: ports.web,
    spsPort: ports.sps,
    cdpPort: ports.cdp,
    doctorPassed: doctor.pass,
    doctorChecks: doctor.checks,
    readyzResult,
  };
}

export async function stopAll(): Promise<void> {
  logInfo('ServiceManager: ===== Stopping all services =====');

  // Stop CDP service (started by BFF manager, not in managed process tree)
  await _stopCdpService();

  await killAllManaged(5000);

  // Only stop Redis if we started it
  if (redisStartedByUs) {
    logInfo('ServiceManager: stopping Redis (started by us)');
    try {
      const { execSync } = require('child_process');
      execSync('brew services stop redis', { timeout: 10000 });
    } catch {
      logError('ServiceManager: failed to stop Redis');
    }
  }

  // Clear PID state (keep logs)
  const pidsPath = path.join(path.dirname(getLogDir()), 'runtime', 'pids.json');
  try {
    fs.writeFileSync(pidsPath, '[]', 'utf-8');
  } catch {}

  managedProcesses.clear();
  logInfo('ServiceManager: ===== All services stopped =====');
}

async function _stopCdpService(): Promise<void> {
  const cdpPort = 8095;

  // 1. Try graceful HTTP stop (collector + uvicorn)
  try {
    await _httpPost('127.0.0.1', cdpPort, '/collector/stop', 3000);
    logInfo('ServiceManager: CDP collector stop requested');
  } catch {
    // Collector may not be running
  }

  // 2. Find and kill whatever is listening on the CDP port
  let pid: number | null = null;

  // Port-based lookup is most reliable (doesn't depend on PID file)
  pid = _findPidByPort(cdpPort);

  // Fallback: try PID file
  if (!pid && _cdProjectRoot) {
    const cdpPidFile = path.join(_cdProjectRoot, 'tmp', 'realtime', 'jyhf_cdp_service', 'service.pid');
    try {
      const filePid = parseInt(fs.readFileSync(cdpPidFile, 'utf-8').trim(), 10);
      if (filePid && !isNaN(filePid)) {
        // Verify the PID is actually the CDP service
        try { process.kill(filePid, 0); pid = filePid; } catch {}
      }
    } catch {}
    // Clean up PID file regardless
    try { fs.unlinkSync(cdpPidFile); } catch {}
  }

  if (!pid) {
    // Final attempt: try lsof directly via execSync
    const { execSync } = require('child_process');
    try {
      const out = execSync(`lsof -nP -iTCP:${cdpPort} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
      const lines = out.split('\n').filter(Boolean);
      for (const line of lines) {
        const p = parseInt(line, 10);
        if (p && !isNaN(p) && p !== process.pid) {
          pid = p;
          break;
        }
      }
    } catch {}
  }

  if (!pid) {
    logInfo('ServiceManager: no CDP service found on port ' + cdpPort);
    return;
  }

  // 3. Kill with SIGTERM, then SIGKILL if needed
  logInfo(`ServiceManager: stopping CDP service PID=${pid}`);
  try {
    process.kill(pid, 'SIGTERM');
    // Wait up to 3s for graceful exit
    const deadline = Date.now() + 3000;
    let alive = true;
    while (Date.now() < deadline) {
      try { process.kill(pid, 0); } catch { alive = false; break; }
      await new Promise(r => setTimeout(r, 200));
    }
    if (alive) {
      process.kill(pid, 'SIGKILL');
      logInfo(`ServiceManager: force-killed CDP service PID=${pid}`);
    }
  } catch {
    logInfo(`ServiceManager: CDP service PID=${pid} already dead`);
  }

  // 4. Verify port is free
  await new Promise(r => setTimeout(r, 500));
  const stillAlive = _findPidByPort(cdpPort);
  if (stillAlive) {
    logInfo(`ServiceManager: CDP port ${cdpPort} still occupied, force killing`);
    try { process.kill(stillAlive, 'SIGKILL'); } catch {}
  }
}

function _findPidByPort(port: number): number | null {
  try {
    const { execSync } = require('child_process');
    const out = execSync(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
    const lines = out.split('\n').filter(Boolean);
    if (lines.length > 0 && /^\d+$/.test(lines[0])) {
      return parseInt(lines[0], 10);
    }
  } catch {
    // lsof failed or no process
  }
  return null;
}

function _httpPost(host: string, port: number, pathStr: string, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: host, port, path: pathStr, method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeout: timeoutMs,
    }, (res) => {
      res.resume();
      res.on('end', resolve);
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.write('{}');
    req.end();
  });
}

export function getServiceStatus(): ServiceStatus[] {
  return Array.from(managedProcesses.entries()).map(([name, info]) => ({
    name,
    running: !!info.pid,
    port: info.port,
    pid: info.pid,
  }));
}
