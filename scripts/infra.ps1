param([ValidateSet("up","status","stop")][string]$Action = "status")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$dockerExe = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
if (!(Test-Path -LiteralPath $dockerExe)) { $dockerExe = "docker" }
$composeArgs = @("compose", "--env-file", (Join-Path $projectRoot "configs\.env"), "-f", (Join-Path $projectRoot "configs\compose.yaml"))
if ($Action -eq "up") { & $dockerExe @composeArgs up -d postgres redis elasticsearch }
elseif ($Action -eq "stop") { & $dockerExe @composeArgs stop }
else { & $dockerExe @composeArgs ps; $containerIds = @(& $dockerExe @composeArgs ps -q); if ($containerIds.Count -gt 0) { & $dockerExe stats --no-stream @containerIds } }
if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $LASTEXITCODE" }
