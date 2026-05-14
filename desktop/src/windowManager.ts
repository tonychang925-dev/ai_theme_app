import { BrowserWindow, app, Menu, shell, dialog } from 'electron';
import * as path from 'path';
import { logInfo } from './runtime/logManager';
import { exportDiagnostics, getLogDir } from './runtime/logManager';

let loadingWindow: BrowserWindow | null = null;
let mainWindow: BrowserWindow | null = null;
let diagnosticsWindow: BrowserWindow | null = null;

export function createLoadingWindow(): BrowserWindow {
  loadingWindow = new BrowserWindow({
    width: 460,
    height: 320,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const loadingPath = path.join(__dirname, '..', 'src', 'ui', 'loading.html');
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
    minWidth: 1024,
    minHeight: 720,
    show: false,
    title: 'AI题材引擎',
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
      label: 'AI题材引擎',
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

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  return mainWindow;
}

export function showErrorPage(title: string, checks: Array<{ name: string; status: string; message: string; fixHint?: string }>): void {
  closeLoadingWindow();

  const errorHtmlPath = path.join(__dirname, '..', 'src', 'ui', 'error.html');
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
