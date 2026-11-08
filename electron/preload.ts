import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('gai', {
  getBackend: () => ipcRenderer.invoke('backend:info'),
  getVersion: () => ipcRenderer.invoke('app:version'),
  getRootDir: () => ipcRenderer.invoke('app:rootDir')
});
