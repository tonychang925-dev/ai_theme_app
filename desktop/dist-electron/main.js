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
const envLoader_1 = require("./runtime/envLoader");
// Determine project root
// V1-dev: running from desktop/ via npm start → project root is ../../
// V1-app: running from .app → reads PROJECT_ROOT from desktop-config.json
//   Note: V1-app requires the source project directory on disk (Scheme A).
//   Scheme B (bundling backend source into .app) is deferred to V2.
function getProjectRoot() {
    // V1-app: respect explicit LOCAL_PROJECT_ROOT if set
    const localRoot = process.env['LOCAL_PROJECT_ROOT'];
    if (localRoot && localRoot.trim()) {
        return localRoot.trim();
    }
    if (electron_1.app.isPackaged) {
        const config = (0, envLoader_1.loadDesktopConfig)();
        if (config && config.PROJECT_ROOT) {
            return config.PROJECT_ROOT;
        }
        throw new Error('PROJECT_ROOT is required in packaged V1-app mode. Run setup to create desktop-config.json.');
    }
    return path.resolve(__dirname, '..', '..');
}
let webPort = 0;
let appStarted = false;
let isQuitting = false;
async function quitSafely(reason = 'main_quitSafely') {
    if (isQuitting) {
        (0, logManager_1.logInfo)('Main: quit already in progress, skipping');
        return;
    }
    isQuitting = true;
    (0, logManager_1.logInfo)(`Main: safe quit (reason=${reason}) — stopping all services`);
    await (0, serviceManager_1.stopAll)(reason);
    (0, logManager_1.logInfo)('Main: quit complete');
    electron_1.app.exit(0);
}
// Set app name BEFORE ready event for correct userData path
electron_1.app.setName('AI投资助理');
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
        let checks;
        if (result.readyzResult?.checks) {
            checks = Object.entries(result.readyzResult.checks).map(([k, v]) => ({
                name: k,
                status: v === 'connected' || v === 'healthy' || v === 'mounted' ? 'pass' : 'fail',
                message: String(v),
            }));
        }
        else if (result.doctorChecks) {
            checks = result.doctorChecks.map(c => ({
                name: c.name,
                status: c.status,
                message: c.message,
                fixHint: c.fixHint,
            }));
        }
        else {
            checks = [{ name: 'startup', status: 'fail', message: 'Service startup failed' }];
        }
        (0, windowManager_1.showErrorPage)('服务启动失败', checks);
        return;
    }
    webPort = result.webPort;
    (0, ipcHandlers_1.setWebPort)(webPort);
    // Create main window (hidden), load, then reveal
    const mainWindow = (0, windowManager_1.createMainWindow)(webPort);
    // Clear HTTP cache only (preserve localStorage for login persistence)
    await mainWindow.webContents.session.clearCache();
    await mainWindow.webContents.session.clearAuthCache();
    // Cache-busting timestamp so Chromium treats this as a fresh page load
    const url = `http://127.0.0.1:${webPort}/login?_cb=${Date.now()}`;
    (0, logManager_1.logInfo)(`Main: loading ${url}`);
    // Wait for page to finish loading, then reveal
    mainWindow.webContents.once('did-finish-load', () => {
        (0, logManager_1.logInfo)('Main: page loaded, showing main window');
        (0, windowManager_1.closeLoadingWindow)();
        mainWindow.show();
    });
    // Enable window resize after navigating away from login page
    mainWindow.webContents.on('did-navigate', (_event, navUrl) => {
        if (!navUrl.endsWith('/login')) {
            (0, logManager_1.logInfo)('Main: navigated away from login, enabling resize');
            mainWindow.setResizable(true);
            mainWindow.setMinimumSize(1024, 720);
        }
    });
    // Safety timeout: reveal window after 15s even if did-finish-load didn't fire
    setTimeout(() => {
        (0, windowManager_1.closeLoadingWindow)();
        if (!mainWindow.isVisible()) {
            mainWindow.show();
        }
    }, 15000);
    mainWindow.loadURL(url);
    appStarted = true;
});
electron_1.app.on('window-all-closed', async () => {
    await quitSafely('main_window_all_closed');
});
electron_1.app.on('before-quit', async (event) => {
    if (!isQuitting && appStarted) {
        event.preventDefault();
        await quitSafely('main_before_quit');
    }
});
// Handle external signals (pkill, SIGTERM) for proper service cleanup
process.on('SIGTERM', async () => {
    (0, logManager_1.logInfo)('Main: received SIGTERM, cleaning up...');
    await quitSafely('main_signal_SIGTERM');
});
process.on('SIGINT', async () => {
    (0, logManager_1.logInfo)('Main: received SIGINT, cleaning up...');
    await quitSafely('main_signal_SIGINT');
});
electron_1.app.on('activate', () => {
    // macOS dock icon click — re-show window if app is still running
    if (appStarted && !isQuitting) {
        const win = (0, windowManager_1.getMainWindow)();
        if (win) {
            win.show();
        }
    }
});
//# sourceMappingURL=main.js.map