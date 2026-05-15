import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';
import { app } from 'electron';
import { logInfo, logError } from './logManager';

interface PortAllocation {
  web: number;
  sps: number;
  cdp: number;
}

interface PidRecord {
  serviceName: string;
  pid: number;
  port: number;
  startedAt: string;
}

const DEFAULT_PORTS: PortAllocation = { web: 8000, sps: 8090, cdp: 8095 };
const FALLBACK_RANGES: Record<keyof PortAllocation, [number, number]> = {
  web: [8100, 8199],
  sps: [8200, 8299],
  cdp: [8300, 8399],
};

function runtimeDir(): string {
  const dir = path.join(app.getPath('userData'), 'runtime');
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

function pidsFilePath(): string {
  return path.join(runtimeDir(), 'pids.json');
}

function portsFilePath(): string {
  return path.join(runtimeDir(), 'ports.json');
}

function isPortInUse(port: number): boolean {
  try {
    const out = execSync(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
    return out.length > 0;
  } catch {
    return false;
  }
}

/** Check if a PID belongs to this project by inspecting its command line. */
function isProjectProcess(pid: number): boolean {
  const markers = [
    'ai_theme_app',
    'web_app_service.main:app',
    'stock_processing_service',
    'services.jyhf_cdp_service.app:app',
  ];
  try {
    const cmdline = execSync(`ps -p ${pid} -o args=`, { encoding: 'utf-8', timeout: 3000 }).trim();
    return markers.some(m => cmdline.includes(m));
  } catch {
    return false;
  }
}

/** Get all PIDs listening on a port. */
function getPidsOnPort(port: number): number[] {
  try {
    const out = execSync(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
    return out.split('\n').filter(Boolean).map(Number);
  } catch {
    return [];
  }
}

/**
 * Scan default ports and kill any process that belongs to this project.
 * Returns a list of killed ports.
 */
export function killProjectProcessesOnDefaultPorts(projectRoot: string): number[] {
  const killed: number[] = [];
  for (const [serviceName, port] of Object.entries(DEFAULT_PORTS) as [string, number][]) {
    const pids = getPidsOnPort(port);
    for (const pid of pids) {
      if (isProjectProcess(pid)) {
        logInfo(`PortManager: killing project process pid=${pid} on port ${port} (${serviceName})`);
        try {
          // Kill process group
          try { process.kill(-pid, 'SIGTERM'); } catch { process.kill(pid, 'SIGTERM'); }
          // Wait for port release
          const deadline = Date.now() + 5000;
          while (Date.now() < deadline) {
            if (!isPortInUse(port)) break;
            const end = Date.now() + 200;
            while (Date.now() < end) { /* spin */ }
          }
          // Force kill if still alive
          if (isPortInUse(port)) {
            logInfo(`PortManager: force-killing stubborn process on port ${port}`);
            try { process.kill(-pid, 'SIGKILL'); } catch { process.kill(pid, 'SIGKILL'); }
            const end = Date.now() + 1000;
            while (Date.now() < end) { /* spin */ }
          }
          killed.push(port);
        } catch (e) {
          logInfo(`PortManager: failed to kill pid=${pid}: ${e}`);
        }
      } else {
        logInfo(`PortManager: port ${port} occupied by non-project pid=${pid}, not killing`);
      }
    }
  }
  return killed;
}

export function loadPreviousPids(): PidRecord[] {
  const f = pidsFilePath();
  if (!fs.existsSync(f)) return [];
  try {
    return JSON.parse(fs.readFileSync(f, 'utf-8'));
  } catch {
    return [];
  }
}

export function savePids(records: PidRecord[]): void {
  fs.writeFileSync(pidsFilePath(), JSON.stringify(records, null, 2), 'utf-8');
}

export function savePorts(allocation: PortAllocation): void {
  fs.writeFileSync(portsFilePath(), JSON.stringify(allocation, null, 2), 'utf-8');
}

export function loadPreviousPorts(): PortAllocation | null {
  const f = portsFilePath();
  if (!fs.existsSync(f)) return null;
  try {
    return JSON.parse(fs.readFileSync(f, 'utf-8'));
  } catch {
    return null;
  }
}

export function allocatePorts(envPorts: Partial<PortAllocation>, projectRoot?: string): PortAllocation {
  const result: PortAllocation = { ...DEFAULT_PORTS };

  // Apply env overrides
  if (envPorts.web) result.web = envPorts.web;
  if (envPorts.sps) result.sps = envPorts.sps;
  if (envPorts.cdp) result.cdp = envPorts.cdp;

  // First pass: clean up project-owned processes on default ports
  // This prevents new instances from using fallback ports when old ones linger
  if (projectRoot) {
    killProjectProcessesOnDefaultPorts(projectRoot);
  }

  // Check each port, fallback only for non-project processes
  for (const key of ['web', 'sps', 'cdp'] as (keyof PortAllocation)[]) {
    if (isPortInUse(result[key])) {
      const pids = getPidsOnPort(result[key]);
      const isProject = pids.some(p => isProjectProcess(p));
      if (isProject) {
        // Should not happen after cleanup, but just in case
        logInfo(`PortManager: ${key} port ${result[key]} still occupied by project process after cleanup, retrying...`);
        killProjectProcessesOnDefaultPorts(projectRoot || '');
        // Wait
        const end = Date.now() + 2000;
        while (Date.now() < end) { /* spin */ }
      }
      if (isPortInUse(result[key])) {
        const [start, end] = FALLBACK_RANGES[key];
        let found = false;
        for (let p = start; p <= end; p++) {
          if (!isPortInUse(p)) {
            logInfo(`PortManager: ${key} port ${result[key]} in use (non-project), using fallback ${p}`);
            result[key] = p;
            found = true;
            break;
          }
        }
        if (!found) {
          logError(`PortManager: no available port for ${key} in range ${start}-${end}`);
          throw new Error(`No available port for ${key}`);
        }
      }
    }
  }

  savePorts(result);
  return result;
}

export function clearStalePids(): void {
  const records = loadPreviousPids();
  const alive: PidRecord[] = [];
  for (const rec of records) {
    try {
      process.kill(rec.pid, 0); // Signal 0 checks existence
      logInfo(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) still alive, cleaning up...`);
      // Kill the process group
      try {
        process.kill(-rec.pid, 'SIGTERM');
      } catch {
        // May fail if we don't have permission, try direct kill
        try { process.kill(rec.pid, 'SIGTERM'); } catch {}
      }
      // Wait briefly
      const start = Date.now();
      let dead = false;
      while (Date.now() - start < 3000) {
        try { process.kill(rec.pid, 0); } catch { dead = true; break; }
        // busy-wait is bad, use a sync sleep workaround
        const end = Date.now() + 50;
        while (Date.now() < end) { /* spin */ }
      }
      if (!dead) {
        try { process.kill(-rec.pid, 'SIGKILL'); } catch {}
        try { process.kill(rec.pid, 'SIGKILL'); } catch {}
        logInfo(`PortManager: force-killed stale PID ${rec.pid}`);
      } else {
        logInfo(`PortManager: stale PID ${rec.pid} terminated gracefully`);
      }
    } catch {
      logInfo(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) already dead, removing`);
      continue;
    }
    // Don't keep it in pids.json — it's been killed
  }
  savePids(alive);
}

export function getRuntimeDir(): string {
  return runtimeDir();
}
