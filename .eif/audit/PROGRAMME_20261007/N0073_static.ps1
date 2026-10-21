# N-0073 static checks: parse every supervisor-related .ps1 (0 errors expected), then exercise the
# orphan / dead-root logic and the atomic status write with fakes (no real process is stopped).
$files = @('scripts/cip-supervisor.ps1', 'scripts/cip-supervisor-install.ps1', 'scripts/cip-supervisor-stop.ps1',
           'scripts/cip-supervisor-status.ps1', 'scripts/pilot-tunnel.ps1', 'scripts/restart-dev.ps1')
$bad = 0
foreach ($f in $files) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f).Path, [ref]$tokens, [ref]$errors)
    "parse {0}: {1} errors" -f $f, $errors.Count
    foreach ($e in $errors) { "   {0}: {1}" -f $e.Extent.StartLineNumber, $e.Message }
    $bad += $errors.Count
}

# Load only the function definitions from the supervisor.
$path = (Resolve-Path 'scripts/cip-supervisor.ps1').Path
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$null)
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($fn.Extent.Text))
}
$WebChildMatch = @('next start', 'next\dist', 'next/dist')
# Same Add-Type as the supervisor's top level (dot-sourcing functions does not run it).
$addType = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.TryStatementAst] -and $n.Extent.Text.Contains('MoveFileEx') }, $false) | Select-Object -First 1
. ([scriptblock]::Create($addType.Extent.Text))
"MoveFileEx available: $script:HaveMoveFileEx"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$fails = 0
function Check([string]$Name, $Got, $Want) {
    $g = (@($Got) | Sort-Object) -join ','
    $w = (@($Want) | Sort-Object) -join ','
    if ($g -eq $w) { "PASS $Name -> [$g]" } else { "FAIL $Name -> got [$g] want [$w]"; $script:fails++ }
}

# Fakes: a process table, a Stop-Process that only records, a quiet Write-Log.
$t0 = Get-Date '2026-10-07T10:00:00'
function P($id, $parent, $min, $cmd, $name = 'python.exe') {
    [pscustomobject]@{ ProcessId = $id; ParentProcessId = $parent; CreationDate = $t0.AddMinutes($min); CommandLine = $cmd; Name = $name }
}
$script:Fake = @(
    (P 500 1 0  'node.exe dev-api.js' 'node.exe'),                                        # alive root
    (P 501 500 1 'python.exe -m uvicorn app.main:app --reload'),
    (P 502 501 2 'python.exe -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=501, pipe_handle=1)" --multiprocessing-fork'),
    (P 610 600 5 'python.exe -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=600, pipe_handle=820)" --multiprocessing-fork'),  # orphan of dead 600
    (P 611 610 6 'python.exe helper'),                                                     # grandchild of the orphan
    (P 620 600 -90 'notepad.exe' 'notepad.exe'),                                           # older unrelated child of an earlier PID 600
    (P 700 1 30 'node.exe something-new' 'node.exe'),                                      # PID 700 reused at minute 30
    (P 701 700 10 'node.exe next\dist\server\lib\start-server.js' 'node.exe'),             # orphan of the ORIGINAL 700 (before reuse)
    (P 702 700 40 'node.exe child-of-new-700' 'node.exe')                                  # child of the new 700
)
$script:RealAll = ${function:Get-AllProcesses}
function Get-AllProcesses { return $script:Fake }
$script:Stopped = New-Object System.Collections.ArrayList
function Stop-Process { param([int]$Id, [switch]$Force, $ErrorAction) [void]$script:Stopped.Add($Id) }
function Write-Log { param([string]$Message) $script:LastLog = $Message }

$script:Stopped.Clear(); Stop-Tree 500 'alive root'
Check 'alive root stops its whole tree' $script:Stopped @(500, 501, 502)

$script:Stopped.Clear(); Stop-Tree 600 'dead api owner' (Get-ApiChildMatch 600)
Check 'dead root: matching orphan and its child, not the unrelated child' $script:Stopped @(610, 611)

$script:Stopped.Clear(); Stop-Tree 600 'dead root, start known' @() $t0.AddMinutes(4)
Check 'dead root with RootStart: only children no older than the root' $script:Stopped @(610, 611)

$script:Stopped.Clear(); Stop-Tree 700 'reused pid' $WebChildMatch $t0.AddMinutes(9)
Check 'reused PID: new owner and its child left alone, old orphan stopped' $script:Stopped @(701)

$script:Stopped.Clear(); Stop-Tree 900 'nothing there'
Check 'dead root with no children stops nothing' $script:Stopped @()
"   log: $script:LastLog"

Check 'orphan roots of 600 for api' (@(Get-OrphanRoots $script:Fake 600 (Get-ApiChildMatch 600) $null $null) | ForEach-Object { $_.ProcessId }) @(610)

# Atomic write: replace an existing file while a reader holds it open with delete sharing (as node/browsers do).
$dir = Join-Path $env:TEMP ('n0073-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dir | Out-Null
$target = Join-Path $dir 'status.json'
Write-TextFile $target '{"v":1}'
Check 'first write creates the file' ([System.IO.File]::ReadAllText($target)) '{"v":1}'
$fs = New-Object System.IO.FileStream($target, 'Open', 'Read', ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
Write-TextFile $target '{"v":2}'
$fs.Close()
Check 'replace while a reader holds it' ([System.IO.File]::ReadAllText($target)) '{"v":2}'
$gaps = 0
$job = Start-Job -ScriptBlock { param($p) $n = 0; $end = (Get-Date).AddSeconds(4); while ((Get-Date) -lt $end) { if (-not [System.IO.File]::Exists($p)) { $n++ } }; $n } -ArgumentList $target
Start-Sleep -Milliseconds 500
$writeErrors = 0
foreach ($i in 1..300) { try { Write-TextFile $target ('{"v":' + $i + '}') } catch { $writeErrors++ } }
Check 'all 300 rewrites succeeded' $writeErrors 0
$gaps = Receive-Job -Job $job -Wait; Remove-Job $job
Check 'reader never saw the file missing during 300 rewrites' $gaps 0
Remove-Item -Recurse -Force $dir

# Live, read-only: who really serves 8001 and 3000 now.
foreach ($port in @(8001, 3000)) {
    foreach ($l in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
        $o = [int]$l.OwningProcess
        $m = $WebChildMatch; if ($port -eq 8001) { $m = Get-ApiChildMatch $o }
        Set-Item -Path Function:\Get-AllProcesses -Value $script:RealAll
        $owner = Resolve-PortOwner $o $m
        "live: port {0} listener pid {1} (alive={2}) -> serving pid {3}" -f $port, $o, [bool](Get-Process -Id $o -ErrorAction SilentlyContinue), $owner
    }
}
"parse errors total: $bad; logic failures: $fails"
if ($bad -or $fails) { exit 1 }
