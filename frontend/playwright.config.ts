import { defineConfig } from '@playwright/test';

const port = process.env.DAILY_REPORT_E2E_PORT || '5173';
if (!['5173', '4173'].includes(port)) throw new Error('Readonly E2E requires a product-allowed Origin');
export default defineConfig({
  testDir: './e2e', testMatch: '**/reports.spec.ts', workers: 1, fullyParallel: false,
  reporter: [['list']], globalSetup: './e2e/global-setup.ts',
  use: { baseURL: `http://127.0.0.1:${port}`, browserName: 'chromium', channel: 'chrome', trace: 'retain-on-failure' },
  projects: [
    { name: 'mobile', use: { viewport: { width: 375, height: 812 } } },
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
  ],
});
