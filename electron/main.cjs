const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const { Worker } = require("node:worker_threads");
const fs = require("node:fs");
const path = require("node:path");

const isDev = process.argv.includes("--dev");
let mainWindow;
let pipelineWorker;

const agentSeed = [
  ["Repo Parser", "Mapping repository structure"],
  ["Requirements", "Extracting actors and capabilities"],
  ["C4 Modeler", "Composing architecture levels"],
  ["UML Generator", "Deriving behavioral views"],
  ["Linker", "Connecting code and diagrams"],
  ["Layout", "Optimizing visual hierarchy"],
  ["Validation", "Checking architecture drift"],
];

function createStore() {
  const userData = app.getPath("userData");
  const fallbackPath = path.join(userData, "karya-diagrams.json");
  try {
    const { DatabaseSync } = require("node:sqlite");
    const db = new DatabaseSync(path.join(userData, "karya.sqlite"));
    db.exec(`
      CREATE TABLE IF NOT EXISTS diagrams (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        commit_sha TEXT,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS code_links (
        node_id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        line_start INTEGER,
        line_end INTEGER,
        commit_sha TEXT
      );
    `);
    return {
      list: () => db.prepare("SELECT payload FROM diagrams ORDER BY updated_at DESC").all().map((row) => JSON.parse(row.payload)),
      save: (item) => db.prepare(`
        INSERT INTO diagrams(id,name,type,commit_sha,payload,updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
      `).run(item.id, item.name, item.type, item.commitSha || "", JSON.stringify(item), new Date().toISOString()),
    };
  } catch (error) {
    console.warn("SQLite unavailable, using local JSON store:", error.message);
    return {
      list: () => {
        try { return JSON.parse(fs.readFileSync(fallbackPath, "utf8")); } catch { return []; }
      },
      save: (item) => {
        let items = [];
        try { items = JSON.parse(fs.readFileSync(fallbackPath, "utf8")); } catch {}
        const index = items.findIndex((entry) => entry.id === item.id);
        index >= 0 ? items[index] = item : items.unshift(item);
        fs.writeFileSync(fallbackPath, JSON.stringify(items, null, 2));
      },
    };
  }
}

let store;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#F0F4F8",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 18 },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  if (isDev) mainWindow.loadURL("http://127.0.0.1:5173");
  else mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

app.whenReady().then(() => {
  store = createStore();
  createWindow();
  app.on("activate", () => BrowserWindow.getAllWindows().length === 0 && createWindow());
});
app.on("window-all-closed", () => process.platform !== "darwin" && app.quit());

ipcMain.handle("agents:list", () => agentSeed.map(([name, detail], index) => ({
  id: `agent-${index}`, name, detail, progress: 0, status: "idle",
})));

ipcMain.handle("agents:run", (_event, input) => {
  pipelineWorker?.terminate();
  pipelineWorker = new Worker(path.join(__dirname, "agent-worker.cjs"), { workerData: input || {} });
  pipelineWorker.on("message", (payload) => mainWindow?.webContents.send("agents:update", payload));
  pipelineWorker.on("error", (error) => mainWindow?.webContents.send("agents:update", {
    agents: [],
    log: `Agent worker failed: ${error.message}`,
    complete: true,
  }));
  return { started: true };
});

ipcMain.handle("agents:stop", () => {
  pipelineWorker?.terminate();
  pipelineWorker = undefined;
  return { stopped: true };
});

ipcMain.handle("diagram:list", () => store.list());
ipcMain.handle("diagram:save", (_event, diagram) => {
  store.save(diagram);
  return { saved: true };
});

ipcMain.handle("diagram:export", async (_event, { svg, suggestedName }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: `${suggestedName || "karya-architecture"}.svg`,
    filters: [{ name: "Scalable Vector Graphic", extensions: ["svg"] }],
  });
  if (result.canceled || !result.filePath) return { canceled: true };
  fs.writeFileSync(result.filePath, svg, "utf8");
  return { path: result.filePath };
});

ipcMain.handle("repo:choose", async () => {
  const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("repo:analyze", (_event, root) => new Promise((resolve, reject) => {
  if (!root || typeof root !== "string") return reject(new Error("A repository path is required"));
  const script = app.isPackaged
    ? path.join(process.resourcesPath, "python", "analysis_service.py")
    : path.join(__dirname, "..", "python", "analysis_service.py");
  const python = spawn(process.platform === "win32" ? "python" : "python3", [script], {
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  let output = "";
  let error = "";
  python.stdout.on("data", (chunk) => { output += chunk.toString(); });
  python.stderr.on("data", (chunk) => { error += chunk.toString(); });
  python.on("error", reject);
  python.on("close", (code) => {
    if (code !== 0) return reject(new Error(error || `Analyzer exited with ${code}`));
    try { resolve(JSON.parse(output.trim())); } catch (parseError) { reject(parseError); }
  });
  python.stdin.end(`${JSON.stringify({ action: "analyze", root })}\n`);
}));

ipcMain.handle("code:open", async (_event, target) => {
  if (!target?.path) return { opened: false };
  const line = Number.isFinite(target.line) ? target.line : 1;
  try {
    const child = spawn("code", ["--goto", `${target.path}:${line}:1`], {
      detached: true,
      stdio: "ignore",
      shell: process.platform === "win32",
    });
    child.unref();
    return { opened: true, editor: "vscode" };
  } catch {
    await shell.openPath(target.path);
    return { opened: true, editor: "system" };
  }
});
