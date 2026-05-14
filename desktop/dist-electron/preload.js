"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('desktopAPI', {
    platform: process.platform,
    appVersion: () => electron_1.ipcRenderer.invoke('app:version'),
    getServiceStatus: () => electron_1.ipcRenderer.invoke('services:status'),
    restartServices: () => electron_1.ipcRenderer.invoke('services:restart'),
    openLogDirectory: () => electron_1.ipcRenderer.invoke('app:openLogs'),
    exportDiagnostics: () => electron_1.ipcRenderer.invoke('app:exportDiagnostics'),
    startCdpService: () => electron_1.ipcRenderer.invoke('services:startCdp'),
    stopCdpService: () => electron_1.ipcRenderer.invoke('services:stopCdp'),
    getReadyzStatus: () => electron_1.ipcRenderer.invoke('app:readyz'),
});
//# sourceMappingURL=preload.js.map