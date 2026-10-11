import { spawn, type ChildProcess } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

type Server = { command: string; args: string[]; port: number; readyPath: string; env?: NodeJS.ProcessEnv };

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.DAILY_REPORT_PYTHON || path.resolve(frontendDir, '../.runtime/venv/Scripts/python.exe');
const vite = path.join(frontendDir, 'node_modules/vite/bin/vite.js');
const children: ChildProcess[] = [];

async function startServer(server: Server): Promise<void> {
  const child = spawn(server.command, server.args, {
    cwd: frontendDir,
    env: { ...process.env, ...server.env },
    stdio: 'ignore',
    windowsHide: true,
  });
  children.push(child);
  child.once('error', (error) => console.error(`E2E server failed to start: ${error.message}`));

  const endpoint = `http://127.0.0.1:${server.port}${server.readyPath}`;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`E2E server exited before becoming ready: ${endpoint}`);
    }
    try {
      const response = await fetch(endpoint, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // The local server is still starting or the port is unavailable.
    }
    await delay(100);
  }
  throw new Error(`E2E server did not become ready within 30 seconds: ${endpoint}`);
}

async function stopServers(): Promise<void> {
  for (const child of [...children].reverse()) {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) continue;
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
    child.kill();
    const stopped = await Promise.race([exited.then(() => true), delay(3_000).then(() => false)]);
    if (!stopped && process.platform === 'win32') {
      const { execFileSync } = await import('node:child_process');
      execFileSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    }
    if (!stopped) {
      await Promise.race([exited, delay(5_000)]);
    }
    if (child.exitCode === null && child.signalCode === null) {
      throw new Error(`E2E server process ${child.pid} did not stop cleanly`);
    }
  }
  children.length = 0;
}

export default async function globalSetup() {
  const operations = process.env.DAILY_REPORT_E2E_MODE === 'operations';
  const appPort = operations ? 5174 : Number(process.env.DAILY_REPORT_E2E_PORT || '5173');
  if (!operations && ![5173, 4173].includes(appPort)) {
    throw new Error('Readonly E2E requires a product-allowed Origin');
  }

  const servers: Server[] = operations
    ? [
        { command: python, args: ['e2e/serve_operations_fixture.py', '--port', '8775'], port: 8775, readyPath: '/openapi.json' },
      ]
    : [
        { command: python, args: ['e2e/serve_fixture.py', '--port', '8765'], port: 8765, readyPath: '/openapi.json' },
        { command: python, args: ['e2e/serve_fixture.py', '--port', '8766', '--broken'], port: 8766, readyPath: '/openapi.json' },
      ];
  servers.push({
    command: process.execPath,
    args: [vite, '--host', '127.0.0.1', '--port', String(appPort), '--strictPort'],
    port: appPort,
    readyPath: '/',
    env: {
      VITE_API_MODE: operations ? 'operations' : 'readonly',
      VITE_API_BASE_URL: operations ? 'http://127.0.0.1:8775' : 'http://127.0.0.1:8765',
    },
  });

  try {
    for (const server of servers) await startServer(server);
  } catch (error) {
    await stopServers();
    throw error;
  }

  return async () => {
    try {
      const verify = operations
        ? (await import('./operations-teardown')).default
        : (await import('./teardown')).default;
      await verify();
    } finally {
      await stopServers();
    }
  };
}
