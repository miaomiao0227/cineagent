# Backend evaluation protocol v2

Frozen before load measurement. No paid LLM traffic.

## Functional
Real local HTTP + PostgreSQL/Redis/Elasticsearch/Celery suite; temporary users removed. MovieLens ratings remain frozen. Keep failed runs; JUnit records latest full run. Mocked computation tests are identified separately from real service faults.

## Load
One synthetic signed-in user, 20 fixed text queries, limit=6, one fixed model and catalogue. 20 warmup requests excluded. Same ordered 2000 requests for sequential cold and warm arms; cold deletes only this user's exact recommendation key immediately before each call, warm primes the same 20 keys. Then 16000 warm requests at concurrency 8 using the same query sequence. Closed-loop clients, no target RPS. Record every attempt, status, cache status, elapsed milliseconds, item IDs; no failure exclusions. Report success denominator, wall throughput, nearest-rank P50/P95 and error count; no production SLA/max capacity claim. Do not compare this non-LLM endpoint with historical browser Agent P95.

## Faults
1. Real worker process kill after running observed while Elasticsearch paused; unpause/start worker in finally. DB lease expiry must eventually recover same job with bounded execution count.
2. Real Redis stop: DB accepts index job, recommendation falls back. Restart Redis in finally; same job must finish after reconnect.
3. Deterministic dependency failure: three execution attempts then terminal failed state; no endless retry.
4. Redis cache contention: 8 threads + mocked compute, one compute; bounded 503, token-owned unlock, expired lock recovery.

## Migration / metadata
Alembic upgrade on existing DB and isolated empty schema, repeated upgrade idempotent; no destructive downgrade. Online metadata description update must change DB generation so cached detail is fresh. Database mutations must roll back atomically. Offline training table counts checked.

## UI
Synthetic local user: sign in, favorite, seen toggle, rating add/remove, library pagination/filter, admin job submit/completion. No personal data, keys or balances in screenshots. Request IDs and errors logged with route templates only.

V1 smoke retained separately (100/100/400 requests). V2 expands sample counts before measurement; protocol otherwise unchanged.

Timing boundary: client runs inside backend container, urllib request to http://127.0.0.1:8000 through complete JSON parsing. Excludes nginx, browser DOM and LLM generation. One closed-loop shared-host run, not dedicated hardware or capacity ceiling; concurrency8 workload can have larger per-request latency than sequential warm cache.
