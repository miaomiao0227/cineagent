$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$dockerExe = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
$imageId = (Get-Content -LiteralPath (Join-Path $root "reports\BACKEND_IMAGE_ID.txt") -Raw).Trim()
$out = Join-Path $root "artifacts\stage1_smoke"
& $dockerExe run --rm --pull never --name cineagent-stage1-smoke --network none --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --memory 2g --cpus 2 --pids-limit 128 --tmpfs /tmp:rw,noexec,nosuid,size=256m --mount "type=bind,source=$root\data\raw,target=/data,readonly" --mount "type=bind,source=$root\scripts,target=/checks,readonly" --mount "type=bind,source=$root\upstream\src,target=/workspace/src,readonly" --mount "type=bind,source=$root\upstream\web_project\backend,target=/app,readonly" --mount "type=bind,source=$out,target=/out" -e FUNREC_RAW_DATA_PATH=/data -e FUNREC_PROCESSED_DATA_PATH=/out -e TF_NUM_INTRAOP_THREADS=2 -e TF_NUM_INTEROP_THREADS=1 --entrypoint timeout $imageId 180s python /checks/training_smoke.py
if ($LASTEXITCODE -ne 0) { throw "Training smoke failed: $LASTEXITCODE" }
