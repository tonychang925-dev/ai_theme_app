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
const electron_1 = require("electron");
const path = __importStar(require("path"));
const windowManager_1 = require("./windowManager");
const ipcHandlers_1 = require("./ipcHandlers");
const serviceManager_1 = require("./runtime/serviceManager");
const logManager_1 = require("./runtime/logManager");
// Determine project root
// V1-dev: running from desktop/ via npm start → project root is ../../
// V1-app: running from .app → project root is app.getAppPath()/../../
function getProjectRoot() {
    if (electron_1.app.isPackaged) {
        // V1-app: the .app bundle
        // extraResources are at process.resourcesPath
        return process.resourcesPath;
    }
    // V1-dev: assume we're in desktop/dist-electron/main.js
    // Project root is ../../ from there
    return path.resolve(__dirname, '..', '..');
}
let webPort = 0;
let appStarted = false;
electron_1.app.whenReady().then(async () => {
    const projectRoot = getProjectRoot();
    (0, logManager_1.logInfo)(`Main: project root = ${projectRoot}`);
    (0, logManager_1.logInfo)(`Main: packaged = ${electron_1.app.isPackaged}`);
    // Register IPC handlers
    (0, ipcHandlers_1.registerIpcHandlers)(projectRoot);
    // Show loading window
    (0, windowManager_1.createLoadingWindow)();
    // Start all services
    const result = await (0, serviceManager_1.startAll)(projectRoot);
    if (!result.success || (result.readyzResult && result.readyzResult.status === 'failed')) {
        const checks = result.readyzResult?.checks
            ? Object.entries(result.readyzResult.checks).map(([k, v]) => ({
                name: k,
                status: v === 'connected' || v === 'healthy' || v === 'mounted' ? 'pass' : 'fail',
                message: String(v),
            }))
            : [{ name: 'startup', status: 'fail', message: 'Service startup failed' }];
        (0, windowManager_1.showErrorPage)('服务启动失败', checks);
        return;
    }
    webPort = result.webPort;
    (0, ipcHandlers_1.setWebPort)(webPort);
    // Close loading, show main window
    (0, windowManager_1.closeLoadingWindow)();
    const mainWindow = (0, windowManager_1.createMainWindow)(webPort);
    // Load the app
    const url = `http://127.0.0.1:${webPort}/login`;
    (0, logManager_1.logInfo)(`Main: loading ${url}`);
    mainWindow.loadURL(url);
    appStarted = true;
});
// ── Quit handling ──
electron_1.app.on('window-all-closed', () => {
    // On macOS it's common for apps to stay active
    // But we want close = quit for service release
    (0, serviceManager_1.stopAll)().then(() => {
        (0, logManager_1.logInfo)('Main: all services stopped, quitting');
        electron_1.app.quit();
    });
});
electron_1.app.on('before-quit', async (event) => {
    if (appStarted) {
        event.preventDefault();
        await (0, serviceManager_1.stopAll)();
        (0, logManager_1.logInfo)('Main: before-quit complete');
        electron_1.app.exit(0);
    }
});
electron_1.app.on('activate', () => {
    // macOS re-activate
    if (appStarted) {
        const { getMainWindow } = require('./windowManager');
        const win = getMainWindow();
        if (win) {
            win.show();
        }
    }
});
//# sourceMappingURL=main.js.map