import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', timeout: 45000, workers: 1,
  use: { baseURL: process.env.SPECSEARCH_BASE_URL || 'http://127.0.0.1:8030', browserName: 'chromium' },
  webServer: process.env.SPECSEARCH_BASE_URL ? undefined : { command: 'rtk proxy .venv/bin/specsearch serve --port 8030',
    url: 'http://127.0.0.1:8030/v1/status', reuseExistingServer: true, timeout: 20000 },
  reporter: 'list', outputDir: '.data/playwright',
});
