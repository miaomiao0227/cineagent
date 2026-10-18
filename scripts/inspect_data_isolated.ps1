# Prepared for explicit user approval; not executed automatically.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$dockerExe = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
$rawPath = Join-Path $projectRoot "data\raw"
$referencePath = Join-Path $projectRoot "data\ml-1m-reference.zip"
$scriptPath = Join-Path $projectRoot "scripts"
$outputPath = Join-Path $projectRoot "reports\DATA_INSPECTION_ISOLATED.log"
& $dockerExe run --rm --network none --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --memory 1g --cpus 2 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=64m --mount "type=bind,source=$rawPath,target=/data,readonly" --mount "type=bind,source=$scriptPath,target=/checks,readonly" --mount "type=bind,source=$referencePath,target=/reference.zip,readonly" --entrypoint python cineagent-backend /checks/inspect_data.py --stdout *> $outputPath
if ($LASTEXITCODE -ne 0) { throw "Isolated data inspection failed: $LASTEXITCODE; see report" }
