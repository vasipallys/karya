const { parentPort, workerData } = require("node:worker_threads");

const agents = [
  ["Repo Parser", "Mapping repository structure"],
  ["Requirements", "Extracting actors and capabilities"],
  ["C4 Modeler", "Composing architecture levels"],
  ["UML Generator", "Deriving behavioral views"],
  ["Linker", "Connecting code and diagrams"],
  ["Layout", "Optimizing visual hierarchy"],
  ["Validation", "Checking architecture drift"],
];

let tick = 0;
const modeOffset = workerData?.mode === "repository" ? 0 : 1;
const timer = setInterval(() => {
  tick += 1;
  const states = agents.map(([name, detail], index) => {
    const progress = Math.max(0, Math.min(100, (tick - index * 3 + modeOffset) * 7));
    return {
      id: `agent-${index}`,
      name,
      detail: progress === 100 ? "Task completed" : detail,
      progress,
      status: progress === 100 ? "complete" : progress > 0 ? "working" : "queued",
    };
  });
  const complete = states.every((agent) => agent.status === "complete");
  parentPort.postMessage({
    agents: states,
    log: states.findLast((agent) => agent.status === "working")?.detail || "Architecture model is ready",
    complete,
  });
  if (complete) {
    clearInterval(timer);
    parentPort.close();
  }
}, 350);
