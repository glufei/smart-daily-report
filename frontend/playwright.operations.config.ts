import { defineConfig } from '@playwright/test';
import path from 'node:path';
const python = process.env.DAILY_REPORT_PYTHON || path.resolve('../.runtime/venv/Scripts/python.exe');
export default defineConfig({
  testDir: './e2e', testMatch: '**/operations.spec.ts', workers: 1, fullyParallel: false, reporter: [['list']],
  globalTeardown: './e2e/operations-teardown.ts', timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:5174', browserName: 'chromium', channel: 'chrome', trace: 'retain-on-failure' },
  projects: [{ name: 'mobile', use: { viewport: { width: 375, height: 812 } } }, { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } }],
  webServer: [
    { command: `"${python}" e2e/serve_operations_fixture.py --port 8775`, url: 'http://127.0.0.1:8775/openapi.json', reuseExistingServer: false },
    { command: 'npm run dev -- --port 5174', url: 'http://127.0.0.1:5174', env: { VITE_API_MODE: 'operations', VITE_API_BASE_URL: 'http://127.0.0.1:8775' }, reuseExistingServer: false },
  ],
});
