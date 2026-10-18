"""Full-catalogue evaluation with explicit exclusions and paired bootstrap."""
import json,time,hashlib,collections
from pathlib import Path
import numpy as np
from scipy import sparse
from recdata import ROOT,OUT,SEED,save_json

def metrics(ranked,targets,genres):
    target=set(targets);v={}
    for k in (10,20):
        hits=np.array([int(x in target) for x in ranked[:k]],dtype='float64');discount=1/np.log2(np.arange(2,len(hits)+2))
        v['Recall@'+str(k)]=float(hits.sum()/len(target));v['NDCG@'+str(k)]=float((hits*discount).sum()/np.sum(1/np.log2(np.arange(2,min(k,len(target))+2))))
    pairs=[]
    for i,a in enumerate(ranked):
        for b in ranked[i+1:]:
            ga,gb=genres.get(a,set()),genres.get(b,set())
            if ga and gb:pairs.append(1-len(ga&gb)/len(ga|gb))
    v['genre_diversity@20']=float(np.mean(pairs)) if pairs else None
    v['valid_genre_pairs']=len(pairs)
    return v

def ci(values):
    a=np.asarray(values,dtype='float64');n=len(a)
    if not n:return {'mean':None,'ci95':None,'n':0}
    rng=np.random.default_rng(SEED);b=np.empty(2000)
    for i in range(2000):b[i]=a[rng.integers(0,n,n)].mean()
    return {'mean':float(a.mean()),'ci95':[float(x) for x in np.quantile(b,[.025,.975])],'n':n}

def load_context():
    meta=json.loads((OUT/'metadata.json').read_text());train=dict(np.load(OUT/'train.npz',allow_pickle=False));catalog=np.array(meta['catalog'],dtype='int64');lookup={int(m):i for i,m in enumerate(catalog)}
    maxu=max(int(u['user_id']) for u in meta['users']);mask=train['rating']>=4
    ui=train['user_id'][mask];mi=np.array([lookup[int(m)] for m in train['movie_id'][mask]])
    X=sparse.csr_matrix((np.ones(len(ui),dtype='float32'),(ui,mi)),shape=(maxu+1,len(catalog)))
    seen=collections.defaultdict(set)
    for u,m in zip(train['user_id'],train['movie_id']):seen[int(u)].add(int(m))
    genres={int(m['movie_id']):set(m['genres']) for m in meta['movies']}
    return meta,train,catalog,lookup,X,seen,genres

def evaluate(methods,phase,context):
    meta,train,catalog,lookup,X,seen,genres=context;hold=dict(np.load(OUT/(phase+'.npz'),allow_pickle=False));by=collections.defaultdict(list)
    for u,m,rating in zip(hold['user_id'],hold['movie_id'],hold['rating']):
        if rating>=4:by[int(u)].append(int(m))
    rows=[];excluded=[];catalog_set=set(catalog.tolist());unknown_targets=0
    for uid in sorted(set(hold['user_id'].tolist())):
        all_targets=by.get(uid,[]);unknown=[m for m in all_targets if m not in catalog_set];unknown_targets+=len(unknown)
        targets=sorted({m for m in all_targets if m in catalog_set and m not in seen[uid]})
        reasons=[]
        if X[uid].nnz==0:reasons.append('no_positive_train_history')
        if not all_targets:reasons.append('no_positive_heldout')
        elif not targets:reasons.append('no_eligible_catalogue_target')
        if reasons:excluded.append({'user_id':uid,'reasons':reasons,'heldout_positive_count':len(all_targets),'unknown_item_targets':len(unknown)});continue
        mask=np.array([int(m) not in seen[uid] for m in catalog]);pool=catalog[mask]
        row={'user_id':uid,'candidate_count':len(pool),'candidate_sha256':hashlib.sha256(pool.astype('<i8').tobytes()).hexdigest(),'targets':targets,'target_count':len(targets),'methods':{}}
        for name,scorer in methods.items():
            try:
                score=np.asarray(scorer(uid),dtype='float64');assert score.shape==(len(catalog),) and np.isfinite(score).all()
                idx=np.flatnonzero(mask);top=idx[np.lexsort((catalog[idx],-score[idx]))[:20]];ranked=catalog[top].tolist()
                result={'ranked_ids':ranked,'failed':False,**metrics(ranked,targets,genres)}
            except Exception as error:result={'ranked_ids':[],'failed':True,'error_type':type(error).__name__,'error':str(error),**metrics([],targets,genres)}
            row['methods'][name]=result
        rows.append(row)
    summary={'protocol':'rec-v1','phase':phase,'candidate_mode':'full_train_catalogue_minus_user_train_observed','catalogue_denominator':len(catalog),'heldout_users':len(set(hold['user_id'].tolist())),'eligible_users':len(rows),'excluded_users':len(excluded),'excluded_reason_counts':dict(collections.Counter(reason for x in excluded for reason in x['reasons'])),'unknown_item_positive_targets':unknown_targets,'methods':{}}
    for name in methods:
        values={k:ci([x['methods'][name][k] for x in rows]) for k in ['Recall@10','Recall@20','NDCG@10','NDCG@20']}
        recommended={m for x in rows for m in x['methods'][name]['ranked_ids']};div=[x['methods'][name]['genre_diversity@20'] for x in rows if x['methods'][name]['genre_diversity@20'] is not None]
        values.update({'coverage@20':len(recommended)/len(catalog),'recommended_unique':len(recommended),'genre_diversity@20':ci(div),'diversity_users_denominator':len(div),'failures':sum(x['methods'][name]['failed'] for x in rows)})
        summary['methods'][name]=values
    names=list(methods)
    summary['paired_differences']={}
    for name in names[1:]:
        summary['paired_differences'][name+' minus '+names[0]]={k:ci([x['methods'][name][k]-x['methods'][names[0]][k] for x in rows]) for k in ['Recall@10','Recall@20','NDCG@10','NDCG@20']}
    stem=phase+'_'+('_'.join(methods))
    with (OUT/(stem+'_per_user.jsonl')).open('w') as f:
        for row in rows:f.write(json.dumps(row)+'\n')
    save_json(OUT/(stem+'_excluded.json'),excluded);save_json(OUT/(stem+'_summary.json'),summary)
    print(json.dumps(summary),flush=True);return summary

def baselines():
    ctx=load_context();_,train,catalog,lookup,X,seen,genres=ctx
    popularity=np.asarray(X.sum(axis=0)).ravel().astype('float32')
    c=(X.T@X).toarray().astype('float32');freq=np.diag(c).copy();den=np.sqrt(freq[:,None]*freq[None,:]);sim=np.divide(c,den,out=np.zeros_like(c),where=den>0);sim*=c/(c+10);np.fill_diagonal(sim,0)
    # Fixed cosine similarity with shrinkage10, top100 neighbors; no tuning on test.
    rows=[];cols=[];vals=[]
    for i in range(len(catalog)):
        order=np.lexsort((catalog,-sim[i]))[:100];order=order[sim[i,order]>0];rows.extend([i]*len(order));cols.extend(order.tolist());vals.extend(sim[i,order].tolist())
    S=sparse.csr_matrix((np.array(vals,dtype='float32'),(rows,cols)),shape=sim.shape);sparse.save_npz(OUT/'itemcf_similarity.npz',S);sparse.save_npz(OUT/'positive_interactions.npz',X);np.save(OUT/'popularity.npy',popularity)
    methods={'Popular':lambda u:popularity,'ItemCF':lambda u:np.asarray((X[u]@S).toarray()).ravel()}
    for phase in ['validation','test']:evaluate(methods,phase,ctx)

if __name__=='__main__':baselines()
