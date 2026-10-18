import json,collections,hashlib,time
from pathlib import Path
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from diagnose_routes import metric,ci,summarize
R=Path('/artifacts/rec_v1');O=Path('/artifacts/content_contribution_v4');O.mkdir(exist_ok=True)
protocol={'version':'content-contribution-v4','split':'original validation; development only, no test arrays','catalogue':'train catalogue minus user all train observed','profile':'last20 rating>=4 training items by(timestamp,movie_id), equal mean then L2norm','features':'train-catalogue title + genres repeated3, char_wb3to5,max25000,float32','methods':['ItemCF','TextProfile','CF_Text_RRF60'],'rrf':'equal weights, full eligible catalogue rank fusion; no sweep or winner deployment','bootstrap':2000,'seed':20261018}
p=O/'PROTOCOL.json'
if p.exists():assert json.loads(p.read_text())==protocol
else:p.write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
meta=json.loads((R/'metadata.json').read_text());catalog=np.array(meta['catalog']);lookup={int(m):i for i,m in enumerate(catalog)};movies={int(m['movie_id']):m for m in meta['movies']};genres={i:set(m['genres']) for i,m in movies.items()}
train=np.load(R/'train.npz',allow_pickle=False);val=np.load(R/'validation.npz',allow_pickle=False);X=sparse.load_npz(R/'positive_interactions.npz');S=sparse.load_npz(R/'itemcf_similarity.npz');seen=collections.defaultdict(set);hist=collections.defaultdict(list);targets=collections.defaultdict(set)
for u,m,t,r in zip(train['user_id'],train['movie_id'],train['timestamp'],train['rating']):
 seen[int(u)].add(int(m))
 if r>=4:hist[int(u)].append((int(t),int(m)))
for u,m,r in zip(val['user_id'],val['movie_id'],val['rating']):
 if r>=4 and int(m) in lookup and int(m) not in seen[int(u)]:targets[int(u)].add(int(m))
users=sorted(set(map(int,val['user_id'])));eligible=[u for u in users if X[u].nnz and targets[u]];excluded=[{'user_id':u,'no_training_positive':not bool(X[u].nnz),'no_eligible_target':not bool(targets[u])} for u in users if u not in eligible]
docs=[' '.join([movies[int(m)]['title']]+movies[int(m)]['genres']*3) for m in catalog];v=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=25000,dtype=np.float32);D=v.fit_transform(docs).tocsr();rows=[]
for u in eligible:
 history=sorted(hist[u])[-20:];indices=[lookup[m] for _,m in history];profile=normalize(sparse.csr_matrix(D[indices].mean(axis=0)));text=np.asarray((D@profile.T).toarray()).ravel();cf=np.asarray((X[u]@S).toarray()).ravel();idx=np.array([j for j,m in enumerate(catalog) if int(m) not in seen[u]]);co=idx[np.lexsort((catalog[idx],-cf[idx]))];to=idx[np.lexsort((catalog[idx],-text[idx]))];rrf=np.zeros(len(catalog));rrf[co]=1/(60+np.arange(1,len(co)+1));rrf[to]+=1/(60+np.arange(1,len(to)+1));row={'user_id':u,'history_ids':[m for _,m in history],'history_max_timestamp':max(t for t,_ in history),'target_ids':sorted(targets[u]),'candidate_count':len(idx),'methods':{}}
 for name,score in [('ItemCF',cf),('TextProfile',text),('CF_Text_RRF60',rrf)]:
  order=idx[np.lexsort((catalog[idx],-score[idx]))];ids=catalog[order[:20]].tolist();row['methods'][name]={'ids':ids,**metric(ids,targets[u],genres),'failed':False}
 row['candidate_recall_CF100']=len(set(map(int,catalog[co[:100]]))&targets[u])/len(targets[u]);union=set(map(int,catalog[co[:100]]))|set(map(int,catalog[to[:100]]));row['candidate_recall_CF100_Text100_union']=len(union&targets[u])/len(targets[u]);row['candidate_union_size']=len(union);rows.append(row)
assert all(r['history_max_timestamp']<975768738 for r in rows)
methods=protocol['methods'];summary=summarize(rows,methods,catalog);paired={name:{k:ci([r['methods'][name][k]-r['methods']['ItemCF'][k] for r in rows]) for k in ['Recall@20','NDCG@20']} for name in methods if name!='ItemCF'}
report={'protocol':protocol,'eligible_users':len(rows),'heldout_users':len(users),'excluded':excluded,'summary':summary,'paired_vs_ItemCF':paired,'candidate':{k:ci([r[k] for r in rows]) for k in ['candidate_recall_CF100','candidate_recall_CF100_Text100_union','candidate_union_size']},'inputs_sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['train.npz','validation.npz','metadata.json']},'test_read':False,'per_user':rows,'limitations':'seen validation, no independent test gain; titles/genres only, no plot/images; current metadata snapshot not historical proof'}
(O/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['eligible_users','summary','paired_vs_ItemCF','candidate']}),flush=True)
