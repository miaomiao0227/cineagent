# Recommendation evaluation rec-v1

Fixed global-time split: 800164/100024/100021 interactions; full candidate catalogue 3662 items.
Test users: 990 eligible of 1209; 219 excluded, reasons persisted. Unknown-item positive targets: 50.

| Method | Recall@20 (95% CI) | NDCG@20 (95% CI) | Coverage@20 | Failures |
|---|---|---|---|---|
| Popular | 0.0875 [0.0805, 0.0949] | 0.1862 [0.1736, 0.1998] | 0.0532 | 0 |
| ItemCF | 0.0942 [0.0868, 0.1018] | 0.2056 [0.1921, 0.2197] | 0.0778 | 0 |
| YouTubeDNN | 0.0431 [0.0374, 0.0495] | 0.0803 [0.0741, 0.0865] | 0.0396 | 0 |
| YT100_DeepFM | 0.0729 [0.0660, 0.0800] | 0.1540 [0.1436, 0.1646] | 0.0732 | 0 |

Neural route did not outperform ItemCF; no improvement claim. These are rating-derived implicit-feedback offline metrics, not real CTR or online A/B results. YouTubeDNN+DeepFM here uses one retrieval route followed by ranking; the online app also uses existing preference/I2I/popular routes and diversity dispersion, so this table is not an evaluation of the complete online app.

Three epochs maximum; checkpoints selected on validation only: retrieval epoch 2, ranking epoch 1. Training/evaluation elapsed 76.428 seconds. Test labels were not used for selection. ItemCF fixed cosine/shrinkage10/top100; all methods share candidate pools and eligibility.

2000 user bootstrap samples, seed20261018. Per-user rankings, target counts, candidate counts/hashes, exclusions, paired differences, Recall/NDCG@10 and genre diversity are in artifacts/rec_v1/*summary.json and *per_user.jsonl. Missing genre pairs are counted separately. No missing input is imputed as a true fact.

## Functional acceptance

HTTP checks passed: 16; actual ranking_strategy=deepfm, recall_count=100, returned20 real IDs, no seen-item overlap. All four enabled channels produced candidates in logs. Cold request returned 6 available movies; requested10 is an upper bound, not fabricated/padded to10.

Input parity: 7 retrieval inputs,8 ranking inputs across32 item rows,positive-history order and embedding-ID order verified. Models preloaded before serving; /ready separates model readiness from dependency health. Functional request timings are not a load test; P50/P95 and fault recovery remain unmeasured.

## Metadata quality

Official 2018 metadata reference (not interactions) matched by numeric ID AND exact normalized title including year:2663/3883 verified identities,243 links corrected,1220 unresolved. Unverified IMDb identity/rating/runtime/adult attributes withheld; raw source preserved. Corrected-link runtime/adult attributes also withheld. Identity confirmation is not full synopsis/poster/historical-availability verification. This does not change train/model/evaluation inputs.

## Limitations / next experiments

- Strong temporal split excludes many users with no positive train history; excluded counts cannot be hidden or interpreted as all-user performance. Cold users/items need separate experiments.
- Only first genre used by ranking,positive history max10,small embeddings and three epochs; neural underperformance may reflect these choices and objective mismatch. These are hypotheses, not established causes.
- Do not tune further against these test results. Next model changes require a new predeclared development protocol or held-out final audit set.
- Formal evaluation covers warm recommendations, not Agent/memory/compression/multimodal or full online multi-channel route.
- Frontend dependency audit22 alerts still needs triage before publishing. Upstream/source data licence and poster provenance need review before public redistribution.
