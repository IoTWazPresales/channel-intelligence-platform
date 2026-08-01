# Backup local cip database (custom format).
param(
  [string]$DatabaseUrl = "postgresql://cip:cip@127.0.0.1:5432/cip",
  [string]$OutDir = "",
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $OutDir) {
  $OutDir = Join-Path $root ".tmp\backups"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $OutDir "cip_$stamp.dump"

$pgDump = Join-Path $PgBin "pg_dump.exe"
if (-not (Test-Path $pgDump)) {
  $cmd = Get-Command pg_dump -ErrorAction SilentlyContinue
  if ($cmd) { $pgDump = $cmd.Source } else { throw "pg_dump not found. Set -PgBin to your PostgreSQL bin directory." }
}

Write-Host "Dumping $DatabaseUrl -> $out"
& $pgDump -Fc -d $DatabaseUrl -f $out
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit $LASTEXITCODE" }
Write-Host "OK dump size=$((Get-Item $out).Length) bytes path=$out"
Write-Host $out
