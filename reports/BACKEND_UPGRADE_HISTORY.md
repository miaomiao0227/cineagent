# Backend upgrade progress

## Completed first slice
- Audited existing auth, rating writes, database pool and routing.
- Added independent online_behaviors and online_behavior_versions tables. Frozen MovieLens ratings remain unchanged.
- Owner-scoped collection / seen / rating mutations and paginated queries.
- Database owner-row locks serialize concurrent owner mutations; upsert and no-op duplicate updates preserve behavior version.
- Legacy rating endpoints now use online business service instead of training table.
- Conversation recommendation excludes signed-in users online watched movies.
- Additive migration scripts/migrate_behavior_v1.py executed.
- 12 real HTTP / PostgreSQL checks pass, including 16 concurrent identical updates, independent-field concurrency, owner isolation, invalid input and frozen row count. Test users removed in finally.
- Corrected SQLAlchemy stale identity response discovered by rating-clear regression.

## Pending
- Frontend business controls and integration verification of legacy endpoints / recommendation exclusion.
- Alembic migration adoption; current additive script is not Alembic.
- Redis versioned recommendation/detail caching, failure fallback and benchmarks.
- Celery persistent jobs, index-update pipeline, worker failure recovery.
- pytest integration suite, CI, observability and final load / fault validation.
- Public export and GitHub synchronization after verification. Do not claim pending work as complete.

## Frontend / integration continuation
- MovieDetail now mounts MovieBehavior: login-gated favorite and seen toggles with pending/error state and ownership inferred server-side.
- Added owner-scoped GET behavior endpoint, including absent-state default.
- Existing StarRating keeps original UX and now reads/writes isolated online ratings through compatibility endpoints.
- Frontend production build succeeded and deployed; browser confirmed movie detail displays My viewing record and login prompt. Signed-in browser click flow not yet verified; do not claim it has been.
- Extended real DB/HTTP checks to 16: legacy rating write/delete, single-item behavior read, and only-eligible-item watched exclusion added; all pass. Synthetic users cleaned up.
- Cache/Celery/Alembic/CI/load tests still pending.

## Versioned recommendation cache
- GET /api/me/recommendations uses authenticated owner; limit 1..20 and query <=200 chars.
- Redis key includes owner, DB behavior version, model/strategy version and all endpoint inputs; TTL 120s. DB remains authoritative. Old version entries expire without global key deletion.
- Latest online favorite / rating>=8 seeds title/genre content recall. Watched exclusions enforced by engine.
- Redis timeouts bounded at 150ms, no client retry; errors fall back to local computation. Degraded engine results not cached.
- Movie detail now shows four personalized recommendations and refreshes them after favorite/seen mutations. Production frontend rebuilt and deployed; signed-in browser click flow remains pending.
- 21 checks pass, including cache miss/hit identity, version invalidation, owner separation and injected Redis outage fallback. No paid calls.
- Single sequential observation cold 188.54ms / warm 5.70ms is not a load benchmark or a performance improvement claim.
- Pending: concurrent cache stampede protection, metadata detail caching and update invalidation, Celery jobs, Alembic, pytest/CI and repeatable load/fault benchmarks. Legacy StarRating changes do not yet trigger a live refresh of the detail suggestions widget; next recommendation request uses new version.

## Concurrent cache protection
- Redis SET NX EX lock per exact recommendation cache key; random ownership token and Lua compare/delete on release, 15s expiry.
- Contending requests wait at most approximately 600ms for cached result, then return 503 with Retry-After instead of unlimited duplicate computation. Redis unavailable still falls back locally.
- Real Redis test with mocked recommendation computation: 8 concurrent requests cause 1 compute. Bounded contention, foreign-owner preservation, expiry recovery and own-lock release verified; CACHE_COALESCING_V1.json stores results.
- All 21 earlier behavior/integration checks re-pass after lock change.
- Rating create/remove now increments parent revision and refreshes behavior/suggestions widget. Frontend production build succeeded.
- Celery/Alembic/pytest not installed in existing backend image; need a pinned additive worker/test dependency image, without redownloading TensorFlow. No Celery capability claimed yet.
