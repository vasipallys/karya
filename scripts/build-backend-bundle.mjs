import { existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const isWindows = process.platform === 'win32'
const executableName = isWindows ? 'storypointer-api.exe' : 'storypointer-api'
const distPath = path.join(root, 'desktop', 'backend-dist')
const workPath = path.join(root, 'desktop', 'backend-build')

const pythonCandidates = [
  process.env.PYTHON,
  path.join(root, 'venv', isWindows ? 'Scripts/python.exe' : 'bin/python'),
  path.join(root, '.venv', isWindows ? 'Scripts/python.exe' : 'bin/python'),
  isWindows ? 'python' : 'python3',
  'python',
].filter(Boolean)

function run(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    stdio: 'inherit',
    shell: false,
    ...options,
  })
}

function canImportPyInstaller(python) {
  const result = spawnSync(python, ['-c', 'import PyInstaller'], {
    cwd: root,
    stdio: 'ignore',
    shell: false,
  })
  return result.status === 0
}

function findPythonWithPyInstaller() {
  for (const python of pythonCandidates) {
    if (path.isAbsolute(python) && !existsSync(python)) continue
    if (canImportPyInstaller(python)) return python
  }
  return ''
}

const python = findPythonWithPyInstaller()
if (!python) {
  console.error('PyInstaller is required to bundle the desktop backend.')
  console.error('Install it with:')
  console.error('  python -m pip install -r requirements-desktop.txt')
  console.error('Then rerun:')
  console.error('  npm run backend:bundle')
  process.exit(1)
}

rmSync(distPath, { recursive: true, force: true })
rmSync(workPath, { recursive: true, force: true })
mkdirSync(distPath, { recursive: true })
mkdirSync(workPath, { recursive: true })

const result = run(python, [
  '-m',
  'PyInstaller',
  '--clean',
  '--noconfirm',
  '--distpath',
  distPath,
  '--workpath',
  workPath,
  path.join(root, 'desktop', 'pyinstaller', 'storypointer-api.spec'),
])

if (result.status !== 0) process.exit(result.status || 1)

const bundled = path.join(distPath, executableName)
if (!existsSync(bundled)) {
  console.error(`Expected backend executable was not created: ${bundled}`)
  process.exit(1)
}

console.log(`Backend executable ready: ${bundled}`)
