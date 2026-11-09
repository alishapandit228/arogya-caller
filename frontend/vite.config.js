import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'

const cert = process.env.LOCAL_TLS_CERT
const key = process.env.LOCAL_TLS_KEY
const host = process.env.UI_HOST || '127.0.0.1'
if (Boolean(cert) !== Boolean(key)) throw new Error('Set both LOCAL_TLS_CERT and LOCAL_TLS_KEY')
if (!['127.0.0.1', 'localhost', '::1'].includes(host) && !cert) {
  throw new Error('LAN development requires trusted TLS certificate and key')
}
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host,
    https: cert && key ? { cert: fs.readFileSync(cert), key: fs.readFileSync(key) } : undefined,
    proxy: { '/voice': { target: 'http://127.0.0.1:8000', ws: true } },
  },
  preview: { host: '127.0.0.1' },
  test: { include: ['src/**/*.test.js'] },
})
