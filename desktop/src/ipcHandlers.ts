import { ipcMain, shell } from 'electron';
import { getServiceStatus, startAll, stopAll } from './runtime/serviceManager';
import { getLogDir, exportDiagnostics, logInfo } from './runtime/logManager';
import { waitForReadyz } from './runtime/healthChecker';
import { spawnCommand, killProcessTree } from './runtime/processTree';
import * as path from 'path';

let projectRoot: string = '';
let currentWebPort: number = 0;

export function registerIpcHandlers(rootDir: string): void {
  projectRoot = rootDir;
}

export function setWebPort(port: number): void {
  currentWebPort = port;
}

export function setupIpcHandlers(): void {
  ipcMain.handle('app:version', () => {
    return '1.0.0';
  });

  ipcMain.handle('services:status', () => {
    return getServiceStatus();
  });

  ipcMain.handle('services:restart', async () => {
    logInfo('IPC: restarting services...');
    await stopAll();
    const result = await startAll(projectRoot);
    if (result.success) {
      currentWebPort = result.webPort;
    }
    return result;
  });

  ipcMain.handle('app:openLogs', () => {
    shell.openPath(getLogDir());
  });

  ipcMain.handle('app:exportDiagnostics', () => {
    const exportDir = exportDiagnostics();
    return exportDir;
  });

  ipcMain.handle('app:readyz', async () => {
    if (!currentWebPort) return null;
    return await waitForReadyz(currentWebPort, '127.0.0.1', 10000);
  });

  ipcMain.handle('services:startCdp', async () => {
    logInfo('IPC: starting CDP service...');
    const cdpPort = 8095;
    const env = {
      ...process.env as Record<string, string>,
      ENABLE_CDP: '1',
    };
    spawnCommand(
      path.join(projectRoot, '.venv', 'bin', 'python'),
      ['-m', 'uvicorn', 'services.jyhf_cdp_service.app:app', '--host', '127.0.0.1', '--port', String(cdpPort)],
      { cwd: projectRoot, env, logName: 'jyhf_cdp_service.log' },
    );
    return { ok: true, port: cdpPort };
  });

  ipcMain.handle('services:stopCdp', async () => {
    logInfo('IPC: stopping CDP service...');
    await killProcessTree('jyhf_cdp_service.log', 5000);
    return { ok: true };
  });
}

setupIpcHandlers();
