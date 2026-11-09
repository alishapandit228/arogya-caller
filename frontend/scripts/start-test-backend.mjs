// Shared Windows/macOS/Linux test launcher; no shell or interpolated paths.
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const child = spawn(python, ['-m', 'uvicorn', 'browser_server:create', '--factory',
  '--app-dir', path.join(root, 'backend/tests'), '--host', '127.0.0.1', '--port', '8000',
  '--no-access-log', '--ws-max-size', '2048'], { stdio: 'inherit', shell: false })
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill())
process.on('exit', () => child.kill())
child.on('error', () => { console.error('Cannot launch test backend; create the local .venv first'); process.exit(1) })
child.on('exit', code => process.exit(code ?? 1))
