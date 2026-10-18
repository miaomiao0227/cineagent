param([ValidateSet('status','up','stop','offline-eval','faults','load','live-smoke','live-compression','diagnose','agent-natural','ablation','repair-offline','natural-v2','showcase')][string]$Action='status')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$docker=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
function Run-Python([string]$name) { python (Join-Path $PSScriptRoot $name);if($LASTEXITCODE -ne 0){throw "Failed: $name"} }
function Run-Container([string]$name) { & $docker exec cineagent-backend-1 python "/checks/$name";if($LASTEXITCODE -ne 0){throw "Failed: $name"} }
if ($Action -in @('status','up','stop')) { & (Join-Path $PSScriptRoot 'app.ps1') $Action }
elseif ($Action -eq 'offline-eval') {
 Copy-Item -LiteralPath (Join-Path $root 'eval\agent_tasks.json') -Destination (Join-Path $root 'reports\AGENT_TASKS_FROZEN.json')
 Run-Python 'eval_agent_http.py';Run-Python 'eval_memory_pairs.py';Run-Python 'check_memory_lifecycle.py';Run-Container 'check_memory_expiry.py';Run-Container 'eval_agent_controlled.py';Run-Container 'eval_cold.py'
}
elseif ($Action -eq 'faults') { Run-Container 'eval_agent_controlled.py';Run-Python 'test_redis_recovery.py' }
elseif ($Action -eq 'load') { Run-Python 'service_load.py' }
elseif ($Action -eq 'live-smoke') { Write-Host 'Uses the existing approved local trial budget; sends synthetic requests to official DeepSeek.';Run-Python 'eval_deepseek_http.py' }
elseif ($Action -eq 'showcase') { Run-Python 'build_delivery.py' }

elseif ($Action -eq 'live-compression') { Run-Python 'eval_compression_live.py' }

elseif ($Action -eq 'diagnose') { Run-Container 'diagnose_routes.py' }
elseif ($Action -eq 'agent-natural') { Run-Python 'freeze_natural_tasks.py';Run-Container 'eval_agent_natural.py' }

elseif ($Action -eq 'ablation') { Run-Container 'eval_recommendation_ablation.py' }
elseif ($Action -eq 'repair-offline') { Run-Container 'eval_agent_repair_offline.py' }
elseif ($Action -eq 'natural-v2') { throw 'Paid batch already executed. Preserve results and ledger; define a new version before rerunning.' }
