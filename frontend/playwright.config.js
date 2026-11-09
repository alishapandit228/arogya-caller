import { defineConfig } from '@playwright/test'
import { randomBytes } from 'node:crypto'
import { mkdtempSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const directory = mkdtempSync(path.join(os.tmpdir(), 'arogya-browser-'))
process.env.AC_BROWSER_TEST_TOKEN ||= randomBytes(48).toString('hex')

export default defineConfig({
  testDir: './browser-tests',
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
  },
  webServer: [
    {
      command: 'node ./scripts/start-test-backend.mjs',
      url: 'http://127.0.0.1:8000/health',
      env: {
        PYTHONPATH: path.join(root, 'backend'),
        ADMIN_API_TOKEN: process.env.AC_BROWSER_TEST_TOKEN,
        DATABASE_URL: 'sqlite:///' + path.join(directory, 'test.db'),
        TRUSTED_ORIGINS: '["http://127.0.0.1:5173"]',
        VOICE_COOKIE_SECURE: 'false',
      },
    },
    { command: 'npm run dev -- --port 5173 --strictPort', url: 'http://127.0.0.1:5173' },
  ],
})
