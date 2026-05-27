# Poll job 733 DSI revalidate until complete; write results JSON for agent pickup.
$outPath = Join-Path $PSScriptRoot ".revalidate-733-results.json"
$logPath = Join-Path $PSScriptRoot ".revalidate-733-poll.log"
$api = "http://localhost:8001/api/v1"

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $logPath -Value $line -Encoding utf8
    Write-Output $line
}

Write-Log "poll started"

$lastPhase = ""
for ($i = 0; $i -lt 80; $i++) {
    try {
        $bt = Invoke-RestMethod "$api/imports/background-tasks?limit=3" -TimeoutSec 30
        $t = $bt.tasks | Where-Object { $_.import_job_id -eq 733 } | Select-Object -First 1
        if (-not $t) {
            Write-Log "no task for job 733 in background-tasks (active_count=$($bt.active_count))"
            Start-Sleep -Seconds 45
            continue
        }
        if ($t.phase -ne $lastPhase) {
            Write-Log "phase change -> $($t.phase) pct=$($t.pct) status=$($t.status)"
            $lastPhase = $t.phase
        } else {
            Write-Log "poll $($i+1): phase=$($t.phase) row=$($t.current_row)/$($t.total_rows) pct=$($t.pct)% status=$($t.status)"
        }
        if ($t.status -ne "running") {
            Write-Log "task finished status=$($t.status)"
            break
        }
    } catch {
        Write-Log "poll error: $_"
    }
    Start-Sleep -Seconds 45
}

# Verification payload
$results = @{
    polled_at = (Get-Date).ToUniversalTime().ToString("o")
    background_task = $t
    dsi_progress = $null
    possible_duplicates_total = $null
    duplicate_unresolved_total = $null
    adriane = @()
    sample_match_bases = @()
    bcs_hints = $null
    tb_hints = $null
    errors = @()
}

try {
    $results.dsi_progress = Invoke-RestMethod "$api/imports/jobs/733/dsi-progress" -TimeoutSec 30
} catch { $results.errors += "dsi-progress: $_" }

try {
    $pd = Invoke-RestMethod "$api/mappings/import-jobs/733/distributor-si-candidates?status=open&entity=customer&possible_duplicates_only=1&limit=10"
    $results.possible_duplicates_total = $pd.total
    foreach ($item in $pd.items) {
        $hints = $item.context.possible_duplicate_of
        if ($hints) {
            foreach ($h in $hints) {
                if ($h.match_basis -and $results.sample_match_bases -notcontains $h.match_basis) {
                    $results.sample_match_bases += $h.match_basis
                }
            }
        }
    }
} catch { $results.errors += "possible_duplicates: $_" }

try {
    $ur = Invoke-RestMethod "$api/mappings/import-jobs/733/distributor-si-candidates?status=open&entity=customer&duplicate_unresolved_only=1&limit=5"
    $results.duplicate_unresolved_total = $ur.total
} catch { $results.errors += "duplicate_unresolved: $_" }

try {
    $all = Invoke-RestMethod "$api/mappings/import-jobs/733/distributor-si-candidates?status=open&entity=customer&limit=1000"
    foreach ($item in $all.items) {
        if ($item.normalized_key -like "*adriane*") {
            $bases = @()
            $hints = $item.context.possible_duplicate_of
            if ($hints) { $bases = @($hints | ForEach-Object { $_.match_basis }) }
            $results.adriane += @{
                key = $item.normalized_key
                hint_bases = $bases
                status = $item.status
            }
        }
        if ($item.normalized_key -match "^(bcs|rbs)\b" -or $item.dealer_group_token -match "^(bcs|rbs)\b") {
            if ($item.context.possible_duplicate_of) { $results.bcs_hints = "UNEXPECTED: $($item.normalized_key)" }
        }
        if ($item.normalized_key -like "*tb computer*" -or $item.normalized_key -like "*tb solution*") {
            if ($item.context.possible_duplicate_of) { $results.tb_hints = "UNEXPECTED: $($item.normalized_key)" }
        }
    }
    # broader scan for bcs/tb if not in first 1000
    if ($results.possible_duplicates_total -gt 0) {
        $scan = Invoke-RestMethod "$api/mappings/import-jobs/733/distributor-si-candidates?status=open&entity=customer&possible_duplicates_only=1&limit=500"
        foreach ($item in $scan.items) {
            $k = $item.normalized_key
            if ($k -match "bcs|rbs|tb computer|tb solution") {
                if ($item.context.possible_duplicate_of) {
                    if ($k -match "bcs|rbs") { $results.bcs_hints = $k }
                    if ($k -match "tb computer|tb solution") { $results.tb_hints = $k }
                }
            }
        }
    }
} catch { $results.errors += "adriane_scan: $_" }

$results | ConvertTo-Json -Depth 8 | Set-Content -Path $outPath -Encoding utf8
Write-Log "wrote $outPath"
Write-Log "DONE possible_duplicates=$($results.possible_duplicates_total) unresolved=$($results.duplicate_unresolved_total) bases=$($results.sample_match_bases -join ',')"
