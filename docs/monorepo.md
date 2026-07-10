# Monorepo Layout

Story Pointer is organized as one repository with three runnable projects:

| Project | Path | Owner | Main commands |
|---|---|---|---|
| API | `backend/` | FastAPI, LangGraph, SQLite, Jira, planning exports | `npm run api:dev`, `npm run api:test` |
| Web | `frontend/` | React 19, Vite, Material 3 shell, C4 canvas | `npm run web:dev`, `npm run web:test`, `npm run web:build` |
| Desktop | `desktop/` | Electron shell, PyInstaller backend bundle | `npm run desktop:dev`, `npm run desktop:build:win` |

The root `package.json` is an orchestrator. Node dependencies belong to the Node workspace that uses them:

- `frontend/package.json` owns browser dependencies and Vitest.
- `desktop/package.json` owns Electron, Electron Builder, and desktop packaging helpers.
- Python dependencies remain in `requirements.txt` and `requirements-desktop.txt`.

## Execute

From the repository root:

```powershell
# API + web together
.\scripts\run-monorepo.ps1 dev

# one project at a time
.\scripts\run-monorepo.ps1 api
.\scripts\run-monorepo.ps1 web
.\scripts\run-monorepo.ps1 desktop-dev

# verification
.\scripts\run-monorepo.ps1 test
.\scripts\run-monorepo.ps1 build
```

Equivalent npm commands:

```powershell
npm run dev:all
npm run api:dev
npm run web:dev
npm run desktop:dev
npm run test:all
npm run build
```

## Boundaries

- Frontend code talks to the backend only through `frontend/src/api/client.js`.
- Backend code does not import frontend or desktop code.
- Desktop code is a runtime shell: it starts or connects to an API and loads the built or dev web UI.
- Shared automation that touches multiple projects lives in `scripts/`.
