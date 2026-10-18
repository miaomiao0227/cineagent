"""Reuse upstream model builders; train-only arrays, validation-only checkpoint selection."""
import os,json,time,random,pickle,collections
import numpy as np,tensorflow as tf
from recdata import ROOT,OUT,SEED,USER_FEATURES,ITEM_FEATURES,save_json
from receval import load_context,evaluate
from funrec.features.feature_column import FeatureColumn
from funrec.models.youtubednn import build_youtubednn_model
from funrec.models.deepfm import build_deepfm_model
from funrec.training.loss import sampledsoftmaxloss
random.seed(SEED);np.random.seed(SEED);tf.random.set_seed(SEED)
MODELS=OUT/'models';MODELS.mkdir(exist_ok=True)

def setup():
    ctx=load_context();meta,train,cat,lookup,X,seen,genres=ctx
    v=json.loads((OUT/'vocab.json').read_text());rv=json.loads((OUT/'retrieval_vocab.json').read_text());tab=dict(np.load(OUT/'feature_tables.npz',allow_pickle=False))
    enc={k:{x:i+1 for i,x in enumerate(a)} for k,a in rv.items()};mi={int(m['movie_id']):m for m in meta['movies']}
    hist=np.zeros((X.shape[0],10),dtype='int32');hg=np.zeros_like(hist)
    for uid,seq in meta['histories'].items():
        uid=int(uid);h=[enc['movie_id'][str(m)] for m in seq];g=[enc['genres'][g] for m in seq for g in mi[m]['genres']][-10:]
        if h:hist[uid,-len(h):]=h
        if g:hg[uid,-len(g):]=g
    allu={k:tab['user_'+k] for k in USER_FEATURES};allu.update(hist_movie_id=hist,hist_genres=hg)
    val=dict(np.load(OUT/'validation.npz',allow_pickle=False));targets=collections.defaultdict(set)
    for u,m,r in zip(val['user_id'],val['movie_id'],val['rating']):
        if r>=4 and int(m) in lookup and int(m) not in seen[int(u)]:targets[int(u)].add(int(m))
    eligible=sorted(u for u in targets if X[u].nnz)
    return ctx,v,rv,tab,allu,val,targets,eligible

def features(ru,rm,tab):
    return {**{k:tab['user_'+k][ru] for k in USER_FEATURES},**{k:tab['item_'+k][rm] for k in ITEM_FEATURES}}

def run():
    start=time.perf_counter();ctx,v,rv,tab,allu,val,targets,eligible=setup();meta,train,cat,lookup,X,seen,genres=ctx
    report={'protocol':'rec-v1','seed':SEED,'training_config':{'epochs_max':3,'batch_size':2048,'embedding_dim':16,'retrieval_units':[64,32],'ranking_units':[128,64,32],'learning_rate':.001,'retrieval_negative_sample':20},'checkpoint_selection':{'retrieval':'validation full-catalogue Recall@20','ranking':'validation sampled-pair binary crossentropy; no test labels used'},'epochs':{}}
    cols=[FeatureColumn(k,emb_dim=16,vocab_size=len(rv[k])+1,group=['user_dnn']) for k in USER_FEATURES]
    cols+=[FeatureColumn('movie_id',emb_dim=16,vocab_size=len(rv['movie_id'])+1,group=['target_item'])]
    for name,key in [('hist_movie_id','movie_id'),('hist_genres','genres')]:cols.append(FeatureColumn(name,emb_name=key,emb_dim=16,vocab_size=len(rv[key])+1,group=['raw_hist_seq'],type='varlen_sparse',max_len=10,combiner='mean'))
    full,um,im=build_youtubednn_model(cols,{'emb_dim':16,'neg_sample':20,'dnn_units':[64,32],'label_name':'movie_id'})
    full.compile(optimizer=tf.keras.optimizers.Adam(.001),loss=sampledsoftmaxloss)
    data=dict(np.load(OUT/'retrieval_train.npz',allow_pickle=False));labels=np.ones(len(data['user_id']),dtype='float32');best=-1.;weights=None;report['epochs']['retrieval']=[]
    item_encoded=np.array([rv['movie_id'].index(str(int(m)))+1 for m in cat],dtype='int32')
    for epoch in range(3):
        h=full.fit(data,labels,epochs=1,batch_size=2048,verbose=0,shuffle=True);loss=float(h.history['loss'][0]);assert np.isfinite(loss)
        uv=um({k:a[eligible] for k,a in allu.items()},training=False).numpy();iv=im({'movie_id':item_encoded},training=False).numpy();score=uv@iv.T;rec=[]
        for i,u in enumerate(eligible):
            mask=np.array([int(m) not in seen[u] for m in cat]);idx=np.flatnonzero(mask);top=idx[np.lexsort((cat[idx],-score[i,idx]))[:20]];rec.append(len(set(cat[top].tolist())&targets[u])/len(targets[u]))
        value=float(np.mean(rec));row={'epoch':epoch+1,'loss_diagnostic_only':loss,'validation_Recall@20':value,'validation_users':len(eligible)};report['epochs']['retrieval'].append(row);print(json.dumps(row),flush=True)
        if value>best:best=value;weights=full.get_weights();report['retrieval_best_epoch']=epoch+1
    full.set_weights(weights);um.save(str(MODELS/'user_model'));im.save(str(MODELS/'item_model'))
    lexids=np.asarray(rv['movie_id']);emb=im({'movie_id':np.arange(1,len(lexids)+1,dtype='int32')},training=False).numpy();assert np.isfinite(emb).all()
    np.save(OUT/'item_embeddings.npy',emb);np.save(OUT/'movie_ids.npy',lexids)
    del data,labels,full,weights
    cols=[FeatureColumn(k,emb_dim=16,vocab_size=len(v[k])+1,group=['deepfm','linear']) for k in USER_FEATURES+ITEM_FEATURES]
    rank,_,_=build_deepfm_model(cols,{'dnn_units':[128,64,32],'dropout_rate':.1,'linear_logits':True});rank.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy')
    pairs=dict(np.load(OUT/'ranking_pairs.npz',allow_pickle=False));f=features(pairs['user_id_raw'],pairs['movie_id_raw'],tab)
    # Validation-only sampled pair set: all eligible observed pairs +4 negatives per positive.
    vm=np.array([(int(u) in eligible and int(m) in lookup and int(m) not in seen[int(u)]) for u,m in zip(val['user_id'],val['movie_id'])]);vu=val['user_id'][vm];vi=val['movie_id'][vm];vy=(val['rating'][vm]>=4).astype('float32');vu0=vu.copy();vi0=vi.copy();observed=collections.defaultdict(set)
    for u,m in zip(vu,vi):observed[int(u)].add(int(m))
    nu=[];ni=[];rng=np.random.default_rng(SEED+1)
    for u in sorted(observed):
        pool=np.array(sorted(set(cat.tolist())-seen[u]-observed[u]),dtype='int32');n=int(((vu==u)&(vy==1)).sum())
        for _ in range(n):
            sample=rng.choice(pool,min(4,len(pool)),replace=False);nu.extend([u]*len(sample));ni.extend(sample.tolist())
    vu=np.concatenate([vu,np.array(nu,dtype='int32')]);vi=np.concatenate([vi,np.array(ni,dtype='int32')]);vy=np.concatenate([vy,np.zeros(len(nu),dtype='float32')]);vf=features(vu,vi,tab)
    np.savez_compressed(OUT/'ranking_validation_pairs.npz',user_id_raw=vu,movie_id_raw=vi,label=vy,source=np.concatenate([np.where(val['rating'][vm]>=4,1,2).astype('uint8'),np.full(len(nu),3,dtype='uint8')]))
    best=float('inf');weights=None;report['epochs']['ranking']=[]
    for epoch in range(3):
        h=rank.fit(f,pairs['label'],epochs=1,batch_size=2048,verbose=0,shuffle=True);loss=float(h.history['loss'][0]);assert np.isfinite(loss)
        pred=rank.predict(vf,batch_size=4096,verbose=0).ravel();pred=np.clip(pred,1e-7,1-1e-7);value=float(np.mean(-vy*np.log(pred)-(1-vy)*np.log(1-pred)))
        row={'epoch':epoch+1,'loss_diagnostic_only':loss,'validation_sampled_BCE':value,'validation_pairs':len(vy)};report['epochs']['ranking'].append(row);print(json.dumps(row),flush=True)
        if value<best:best=value;weights=rank.get_weights();report['ranking_best_epoch']=epoch+1
    rank.set_weights(weights);rank.save(str(MODELS/'ranking_model'))
    # Verify checkpoints and exact item-embedding association, not only array lengths.
    uload=tf.keras.models.load_model(str(MODELS/'user_model'),compile=False);rload=tf.keras.models.load_model(str(MODELS/'ranking_model'),compile=False)
    ub={k:a[eligible[:8]] for k,a in allu.items()};np.testing.assert_allclose(um(ub,training=False).numpy(),uload(ub,training=False).numpy(),rtol=1e-5,atol=1e-6)
    rb={k:a[:8] for k,a in vf.items()};np.testing.assert_allclose(rank(rb,training=False).numpy(),rload(rb,training=False).numpy(),rtol=1e-5,atol=1e-6)
    iload=tf.keras.models.load_model(str(MODELS/'item_model'),compile=False);np.testing.assert_allclose(iload({'movie_id':np.arange(1,len(lexids)+1,dtype='int32')},training=False).numpy(),emb,rtol=1e-5,atol=1e-6)
    uv=uload(allu,training=False).numpy();raw_lookup={int(mid):i for i,mid in enumerate(lexids)};ordered=emb[[raw_lookup[int(m)] for m in cat]];scores=uv@ordered.T
    rank_fn=tf.function(lambda d:rload(d,training=False),reduce_retracing=True)
    def rerank(uid):
        valid=np.array([int(m) not in seen[uid] for m in cat]);idx=np.flatnonzero(valid);idx=idx[np.lexsort((cat[idx],-scores[uid,idx]))[:100]];inputs=features(np.full(len(idx),uid,dtype='int32'),cat[idx],tab);p=rank_fn(inputs).numpy().ravel();out=np.full(len(cat),-1e9);out[idx]=p;return out
    popularity=np.load(OUT/'popularity.npy',allow_pickle=False);from scipy import sparse
    S=sparse.load_npz(OUT/'itemcf_similarity.npz')
    methods={'Popular':lambda u:popularity,'ItemCF':lambda u:np.asarray((X[u]@S).toarray()).ravel(),'YouTubeDNN':lambda u:scores[u],'YT100_DeepFM':rerank}
    for phase in ['validation','test']:evaluate(methods,phase,ctx)
    report.update({'ok':True,'reload_checks':True,'embedding_id_association_verified':True,'seconds':round(time.perf_counter()-start,3),'test_used_for_selection':False,'candidate_route':'YouTubeDNN full catalogue; YT100_DeepFM top100 unseen from same catalogue then DeepFM; no diversity reranker in this experiment'})
    save_json(OUT/'TRAINING.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':run()
