import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 60000,
  retries: 0,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    baseURL: 'http://localhost:51421',
  },
  webServer: {
    command: 'npm run dev',
    port: 51421,
    cwd: '../../apps/admin-web',
    reuseExistingServer: true,
  },
});
