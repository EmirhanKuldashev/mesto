import { defineConfig, devices } from '@playwright/test';

// Fixed loopback URLs match docker-compose.e2e.yml; never target production.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['mesto-smoke.spec.ts', 'mesto-v2-presentation.spec.ts', 'mesto-local.spec.ts', 'mesto-mobility.spec.ts', 'mesto-match-v2.spec.ts', 'mesto-recommendations-v2.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:3100',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    serviceWorkers: 'block',
  },
  projects: [{
    name: 'chromium',
    use: {
      ...devices['Desktop Chrome'],
      launchOptions: { args: ['--enable-unsafe-swiftshader'] },
    },
  }],
});
