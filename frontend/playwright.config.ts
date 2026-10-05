import { defineConfig } from '@playwright/test';
import path from 'node:path';

const python = process.env.DAILY_REPORT_PYTHON || path.resolve('../.runtime/venv/Scripts/python.exe');
const port = process.env.DAILY_REPORT_E2E_PORT || '5173';
if (!['5173', '4173'].includes(port)) throw new Error('Readonly E2E requires a product-allowed Origin');
export default defineConfig({
  testDir: './e2e', testMatch: '**/reports.spec.ts', workers: 1, fullyParallel: false,
  reporter: [['list']], globalTeardown: './e2e/teardown.ts',
  use: { baseURL: `http://127.0.0.1:${port}`, browserName: 'chromium', channel: 'chrome', trace: 'retain-on-failure' },
  projects: [
    { name: 'mobile', use: { viewport: { width: 375, height: 812 } } },
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    { command: `"${python}" e2e/serve_fixture.py --port 8765`, url: 'http://127.0.0.1:8765/openapi.json', reuseExistingServer: false },
    { command: `"${python}" e2e/serve_fixture.py --port 8766 --broken`, url: 'http://127.0.0.1:8766/openapi.json', reuseExistingServer: false },
    { command: `npm run dev -- --port ${port}`, url: `http://127.0.0.1:${port}`, env: { VITE_API_MODE: 'readonly', VITE_API_BASE_URL: 'http://127.0.0.1:8765' }, reuseExistingServer: false },
  ],
});
