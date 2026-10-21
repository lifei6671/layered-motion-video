# Windows-only, dependency-free process-tree sampling for SC-P7. Does not approve media.
# CommandFile: {"argv":["absolute executable", "arg", ...], "cwd":"absolute directory",
#               "label":"60s-cold", "cache_expectation":"cold"}
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CommandFile,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [ValidateRange(0.25, 60)][double]$IntervalSeconds = 1,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 3600
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'Requires Windows and PowerShell 7.'
}
$job = Get-Content -LiteralPath $CommandFile -Raw | ConvertFrom-Json
if ($job.argv -isnot [array] -or $job.argv.Count -lt 1 -or
    @($job.argv | Where-Object { $_ -isnot [string] }).Count -gt 0 -or
    -not [IO.Path]::IsPathFullyQualified($job.argv[0]) -or
    -not (Test-Path -LiteralPath $job.argv[0] -PathType Leaf) -or
    -not [IO.Path]::IsPathFullyQualified($job.cwd) -or
    -not (Test-Path -LiteralPath $job.cwd -PathType Container)) {
    throw 'argv must be strings with an existing absolute executable and cwd.'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'OutputDirectory must be new; keep prior measurements.' }
$out = New-Item -ItemType Directory -Path $OutputDirectory
Copy-Item -LiteralPath $CommandFile -Destination (Join-Path $out.FullName 'command.json')
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $job.argv[0]
$start.WorkingDirectory = $job.cwd
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
foreach ($arg in $job.argv | Select-Object -Skip 1) { $start.ArgumentList.Add($arg) }
$proc = [Diagnostics.Process]::new()
$proc.StartInfo = $start
$rows = [Collections.Generic.List[object]]::new()
$errors = [Collections.Generic.List[string]]::new()
$known = @{}
$lastCpu = @{}
$gpuTool = Get-Command nvidia-smi -ErrorAction SilentlyContinue
$wall = [Diagnostics.Stopwatch]::StartNew()
$startedAt = [DateTimeOffset]::Now.ToString('o')
$exitCode = 2
$state = 'FAIL'
$stdout = $null
$stderr = $null
$started = $false
$gpuProc = $null
$gpuFile = $null
$gpuCopy = $null
$gpu = @{status='UNAVAILABLE'; scope='host samples during command; includes other work'}
$cancel = [Threading.CancellationTokenSource]::new()
try {
    if ($gpuTool) {
        try {
            $gpuStart = [Diagnostics.ProcessStartInfo]::new($gpuTool.Source)
            $gpuStart.UseShellExecute = $false
            $gpuStart.CreateNoWindow = $true
            $gpuStart.RedirectStandardOutput = $true
            $gpuStart.ArgumentList.Add('--query-gpu=timestamp,name,utilization.gpu,memory.used')
            $gpuStart.ArgumentList.Add('--format=csv,noheader,nounits')
            $gpuStart.ArgumentList.Add('--loop-ms=1000')
            $gpuFile = [IO.File]::Create((Join-Path $out.FullName 'gpu.csv'))
            $gpuProc = [Diagnostics.Process]::Start($gpuStart)
            $gpuCopy = $gpuProc.StandardOutput.BaseStream.CopyToAsync($gpuFile)
        } catch { $gpu.error = $_.Exception.Message }
    }
    $stdout = [IO.File]::Create((Join-Path $out.FullName 'stdout.log'))
    $stderr = [IO.File]::Create((Join-Path $out.FullName 'stderr.log'))
    [void]$proc.Start()
    $started = $true
    $rootStarted = $proc.StartTime
    $copyOut = $proc.StandardOutput.BaseStream.CopyToAsync($stdout, $cancel.Token)
    $copyErr = $proc.StandardError.BaseStream.CopyToAsync($stderr, $cancel.Token)
    $lastWall = 0.0
    while (-not $proc.HasExited -or -not $copyOut.IsCompleted -or -not $copyErr.IsCompleted) {
        try {
            $all = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,CreationDate,Name,WorkingSetSize,KernelModeTime,UserModeTime)
            $selected = @{}
            foreach ($p in $all) {
                $key = "$($p.ProcessId):$($p.CreationDate.ToString('o'))"
                if (($p.ProcessId -eq $proc.Id -and $p.CreationDate.ToUniversalTime().ToString('yyyyMMddHHmmssffffff') -eq $rootStarted.ToUniversalTime().ToString('yyyyMMddHHmmssffffff')) -or
                    ($p.ParentProcessId -eq $proc.Id -and $p.CreationDate -ge $rootStarted) -or
                    $known.ContainsKey($key)) { $selected[$p.ProcessId] = $p }
            }
            do {
                $added = $false
                foreach ($p in $all) {
                    if (-not $selected.ContainsKey($p.ProcessId) -and $selected.ContainsKey($p.ParentProcessId) -and
                        $p.CreationDate -ge $selected[$p.ParentProcessId].CreationDate) {
                        $selected[$p.ProcessId] = $p
                        $added = $true
                    }
                }
            } while ($added)
            $rss = 0L
            $cpuDelta = 0.0
            $browsers = 0
            foreach ($p in $selected.Values) {
                $key = "$($p.ProcessId):$($p.CreationDate.ToString('o'))"
                $known[$key] = $true
                $rss += [long]$p.WorkingSetSize
                $cpu = ([double]$p.KernelModeTime + [double]$p.UserModeTime) / 10000000
                if ($lastCpu.ContainsKey($key)) { $cpuDelta += [Math]::Max(0, $cpu - $lastCpu[$key]) }
                else { $cpuDelta += $cpu }
                $lastCpu[$key] = $cpu
                if ($p.Name -match '^(chrome|chrome-headless-shell|msedge|chromium)(\.exe)?$') { $browsers++ }
            }
            $now = $wall.Elapsed.TotalSeconds
            $rows.Add(@{elapsed_seconds=$now; tree_process_count=$selected.Count; tree_working_set_bytes=$rss;
                browser_process_count=$browsers; cpu_core_percent=100*$cpuDelta/($now-$lastWall)})
            $lastWall = $now
        } catch { $errors.Add("process sample: $($_.Exception.Message)") }
        if ($wall.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            $state = 'TIMEOUT'
            $exitCode = 124
            $cancel.Cancel()
            if (-not $proc.HasExited) { $proc.Kill($true) }
            foreach ($p in $selected.Values) {
                try {
                    $child = [Diagnostics.Process]::GetProcessById($p.ProcessId)
                    # CIM keeps microseconds; Process.StartTime also contains 100 ns ticks.
                    if ($child.StartTime.ToUniversalTime().ToString('yyyyMMddHHmmssffffff') -eq $p.CreationDate.ToUniversalTime().ToString('yyyyMMddHHmmssffffff')) {
                        $child.Kill($true)
                        [void]$child.WaitForExit(5000)
                    }
                    $child.Dispose()
                } catch { } # A sampled process may have exited before termination.
            }
            break
        }
        if (-not $proc.HasExited -or -not $copyOut.IsCompleted -or -not $copyErr.IsCompleted) {
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    if (-not $proc.WaitForExit(5000)) { throw 'Process did not exit after termination' }
    if ($state -ne 'TIMEOUT') {
        [void]$copyOut.GetAwaiter().GetResult()
        [void]$copyErr.GetAwaiter().GetResult()
        $exitCode = $proc.ExitCode
        $state = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
    }
} catch {
    $errors.Add($_.Exception.Message)
    $cancel.Cancel()
    if ($started -and -not $proc.HasExited) { $proc.Kill($true); [void]$proc.WaitForExit(5000) }
} finally {
    $wall.Stop()
    if ($stdout) { $stdout.Dispose() }
    if ($stderr) { $stderr.Dispose() }
    if ($gpuProc) {
        if (-not $gpuProc.HasExited) { $gpuProc.Kill(); $gpuProc.WaitForExit() }
        if ($gpuCopy) { [void]$gpuCopy.GetAwaiter().GetResult() }
        $gpuProc.Dispose()
    }
    if ($gpuFile) {
        $gpuFile.Dispose()
        $gpuRows = @(Get-Content -LiteralPath (Join-Path $out.FullName 'gpu.csv') |
            Where-Object { $_ -match ',\s*\d+(\.\d+)?,\s*\d+(\.\d+)?\s*$' })
        if ($gpuRows.Count -gt 0) {
            $gpu.status = 'PASS'
            $gpu.sample_count = $gpuRows.Count
            $gpu.sampled_peak_utilization_percent = ($gpuRows | ForEach-Object { [double]($_ -split ',')[-2] } | Measure-Object -Maximum).Maximum
            $gpu.sampled_peak_memory_mib = ($gpuRows | ForEach-Object { [double]($_ -split ',')[-1] } | Measure-Object -Maximum).Maximum
        }
    }
    $valid = @($rows | Where-Object { $_.tree_process_count -gt 0 })
    $report = @{schema_version='1.0'; status=$state; exit_code=$exitCode; started_at=$startedAt;
        label=$job.label; cache_expectation=$job.cache_expectation; cache_verified=$false;
        command_sha256=(Get-FileHash -LiteralPath $CommandFile -Algorithm SHA256).Hash.ToLowerInvariant();
        host=[Environment]::MachineName; os=[Environment]::OSVersion.ToString(); logical_processors=[Environment]::ProcessorCount;
        wall_seconds=$wall.Elapsed.TotalSeconds; interval_seconds=$IntervalSeconds;
        measurement_status=$(if ($valid.Count -gt 0 -and $errors.Count -eq 0) {'PASS'} else {'INCOMPLETE'});
        sampled_peak_tree_working_set_bytes=($valid.tree_working_set_bytes | Measure-Object -Maximum).Maximum;
        sampled_peak_browser_process_count=($valid.browser_process_count | Measure-Object -Maximum).Maximum;
        sampled_peak_cpu_core_percent=($valid.cpu_core_percent | Measure-Object -Maximum).Maximum;
        gpu=$gpu; errors=@($errors.ToArray()); samples=@($rows.ToArray());
        limitations=@('Sampled peaks may miss short-lived children and between-sample peaks.',
          'CPU 100% means one logical core; sum of observed process CPU deltas.',
          'Tree excludes pre-existing VoiceStudio and other shared services.',
          'Timeout terminates the root and observed descendants; exited unsampled ancestors can hide descendants.',
          'Cold/warm label is declared only. Inspect episode cache events separately.',
          'Wall time includes sampling overhead; host GPU samples are not workload attribution.')}
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $out.FullName 'measurement.json') -Encoding utf8
    $proc.Dispose()
    $cancel.Dispose()
}
exit $exitCode
