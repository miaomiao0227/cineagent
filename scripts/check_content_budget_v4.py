import json
from pathlib import Path
import numpy as np
from scipy import sparse
from diagnose_routes import ci
R=Path('/artifacts/rec_v1');O=Path('/artifacts/content_contribution_v4');result=json.loads((O/'RESULTS.json').read_text());protocol={'purpose':'post-hoc cardinality control, no change to original full-catalogue rank experiment','control':'CF topN where N equals CF100+Text100 unique union size per user; compare target coverage at equal count','predeclared_before_control_execution':True}
(O/'MATCHED_BUDGET_PROTOCOL.json').write_text(json.dumps(protocol,indent=2));X=sparse.load_npz(R/'positive_interactions.npz');S=sparse.load_npz(R/'itemcf_similarity.npz');train=np.load(R/'train.npz');catalog=np.array(json.loads((R/'metadata.json').read_text())['catalog']);seen={r['user_id']:set() for r in result['per_user']}
for u,m in zip(train['user_id'],train['movie_id']):
 if int(u) in seen:seen[int(u)].add(int(m))
rows=[]
for r in result['per_user']:
 u=r['user_id'];score=np.asarray((X[u]@S).toarray()).ravel();idx=np.array([j for j,m in enumerate(catalog) if int(m) not in seen[u]]);order=idx[np.lexsort((catalog[idx],-score[idx]))];n=r['candidate_union_size'];target=set(r['target_ids']);matched=len(set(map(int,catalog[order[:n]]))&target)/len(target);rows.append({'user_id':u,'candidate_count':n,'CF_matchedN':matched,'union':r['candidate_recall_CF100_Text100_union'],'delta_union_minus_CF_matchedN':r['candidate_recall_CF100_Text100_union']-matched})
report={'protocol':protocol,'n':len(rows),'CF_matchedN':ci([r['CF_matchedN'] for r in rows]),'union':ci([r['union'] for r in rows]),'paired_delta':ci([r['delta_union_minus_CF_matchedN'] for r in rows]),'per_user':rows};(O/'MATCHED_BUDGET.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ['n','CF_matchedN','union','paired_delta']}))
