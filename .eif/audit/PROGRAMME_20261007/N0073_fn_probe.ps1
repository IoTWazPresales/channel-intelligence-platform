# N-0073: load only the function definitions from the supervisor (no main loop) and run the adoption checks.
$path = (Resolve-Path 'scripts/cip-supervisor.ps1').Path
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$null)
$fns = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)
foreach ($f in $fns) { . ([scriptblock]::Create($f.Extent.Text)) }
$MetricsPort = 20241
$all = Get-AllProcesses
$workers = @(Get-RootProcs @(Find-Procs $all 'python.exe' @('app.worker.celery_app worker')))
$beats   = @(Get-RootProcs @(Find-Procs $all 'python.exe' @('app.worker.celery_app beat')))
$wrappers = @(Find-Procs $all 'node.exe' @('dev-worker.js'))
"celery roots: worker=$($workers.Count) beat=$($beats.Count) wrappers=$($wrappers.Count); listeners 3000=$(@(Get-Listeners 3000).Count) 8001=$(@(Get-Listeners 8001).Count)"
$running = @(Get-QuickTunnels $all)
"quick tunnels found: $($running.Count) -> $(($running | ForEach-Object { $_.ProcessId }) -join ',')"
foreach ($t in $running) {
  $port = Get-MetricsPort $t.ProcessId
  "pid $($t.ProcessId) metrics port $port quicktunnel status $(Get-HttpStatus ("http://127.0.0.1:{0}/quicktunnel" -f $port)) ready $(Get-HttpStatus ("http://127.0.0.1:{0}/ready" -f $port))"
}
