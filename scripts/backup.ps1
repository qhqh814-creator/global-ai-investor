# Global AI Investor - database backup (P0)
param(
  [string]$Root = 'F:\GlobalAIInvestor'
)
$ErrorActionPreference = 'Stop'
$db = Join-Path $Root 'data\db\gai.db'
if (-not (Test-Path $db)) { Write-Host '[backup] no database yet'; exit 0 }
$dest = Join-Path $Root 'backups\db'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $dest "gai-$stamp.db"
Copy-Item -LiteralPath $db -Destination $target -Force
$sha = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "[backup] $target sha256=$sha"
