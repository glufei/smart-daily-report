import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.{ts,tsx}'], coverage: { provider: 'v8', include: ['src/api.ts', 'src/operations.ts', 'src/App.tsx', 'src/OperationPanel.tsx'], thresholds: { perFile: true, lines: 90, statements: 90, functions: 90, branches: 90 }, reporter: ['text', 'json-summary', 'html'] } },
});
