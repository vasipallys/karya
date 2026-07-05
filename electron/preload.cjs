const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("karya", {
  platform: process.platform,
  listAgents: () => ipcRenderer.invoke("agents:list"),
  runPipeline: (input) => ipcRenderer.invoke("agents:run", input),
  stopPipeline: () => ipcRenderer.invoke("agents:stop"),
  onAgentUpdate: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("agents:update", listener);
    return () => ipcRenderer.removeListener("agents:update", listener);
  },
  saveDiagram: (diagram) => ipcRenderer.invoke("diagram:save", diagram),
  loadDiagrams: () => ipcRenderer.invoke("diagram:list"),
  exportDiagram: (payload) => ipcRenderer.invoke("diagram:export", payload),
  openCode: (target) => ipcRenderer.invoke("code:open", target),
  chooseRepository: () => ipcRenderer.invoke("repo:choose"),
  analyzeRepository: (root) => ipcRenderer.invoke("repo:analyze", root),
});
