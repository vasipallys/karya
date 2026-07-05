# karya

Karya is a tactile, AI-assisted architecture workspace for turning requirements and
source repositories into living C4 and UML models.

## Quick start

```bash
npm install
npm run dev
```

Use `npm run dev:web` to preview only the React renderer, or `npm run build` to
type-check and produce the renderer bundle used by Electron.

## Create the Windows installer

```bash
npm run dist:win
```

The generated installer is written to `release/Karya-Setup-0.1.0.exe`.

See the complete [Windows run and packaging guide](docs/WINDOWS_RUN_AND_BUILD.md)
for prerequisites, development and production commands, installer behavior,
code signing, and troubleshooting.

## Included architecture

- Electron main process with a secure context-isolated preload bridge
- React + TypeScript renderer and custom SVG diagram engine
- Worker-thread agent pipeline with seven visible architecture agents
- SQLite metadata and node-to-code mapping schema, with JSON fallback
- Bundled Python static-analysis worker for Python, TypeScript/JavaScript, Java,
  C#, and Go repository indexing
- Requirements and Git/Bitbucket repository workflows
- Living source links, architecture drift states, branch/commit context, settings,
  and SVG/HTML/model export surfaces

Provider authentication, hosted LLM calls, and remote Git OAuth are intentionally
isolated behind the desktop IPC boundaries so production credentials can be added
without exposing them to the renderer.
