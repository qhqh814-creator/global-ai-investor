import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { join } from 'node:path';
import { startSidecar, stopSidecar, type SidecarInfo } from './sidecar';

const rootDir = app.isPackaged ? process.resourcesPath : join(__dirname, '..', '..');
let mainWindow: BrowserWindow | null = null;
let sidecar: SidecarInfo | null = null;

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    backgroundColor: '#0f1420',
    show: false,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(join(rootDir, 'dist', 'renderer', 'index.html'));
  }
}

ipcMain.handle('backend:info', () => sidecar);
ipcMain.handle('app:version', () => app.getVersion());
ipcMain.handle('app:rootDir', () => rootDir);

app.whenReady().then(async () => {
  sidecar = await startSidecar(rootDir);
  console.log('[main] sidecar:', sidecar.status, sidecar.baseUrl, sidecar.error ?? '');
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => stopSidecar());
app.on('will-quit', () => stopSidecar());
