# Restore a cip dump into an existing disposable DB owned by cip, verify, optionally wipe.
# Preferred when the app role lacks CREATEDB (local Windows default).
#
# Safety (review round 1): this script wipes the target's public schema, so it does its own checks and
# does not rely on its caller. It refuses a target URL that is not a plain postgresql:// URL, one whose
# query string could change the database or connection target, cip, cip_test, postgres, the templates,
# the backed-up database (-SourceUrl) and any name that does not say it is disposable; and it asks the
# server for current_database() and re-checks that name before wiping anything.
#
# Success: every native step (current_database, schema wipe, pg_restore, the count queries) must exit 0.
# RESTORE_SMOKE_OK is printed only then and the script ends with exit 0; any failure throws (exit 1).
param(
  [Parameter(Mandatory = $true)][string]$DumpPath,
  [string]$TargetUrl = "postgresql://cip:cip@127.0.0.1:5432/cip_alembic_smoke",
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  # The database the dump was taken from. Used to refuse restoring onto it and for the parity count.
  [Parameter(Mandatory = $true)][string]$SourceUrl,
  [switch]$SkipWipe
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nightly_backup_lib.ps1")

if (-not (Test-Path $DumpPath)) { throw "Dump not found: $DumpPath" }

$refusal = Get-RestoreTargetRefusal -TargetUrl $TargetUrl -SourceUrl $SourceUrl
if ($refusal) { throw "Refusing to restore. $refusal" }
$urlDb = Get-EffectiveDatabaseName $TargetUrl

$psql = Join-Path $PgBin "psql.exe"
$pgRestore = Join-Path $PgBin "pg_restore.exe"
if (-not (Test-Path $psql)) { throw "psql not found at $psql" }
if (-not (Test-Path $pgRestore)) { throw "pg_restore not found at $pgRestore" }

function Invoke-PsqlScalar {
  # One psql query -> trimmed single value. Throws on a non-zero exit or an empty result.
  param([string]$Url, [string]$Sql, [string]$What)
  $global:LASTEXITCODE = $null
  $out = & $psql -d $Url -v ON_ERROR_STOP=1 -tAc $Sql | Out-String
  if ($LASTEXITCODE -ne 0) { throw "$What failed (psql exit $LASTEXITCODE)" }
  $v = $out.Trim()
  if ([string]::IsNullOrWhiteSpace($v)) { throw "$What returned no value" }
  return $v
}

# Verify both actual identities before any destructive command. An unexpected proxy mapping must
# not let a disposable-looking source URL bypass the same-source protection.
$sourceDb = Invoke-PsqlScalar $SourceUrl "SELECT current_database();" "current_database() on the source"
if ($sourceDb.ToLowerInvariant() -ne (Get-EffectiveDatabaseName $SourceUrl)) {
  throw "Refusing to restore: the source server database does not match its URL."
}
$db = Invoke-PsqlScalar $TargetUrl "SELECT current_database();" "current_database() on the target"
if ($db.ToLowerInvariant() -ne $urlDb) { throw "Refusing to restore: the server connected to '$db' but the URL names '$urlDb'." }
$nameRefusal = Get-DisposableDatabaseNameRefusal -Database $db -SourceUrl $SourceUrl
if ($nameRefusal) { throw "Refusing to restore. Connected database: $nameRefusal" }

Write-Host "Target database=$db"
if (-not $SkipWipe) {
  Write-Host "Wiping public schema on $db"
  $global:LASTEXITCODE = $null
  & $psql -d $TargetUrl -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public AUTHORIZATION CURRENT_USER; GRANT ALL ON SCHEMA public TO CURRENT_USER; GRANT ALL ON SCHEMA public TO public;"
  if ($LASTEXITCODE -ne 0) { throw "Schema wipe failed (psql exit $LASTEXITCODE); the restore did not run." }
}

Write-Host "Restoring $DumpPath -> $db"
$global:LASTEXITCODE = $null
& $pgRestore --exit-on-error --no-owner --no-privileges -d $TargetUrl $DumpPath
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed (exit $LASTEXITCODE); the restored database is incomplete or has errors." }

$products = Invoke-PsqlScalar $TargetUrl "SELECT count(*) FROM dim_product;" "dim_product count"
$jobs = Invoke-PsqlScalar $TargetUrl "SELECT count(*) FROM import_job;" "import_job count"
$alembic = Invoke-PsqlScalar $TargetUrl "SELECT version_num FROM alembic_version LIMIT 1;" "alembic_version read"
$liveProducts = Invoke-PsqlScalar $SourceUrl "SELECT count(*) FROM dim_product;" "dim_product count on the source"
foreach ($n in @($products, $jobs, $liveProducts)) { if ($n -notmatch '^\d+$') { throw "A count query returned '$n', not a number." } }
if ($alembic -notmatch '^\S+$') { throw "alembic_version returned '$alembic'." }

Write-Host "RESTORE_SMOKE_OK database=$db dim_product=$products import_job=$jobs alembic=$alembic live_cip_dim_product=$liveProducts"
if ($products -ne $liveProducts) {
  Write-Host "NOTE: restored dim_product count differs from live cip (dump may be older than live)."
}
exit 0
