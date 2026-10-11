import { defineConfig } from '@playwright/test';
process.env.DAILY_REPORT_E2E_MODE = 'operations';
export default defineConfig({
  testDir: './e2e', testMatch: '**/operations.spec.ts', workers: 1, fullyParallel: false, reporter: [['list']],
  globalSetup: './e2e/global-setup.ts', timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:5174', browserName: 'chromium', channel: 'chrome', trace: 'retain-on-failure' },
  projects: [{ name: 'mobile', use: { viewport: { width: 375, height: 812 } } }, { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } }],
});
