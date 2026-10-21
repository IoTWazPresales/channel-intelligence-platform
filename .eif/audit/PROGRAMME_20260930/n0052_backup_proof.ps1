# N-0052 restore proof. Read-only on cip. Restore lands on the disposable clone.
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$pgBin = Join-Path $env:ProgramFiles "PostgreSQL\18\bin"
$psql = Join-Path $pgBin "psql.exe"
if (-not (Test-Path $psql)) { throw "psql not found" }
$env:PGPASSWORD = "cip"
$db = (& $psql -h 127.0.0.1 -p 5432 -U cip -d cip -tAc "SELECT current_database();").Trim()
Write-Host "Read-only source current_database=$db"
if ($db -ne "cip") { throw "Refusing dump: current_database()=$db expected cip" }

$dumpSw = [Diagnostics.Stopwatch]::StartNew()
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts/ops/backup_cip.ps1")
if ($LASTEXITCODE -ne 0) { throw "backup_cip.ps1 exited $LASTEXITCODE" }
$dumpSw.Stop()

$dumpDir = Join-Path $root ".tmp\backups"
$dump = Get-ChildItem (Join-Path $dumpDir "cip_*.dump") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $dump) { throw "dump file missing" }

$restoreSw = [Diagnostics.Stopwatch]::StartNew()
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts/ops/restore_cip_smoke.ps1") -DumpPath $dump.FullName
if ($LASTEXITCODE -ne 0) { throw "restore_cip_smoke.ps1 exited $LASTEXITCODE" }
$restoreSw.Stop()

$proof = Join-Path $PSScriptRoot "n0052_restore_proof.txt"
@(
  "current_database=$db"
  "dump_name=$($dump.Name)"
  "dump_bytes=$($dump.Length)"
  "dump_elapsed_sec=$([math]::Round($dumpSw.Elapsed.TotalSeconds, 1))"
  "restore_elapsed_sec=$([math]::Round($restoreSw.Elapsed.TotalSeconds, 1))"
) | Set-Content -Encoding utf8 $proof
Write-Host "PROOF_WRITTEN"
