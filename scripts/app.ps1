param([ValidateSet("build","smoke","up","status","stop")][string]$Action = "status")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$dockerExe = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
if (!(Test-Path -LiteralPath $dockerExe)) { $dockerExe = "docker" }
$composeArgs = @("compose", "--env-file", (Join-Path $projectRoot "configs\.env"), "-f", (Join-Path $projectRoot "configs\compose.yaml"))
if ($Action -eq "build") {
 & $dockerExe @composeArgs --profile app build
 if($LASTEXITCODE -ne 0){throw 'Image build failed'}
 $imageId=& $dockerExe image inspect cineagent-backend --format '{{.Id}}'
 if($LASTEXITCODE -ne 0){throw 'Backend image lookup failed'}
 Set-Content -LiteralPath (Join-Path $projectRoot 'reports\BACKEND_IMAGE_ID.txt') -Value $imageId -Encoding ascii
}
elseif ($Action -eq "smoke") { & $dockerExe @composeArgs run --rm -T --no-deps backend python /checks/runtime_smoke.py }
elseif ($Action -eq "up") {
 & $dockerExe @composeArgs --profile app up -d
 if ($LASTEXITCODE -ne 0) {throw 'Application startup failed'}
 $ready=$false
 for($taskAttempt=0;$taskAttempt -lt 60;$taskAttempt++) {
  try {$response=Invoke-RestMethod -Uri 'http://127.0.0.1:18000/ready' -TimeoutSec 2;if($response.ready){$ready=$true;break}}catch{}
  Start-Sleep -Seconds 1
 }
 if(!$ready){throw 'Model warmup did not become ready. Inspect cineagent-backend-1 logs.'}
 Write-Host 'Ready: http://127.0.0.1:13000/chat'
}
elseif ($Action -eq "stop") { & $dockerExe @composeArgs --profile app stop backend frontend }
else { & $dockerExe @composeArgs --profile app ps }
if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $LASTEXITCODE" }


