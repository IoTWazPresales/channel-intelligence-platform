# N-0073: compare file swap methods for status.json. A background reader counts how often the file is
# missing or unreadable while the foreground rewrites it 300 times with each method.
Add-Type -Namespace N0073 -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern bool MoveFileEx(string existing, string replacement, int flags);
'@
$enc = New-Object System.Text.UTF8Encoding($false)
$dir = Join-Path $env:TEMP ('n0073-swap-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dir | Out-Null
$target = Join-Path $dir 'status.json'
$methods = [ordered]@{
    'Move-Item -Force' = { param($tmp, $dst) Move-Item -Path $tmp -Destination $dst -Force }
    'File.Replace'     = { param($tmp, $dst) [System.IO.File]::Replace($tmp, $dst, [NullString]::Value) }
    'MoveFileEx'       = { param($tmp, $dst) if (-not [N0073.Native]::MoveFileEx($tmp, $dst, 1 -bor 8)) { throw "MoveFileEx failed $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" } }
}
foreach ($name in $methods.Keys) {
    [System.IO.File]::WriteAllText($target, '{"v":0}', $enc)
    $job = Start-Job -ScriptBlock {
        param($p)
        $missing = 0; $unreadable = 0; $reads = 0
        $end = (Get-Date).AddSeconds(5)
        while ((Get-Date) -lt $end) {
            $reads++
            try { [void][System.IO.File]::ReadAllText($p) }
            catch [System.IO.FileNotFoundException] { $missing++ }
            catch { $unreadable++ }
        }
        "reads=$reads missing=$missing other_errors=$unreadable"
    } -ArgumentList $target
    Start-Sleep -Milliseconds 800
    $errs = 0
    $t = [Diagnostics.Stopwatch]::StartNew()
    foreach ($i in 1..300) {
        $tmp = "$target.tmp"
        [System.IO.File]::WriteAllText($tmp, ('{"v":' + $i + '}'), $enc)
        try { & $methods[$name] $tmp $target } catch { $errs++ }
    }
    $ms = $t.ElapsedMilliseconds
    $r = Receive-Job -Job $job -Wait; Remove-Job $job
    "{0,-17} writer_errors={1} writer_ms={2} reader: {3}" -f $name, $errs, $ms, $r
}
Remove-Item -Recurse -Force $dir
