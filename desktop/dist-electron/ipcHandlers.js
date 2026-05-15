"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerIpcHandlers = registerIpcHandlers;
exports.setWebPort = setWebPort;
exports.setupIpcHandlers = setupIpcHandlers;
const electron_1 = require("electron");
const serviceManager_1 = require("./runtime/serviceManager");
const logManager_1 = require("./runtime/logManager");
const healthChecker_1 = require("./runtime/healthChecker");
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
        (0, logManager_1.logInfo)(`IPC: restarting services... stack:\n${new Error().stack}`);
        await (0, serviceManager_1.stopAll)('ipc_services_restart');
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
        (0, logManager_1.logInfo)('IPC: services:startCdp is DEPRECATED — CDP lifecycle is managed by web_app JyhfCdpManager');
        return { ok: false, message: 'DEPRECATED: CDP must be started via web_app BFF (/api/v2/realtime/jyhf-cdp/start). Direct Electron spawn bypasses lifecycle management.' };
    });
    electron_1.ipcMain.handle('services:stopCdp', async () => {
        (0, logManager_1.logInfo)('IPC: services:stopCdp is DEPRECATED — CDP lifecycle is managed by web_app JyhfCdpManager');
        return { ok: false, message: 'DEPRECATED: CDP must be stopped via web_app BFF (/api/v2/realtime/jyhf-cdp/stop). Direct Electron kill bypasses lifecycle management.' };
    });
}
setupIpcHandlers();
//# sourceMappingURL=ipcHandlers.js.map