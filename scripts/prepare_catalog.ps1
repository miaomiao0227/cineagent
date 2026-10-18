# Isolated external pickle -> inert JSON. No service credentials or network are mounted.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$dest=Join-Path $root 'data\catalog.safe.json.gz'
if (Test-Path -LiteralPath $dest) { Write-Host 'Existing safe JSON preserved; no pickle re-executed.'; exit 0 }
$archive=Join-Path $root 'data\funrec-movielens-1m.zip'
$expected='989d9677930fcb716cdc0e318484c9dfc515a482963eb0a8c5a4fd5dfce76abb'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {throw 'Pinned source archive hash mismatch'}
$docker=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$docker;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.CreateNoWindow=$true
$argsList=@('run','--rm','--network','none','--read-only','--user','65534:65534','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1g','--cpus','2','--pids-limit','64','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--mount',"type=bind,source=$root\data\raw,target=/data,readonly",'--mount',"type=bind,source=$root\scripts,target=/checks,readonly",'--entrypoint','python','cineagent-backend','/checks/export_catalog_json.py')
foreach($arg in $argsList){$info.ArgumentList.Add($arg)}
$proc=[Diagnostics.Process]::Start($info);$errors=$proc.StandardError.ReadToEndAsync();$tmp="$dest.partial"
$stream=[IO.File]::Open($tmp,[IO.FileMode]::CreateNew)
try {$proc.StandardOutput.BaseStream.CopyTo($stream)} finally {$stream.Dispose()}
$proc.WaitForExit();$errorText=$errors.GetAwaiter().GetResult()
if ($proc.ExitCode -ne 0) {throw 'Isolated export failed; partial retained for inspection (no credential mounts).'}
Move-Item -LiteralPath $tmp -Destination $dest
Write-Host 'Safe JSON exported from pinned data in isolated container.'
