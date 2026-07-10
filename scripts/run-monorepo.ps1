[CmdletBinding()]
param(
  [ValidateSet('dev', 'web', 'api', 'desktop-dev', 'test', 'build', 'seed-demo', 'seed-banking')]
  [string]$Task = 'dev'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-RepoCommand {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Command,
    [string[]]$Arguments = @()
  )

  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

switch ($Task) {
  'dev' {
    Invoke-RepoCommand 'Starting API and web app' 'npm' @('run', 'dev:all')
  }
  'web' {
    Invoke-RepoCommand 'Starting web app' 'npm' @('run', 'web:dev')
  }
  'api' {
    Invoke-RepoCommand 'Starting API' 'npm' @('run', 'api:dev')
  }
  'desktop-dev' {
    Invoke-RepoCommand 'Starting Electron desktop app' 'npm' @('run', 'desktop:dev')
  }
  'test' {
    Invoke-RepoCommand 'Running API and web tests' 'npm' @('run', 'test:all')
  }
  'build' {
    Invoke-RepoCommand 'Building web app' 'npm' @('run', 'build')
  }
  'seed-demo' {
    Invoke-RepoCommand 'Seeding demo project' 'npm' @('run', 'api:seed:demo')
  }
  'seed-banking' {
    Invoke-RepoCommand 'Seeding banking sample' 'npm' @('run', 'api:seed:banking')
  }
}
