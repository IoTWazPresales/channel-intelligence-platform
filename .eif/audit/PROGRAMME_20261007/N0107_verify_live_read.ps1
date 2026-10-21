# N-0107 GOV-008 (RUN-20261008-N0107-VER) read-only helper: prints the link section of the supervisor's status.json and
# whether the rendered link.html carries the blocked note. Same files and folder the status script reads; writes nothing.
$stateDir = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$statusFile = Join-Path $stateDir 'status.json'
$linkFile = Join-Path $stateDir 'link.html'
foreach ($f in @($statusFile, $linkFile)) { "{0} exists={1} modified={2}" -f (Split-Path -Leaf $f), (Test-Path $f), $(if (Test-Path $f) { (Get-Item $f).LastWriteTime.ToString('s') }) }
$s = $null
foreach ($i in 1..5) { try { $s = Get-Content -Raw -Path $statusFile -ErrorAction Stop | ConvertFrom-Json; break } catch { Start-Sleep -Milliseconds 300 } }
if ($s) {
    "status.json heartbeat={0}" -f $s.supervisor.heartbeat
    "status.json link.blocked_reason={0}" -f $s.link.blocked_reason
    "status.json link.blocked_since={0}" -f $s.link.blocked_since
    "status.json link.next_fresh_attempt={0}" -f $s.link.next_fresh_attempt
    "status.json link.public_login={0} public_auth_me={1} checked={2}" -f $s.link.public_login, $s.link.public_auth_me, $s.link.public_checked
    "status.json components.tunnel.state={0} launches={1}" -f $s.components.tunnel.state, $s.components.tunnel.launches
} else { 'status.json unreadable' }
$h = $null
foreach ($i in 1..5) { try { $h = Get-Content -Raw -Path $linkFile -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 300 } }
if ($h) {
    "link.html has blocked note div: {0}" -f $h.Contains("<div class='blocked'>")
    "link.html note names the reason: {0}" -f $h.Contains('network blocks tunnel port 7844 (outbound TCP)')
    "link.html tunnel row styled warn/blocked: {0}" -f $h.Contains("<td class='warn'>blocked</td>")
    $m = [regex]::Match($h, "<div class='blocked'>[^<]*</div>")
    if ($m.Success) { "link.html note text: " + $m.Value }
} else { 'link.html unreadable' }

# The product detector on the live cloudflared err log (read with full sharing by the product's own Read-LogTail).
$src = Join-Path $PSScriptRoot '..\..\..\scripts\cip-supervisor.ps1'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $src).Path, [ref]$tokens, [ref]$errs)
foreach ($name in @('Read-LogTail', 'Get-TunnelNetworkVerdict')) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    . ([scriptblock]::Create($fn.Extent.Text))
}
$logDir = Join-Path $stateDir 'logs'
$f = Get-ChildItem -Path $logDir -Filter 'tunnel*.err.log' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name.EndsWith('.err.log') } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($f) {
    $lines = @(Read-LogTail $f.FullName 65536)
    "live err log {0} modified={1} lines={2}" -f $f.Name, $f.LastWriteTime.ToString('s'), $lines.Count
    $regIdx = -1; for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].Contains('Registered tunnel connection')) { $regIdx = $i } }
    "registered lines: {0}" -f @($lines | Where-Object { $_.Contains('Registered tunnel connection') }).Count
    "7844 i/o timeout lines: total {0}; after last registered {1}" -f @($lines | Where-Object { $_.Contains('dial tcp ') -and $_.Contains(':7844: i/o timeout') }).Count,
        @($lines | Select-Object -Skip ($regIdx + 1) | Where-Object { $_.Contains('dial tcp ') -and $_.Contains(':7844: i/o timeout') }).Count
    if ($regIdx -ge 0) { "last registered line (ids trimmed): " + ($lines[$regIdx] -replace 'connection=[0-9a-f-]+', 'connection=<id>') }
    "detector verdict on live tail: " + (Get-TunnelNetworkVerdict $lines 6)
} else { 'no tunnel err log found' }
