# D-d (Warren, 2026-09-23): move untracked scratch files to an archive folder OUTSIDE the repo. Never deletes.
# Run from the repo root in PowerShell:  .\.eif\audit\PROGRAMME_20260924\n0045\archive_untracked.ps1
# Dry run first (default); add -Apply to move.  List: archive_list.final.txt (105 paths, classified 2026-09-24).
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$repo = (Get-Location).Path
$dest = 'C:\Users\warren_eliason\cip-untracked-archive-20260924'
$list = Join-Path $PSScriptRoot 'archive_list.final.txt'
$moved = 0; $missing = 0; $tracked = 0
foreach ($rel in Get-Content $list) {
  if (-not $rel) { continue }
  $rel = $rel.TrimEnd('/')
  $src = Join-Path $repo $rel
  if (-not (Test-Path -LiteralPath $src)) { $missing++; continue }
  git ls-files --error-unmatch -- $rel 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { Write-Warning "tracked, skipped: $rel"; $tracked++; continue }
  $target = Join-Path $dest $rel
  if ($Apply) {
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Move-Item -LiteralPath $src -Destination $target
  } else { Write-Host "would move: $rel" }
  $moved++
}
Write-Host ("{0}: {1} to move, {2} missing, {3} tracked-skipped. Destination {4}" -f ($(if ($Apply) {'APPLIED'} else {'DRY RUN'})), $moved, $missing, $tracked, $dest)
