"""Hand-computed metric checks and independent data leakage checks."""
import json,numpy as np
from recdata import OUT,ROOT,SEED
from receval import metrics
v=metrics([1,3],{1,2},{1:{'A'},3:{'B'}})
assert v['Recall@10']==.5
assert np.isclose(v['NDCG@10'],1/(1+1/np.log2(3)))
assert v['genre_diversity@20']==1
assert metrics([],{1},{})['Recall@20']==0
assert metrics([2,1],{1,2},{})['NDCG@20']==1
cfg=json.loads((ROOT/'configs/eval_protocol.json').read_text());a=dict(np.load(OUT/'train.npz',allow_pickle=False));b=dict(np.load(OUT/'validation.npz',allow_pickle=False));c=dict(np.load(OUT/'test.npz',allow_pickle=False))
assert a['timestamp'].max()<cfg['train_end_exclusive']<=b['timestamp'].min()
assert b['timestamp'].max()<cfg['validation_end_exclusive']<=c['timestamp'].min()
rv=json.loads((OUT/'retrieval_vocab.json').read_text());d=dict(np.load(OUT/'retrieval_train.npz',allow_pickle=False))
# Independent lookup from original train rows, not preprocessing's history objects.
times={(int(u),int(m)):int(t) for u,m,t in zip(a['user_id'],a['movie_id'],a['timestamp'])}
rng=np.random.default_rng(SEED);indices=rng.choice(len(d['user_id']),size=256,replace=False);checked=0
for i in indices:
 u=int(rv['user_id'][d['user_id'][i]-1]);target=int(rv['movie_id'][d['movie_id'][i]-1]);t=times[(u,target)]
 for encoded in d['hist_movie_id'][i]:
  if encoded:
   m=int(rv['movie_id'][encoded-1]);assert times[(u,m)]<t;checked+=1
p=dict(np.load(OUT/'ranking_pairs.npz',allow_pickle=False));assert set(np.unique(p['source']))=={1,2,3}
assert np.all(p['label'][p['source']==1]==1) and np.all(p['label'][p['source']!=1]==0)
assert len(p['label'][p['source']==3])==4*len(p['label'][p['source']==1])
result={'ok':True,'hand_computed_metric_checks':5,'sampled_history_targets':256,'checked_history_events':checked,'temporal_partition_checks':True,'training_label_source_checks':True,'full_negative_membership_check':'performed in recdata prepare using independent numeric pair-key membership'}
(OUT/'PROTOCOL_CHECKS.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
