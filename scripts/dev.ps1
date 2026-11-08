# Global AI Investor - dev launcher (P0)
$ErrorActionPreference = 'Stop'
$root = 'F:\GlobalAIInvestor'
$node = Join-Path $root 'tools\node'
$env:Path = "$node;$env:Path"

Write-Host "[dev] node: $(& (Join-Path $node 'node.exe') -v) / npm: $(& (Join-Path $node 'npm.cmd') -v)" -ForegroundColor Cyan
Set-Location $root

# 关键：某些环境（如 DSH / WorkBuddy 终端）会设置 ELECTRON_RUN_AS_NODE=1，
# 这会让 electron.exe 以纯 Node 模式运行，导致 require('electron').app 为 undefined。
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "Python venv not found: $py" }
$env:GAI_PYTHON = $py

Write-Host "[dev] starting vite + electron ..." -ForegroundColor Cyan
& (Join-Path $node 'npm.cmd') run dev
