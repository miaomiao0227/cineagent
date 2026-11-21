param([switch]$Load)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
$docker=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $docker exec cineagent-backend-1 pytest -q -p no:cacheprovider /app/tests --junitxml=/trial-ledger/BACKEND_PYTEST.xml
if($LASTEXITCODE -ne 0){throw 'Backend pytest failed'}
foreach($check in @('check_behavior_v1.py','check_cache_coalescing.py','check_backend_ci_isolated.py')) {
 & $docker exec cineagent-backend-1 python "/checks/$check"
 if($LASTEXITCODE -ne 0){throw "Failed: $check"}
}
if($Load){& $docker exec cineagent-backend-1 python /checks/backend_load.py;if($LASTEXITCODE -ne 0){throw 'Load checks failed'}}
