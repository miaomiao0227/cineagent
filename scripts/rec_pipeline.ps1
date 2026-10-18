param([ValidateSet('prepare','check','baselines','train','bootstrap','repair-metadata','verify')][string]$Action = 'check')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$dockerExe=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$image=(Get-Content -LiteralPath (Join-Path $root 'reports\BACKEND_IMAGE_ID.txt') -Raw).Trim()
$compose=@('compose','--env-file',(Join-Path $root 'configs\.env'),'-f',(Join-Path $root 'configs\compose.yaml'))
if ($Action -eq 'bootstrap') {
  & $dockerExe @compose run --rm -T -v "${root}\data\catalog.safe.json.gz:/catalog.safe.json.gz:ro" backend python -u /checks/bootstrap_service.py
} elseif ($Action -eq 'repair-metadata') {
  & $dockerExe @compose run --rm -T --no-deps -v "${root}\reports\METADATA_OFFICIAL_LINKS.json:/verified-links.json:ro" backend python -u /checks/repair_verified_metadata.py
} elseif ($Action -eq 'verify') {
  & $dockerExe @compose run --rm -T --no-deps backend python /checks/verify_online_parity.py
  if ($LASTEXITCODE -ne 0) { throw 'Online input parity failed' }
  python (Join-Path $root 'scripts\verify_http.py')
} else {
  $script=@{prepare='recdata.py';check='check_rec_protocol.py';baselines='receval.py';train='rectrain.py'}[$Action]
  $seconds=if ($Action -eq 'train') {900} else {600}
  $taskDockerArgs=@('run','--rm','--pull','never','--network','none','--read-only','--user','65534:65534','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','3g','--cpus','4','--pids-limit','128','--tmpfs','/tmp:rw,noexec,nosuid,size=256m')
  foreach ($mount in @("${root}\data\ml-1m-reference.zip,target=/project/data/ml-1m-reference.zip,readonly","${root}\configs\eval_protocol.json,target=/project/configs/eval_protocol.json,readonly","${root}\scripts,target=/checks,readonly","${root}\upstream\src,target=/workspace/src,readonly","${root}\artifacts\rec_v1,target=/project/artifacts/rec_v1")) { $taskDockerArgs+=@('--mount',"type=bind,source=$mount") }
  $taskDockerArgs+=@('-e','TF_NUM_INTRAOP_THREADS=4','-e','TF_NUM_INTEROP_THREADS=1','-e','OMP_NUM_THREADS=4','-e','OPENBLAS_NUM_THREADS=4','--entrypoint','timeout',$image,"${seconds}s",'python','-u',"/checks/$script")
  & $dockerExe @taskDockerArgs
}
if ($LASTEXITCODE -ne 0) { throw "Stage $Action failed: $LASTEXITCODE" }
