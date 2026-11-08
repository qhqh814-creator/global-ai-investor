import { ChildProcess, spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

export interface SidecarInfo {
  baseUrl: string;
  token: string;
  pid?: number;
  status: 'starting' | 'running' | 'failed';
  error?: string;
}

let child: ChildProcess | null = null;

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      if (addr && typeof addr === 'object') {
        const port = addr.port;
        srv.close(() => resolve(port));
      } else {
        srv.close(() => reject(new Error('no port')));
      }
    });
  });
}

function resolvePython(rootDir: string): string {
  if (process.env.GAI_PYTHON && existsSync(process.env.GAI_PYTHON)) {
    return process.env.GAI_PYTHON;
  }
  const venv = join(rootDir, '.venv', 'Scripts', 'python.exe');
  if (existsSync(venv)) return venv;
  return 'python';
}

export async function startSidecar(rootDir: string): Promise<SidecarInfo> {
  const port = await findFreePort();
  const token = Buffer.from(crypto.randomUUID()).toString('base64url');
  const python = resolvePython(rootDir);
  const env = {
    ...process.env,
    GAI_ROOT: rootDir,
    GAI_PORT: String(port),
    GAI_TOKEN: token,
    PYTHONUNBUFFERED: '1'
  };

  child = spawn(
    python,
    ['-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: rootDir, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }
  );

  child.stdout?.on('data', (d) => console.log('[sidecar]', d.toString().trim()));
  child.stderr?.on('data', (d) => console.error('[sidecar]', d.toString().trim()));

  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      return { baseUrl, token, status: 'failed', error: `sidecar exited with ${child.exitCode}` };
    }
    try {
      const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return { baseUrl, token, pid: child.pid, status: 'running' };
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return { baseUrl, token, pid: child.pid, status: 'failed', error: 'health check timeout' };
}

export function stopSidecar(): void {
  if (child && child.exitCode === null) {
    child.kill();
    child = null;
  }
}
