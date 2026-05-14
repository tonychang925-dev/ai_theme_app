import { app } from 'electron';
import * as path from 'path';
import { createLoadingWindow, closeLoadingWindow, createMainWindow, showErrorPage } from './windowManager';
import { registerIpcHandlers, setWebPort } from './ipcHandlers';
import { startAll, stopAll } from './runtime/serviceManager';
import { logInfo, logError } from './runtime/logManager';

// Determine project root
// V1-dev: running from desktop/ via npm start → project root is ../../
// V1-app: running from .app → project root is app.getAppPath()/../../
function getProjectRoot(): string {
  if (app.isPackaged) {
    // V1-app: the .app bundle
    // extraResources are at process.resourcesPath
    return process.resourcesPath;
  }
  // V1-dev: assume we're in desktop/dist-electron/main.js
  // Project root is ../../ from there
  return path.resolve(__dirname, '..', '..');
}

let webPort: number = 0;
let appStarted: boolean = false;

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

// ── Quit handling ──

app.on('window-all-closed', () => {
  // On macOS it's common for apps to stay active
  // But we want close = quit for service release
  stopAll().then(() => {
    logInfo('Main: all services stopped, quitting');
    app.quit();
  });
});

app.on('before-quit', async (event) => {
  if (appStarted) {
    event.preventDefault();
    await stopAll();
    logInfo('Main: before-quit complete');
    app.exit(0);
  }
});

app.on('activate', () => {
  // macOS re-activate
  if (appStarted) {
    const { getMainWindow } = require('./windowManager');
    const win = getMainWindow();
    if (win) {
      win.show();
    }
  }
});
