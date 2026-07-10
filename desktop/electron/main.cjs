const { app, BrowserWindow, dialog, shell } = require('electron')
const { spawn } = require('child_process')
const fs = require('fs')
const http = require('http')
const net = require('net')
const path = require('path')

const isDev = !app.isPackaged
const DEFAULT_DESKTOP_PORT = 8765
let apiBaseUrl = ''
let backendProcess = null
let mainWindow = null

function projectRoot() {
  return path.resolve(__dirname, '..', '..')
}

function exists(candidate) {
  try {
    return fs.existsSync(candidate)
  } catch {
    return false
  }
}

function mergeCsv(...values) {
  const ordered = []
  const seen = new Set()
  values
    .filter(Boolean)
    .flatMap((value) => String(value).split(','))
    .map((value) => value.trim())
    .filter(Boolean)
    .forEach((value) => {
      if (!seen.has(value)) {
        seen.add(value)
        ordered.push(value)
      }
    })
  return ordered.join(',')
}

function writeDefaultDesktopEnv(target) {
  const packagedTemplate = path.join(process.resourcesPath || '', 'backend.env.example')
  const devTemplate = path.join(projectRoot(), 'desktop', 'backend.env.example')
  const template = exists(packagedTemplate) ? packagedTemplate : devTemplate
  fs.mkdirSync(path.dirname(target), { recursive: true })
  if (exists(template)) {
    fs.copyFileSync(template, target)
  } else {
    fs.writeFileSync(target, 'LLM_PROVIDER=mock\nLLM_MODEL=mock\nLLM_API_KEY=\nJIRA_INSTANCES=\nJIRA_WRITE_ENABLED=false\nCORS_ORIGINS=null,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174\n')
  }
}

function desktopBackendEnv(port) {
  const userData = app.getPath('userData')
  const dataDir = path.join(userData, 'data')
  const envFile = process.env.STORYPOINTER_ENV_FILE || path.join(userData, 'backend.env')
  if (!exists(envFile)) writeDefaultDesktopEnv(envFile)

  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    STORYPOINTER_API_HOST: '127.0.0.1',
    STORYPOINTER_API_PORT: String(port),
    STORYPOINTER_DB: process.env.STORYPOINTER_DB || path.join(dataDir, 'storypointer.db'),
    STORYPOINTER_ENV_FILE: envFile,
    STORYPOINTER_DESKTOP: 'true',
    CORS_ORIGINS: mergeCsv(
      process.env.CORS_ORIGINS,
      'null',
      'http://localhost:5173',
      'http://127.0.0.1:5173',
      'http://localhost:5174',
      'http://127.0.0.1:5174',
    ),
  }
}

function findPython() {
  const root = projectRoot()
  const candidates = [
    process.env.PYTHON,
    path.join(root, 'venv', process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python'),
    path.join(root, '.venv', process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python'),
    process.platform === 'win32' ? 'python' : 'python3',
    'python',
  ].filter(Boolean)
  return candidates.find((candidate) => !path.isAbsolute(candidate) || exists(candidate)) || 'python'
}

function walkForExecutable(dir, names) {
  if (!exists(dir)) return ''
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const candidate = path.join(dir, entry.name)
    if (entry.isFile() && names.includes(entry.name)) return candidate
    if (entry.isDirectory()) {
      const nested = walkForExecutable(candidate, names)
      if (nested) return nested
    }
  }
  return ''
}

function bundledBackendExecutable() {
  const names = process.platform === 'win32' ? ['storypointer-api.exe'] : ['storypointer-api']
  return walkForExecutable(path.join(process.resourcesPath || '', 'backend'), names)
}

function backendCommand() {
  const bundled = app.isPackaged ? bundledBackendExecutable() : ''
  if (bundled) return { command: bundled, args: [], cwd: path.dirname(bundled), shell: false }
  return { command: findPython(), args: ['-m', 'desktop.backend_launcher'], cwd: projectRoot(), shell: false }
}

function portIsAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.once('listening', () => server.close(() => resolve(true)))
    server.listen(port, '127.0.0.1')
  })
}

function randomAvailablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.once('listening', () => {
      const address = server.address()
      server.close(() => resolve(address.port))
    })
    server.listen(0, '127.0.0.1')
  })
}

function requestHealth(baseUrl, timeoutMs = 1200) {
  return new Promise((resolve) => {
    const request = http.get(`${baseUrl}/health`, { timeout: timeoutMs }, (response) => {
      response.resume()
      resolve(response.statusCode >= 200 && response.statusCode < 500)
    })
    request.on('timeout', () => {
      request.destroy()
      resolve(false)
    })
    request.on('error', () => resolve(false))
  })
}

async function waitForBackend(baseUrl, timeoutMs = 45000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    if (await requestHealth(baseUrl)) return
    await new Promise((resolve) => setTimeout(resolve, 350))
  }
  throw new Error(`The local Story Pointer API did not become ready at ${baseUrl}.`)
}

async function chooseBackendPort() {
  const preferred = Number(process.env.STORYPOINTER_API_PORT || DEFAULT_DESKTOP_PORT)
  const preferredBase = `http://127.0.0.1:${preferred}`
  if (await requestHealth(preferredBase)) return { port: preferred, reuse: true }
  if (await portIsAvailable(preferred)) return { port: preferred, reuse: false }
  return { port: await randomAvailablePort(), reuse: false }
}

function attachPackagedLogs(child) {
  if (isDev) return
  const logPath = path.join(app.getPath('userData'), 'backend.log')
  const logStream = fs.createWriteStream(logPath, { flags: 'a' })
  child.stdout?.pipe(logStream, { end: false })
  child.stderr?.pipe(logStream, { end: false })
}

async function startBackend() {
  if (process.env.STORYPOINTER_EXTERNAL_API_URL) {
    apiBaseUrl = process.env.STORYPOINTER_EXTERNAL_API_URL.replace(/\/$/, '')
    return
  }

  const { port, reuse } = await chooseBackendPort()
  apiBaseUrl = `http://127.0.0.1:${port}`
  if (reuse) return

  const command = backendCommand()
  backendProcess = spawn(command.command, command.args, {
    cwd: command.cwd,
    env: desktopBackendEnv(port),
    shell: command.shell,
    stdio: isDev ? 'inherit' : ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  attachPackagedLogs(backendProcess)

  const failOnStartupExit = new Promise((_, reject) => {
    backendProcess.once('error', reject)
    backendProcess.once('exit', (code, signal) => {
      reject(new Error(`The local API process exited before startup completed (${signal || code}).`))
    })
  })

  await Promise.race([waitForBackend(apiBaseUrl), failOnStartupExit])
  backendProcess.removeAllListeners('error')
  backendProcess.removeAllListeners('exit')
  backendProcess.once('exit', (code, signal) => {
    if (!app.isQuitting && code !== 0) {
      dialog.showErrorBox('Story Pointer backend stopped', `The local API process exited unexpectedly (${signal || code}).`)
    }
  })
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1100,
    minHeight: 760,
    show: false,
    backgroundColor: '#f8fafd',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [`--storypointer-api-base=${apiBaseUrl}`],
    },
  })

  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_DEV_SERVER_URL)
    if (process.env.STORYPOINTER_OPEN_DEVTOOLS === 'true') mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', '..', 'dist', 'index.html'))
  }
}

function stopBackend() {
  if (!backendProcess || backendProcess.killed) return
  if (process.platform === 'win32' && backendProcess.pid) {
    spawn('taskkill', ['/pid', String(backendProcess.pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    })
    return
  }
  backendProcess.kill('SIGTERM')
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) app.quit()

app.on('second-instance', () => {
  if (!mainWindow) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.focus()
})

app.whenReady()
  .then(startBackend)
  .then(createMainWindow)
  .catch((error) => {
    dialog.showErrorBox('Story Pointer failed to start', error.stack || error.message || String(error))
    app.quit()
  })

app.on('before-quit', () => {
  app.isQuitting = true
  stopBackend()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && apiBaseUrl) createMainWindow()
})
