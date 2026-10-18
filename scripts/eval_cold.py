"""cold-v1: hash-held-out item interactions removed before fitting behavior stats."""
import json,hashlib,math,collections,time
from pathlib import Path
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
r=Path('/artifacts/rec_v1');out=Path('/artifacts/content_v1');out.mkdir(exist_ok=True)
meta=json.loads((r/'metadata.json').read_text());catalog=np.array(meta['catalog'],dtype=int);seed=20261018
cold=np.array(sorted(int(m) for m in catalog if int(hashlib.sha256(f'cold-v1:{seed}:{int(m)}'.encode()).hexdigest(),16)%10==0));warm=np.array(sorted(set(catalog)-set(cold)));coldset=set(cold);warmset=set(warm)
manifest={'protocol':'cold-v1','selection':'SHA256(cold-v1:20261018:movie_id) mod10 == 0','cold_ids':cold.tolist(),'warm_ids':warm.tolist(),'metadata':'official MovieLens titles and genres; current file snapshot, historical availability not independently established','image_arm':'not run: source poster rights and semantic ID alignment not independently verified','neural_models':'excluded because rec-v1 checkpoints saw cold interactions'}
# Persist the split before fitting any cold-experiment statistics/representations.
(out/'COLD_SPLIT.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
train=dict(np.load(r/'train.npz',allow_pickle=False));test=dict(np.load(r/'test.npz',allow_pickle=False));keep=np.array([int(m) in warmset for m in train['movie_id']]);removed=int((~keep).sum());assert not set(map(int,train['movie_id'][keep]))&coldset
movies={int(m['movie_id']):m for m in meta['movies']};allids=np.array(sorted(movies));lookup={int(m):i for i,m in enumerate(allids)}
texts=[' '.join([movies[int(mid)]['title']]+movies[int(mid)]['genres']*3) for mid in allids]
vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=25000,dtype=np.float32);Z=vectorizer.fit_transform(texts).tocsr();coldidx=np.array([lookup[int(m)] for m in cold]);C=Z[coldidx]
history=collections.defaultdict(list)
order=np.lexsort((train['movie_id'],train['timestamp']))
for j in order:
 if keep[j] and train['rating'][j]>=4:history[int(train['user_id'][j])].append(int(train['movie_id'][j]))
targets=collections.defaultdict(set)
heldoutusers=set(map(int,test['user_id']))
for u,m,label in zip(test['user_id'],test['movie_id'],test['rating']):
 if label>=4 and int(m) in coldset:targets[int(u)].add(int(m))
rows=[];excluded=[]
for uid in sorted(heldoutusers):
 if not history[uid] or not targets[uid]:excluded.append({'user_id':uid,'reasons':(['no_warm_positive_history'] if not history[uid] else [])+(['no_cold_positive_target'] if not targets[uid] else [])});continue
 try:
  idx=[lookup[m] for m in history[uid][-10:]];profile=Z[idx].mean(axis=0);norm=np.sqrt(np.asarray(profile.multiply(profile).sum())) if sparse.issparse(profile) else float(np.linalg.norm(profile));score=np.asarray(C@np.asarray(profile).ravel()).ravel()/max(float(norm),1e-8)
  text_rank=cold[np.lexsort((cold,-score))[:20]].tolist();baseline=cold[:20].tolist()
  metrics={}
  for name,rank in [('id_order_no_cold_signal',baseline),('text_title_genres',text_rank)]:
   values={}
   for k in [10,20]:
    hits=[int(m in targets[uid]) for m in rank[:k]];ideal=sum(1/math.log2(i+2) for i in range(min(k,len(targets[uid]))));values[f'Recall@{k}']=sum(hits)/len(targets[uid]);values[f'NDCG@{k}']=sum(hit/math.log2(i+2) for i,hit in enumerate(hits))/ideal
   metrics[name]=values
  rows.append({'user_id':uid,'target_ids':sorted(targets[uid]),'candidate_count':len(cold),'ranked':{'id_order_no_cold_signal':baseline,'text_title_genres':text_rank},'metrics':metrics,'error':None})
 except Exception as exc:rows.append({'user_id':uid,'target_ids':sorted(targets[uid]),'candidate_count':len(cold),'metrics':{name:{f'{metric}@{k}':0 for metric in ['Recall','NDCG'] for k in [10,20]} for name in ['id_order_no_cold_signal','text_title_genres']},'error':type(exc).__name__})
summary={};rng=np.random.default_rng(seed)
for method in ['id_order_no_cold_signal','text_title_genres']:
 summary[method]={}
 for metric in ['Recall@10','Recall@20','NDCG@10','NDCG@20']:
  values=np.array([x['metrics'][method][metric] for x in rows]);samples=np.mean(values[rng.integers(0,len(values),(2000,len(values)))],axis=1);summary[method][metric]={'mean':float(np.mean(values)),'user_bootstrap_95':np.quantile(samples,[.025,.975]).tolist()}
 recommended={m for row in rows for m in row.get('ranked',{}).get(method,[])};summary[method]['coverage_at20']=len(recommended)/len(cold)
report={'protocol':'cold-v1','cold_catalogue':len(cold),'removed_train_interactions':removed,'remaining_train_interactions':int(keep.sum()),'eligible_users':len(rows),'heldout_users':len(heldoutusers),'excluded_users':excluded,'failures':sum(row['error'] is not None for row in rows),'baseline_note':'Cold items have zero behavioral observations: popularity and ItemCF are identically zero; deterministic ascending ID is the explicit no-signal baseline. No warm-trained neural score is used.','image_comparison':'not run; see COLD_SPLIT manifest','summary':summary,'per_user':rows}
Path('/trial-ledger/COLD_RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['cold_catalogue','eligible_users','failures','summary']}))
