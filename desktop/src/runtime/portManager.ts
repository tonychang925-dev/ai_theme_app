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

export function allocatePorts(envPorts: Partial<PortAllocation>): PortAllocation {
  const result: PortAllocation = { ...DEFAULT_PORTS };

  // Apply env overrides
  if (envPorts.web) result.web = envPorts.web;
  if (envPorts.sps) result.sps = envPorts.sps;
  if (envPorts.cdp) result.cdp = envPorts.cdp;

  // Check each port, fallback if needed
  for (const key of ['web', 'sps', 'cdp'] as (keyof PortAllocation)[]) {
    if (isPortInUse(result[key])) {
      const [start, end] = FALLBACK_RANGES[key];
      let found = false;
      for (let p = start; p <= end; p++) {
        if (!isPortInUse(p)) {
          logInfo(`PortManager: ${key} port ${result[key]} in use, using fallback ${p}`);
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

  savePorts(result);
  return result;
}

export function clearStalePids(): void {
  const records = loadPreviousPids();
  const alive: PidRecord[] = [];
  for (const rec of records) {
    try {
      process.kill(rec.pid, 0); // Signal 0 just checks existence
      logInfo(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) still alive, will clean up`);
    } catch {
      logInfo(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) already dead, removing`);
      continue;
    }
    alive.push(rec);
  }
  savePids(alive);
}

export function getRuntimeDir(): string {
  return runtimeDir();
}
