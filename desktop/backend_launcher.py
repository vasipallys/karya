"""Entry point used by Electron and PyInstaller to run the FastAPI backend."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("STORYPOINTER_API_HOST", "127.0.0.1")
    port = int(os.getenv("STORYPOINTER_API_PORT", "8765"))
    log_level = os.getenv("STORYPOINTER_LOG_LEVEL", "info")
    uvicorn.run("backend.api.main:app", host=host, port=port, log_level=log_level, reload=False)


if __name__ == "__main__":
    main()
