"""Small predeclared validation-only ItemCF/fusion ablation, never reads test.npz."""
import json,time,hashlib,collections
from pathlib import Path
import numpy as np
from scipy import sparse
from diagnose_routes import metric,ci,summarize
ROOT=Path('/artifacts/rec_v1');OUT=Path('/artifacts/ablation_v2');OUT.mkdir(exist_ok=True)
protocol={'version':'ablation-v2','seed':20261018,'scope':'seen validation development only; test not read; no test improvement claim','grid':{'shrinkage':[0,10,50],'neighbors':[50,100]},'fusion':['ItemCF10n100','CF_Pop_RRF60','CF_Pop_RRF60_within_union200'],'candidate':'all train movies excluding every train-rated item per user','positive':'rating>=4','selection':'highest macro NDCG20 on validation; ties Recall20 then method name','text':'excluded: rating task has no query; fabricating test preference queries would leak labels','bootstrap':2000}
p=OUT/'PROTOCOL.json';raw=json.dumps(protocol,ensure_ascii=False,indent=2)
if p.exists():assert json.loads(p.read_text())==protocol
else:p.write_text(raw,encoding='utf-8')
meta=json.loads((ROOT/'metadata.json').read_text());catalog=np.array(meta['catalog']);lookup={int(m):i for i,m in enumerate(catalog)};genres={int(m['movie_id']):set(m['genres']) for m in meta['movies']}
train=np.load(ROOT/'train.npz',allow_pickle=False);val=np.load(ROOT/'validation.npz',allow_pickle=False);X=sparse.load_npz(ROOT/'positive_interactions.npz');pop=np.load(ROOT/'popularity.npy',allow_pickle=False)
seen=collections.defaultdict(set);targets=collections.defaultdict(set)
for u,m in zip(train['user_id'],train['movie_id']):seen[int(u)].add(int(m))
for u,m,r in zip(val['user_id'],val['movie_id'],val['rating']):
 if r>=4 and int(m) in lookup and int(m) not in seen[int(u)]:targets[int(u)].add(int(m))
users=sorted(set(map(int,val['user_id'])));eligible=[u for u in users if X[u].nnz and targets[u]];rows={u:{'user_id':u,'targets':sorted(targets[u]),'methods':{}} for u in eligible}
counts=(X.T@X).tocsr();norm=np.sqrt(np.asarray(X.multiply(X).sum(axis=0))).ravel();norm[norm==0]=1;Y=X.multiply(1/norm).tocsr();cos=(Y.T@Y).tocsr()
base_scores={};started=time.perf_counter()
for shrink in [0,10,50]:
 for neighbors in [50,100]:
  name=f'CF_s{shrink}_n{neighbors}';S=cos.copy()
  if shrink:
   weights=counts.copy();weights.data=weights.data/(weights.data+shrink);S=S.multiply(weights).tocsr()
  S.setdiag(0);S.eliminate_zeros()
  for i in range(S.shape[0]):
   a,b=S.indptr[i:i+2]
   if b-a>neighbors:
    keep=np.lexsort((S.indices[a:b],-S.data[a:b]))[:neighbors];remove=np.ones(b-a,bool);remove[keep]=False;S.data[a:b][remove]=0
  S.eliminate_zeros();allscore=(X[eligible]@S).toarray()
  if shrink==10 and neighbors==100:base_scores=allscore.copy()
  for i,u in enumerate(eligible):
   idx=np.array([j for j,m in enumerate(catalog) if int(m) not in seen[u]]);order=idx[np.lexsort((catalog[idx],-allscore[i,idx]))];ids=catalog[order[:20]].tolist();rows[u]['methods'][name]={'ids':ids,**metric(ids,targets[u],genres),'failed':False}
  print(name,flush=True)
for i,u in enumerate(eligible):
 idx=np.array([j for j,m in enumerate(catalog) if int(m) not in seen[u]]);cforder=idx[np.lexsort((catalog[idx],-base_scores[i,idx]))];po=idx[np.lexsort((catalog[idx],-pop[idx]))]
 rrf=np.zeros(len(catalog));rrf[cforder]=1/(60+np.arange(1,len(cforder)+1));rrf[po]+=1/(60+np.arange(1,len(po)+1))
 for name,pool,score in [('Popular',idx,pop),('CF_Pop_RRF60',idx,rrf),('CF_Pop_RRF60_within_union200',np.union1d(cforder[:100],po[:100]),rrf)]:
  order=pool[np.lexsort((catalog[pool],-score[pool]))];ids=catalog[order[:20]].tolist();rows[u]['methods'][name]={'ids':ids,**metric(ids,targets[u],genres),'failed':False}
methods=list(rows[eligible[0]]['methods']);per=list(rows.values());summary=summarize(per,methods,catalog);base='CF_s10_n100'
paired={m:{k:ci([r['methods'][m][k]-r['methods'][base][k] for r in per]) for k in ['Recall@20','NDCG@20']} for m in methods if m!=base}
winner=sorted(methods,key=lambda m:(-summary[m]['NDCG@20']['mean'],-summary[m]['Recall@20']['mean'],m))[0]
report={'protocol':protocol,'input_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['train.npz','validation.npz','positive_interactions.npz']},'eligible_users':len(per),'all_validation_users':len(users),'excluded':[{'user_id':u,'reasons':(['no_train_positive'] if not X[u].nnz else [])+(['no_eligible_target'] if not targets[u] else [])} for u in users if u not in eligible],'summary':summary,'paired_vs_original_ItemCF':paired,'selected_validation_method':winner,'test_read':False,'neural_training':False,'elapsed_seconds':time.perf_counter()-started,'per_user':per}
(OUT/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['eligible_users','summary','selected_validation_method','elapsed_seconds']}),flush=True)
