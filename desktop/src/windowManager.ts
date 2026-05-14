import { BrowserWindow, app, Menu, shell, dialog } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { logInfo } from './runtime/logManager';
import { exportDiagnostics, getLogDir } from './runtime/logManager';

let loadingWindow: BrowserWindow | null = null;
let mainWindow: BrowserWindow | null = null;
let diagnosticsWindow: BrowserWindow | null = null;

/** Resolve a UI asset path that works both in dev (npm start) and packaged (.app). */
function uiPath(filename: string): string {
  // Dev mode: __dirname = dist-electron/, look in ../src/ui/
  const devPath = path.join(__dirname, '..', 'src', 'ui', filename);
  if (fs.existsSync(devPath)) return devPath;
  // Packaged: try relative to app root
  const pkgPath = path.join(app.getAppPath(), 'src', 'ui', filename);
  if (fs.existsSync(pkgPath)) return pkgPath;
  // Fallback: try relative to resourcesPath
  const resPath = path.join(process.resourcesPath || '', 'src', 'ui', filename);
  if (fs.existsSync(resPath)) return resPath;
  // Last resort — return dev path and let Electron error
  return devPath;
}

export function createLoadingWindow(): BrowserWindow {
  loadingWindow = new BrowserWindow({
    width: 800,
    height: 500,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    center: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const loadingPath = uiPath('loading.html');
  logInfo(`WindowManager: loading window path = ${loadingPath}, exists = ${fs.existsSync(loadingPath)}`);
  loadingWindow.loadFile(loadingPath);
  return loadingWindow;
}

export function closeLoadingWindow(): void {
  if (loadingWindow) {
    loadingWindow.close();
    loadingWindow = null;
  }
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}

export function createMainWindow(webPort: number): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    resizable: false,
    show: false,
    backgroundColor: '#00050e',
    title: 'AI 投资助理',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  // Deny new window openings
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

  // Restrict navigation to localhost:webPort only
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const allowed = url.startsWith(`http://127.0.0.1:${webPort}`) ||
                    url.startsWith(`http://localhost:${webPort}`) ||
                    url.startsWith(`http://[::1]:${webPort}`);
    if (!allowed) {
      event.preventDefault();
      logInfo(`WindowManager: blocked navigation to ${url}`);
    }
  });

  // Build app menu
  const menuTemplate: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'AI 投资助理',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        {
          label: '重新启动后端服务',
          click: () => { mainWindow?.webContents.send('menu:restartServices'); },
        },
        {
          label: '打开日志目录',
          click: () => { shell.openPath(getLogDir()); },
        },
        {
          label: '导出诊断包',
          click: async () => {
            const exportDir = exportDiagnostics();
            dialog.showMessageBox({
              type: 'info',
              message: `诊断包已导出到:\n${exportDir}`,
            });
          },
        },
        { type: 'separator' },
        {
          label: '诊断 / 打开开发者工具',
          accelerator: 'CmdOrCtrl+Shift+I',
          click: () => { mainWindow?.webContents.openDevTools(); },
        },
        { role: 'quit' },
      ],
    },
    {
      label: '实时采集',
      submenu: [
        {
          label: '启动实时采集服务 (CDP)',
          click: () => { mainWindow?.webContents.send('menu:startCdp'); },
        },
        {
          label: '停止实时采集服务 (CDP)',
          click: () => { mainWindow?.webContents.send('menu:stopCdp'); },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(menuTemplate);
  Menu.setApplicationMenu(menu);

  return mainWindow;
}

export function showErrorPage(title: string, checks: Array<{ name: string; status: string; message: string; fixHint?: string }>): void {
  closeLoadingWindow();

  const errorHtmlPath = uiPath('error.html');
  logInfo(`WindowManager: error page path = ${errorHtmlPath}, exists = ${fs.existsSync(errorHtmlPath)}`);
  diagnosticsWindow = new BrowserWindow({
    width: 700,
    height: 600,
    title: '启动诊断',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  diagnosticsWindow.loadFile(errorHtmlPath, {
    query: {
      title,
      checks: JSON.stringify(checks),
    },
  });
}
