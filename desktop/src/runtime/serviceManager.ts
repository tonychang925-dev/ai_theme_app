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
let _cdProjectRoot: string | null = null;  // retained for reference, CDP lifecycle delegated to web_app BFF

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
  // (cdProjectRoot kept for reference, CDP lifecycle delegated to web_app BFF)
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

  // CDP lifecycle is managed by web_app BFF (JyhfCdpManager).
  // Delegate via the /api/v2/realtime/jyhf-cdp/service/stop endpoint.
  // This respects owner=managed vs owner=external: only managed gets killed.
  if (_cdProjectRoot) {
    try {
      await _httpPost('127.0.0.1', 8000, '/api/v2/realtime/jyhf-cdp/service/stop', 5000);
      logInfo('ServiceManager: CDP stop delegated to web_app BFF');
    } catch {
      logInfo('ServiceManager: CDP service stop request failed (web_app may be down)');
    }
  }

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
