import { existsSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const isWindows = process.platform === 'win32'
const requestedArgs = process.argv.slice(2)

const candidates = [
  process.env.PYTHON ? { command: process.env.PYTHON, args: [] } : null,
  { command: path.join(root, '.venv', isWindows ? 'Scripts/python.exe' : 'bin/python'), args: [] },
  { command: path.join(root, 'venv', isWindows ? 'Scripts/python.exe' : 'bin/python'), args: [] },
  isWindows ? { command: 'py', args: ['-3.11'] } : null,
  { command: isWindows ? 'python' : 'python3', args: [] },
  { command: 'python', args: [] },
].filter(Boolean)

function canRun(candidate) {
  if (path.isAbsolute(candidate.command) && !existsSync(candidate.command)) return false
  const result = spawnSync(candidate.command, [...candidate.args, '--version'], {
    cwd: root,
    encoding: 'utf8',
    shell: false,
    stdio: 'ignore',
  })
  return result.status === 0
}

const python = candidates.find(canRun)
if (!python) {
  console.error('Could not find Python. Create .venv or set PYTHON to a Python 3.11+ executable.')
  process.exit(1)
}

const result = spawnSync(python.command, [...python.args, ...requestedArgs], {
  cwd: root,
  env: process.env,
  shell: false,
  stdio: 'inherit',
})

if (result.error) {
  console.error(result.error.message)
  process.exit(1)
}

process.exit(result.status ?? 1)
