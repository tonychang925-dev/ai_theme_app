import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('desktopAPI', {
  platform: process.platform,
  appVersion: () => ipcRenderer.invoke('app:version'),
  getServiceStatus: () => ipcRenderer.invoke('services:status'),
  restartServices: () => ipcRenderer.invoke('services:restart'),
  openLogDirectory: () => ipcRenderer.invoke('app:openLogs'),
  exportDiagnostics: () => ipcRenderer.invoke('app:exportDiagnostics'),
  startCdpService: () => ipcRenderer.invoke('services:startCdp'),
  stopCdpService: () => ipcRenderer.invoke('services:stopCdp'),
  getReadyzStatus: () => ipcRenderer.invoke('app:readyz'),
});
