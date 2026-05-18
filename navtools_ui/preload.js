const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('navtools', {
  launchApp: (appId) => ipcRenderer.invoke('launch-app', appId),
  openPath: (path) => ipcRenderer.invoke('open-path', path),
  browseApp: () => ipcRenderer.invoke('browse-app'),
  detectArduino: () => ipcRenderer.invoke('detect-arduino'),
  flashArduino: (params) => ipcRenderer.invoke('flash-arduino', params),
  readFirmwareCode: () => ipcRenderer.invoke('read-firmware-code'),
  collectData: (params) => ipcRenderer.invoke('collect-data', params),
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  isElectron: true,
  // EOG direct control — called by Python via HTTP → main.js IPC
  onEogAction: (callback) => ipcRenderer.on('eog-action', (_event, action) => callback(action)),
});

