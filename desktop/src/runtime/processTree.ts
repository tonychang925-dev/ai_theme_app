import { ChildProcess, spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { logInfo, logError } from './logManager';

interface SpawnOptions {
  cwd: string;
  env: Record<string, string>;
  logName: string;
}

interface ManagedProcess {
  child: ChildProcess;
  name: string;
}

const KNOWN_PROCESSES: ManagedProcess[] = [];

export function spawnCommand(
  command: string,
  args: string[],
  opts: SpawnOptions,
): ChildProcess {
  const logPath = opts.env['DESKTOP_LOG_DIR'] || '';
  const logFile = path.join(logPath, opts.logName);
  const outFd = fs.openSync(logFile, 'a');

  logInfo(`ProcessTree: spawning ${command} ${args.join(' ')}`);

  const child = spawn(command, args, {
    cwd: opts.cwd,
    env: { ...process.env, ...opts.env },
    detached: true,
    stdio: ['ignore', outFd, outFd],
  });

  child.on('error', (err) => {
    logError(`ProcessTree: ${opts.logName} spawn error: ${err.message}`);
  });

  child.on('exit', (code, signal) => {
    logInfo(`ProcessTree: ${opts.logName} exited code=${code} signal=${signal}`);
    fs.closeSync(outFd);
  });

  KNOWN_PROCESSES.push({ child, name: opts.logName });

  return child;
}

export function killProcessTree(name: string, timeoutMs: number = 5000): Promise<void> {
  const entry = KNOWN_PROCESSES.find(p => p.name === name);
  if (!entry || !entry.child.pid) {
    logInfo(`ProcessTree: no process "${name}" to kill`);
    return Promise.resolve();
  }

  const pid = entry.child.pid;
  logInfo(`ProcessTree: killing process group for "${name}" (PGID=${pid})`);

  return new Promise((resolve) => {
    try {
      // Kill the entire process group (negative PID)
      process.kill(-pid, 'SIGTERM');
    } catch (e) {
      logError(`ProcessTree: SIGTERM failed for ${pid}: ${e}`);
    }

    const forceKillTimeout = setTimeout(() => {
      logInfo(`ProcessTree: force killing "${name}" (PGID=${-pid})`);
      try {
        process.kill(-pid, 'SIGKILL');
      } catch (e) {
        logError(`ProcessTree: SIGKILL failed for ${pid}: ${e}`);
      }
      resolve();
    }, timeoutMs);

    entry.child.once('exit', () => {
      clearTimeout(forceKillTimeout);
      logInfo(`ProcessTree: "${name}" exited gracefully`);
      resolve();
    });
  });
}

export async function killAllManaged(timeoutMs: number = 5000): Promise<void> {
  // Stop in reverse order: CDP → web_app → SPS
  const order = ['jyhf_cdp_service.log', 'web_app_service.log', 'stock_processing_service.log'];
  for (const name of order) {
    await killProcessTree(name, timeoutMs);
  }
  KNOWN_PROCESSES.length = 0;
}
