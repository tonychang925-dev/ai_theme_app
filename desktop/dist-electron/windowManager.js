"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.createLoadingWindow = createLoadingWindow;
exports.closeLoadingWindow = closeLoadingWindow;
exports.getMainWindow = getMainWindow;
exports.createMainWindow = createMainWindow;
exports.showErrorPage = showErrorPage;
const electron_1 = require("electron");
const path = __importStar(require("path"));
const logManager_1 = require("./runtime/logManager");
const logManager_2 = require("./runtime/logManager");
let loadingWindow = null;
let mainWindow = null;
let diagnosticsWindow = null;
function createLoadingWindow() {
    loadingWindow = new electron_1.BrowserWindow({
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
function closeLoadingWindow() {
    if (loadingWindow) {
        loadingWindow.close();
        loadingWindow = null;
    }
}
function getMainWindow() {
    return mainWindow;
}
function createMainWindow(webPort) {
    mainWindow = new electron_1.BrowserWindow({
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
            (0, logManager_1.logInfo)(`WindowManager: blocked navigation to ${url}`);
        }
    });
    // Build app menu
    const menuTemplate = [
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
                    click: () => { electron_1.shell.openPath((0, logManager_2.getLogDir)()); },
                },
                {
                    label: '导出诊断包',
                    click: async () => {
                        const exportDir = (0, logManager_2.exportDiagnostics)();
                        electron_1.dialog.showMessageBox({
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
    const menu = electron_1.Menu.buildFromTemplate(menuTemplate);
    electron_1.Menu.setApplicationMenu(menu);
    mainWindow.once('ready-to-show', () => {
        mainWindow?.show();
    });
    return mainWindow;
}
function showErrorPage(title, checks) {
    closeLoadingWindow();
    const errorHtmlPath = path.join(__dirname, '..', 'src', 'ui', 'error.html');
    diagnosticsWindow = new electron_1.BrowserWindow({
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
//# sourceMappingURL=windowManager.js.map