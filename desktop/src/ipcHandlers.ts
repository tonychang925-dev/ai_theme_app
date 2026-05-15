import { ipcMain, shell } from 'electron';
import { getServiceStatus, startAll, stopAll } from './runtime/serviceManager';
import { getLogDir, exportDiagnostics, logInfo } from './runtime/logManager';
import { waitForReadyz } from './runtime/healthChecker';

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
    logInfo(`IPC: restarting services... stack:\n${new Error().stack}`);
    await stopAll('ipc_services_restart');
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
    logInfo('IPC: services:startCdp is DEPRECATED — CDP lifecycle is managed by web_app JyhfCdpManager');
    return { ok: false, message: 'DEPRECATED: CDP must be started via web_app BFF (/api/v2/realtime/jyhf-cdp/start). Direct Electron spawn bypasses lifecycle management.' };
  });

  ipcMain.handle('services:stopCdp', async () => {
    logInfo('IPC: services:stopCdp is DEPRECATED — CDP lifecycle is managed by web_app JyhfCdpManager');
    return { ok: false, message: 'DEPRECATED: CDP must be stopped via web_app BFF (/api/v2/realtime/jyhf-cdp/stop). Direct Electron kill bypasses lifecycle management.' };
  });
}

setupIpcHandlers();
