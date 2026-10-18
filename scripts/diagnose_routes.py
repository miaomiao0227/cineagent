"""Train-period rolling baselines and seen-validation route bottleneck diagnosis.
Reads no rec-v1 test arrays; never loads a full-train neural model for rolling folds.
"""
import json,hashlib,time,math,collections,gc
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT=Path('/artifacts/rec_v1');OUT=Path('/artifacts/diagnostics_v1');OUT.mkdir(exist_ok=True)
SEED=20261018

def save(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def ci(vals):
 a=np.asarray(vals,dtype=float)
 if not len(a):return {'mean':None,'ci95':None,'n':0}
 rng=np.random.default_rng(SEED);b=np.empty(2000)
 for i in range(2000):b[i]=a[rng.integers(0,len(a),len(a))].mean()
 return {'mean':float(a.mean()),'ci95':np.quantile(b,[.025,.975]).tolist(),'n':len(a)}
def metric(rank,target,genres):
 hit=[int(m in target) for m in rank[:20]];ideal=sum(1/math.log2(i+2) for i in range(min(20,len(target))))
 pairs=[]
 for i,a in enumerate(rank[:20]):
  for b in rank[:20][i+1:]:
   ga,gb=genres[a],genres[b]
   if ga and gb:pairs.append(1-len(ga&gb)/len(ga|gb))
 return {'Recall@20':sum(hit)/len(target),'NDCG@20':sum(v/math.log2(i+2) for i,v in enumerate(hit))/ideal,'genre_diversity@20':float(np.mean(pairs)) if pairs else None}
def similarity(X):
 counts=(X.T@X).tocsr();norm=np.sqrt(np.asarray(X.multiply(X).sum(axis=0))).ravel();norm[norm==0]=1
 Y=X.multiply(1/norm).tocsr();S=(Y.T@Y).tocsr();counts.data=counts.data/(counts.data+10);S=S.multiply(counts).tocsr();S.setdiag(0);S.eliminate_zeros()
 for i in range(S.shape[0]):
  a,b=S.indptr[i:i+2]
  if b-a>100:
   values=S.data[a:b];keep=np.lexsort((S.indices[a:b],-values))[:100];remove=np.ones(b-a,bool);remove[keep]=False;values[remove]=0
 S.eliminate_zeros();return S

def summarize(rows,methods,catalog):
 summary={}
 for method in methods:
  summary[method]={k:ci([r['methods'][method][k] for r in rows]) for k in ['Recall@20','NDCG@20']}
  summary[method]['coverage@20']=len({m for r in rows for m in r['methods'][method]['ids']})/len(catalog)
  div=[r['methods'][method]['genre_diversity@20'] for r in rows if r['methods'][method]['genre_diversity@20'] is not None];summary[method]['genre_diversity@20']=ci(div);summary[method]['failures']=sum(r['methods'][method].get('failed',False) for r in rows)
 return summary

def rolling(train,meta,genres):
 times=np.sort(train['timestamp']);a=int(times[int(.75*len(times))]);b=int(times[int(.875*len(times))]);end=975768738
 protocol={'version':'diagnostics-v1','seed':SEED,'source_train_sha256':hashlib.sha256((ROOT/'train.npz').read_bytes()).hexdigest(),'train_period_only':True,'folds':[{'train_end_exclusive':a,'validation_end_exclusive':b},{'train_end_exclusive':b,'validation_end_exclusive':end}],'fit':'Popular/ItemCF only, no reused full-train neural checkpoints','candidate':'fold train catalogue minus all user fold-train observed','positive_rating_min':4,'top_k':20,'pool_k':100,'diagnostic_neural_section':'original seen validation only, no test data read'}
 p=OUT/'PROTOCOL.json'
 if p.exists():assert json.loads(p.read_text())==protocol
 else:save('PROTOCOL.json',protocol)
 summaries=[]
 for fold,spec in enumerate(protocol['folds'],1):
  tm=train['timestamp']<spec['train_end_exclusive'];vm=(train['timestamp']>=spec['train_end_exclusive'])&(train['timestamp']<spec['validation_end_exclusive']);catalog=np.unique(train['movie_id'][tm]);lookup={int(m):i for i,m in enumerate(catalog)};seen=collections.defaultdict(set)
  for u,m in zip(train['user_id'][tm],train['movie_id'][tm]):seen[int(u)].add(int(m))
  pos=tm&(train['rating']>=4);X=sparse.csr_matrix((np.ones(int(pos.sum()),dtype=np.float32),(train['user_id'][pos],np.array([lookup[int(m)] for m in train['movie_id'][pos]]))),shape=(6041,len(catalog)));pop=np.asarray(X.sum(axis=0)).ravel();S=similarity(X);targets=collections.defaultdict(set)
  unknown=0
  for u,m,r in zip(train['user_id'][vm],train['movie_id'][vm],train['rating'][vm]):
   if r>=4:
    if int(m) not in lookup:unknown+=1
    elif int(m) not in seen[int(u)]:targets[int(u)].add(int(m))
  rows=[];excluded=[]
  for uid in sorted(set(map(int,train['user_id'][vm]))):
   reasons=[]
   if not X[uid].nnz:reasons.append('no_positive_training_history')
   if not targets[uid]:reasons.append('no_eligible_positive_target')
   if reasons:excluded.append({'user_id':uid,'reasons':reasons});continue
   valid=np.array([int(m) not in seen[uid] for m in catalog]);idx=np.flatnonzero(valid);row={'user_id':uid,'target_ids':sorted(targets[uid]),'candidate_count':len(idx),'history_positive_count':X[uid].nnz,'methods':{}}
   for name,score in [('Popular',pop),('ItemCF',np.asarray((X[uid]@S).toarray()).ravel())]:
    order=idx[np.lexsort((catalog[idx],-score[idx]))[:100]];ids=catalog[order[:20]].tolist();row['methods'][name]={'ids':ids,**metric(ids,targets[uid],genres),'candidate_Recall@100':len(set(catalog[order])&targets[uid])/len(targets[uid]),'failed':False}
   rows.append(row)
  result={'protocol':spec,'training_count':int(tm.sum()),'validation_count':int(vm.sum()),'catalogue_size':len(catalog),'eligible_users':len(rows),'excluded_users':excluded,'unknown_positive_targets':unknown,'summary':summarize(rows,['Popular','ItemCF'],catalog),'per_user':rows}
  for name in ['Popular','ItemCF']:result['summary'][name]['candidate_Recall@100']=ci([r['methods'][name]['candidate_Recall@100'] for r in rows])
  result['paired_ItemCF_minus_Popular']={k:ci([r['methods']['ItemCF'][k]-r['methods']['Popular'][k] for r in rows]) for k in ['Recall@20','NDCG@20']};save(f'ROLLING_FOLD_{fold}.json',result);summaries.append({k:result[k] for k in ['protocol','training_count','validation_count','catalogue_size','eligible_users','summary','paired_ItemCF_minus_Popular']});print(json.dumps({'fold':fold,'eligible':len(rows),'summary':result['summary']}),flush=True)
  del X,S,rows,result;gc.collect()
 return summaries

def neural(meta,train,genres):
 import tensorflow as tf
 from online.ranking.resource_manager import RankingResourceManager
 from app.cineagent.engine import engine
 manager=RankingResourceManager();manager._ensure_resources_loaded();original=manager.ranking_model
 model=tf.keras.models.load_model(str(ROOT/'models/user_model'),compile=False)
 table=dict(np.load(ROOT/'feature_tables.npz',allow_pickle=False));rv=json.loads((ROOT/'retrieval_vocab.json').read_text());v=json.loads((ROOT/'vocab.json').read_text());catalog=np.array(meta['catalog']);lookup={int(m):i for i,m in enumerate(catalog)};seen=collections.defaultdict(set)
 for u,m in zip(train['user_id'],train['movie_id']):seen[int(u)].add(int(m))
 X=sparse.load_npz(ROOT/'positive_interactions.npz');S=sparse.load_npz(ROOT/'itemcf_similarity.npz');pop=np.load(ROOT/'popularity.npy',allow_pickle=False);val=dict(np.load(ROOT/'validation.npz',allow_pickle=False));targets=collections.defaultdict(set);excluded=[]
 for u,m,r in zip(val['user_id'],val['movie_id'],val['rating']):
  if r>=4 and int(m) in lookup and int(m) not in seen[int(u)]:targets[int(u)].add(int(m))
 eligible=[]
 for u in sorted(set(map(int,val['user_id']))):
  if X[u].nnz and targets[u]:eligible.append(u)
  else:excluded.append(u)
 enc={k:{s:i+1 for i,s in enumerate(values)} for k,values in rv.items()};movie={int(m['movie_id']):m for m in meta['movies']};h=np.zeros((len(eligible),10),dtype='int32');g=np.zeros_like(h)
 for i,u in enumerate(eligible):
  seq=meta['histories'].get(str(u),[]);mh=[enc['movie_id'][str(m)] for m in seq];gh=[enc['genres'][name] for m in seq for name in movie[m]['genres']][-10:]
  if mh:h[i,-len(mh):]=mh
  if gh:g[i,-len(gh):]=gh
 features={k:table['user_'+k][eligible] for k in ['user_id','gender','age','occupation','zip_code']};features.update(hist_movie_id=h,hist_genres=g);uv=model(features,training=False).numpy();lex=np.load(ROOT/'movie_ids.npy',allow_pickle=False);emb=np.load(ROOT/'item_embeddings.npy',allow_pickle=False);lex_lookup={int(m):i for i,m in enumerate(lex)};scores=uv@emb[[lex_lookup[int(m)] for m in catalog]].T
 engine.load();nontrain=sorted(set(engine.movies)-set(map(int,catalog)));observed={};decoded=np.array([0]+[int(m) for m in v['movie_id']])
 def observe(d,training=False):
  out=original(d,training=training);observed['ids']=decoded[np.asarray(d['movie_id'],dtype=int)].tolist();observed['predictions']=np.asarray(out).ravel().tolist();return out
 manager.ranking_model=observe;rows=[]
 for i,uid in enumerate(eligible):
  idx=np.array([j for j,m in enumerate(catalog) if int(m) not in seen[uid]]);cf=np.asarray((X[uid]@S).toarray()).ravel();channels={'YT100':scores[i],'CF100':cf,'Popular100':pop};pools={name:catalog[idx[np.lexsort((catalog[idx],-score[idx]))[:100]]].tolist() for name,score in channels.items()}
  result=engine.recommend(uid,{'exclude_ids':nontrain},'',top_k=20)
  assert all(m in lookup and m not in seen[uid] for m in observed['ids'])
  pools['ActualChatPool']=observed['ids'];union=sorted({m for pool in pools.values() for m in pool});mid=np.array(union,dtype='int32');d={k:np.full(len(mid),table['user_'+k][uid],dtype='int32') for k in ['user_id','gender','age','occupation','zip_code']};d.update({k:table['item_'+k][mid] for k in ['movie_id','genres','startYear']});pred=np.asarray(original(d,training=False)).ravel();rankscore=dict(zip(union,map(float,pred)));row={'user_id':uid,'history_positive_count':X[uid].nnz,'target_ids':sorted(targets[uid]),'candidate_count':len(idx),'pools':{},'methods':{}}
  for name,pool in pools.items():
   relevant=len(set(pool)&targets[uid]);row['pools'][name]={'size':len(pool),'ids':pool,'recall_ceiling':relevant/len(targets[uid]),'oracle_Recall@20':min(20,relevant)/len(targets[uid])}
   for order_name,key in [('Popular',lambda m:(-pop[lookup[m]],m)),('DeepFM',lambda m:(-rankscore[m],m))]:
    rank=sorted(pool,key=key)[:20];row['methods'][name+'_'+order_name]={'ids':rank,**metric(rank,targets[uid],genres),'failed':False}
  actual=[m['movie_id'] for m in result['items']];row['methods']['ActualChat_mix_and_diversity']={'ids':actual,**metric(actual,targets[uid],genres),'failed':False};row['degradation']=result['degradation'];row['YT_CF_overlap_at100']=len(set(pools['YT100'])&set(pools['CF100']))/100
  # Quantify exact equality of the observer's real engine inputs and independent frozen tables.
  assert all(abs(rankscore[m]-p)<1e-5 for m,p in zip(observed['ids'],observed['predictions']))
  rows.append(row)
 methods=list(rows[0]['methods']);summary=summarize(rows,methods,catalog);pool_summary={name:{k:ci([r['pools'][name][k] for r in rows]) for k in ['size','recall_ceiling','oracle_Recall@20']} for name in rows[0]['pools']}
 paired={name:ci([r['methods'][name+'_DeepFM']['NDCG@20']-r['methods'][name+'_Popular']['NDCG@20'] for r in rows]) for name in pool_summary}
 segments={}
 for name,low,high in [('history_1_10',1,10),('history_11_50',11,50),('history_51_plus',51,100000)]:
  group=[r for r in rows if low<=r['history_positive_count']<=high]
  segments[name]={'users':len(group),'YT100_recall_ceiling':ci([r['pools']['YT100']['recall_ceiling'] for r in group]),'CF100_recall_ceiling':ci([r['pools']['CF100']['recall_ceiling'] for r in group])}
 report={'scope':'original validation already used for checkpoint selection, development diagnostics only; test.npz never read','eligible_users':len(rows),'heldout_users':len(set(map(int,val['user_id']))),'excluded_user_ids':excluded,'catalogue_size':len(catalog),'pool_summary':pool_summary,'ranking_summary':summary,'paired_DeepFM_minus_Popular_NDCG20_same_pool':paired,'segments':segments,'mean_YT_CF_overlap100':float(np.mean([r['YT_CF_overlap_at100'] for r in rows])),'ranking_user_id_OOV':int(sum(table['user_user_id'][eligible]==0)),'history_nonpadding_items':int((h!=0).sum()),'actual_engine_note':'Current chat engine, empty intent, warm catalogue masked explicitly; not the homepage four-channel pipeline. Real candidate IDs observed at model call; independent table scores match. Fixed fusion/diversity weights unchanged.','per_user':rows}
 save('NEURAL_ROUTE_DIAGNOSIS.json',report);print(json.dumps({k:report[k] for k in ['eligible_users','pool_summary','ranking_summary','paired_DeepFM_minus_Popular_NDCG20_same_pool','ranking_user_id_OOV','mean_YT_CF_overlap100']}),flush=True)
 return {k:report[k] for k in ['eligible_users','pool_summary','ranking_summary','paired_DeepFM_minus_Popular_NDCG20_same_pool','segments','ranking_user_id_OOV','mean_YT_CF_overlap100']}

if __name__=='__main__':
 start=time.perf_counter();meta=json.loads((ROOT/'metadata.json').read_text());train=dict(np.load(ROOT/'train.npz',allow_pickle=False));assert int(train['timestamp'].max())<975768738;genres={int(m['movie_id']):set(m['genres']) for m in meta['movies']}
 folds=rolling(train,meta,genres);result=neural(meta,train,genres);report={'version':'diagnostics-v1','test_read':False,'new_neural_models_trained':False,'rolling':folds,'seen_validation':result,'seconds':round(time.perf_counter()-start,3)};save('SUMMARY.json',report)

