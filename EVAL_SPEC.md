# EVAL_SPEC rec-v1

Status: protocol fixed before training; formal evaluators not yet implemented. Stage-1 smoke is a separate execution check and never a performance claim.

## Data and chronology
Use official MovieLens-1M interactions, verified byte-level values against the enriched bundle by (user_id,movie_id): timestamps identical; enriched ratings exactly 2x original. Normalize ratings to 1-5 and cast IDs/timestamps to integers before any sorting. Source hashes and exact global boundaries/counts are in configs/eval_protocol.json. Time ties stay in one partition. No future interactions in fitting, feature statistics, histories, ItemCF or popularity. Vocabulary/OOV strategy must be explicit; do not infer behavioral statistics from full data.

Positive = rating >=4. Ratings 1-3 are explicit nonpositive observations, not actual nonclick impressions. Unobserved pairs are unlabeled. This is an implicit-feedback recommendation task; no real CTR, exposure or online A/B claim.

## Training / selection
Seed 20261018. Popular, ItemCF and existing neural pipeline use identical split and eligibility. Ranking training may sample 4 unobserved items per positive from train catalogue, excluding all observed TRAIN pairs. Do not use future interactions to select train negatives. Persist actual sampled pairs and realized ratio. Explicit low ratings and sampled unobserved negatives must have separate source labels/counts. Hyperparameters selected on validation only; test used once after selection. Histories are frozen at train boundary for rec-v1; no validation/test feedback injected. Record any later train+validation refit as another protocol version.

## Primary full-catalogue evaluation
Candidate catalogue = items observed in training; candidate pool per user excludes that user's observed train items (all ratings). Relevant targets = positive heldout interactions within the catalogue. Eligible users need >=1 positive train item and >=1 eligible heldout target. Report all ineligible users/targets and reasons; unknown items are counted and separately studied as cold items. Evaluate all eligible users. K=10,20. Macro Recall@K and NDCG@K with IDCG=min(K,target_count). Persist per-user candidate_count,target_count,ranked IDs,metrics,failures. Empty/error output for an eligible user scores zero and remains in denominator. No random sampled-candidate figures in the primary table.

Secondary sampled-candidate evaluation, if implemented, uses frozen identical candidate lists per method with requested/realized counts and all eligible targets; it is reported separately. AUC/LogLoss only for explicitly documented labels and sampled pairs.

Coverage = unique recommended IDs / train-catalogue size. Diversity = per-user mean pairwise genre Jaccard distance with valid-pair denominator. Missing genres counted; novelty, if added, uses train-only item frequency. Report paired user-bootstrap 95% intervals (2000 resamples, fixed seed), paired method differences and every failure.

## Cold items / content
Separate experiment, never mix with warm evaluation. Freeze hash-selected heldout item list before fitting; remove all their training interactions from every fitted model, statistics and indexes that learn behavior. Text/image encoders may access approved metadata only. Report snapshot availability date, historical-availability limitations, ID alignment, missing/download/decoding counts and licence status. Text vs text+image comparison uses same complete-input item/task subset; whole-catalogue text fallback separately reported. Current IMDb aggregate rating/vote counts are excluded from historical model features. Contemporary synopsis/posters do not establish historical point-in-time availability.

## Agent / service (later implementation)
Freeze authored/synthetic task files before experiments and label their source. Start with 60 single-turn tasks and 30 multi-turn scripts; include failures, contradictions, missing attributes, correction, deletion and reference resolution. Deterministic expected IDs/constraints/tool-schema checks primary; LLM judging auxiliary only. Compare condition-driven vs original, memory off/on, compression off/on under same tasks/candidates/model. Report successes/total, constraint satisfaction, memory correctness/misuse, valid tool calls/total, repeats and key-fact retention with confidence intervals. Record excluded/missing-input tasks explicitly.

Service load: fixed host/resources, 1 and 5 concurrent clients, 30s warmup +120s measurement per setting, same predeclared request set, all requests counted. Report P50/P95, errors, degradation successes/eligible failures and recovery. Inject timeout,429,LLM unavailable,Redis unavailable and individual recall unavailable. No fault-induced relaxation of known hard constraints; feedback idempotency required.

## Stage-1 smoke-only contract
Fixed seed; first 32 numeric user IDs, up to 50 chronologically earliest interactions each; same valid movie metadata subset as needed. Normalize numeric fields first. Run upstream feature and model training functions via explicit smoke adapter, one epoch, small batch. Disable retrieval/ranking performance evaluator; fit diagnostics remain logs only. Verify finite scores, model save/reload and item-ID mapping. All outputs go to separate artifacts/stage1_smoke, never deploy as production models or include in formal result tables. Upstream average-based labels/splits in smoke are acknowledged legacy execution checks only and are replaced by rec-v1 for formal experiments.

## Implementation choices fixed before neural fit
- Popularity counts positive TRAIN interactions. ItemCF uses positive binary cosine, shrinkage c/(c+10), top100 neighbors, deterministic raw-ID tie break; no test tuning.
- Vocabulary from train users/catalogue only; unknown0. Metadata uses official profile, first genre and title year; constant/unverified adult attribute omitted rather than fabricated. No IMDb vote/rating features.
- User history is positive-only, max10, left-zero padded, strictly earlier timestamp. Same-second events excluded from each other's histories.
- YouTubeDNN and DeepFM reuse upstream builders; embedding16, retrieval DNN64/32, ranking DNN128/64/32, Adam0.001, batch2048, at most3 epochs. Retrieval checkpoint chosen by global-validation full-catalogue Recall@20. Ranking checkpoint chosen by binary crossentropy on a persisted validation pair set (observed positives/low ratings plus4 sampled unobserved per positive, excluding train+validation observed). This BCE is only a checkpoint-selection diagnostic with sampled labels, not real CTR.
- Report standalone YouTubeDNN and YouTubeDNN-top100 then DeepFM as named model routes. These are not the complete upstream multi-channel/diversity pipeline. Primary catalogue/eligibility stays identical to baselines. All test scores come from frozen selected checkpoints; no test-based tuning.

## conversation-v1 freeze (2026-10-18, before conversation experiments)
- eval/agent_tasks.json contains 60 authored template-generated single-turn cases (10 families x 6 variants) and 30 multi-turn cases (6 families x 5 variants). Repeated template variants are correlated; these are engineering regressions, not real users or a general language-understanding benchmark.
- Single-turn compares the same 3883-item initial catalogue, same fixed guest profile, same ranking and top6: unconstrained ordinary engine versus explicit intent filters. Hard-constraint satisfaction counts a case successful only if all returned items satisfy the oracle and nonempty was expected, or the specified contradiction/reference failure was explicitly clarified. Report every task and returned IDs. Unsupported pace/emotion must be disclosed, not scored as understood.
- Multi-turn covers reference exclusion, same-director exclusion (missing director requires clarification), explicit memory source, correction, reset and contradictory update. Memory on/off uses separate fresh sessions with the same owner/profile and query. Expired/revoked/deleted facts are tested separately.
- Structured compression compares identical state and recommendation inputs with original turns vs structured state + last4. Report constraint/source preservation and serialized character lengths, including cases where compression increases length. Character count is not a token count.
- LLM live acceptance is a separately labelled tiny smoke subset, at most 3 conversational requests (<=6 provider calls normally) within the shared 30-request/$0.10 trial. Do not attribute offline-task accuracy to DeepSeek.
- Fault tests use deterministic internal adapters for timeout/429/unavailable/channel failures plus an actual isolated Redis-container stop/restart. Successful degradation must preserve known constraints. Record failures, bounded attempt counts, circuit open and half-open recovery. Public APIs have no fault-injection switch.
- Service load: offline chat path, same predeclared 3-query cycle, target aggregate 5 requests/second, 1 and 5 clients, each 30 seconds warmup then 120 seconds measured. Requests have unique IDs and fresh sessions, same guest profile. All attempts and warmup counts retained; warmup excluded from latency quantiles. This is a bounded-rate laptop test, not saturation capacity. No external model calls in load test.
- Wilson 95% intervals for case proportions; task-template correlation means intervals are descriptive only. Recommendation user-bootstrap remains separate. No image comparison is run without verified inputs/rights; the omitted arm and concrete data gaps must appear in the report.

## compression-live-v1 supplement (before executing this pair)
One authored pair uses identical 12-turn synthetic histories, same guest profile and catalogue, same query/model/prompt; only structured-summary+last4 vs full history differs. Each arm uses at most2 model turns normally (4 provider calls total), shared approved trial ledger. Check all3 declared hard facts and all3 original-source locations, compare exact recommendation IDs, and record characters/actual provider usage. This is a small live functional acceptance, not general compression accuracy or proven task improvement. Fixture is eval/compression_live_task.json, frozen before its first API request. Results remain separate from the 90 offline template cases and the earlier3 live conversation turns.

## V2扩展协议
本轮推荐仅已见validation492/1134用户、6参数ItemCF与固定RRF；不读test，不声明测试提升。真实API使用eval/agent_natural_v2.json及其SHA256，30场景60轮，先冻结再执行，报告业务通过、工具循环、澄清与降级四种分母。原7题只作开发回归。冲突偏好写入判据变化见PHASE2_RESULTS，保留旧判据结果。

## V3排除治理
固定eval/agent_exclusion_v3.json：8历史场景+3新合成场景、22轮，原始模型参数/有效参数/保护事件分别保存。历史问题轮与前置轮分开报告，开发回归不冒充独立泛化；模型本次遵守schema，不能把离线坏参数重放算作现场修正。共享原追加240次/0.50美元账本，累计89用户轮次。

## V4三项协议
冻结eval/complete_v4.json与COMPLETE_V4_SPEC.json；内容实验固定492验证用户、训练期TFIDF/历史、不读test。实际浏览器20场景40轮，43条尝试含3失败，恢复结果和首次分开。计时fetch前→Vue nextTick，LLM轮36与澄清4分开，费用合并每用户轮次全部调用并与账本关联。主观质量等待用户填写人工表；无LLM规则同题对照40/40且列表一致，不宣称LLM推荐质量提升。
