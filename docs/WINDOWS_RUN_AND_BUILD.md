# Running Karya and creating a Windows EXE

This guide explains how to run Karya during development, test the production
build, and create an installable Windows `.exe`.

## 1. Prerequisites

Install these tools before continuing:

- **Windows 10 or Windows 11, 64-bit**
- **Node.js 22 LTS or newer**, including npm
- **Python 3.10 or newer** for repository static analysis
- **Git** for cloning and analyzing repositories
- **Visual Studio Code** is optional; Karya uses its `code --goto` command for
  source-link navigation when available

Verify the tools in PowerShell:

```powershell
node --version
npm --version
python --version
git --version
```

## 2. Install project dependencies

Open PowerShell in the project directory:

```powershell
cd D:\vasipallys-github\karya
npm install
```

Run `npm install` again whenever `package.json` or `package-lock.json` changes.

## 3. Run in development mode

```powershell
npm run dev
```

This command starts the Vite development server and opens the Electron desktop
window. Changes under `src/` are refreshed automatically.

To preview only the React interface in a browser:

```powershell
npm run dev:web
```

Then open <http://127.0.0.1:5173>.

Stop either command with `Ctrl+C`.

## 4. Test the production application locally

Build the renderer:

```powershell
npm run build
```

The command performs TypeScript validation and writes the optimized renderer to
`dist/`.

Launch Electron against that production build:

```powershell
npm start
```

Run `npm run build` again after changing renderer code.

## 5. Create the Windows installer EXE

Run:

```powershell
npm run dist:win
```

The packaging process:

1. Type-checks and builds the React renderer.
2. Packages Electron, the desktop process, preload bridge, and worker thread.
3. Copies the Python analyzer into the application resources.
4. Creates a 64-bit NSIS installer.

The resulting file is:

```text
release\Karya-Setup-0.1.0.exe
```

The `release\win-unpacked\` directory also contains the unpacked application
used by the installer.

## 6. Install and run the EXE

1. Double-click `release\Karya-Setup-0.1.0.exe`.
2. Choose an installation directory.
3. Complete the installer.
4. Launch **Karya** from the desktop shortcut or Start menu.

The installer does not delete Karya's local metadata when uninstalling. Diagram
metadata is stored in Electron's Windows application-data directory.

## 7. Create an unpacked build without an installer

For a faster packaging smoke test:

```powershell
npm run pack
```

Run the result directly:

```powershell
.\release\win-unpacked\Karya.exe
```

## 8. Versioning the installer

Update the `version` field in `package.json` before creating a release:

```json
{
  "version": "0.2.0"
}
```

Then run `npm install` to synchronize `package-lock.json`, followed by:

```powershell
npm run dist:win
```

The artifact name will become `Karya-Setup-0.2.0.exe`.

## 9. Code signing for distribution

The locally generated installer is unsigned. Windows SmartScreen may warn users
when they run an unsigned installer downloaded from another computer.

For public distribution, obtain a Windows code-signing certificate and provide
it to electron-builder:

```powershell
$env:CSC_LINK = "C:\certificates\karya-signing.pfx"
$env:CSC_KEY_PASSWORD = "certificate-password"
npm run dist:win
```

Do not commit certificates or passwords to Git.

## 10. Troubleshooting

### Port 5173 is already in use

Stop the process using the development port, then run `npm run dev` again:

```powershell
Get-NetTCPConnection -LocalPort 5173
Stop-Process -Id <PID>
```

Only stop a PID after confirming it belongs to the stale Vite process.

### The desktop window is blank in development

Confirm that Vite printed `http://127.0.0.1:5173`, close both processes with
`Ctrl+C`, and rerun:

```powershell
npm run dev
```

### Repository analysis reports that Python is missing

Install Python and ensure `python.exe` is available on `PATH`:

```powershell
python --version
```

Restart PowerShell and Karya after changing `PATH`.

### Source links do not open in Visual Studio Code

Install the VS Code shell command and verify:

```powershell
code --version
```

Karya falls back to the Windows file association when the command is not
available.

### Windows displays a SmartScreen warning

This is expected for an unsigned local installer. For distribution outside the
development team, sign the application as described in the code-signing section.

### Clean rebuild

Delete only generated dependencies and outputs, then reinstall:

```powershell
Remove-Item -Recurse -Force node_modules, dist, release
npm install
npm run dist:win
```

Do not delete the project source directories.
