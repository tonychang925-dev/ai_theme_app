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
exports.registerIpcHandlers = registerIpcHandlers;
exports.setWebPort = setWebPort;
exports.setupIpcHandlers = setupIpcHandlers;
const electron_1 = require("electron");
const serviceManager_1 = require("./runtime/serviceManager");
const logManager_1 = require("./runtime/logManager");
const healthChecker_1 = require("./runtime/healthChecker");
const processTree_1 = require("./runtime/processTree");
const path = __importStar(require("path"));
let projectRoot = '';
let currentWebPort = 0;
function registerIpcHandlers(rootDir) {
    projectRoot = rootDir;
}
function setWebPort(port) {
    currentWebPort = port;
}
function setupIpcHandlers() {
    electron_1.ipcMain.handle('app:version', () => {
        return '1.0.0';
    });
    electron_1.ipcMain.handle('services:status', () => {
        return (0, serviceManager_1.getServiceStatus)();
    });
    electron_1.ipcMain.handle('services:restart', async () => {
        (0, logManager_1.logInfo)('IPC: restarting services...');
        await (0, serviceManager_1.stopAll)();
        const result = await (0, serviceManager_1.startAll)(projectRoot);
        if (result.success) {
            currentWebPort = result.webPort;
        }
        return result;
    });
    electron_1.ipcMain.handle('app:openLogs', () => {
        electron_1.shell.openPath((0, logManager_1.getLogDir)());
    });
    electron_1.ipcMain.handle('app:exportDiagnostics', () => {
        const exportDir = (0, logManager_1.exportDiagnostics)();
        return exportDir;
    });
    electron_1.ipcMain.handle('app:readyz', async () => {
        if (!currentWebPort)
            return null;
        return await (0, healthChecker_1.waitForReadyz)(currentWebPort, '127.0.0.1', 10000);
    });
    electron_1.ipcMain.handle('services:startCdp', async () => {
        (0, logManager_1.logInfo)('IPC: starting CDP service...');
        const cdpPort = 8095;
        const env = {
            ...process.env,
            ENABLE_CDP: '1',
        };
        (0, processTree_1.spawnCommand)(path.join(projectRoot, '.venv', 'bin', 'python'), ['-m', 'uvicorn', 'services.jyhf_cdp_service.app:app', '--host', '127.0.0.1', '--port', String(cdpPort)], { cwd: projectRoot, env, logName: 'jyhf_cdp_service.log' });
        return { ok: true, port: cdpPort };
    });
    electron_1.ipcMain.handle('services:stopCdp', async () => {
        (0, logManager_1.logInfo)('IPC: stopping CDP service...');
        await (0, processTree_1.killProcessTree)('jyhf_cdp_service.log', 5000);
        return { ok: true };
    });
}
setupIpcHandlers();
//# sourceMappingURL=ipcHandlers.js.map