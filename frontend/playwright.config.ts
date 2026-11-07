import { defineConfig, devices } from '@playwright/test';

const externalURL = process.env.WOHIN_TEST_URL;
const baseURL = externalURL ?? 'http://127.0.0.1:4173';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.e2e.ts',
  timeout: 35_000,
  expect: { timeout: 6_000 },
  workers: 2,
  reporter: 'list',
  use: { ...devices['Desktop Chrome'], baseURL, trace: 'retain-on-failure' },
  webServer: externalURL
    ? undefined
    : {
        command:
          'npm run build && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
        url: baseURL,
        timeout: 30_000,
        reuseExistingServer: false,
      },
});
