"""rec-v1 data contract; official text input only, no external pickle execution."""
from pathlib import Path
import json, zipfile, hashlib, collections
import numpy as np
import pandas as pd
ROOT=Path('/project'); OUT=ROOT/'artifacts/rec_v1'; OUT.mkdir(parents=True,exist_ok=True)
SEED=20261018
USER_FEATURES=['user_id','gender','age','occupation','zip_code']
ITEM_FEATURES=['movie_id','genres','startYear']
def save_json(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def load_source():
    with zipfile.ZipFile(ROOT/'data/ml-1m-reference.zip') as z:
        with z.open('ml-1m/ratings.dat') as f:r=pd.read_csv(f,sep=':',header=None,usecols=[0,2,4,6],names=['user_id','movie_id','rating','timestamp'],dtype='int64')
        users=[]
        for line in z.read('ml-1m/users.dat').decode('latin-1').splitlines():
            a=line.split('::');users.append(dict(zip(USER_FEATURES,a)))
        movies=[]
        for line in z.read('ml-1m/movies.dat').decode('latin-1').splitlines():
            mid,title,genres=line.split('::');year=title[-5:-1] if title.endswith(')') and title[-5:-1].isdigit() else 'unknown'
            movies.append({'movie_id':int(mid),'title':title,'genres':genres.split('|'),'startYear':year})
    return r,users,movies

def prepare():
    cfg=json.loads((ROOT/'configs/eval_protocol.json').read_text());src=ROOT/'data/ml-1m-reference.zip'
    assert hashlib.sha256(src.read_bytes()).hexdigest()==cfg['source_sha256']
    r,users,movies=load_source();r=r.sort_values(['timestamp','user_id','movie_id'],kind='stable').reset_index(drop=True)
    t1,t2=cfg['train_end_exclusive'],cfg['validation_end_exclusive']
    split={'train':r[r.timestamp<t1].copy(),'validation':r[(r.timestamp>=t1)&(r.timestamp<t2)].copy(),'test':r[r.timestamp>=t2].copy()}
    assert {k:len(v) for k,v in split.items()}==cfg['counts']
    assert r.rating.between(1,5).all() and not r.duplicated(['user_id','movie_id']).any()
    train=split['train'];catalog=sorted(train.movie_id.unique().tolist());user_ids=sorted(train.user_id.unique().tolist());ms={m['movie_id']:m for m in movies};us={int(u['user_id']):u for u in users}
    vocab={}
    for key in USER_FEATURES:vocab[key]=sorted({str(us[u][key]) for u in user_ids})
    for key in ITEM_FEATURES:
        vocab[key]=sorted({str(mid) if key=='movie_id' else ms[mid]['genres'][0] if key=='genres' else ms[mid]['startYear'] for mid in catalog})
    # Retrieval uses all declared genres, not just ranking's primary genre.
    retrieval_vocab=dict(vocab);retrieval_vocab['genres']=sorted({g for mid in catalog for g in ms[mid]['genres']})
    enc={k:{x:i+1 for i,x in enumerate(v)} for k,v in vocab.items()};re={k:{x:i+1 for i,x in enumerate(v)} for k,v in retrieval_vocab.items()}
    uf={k:np.zeros(max(us)+1,dtype='int32') for k in USER_FEATURES}
    for u in users:
        uid=int(u['user_id'])
        for k in USER_FEATURES:uf[k][uid]=enc[k].get(str(u[k]),0)
    it={k:np.zeros(max(ms)+1,dtype='int32') for k in ITEM_FEATURES}
    for mid in catalog:
        for k in ITEM_FEATURES:
            val=str(mid) if k=='movie_id' else ms[mid]['genres'][0] if k=='genres' else ms[mid]['startYear'];it[k][mid]=enc[k].get(val,0)
    # Training positives get ONLY strictly earlier positive interactions; equal-time events are grouped.
    positives=train[train.rating>=4];n=len(positives);hist=np.zeros((n,10),dtype='int32');hg=np.zeros((n,10),dtype='int32');row_u=np.zeros(n,dtype='int32');row_m=np.zeros(n,dtype='int32');histories={};seen={};pos_by_user={};cursor=0
    for uid,group in train.groupby('user_id',sort=True):
        uid=int(uid);seen[uid]=set(group.movie_id.tolist());prior=[]
        for ts,events in group.groupby('timestamp',sort=True):
            current=events.loc[events.rating>=4,'movie_id'].tolist()
            encoded=[re['movie_id'][str(mid)] for mid in prior[-10:]]
            genres=[re['genres'][g] for mid in prior[-10:] for g in ms[mid]['genres']][-10:]
            for mid in current:
                row_u[cursor]=uid;row_m[cursor]=mid
                if encoded:hist[cursor,-len(encoded):]=encoded
                if genres:hg[cursor,-len(genres):]=genres
                cursor+=1
            prior.extend(current)
        histories[uid]=prior[-10:];pos_by_user[uid]=prior
    assert cursor==n
    rec={k:uf[k][row_u] for k in USER_FEATURES};rec.update(movie_id=np.array([re['movie_id'][str(x)] for x in row_m],dtype='int32'),hist_movie_id=hist,hist_genres=hg)
    np.savez_compressed(OUT/'retrieval_train.npz',**rec)
    # Complete item feature table, no skipped negatives; persist every sampled pair and source.
    rng=np.random.default_rng(SEED);neg_u=[];neg_m=[];neg_ts=[]
    for uid,g in positives.groupby('user_id',sort=True):
        pool=np.array(sorted(set(catalog)-seen[int(uid)]),dtype='int32');need=len(g)*4
        if len(pool)==0:raise ValueError('No negative pool for '+str(uid))
        # Four distinct negatives per positive, repeats across positives allowed.
        for ts in g.timestamp.values:
            sampled=rng.choice(pool,size=min(4,len(pool)),replace=False)
            neg_u.extend([int(uid)]*len(sampled));neg_m.extend(sampled.tolist());neg_ts.extend([int(ts)]*len(sampled))
    train_u=train.user_id.to_numpy(dtype='int32');train_m=train.movie_id.to_numpy(dtype='int32')
    ru=np.concatenate([train_u,np.asarray(neg_u,dtype='int32')]);rm=np.concatenate([train_m,np.asarray(neg_m,dtype='int32')]);labels=np.concatenate([(train.rating.values>=4).astype('float32'),np.zeros(len(neg_u),dtype='float32')]);source=np.concatenate([np.where(train.rating.values>=4,1,2).astype('uint8'),np.full(len(neg_u),3,dtype='uint8')])
    rt=np.concatenate([train.timestamp.to_numpy(dtype='int64'),np.asarray(neg_ts,dtype='int64')])
    pairs={'user_id_raw':ru,'movie_id_raw':rm,'timestamp':rt,'label':labels,'source':source}
    np.savez_compressed(OUT/'ranking_pairs.npz',**pairs)
    # Check negative membership and real ratio without excluding future positives.
    assert not np.isin(np.asarray(neg_u,dtype='int64')*len(it['movie_id'])+np.asarray(neg_m,dtype='int64'),train_u.astype('int64')*len(it['movie_id'])+train_m).any()
    assert rt.max()<t1 and len(neg_u)==n*4
    np.savez_compressed(OUT/'feature_tables.npz',**{'user_'+k:v for k,v in uf.items()},**{'item_'+k:v for k,v in it.items()})
    for name,df in split.items():np.savez_compressed(OUT/(name+'.npz'),**{k:df[k].to_numpy(dtype='int64') for k in df})
    save_json(OUT/'vocab.json',vocab);save_json(OUT/'retrieval_vocab.json',retrieval_vocab)
    save_json(OUT/'metadata.json',{'users':users,'movies':movies,'catalog':catalog,'histories':histories,'positive_histories':pos_by_user})
    report={'protocol':'rec-v1','split_counts':{k:len(v) for k,v in split.items()},'catalog_items':len(catalog),'train_users':len(user_ids),'positive_train_interactions':n,'ranking_samples':len(ru),'source_counts':{'positive_observed':int((source==1).sum()),'low_rating_observed':int((source==2).sum()),'sampled_unobserved':int((source==3).sum())},'negative_requested_per_positive':4,'negative_actual_per_positive':len(neg_u)/n,'checks':{'train_time_max_lt_boundary':bool(rt.max()<t1),'sampled_negatives_exclude_train_observed':True,'history_strictly_earlier_timestamp':True,'no_imdb_aggregate_features':True,'vocab_fit_train_only':True},'vocab_sizes':{k:len(v)+1 for k,v in vocab.items()},'history_policy':'positive-only; left-pad zero; max10; equal timestamp events do not see each other','metadata_policy':'official user/movie metadata; primary genre and title release year; no fabricated adult attribute'}
    save_json(OUT/'PREPARE.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':prepare()
