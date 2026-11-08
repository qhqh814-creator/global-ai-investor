/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface BackendInfo {
  baseUrl: string;
  token: string;
  pid?: number;
  status: 'starting' | 'running' | 'failed';
  error?: string;
}

interface Window {
  gai: {
    getBackend: () => Promise<BackendInfo>;
    getVersion: () => Promise<string>;
    getRootDir: () => Promise<string>;
  };
}
