import { app } from 'electron';
import * as path from 'path';
import { createLoadingWindow, closeLoadingWindow, createMainWindow, showErrorPage, getMainWindow } from './windowManager';
import { registerIpcHandlers, setWebPort } from './ipcHandlers';
import { startAll, stopAll } from './runtime/serviceManager';
import { logInfo, logError } from './runtime/logManager';

// Determine project root
// V1-dev: running from desktop/ via npm start → project root is ../../
// V1-app: running from .app → uses LOCAL_PROJECT_ROOT env var or falls back to resourcesPath
//   Note: V1-app currently requires the source project directory on disk (Scheme A).
//   Scheme B (bundling backend source into .app) is deferred to V2.
function getProjectRoot(): string {
  // V1-app: respect explicit LOCAL_PROJECT_ROOT if set
  const localRoot = process.env['LOCAL_PROJECT_ROOT'];
  if (localRoot && localRoot.trim()) {
    return localRoot.trim();
  }
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.resolve(__dirname, '..', '..');
}

let webPort: number = 0;
let appStarted: boolean = false;
let isQuitting: boolean = false;

async function quitSafely(): Promise<void> {
  if (isQuitting) {
    logInfo('Main: quit already in progress, skipping');
    return;
  }
  isQuitting = true;
  logInfo('Main: safe quit — stopping all services');
  await stopAll();
  logInfo('Main: quit complete');
  app.exit(0);
}

app.whenReady().then(async () => {
  const projectRoot = getProjectRoot();
  logInfo(`Main: project root = ${projectRoot}`);
  logInfo(`Main: packaged = ${app.isPackaged}`);

  // Register IPC handlers
  registerIpcHandlers(projectRoot);

  // Show loading window
  createLoadingWindow();

  // Start all services
  const result = await startAll(projectRoot);

  if (!result.success || (result.readyzResult && result.readyzResult.status === 'failed')) {
    const checks = result.readyzResult?.checks
      ? Object.entries(result.readyzResult.checks).map(([k, v]) => ({
          name: k,
          status: v === 'connected' || v === 'healthy' || v === 'mounted' ? 'pass' : 'fail',
          message: String(v),
        }))
      : [{ name: 'startup', status: 'fail', message: 'Service startup failed' }];
    showErrorPage('服务启动失败', checks);
    return;
  }

  webPort = result.webPort;
  setWebPort(webPort);

  // Close loading, show main window
  closeLoadingWindow();
  const mainWindow = createMainWindow(webPort);

  // Load the app
  const url = `http://127.0.0.1:${webPort}/login`;
  logInfo(`Main: loading ${url}`);
  mainWindow.loadURL(url);

  appStarted = true;
});

// ── Quit handling (unified via quitSafely guard) ──

app.on('window-all-closed', async () => {
  await quitSafely();
});

app.on('before-quit', async (event) => {
  if (!isQuitting && appStarted) {
    event.preventDefault();
    await quitSafely();
  }
});

// Handle external signals (pkill, SIGTERM) for proper service cleanup
process.on('SIGTERM', async () => {
  logInfo('Main: received SIGTERM, cleaning up...');
  await quitSafely();
});
process.on('SIGINT', async () => {
  logInfo('Main: received SIGINT, cleaning up...');
  await quitSafely();
});

app.on('activate', () => {
  // macOS re-activate
  if (appStarted && !isQuitting) {
    const win = getMainWindow();
    if (win) {
      win.show();
    }
  }
});
