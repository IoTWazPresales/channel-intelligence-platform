# Restore a cip dump into an existing disposable DB owned by cip, verify, optionally wipe.
# Preferred when the app role lacks CREATEDB (local Windows default).
param(
  [Parameter(Mandatory = $true)][string]$DumpPath,
  [string]$TargetUrl = "postgresql://cip:cip@127.0.0.1:5432/cip_alembic_smoke",
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  [switch]$SkipWipe
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $DumpPath)) { throw "Dump not found: $DumpPath" }

$psql = Join-Path $PgBin "psql.exe"
$pgRestore = Join-Path $PgBin "pg_restore.exe"
if (-not (Test-Path $psql)) { throw "psql not found at $psql" }
if (-not (Test-Path $pgRestore)) { throw "pg_restore not found at $pgRestore" }

$db = (& $psql -d $TargetUrl -tAc "SELECT current_database();").Trim()
if ($db -eq "cip") { throw "Refusing to restore onto live cip. Pass a disposable -TargetUrl." }
if ($db -eq "postgres") { throw "Refusing to restore onto postgres." }

Write-Host "Target database=$db"
if (-not $SkipWipe) {
  Write-Host "Wiping public schema on $db"
  & $psql -d $TargetUrl -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public AUTHORIZATION CURRENT_USER; GRANT ALL ON SCHEMA public TO CURRENT_USER; GRANT ALL ON SCHEMA public TO public;"
}

Write-Host "Restoring $DumpPath -> $db"
& $pgRestore --no-owner --no-privileges -d $TargetUrl $DumpPath

$products = (& $psql -d $TargetUrl -tAc "SELECT count(*) FROM dim_product;").Trim()
$jobs = (& $psql -d $TargetUrl -tAc "SELECT count(*) FROM import_job;").Trim()
$alembic = (& $psql -d $TargetUrl -tAc "SELECT version_num FROM alembic_version LIMIT 1;").Trim()
$liveProducts = (& $psql -d "postgresql://cip:cip@127.0.0.1:5432/cip" -tAc "SELECT count(*) FROM dim_product;").Trim()

Write-Host "RESTORE_SMOKE_OK database=$db dim_product=$products import_job=$jobs alembic=$alembic live_cip_dim_product=$liveProducts"
if ($products -ne $liveProducts) {
  Write-Host "NOTE: restored dim_product count differs from live cip (dump may be older than live)."
}
