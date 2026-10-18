"""Small content/CF adapter over rec-v1 artifacts and the existing DeepFM model."""
import json,time,threading
from pathlib import Path
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import text
from app.database import SessionLocal
from app.models import Movie,TitleCrew
from .reliability import Resilience

class MovieEngine:
    def __init__(self):
        self.lock=threading.Lock();self.ready=False;self.resilience=Resilience();self.rank_lock=threading.Lock()
    def load(self):
        if self.ready:return
        with self.lock:
            if self.ready:return
            path=Path('/artifacts/rec_v1');self.meta=json.loads((path/'metadata.json').read_text())
            self.tab=dict(np.load(path/'feature_tables.npz',allow_pickle=False))
            train=dict(np.load(path/'train.npz',allow_pickle=False));mask=train['rating']>=4
            self.ids=np.array(sorted(m['movie_id'] for m in self.meta['movies']),dtype=int);self.lookup={int(m):i for i,m in enumerate(self.ids)}
            uid=train['user_id'][mask];mi=np.array([self.lookup[int(m)] for m in train['movie_id'][mask]])
            self.X=sparse.csr_matrix((np.ones(len(uid)),(uid,mi)),shape=(int(train['user_id'].max())+1,len(self.ids)),dtype=np.float32)
            self.pop=np.asarray(self.X.sum(axis=0)).ravel();self.pop=self.pop/max(1,float(self.pop.max()))
            norm=np.sqrt(np.asarray(self.X.multiply(self.X).sum(axis=0))).ravel();norm[norm==0]=1
            binary=self.X.multiply(1/norm).tocsr();self.cf=(binary.T@binary).tocsr();counts=(self.X.T@self.X).tocsr();counts.data=counts.data/(counts.data+10);self.cf=self.cf.multiply(counts).tocsr();self.cf.setdiag(0);self.cf.eliminate_zeros()
            for i in range(self.cf.shape[0]):
                a,b=self.cf.indptr[i:i+2]
                if b-a>100:
                    vals=self.cf.data[a:b];keep=np.lexsort((self.cf.indices[a:b],-vals))[:100];remove=np.ones(b-a,bool);remove[keep]=False;vals[remove]=0
            self.cf.eliminate_zeros()
            self.seen={}
            for u,m in zip(train['user_id'],train['movie_id']):self.seen.setdefault(int(u),set()).add(int(m))
            self.movies={int(m['movie_id']):{'movie_id':int(m['movie_id']),'title':m['title'],'genres':m['genres'],'runtime_minutes':None,'directors':[],'year':m.get('startYear'),'metadata_status':'unverified'} for m in self.meta['movies']}
            with SessionLocal() as db:
                quality={int(r.movie_id):r.status for r in db.execute(text('SELECT movie_id,status FROM movie_metadata_quality'))}
                for m,crew in db.query(Movie,TitleCrew).outerjoin(TitleCrew,Movie.imdb_id==TitleCrew.tconst).all():
                    if m.movie_id in self.movies:self.movies[m.movie_id].update(runtime_minutes=m.runtime_minutes,directors=(crew.directors or []) if crew and quality.get(m.movie_id)=='identity_verified' else [],metadata_status=quality.get(m.movie_id,'unverified'))
            docs=[' '.join([self.movies[int(i)]['title']]+self.movies[int(i)]['genres']*3) for i in self.ids]
            self.vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=25000,dtype=np.float32)
            self.text=self.vectorizer.fit_transform(docs).tocsr()
            out=Path('/artifacts/content_v1');out.mkdir(exist_ok=True)
            sparse.save_npz(out/'title_genre_tfidf.npz',self.text)
            (out/'index.json').write_text(json.dumps({'version':'content-v1','source':'official MovieLens titles and genres only','movie_ids':self.ids.tolist(),'vocabulary':{k:int(v) for k,v in self.vectorizer.vocabulary_.items()},'idf':self.vectorizer.idf_.tolist(),'images_used':False}),encoding='utf-8')
            self.ready=True
    def details(self,ids):
        self.load();return [dict(self.movies[i],poster_url=f'/api/posters/{i}.png') for i in ids if i in self.movies]
    def recommend(self,uid,state,text_query='',preferences=(),top_k=6,faults=()):
        self.load();start=time.perf_counter();trace=[];degraded=[];warnings=[];uid=int(uid or 0)
        exclude=set(state.get('exclude_ids',[]))|self.seen.get(uid,set())
        director_seed=state.get('exclude_director_of');bad_directors=set()
        if director_seed:
            bad_directors=set(self.movies.get(director_seed,{}).get('directors',[]))
            if not bad_directors:return {'items':[],'warnings':['上一部电影缺少已核验导演，无法保证排除同一导演，请调整条件。'],'trace':[],'degradation':[],'eligible_count':0,'needs_clarification':True}
        missing_runtime=missing_director=0;eligible=[]
        for mid in self.ids:
            mid=int(mid);m=self.movies[mid];g=set(m['genres'])
            if mid in exclude or not set(state.get('include_genres',[]))<=g or set(state.get('exclude_genres',[]))&g:continue
            runtime=m['runtime_minutes']
            if 'max_runtime' in state or 'min_runtime' in state:
                if runtime is None:missing_runtime+=1;continue
                if runtime>state.get('max_runtime',100000) or runtime<state.get('min_runtime',0):continue
            if bad_directors:
                if not m['directors']:missing_director+=1;continue
                if bad_directors&set(m['directors']):continue
            eligible.append(self.lookup[mid])
        trace.append({'tool':'filter','input_count':len(self.ids),'eligible_count':len(eligible),'missing_runtime_excluded':missing_runtime,'missing_director_excluded':missing_director})
        if not eligible:return {'items':[],'warnings':['没有满足全部已知硬约束的电影；请放宽条件。'],'trace':trace,'degradation':degraded,'eligible_count':0}
        idx=np.array(eligible);channels={'popular':self.pop};cfscore=np.zeros(len(self.ids),dtype=np.float32)
        if 0<uid<self.X.shape[0]:cfscore=np.asarray((self.X[uid]@self.cf).toarray()).ravel()
        def channel(name,fn):
            def run():
                if name in faults:raise ConnectionError('injected')
                return fn()
            try:channels[name]=self.resilience.call('recall_'+name,run,timeout=.4,trace=trace)
            except Exception as exc:degraded.append('recall_'+name+':'+type(exc).__name__)
        channel('itemcf',lambda:cfscore)
        def content():
            seed=state.get('similar_to')
            if seed in self.lookup:return np.asarray((self.text@self.text[self.lookup[seed]].T).toarray()).ravel()
            query=' '.join(state.get('include_genres',[]))+' '+text_query
            return np.asarray((self.text@self.vectorizer.transform([query]).T).toarray()).ravel()
        channel('text',content)
        def cached():
            if 'cache' in faults:raise ConnectionError('injected')
            import redis
            from redis.retry import Retry
            from redis.backoff import NoBackoff
            cache=redis.Redis(host='redis',port=6379,socket_connect_timeout=.15,socket_timeout=.15,retry=Retry(NoBackoff(),0))
            key='ca:profile:rec-v1:'+str(uid)
            raw=cache.get(key)
            if raw is not None:
                value=json.loads(raw)
                if value.get('version')!='rec-v1' or not isinstance(value.get('indices'),list) or any(type(i) is not int or not 0<=i<len(self.ids) for i in value['indices']):raise ValueError('invalid_cached_profile')
                return value['indices']
            indices=self.X[uid].indices.tolist() if 0<uid<self.X.shape[0] else []
            cache.setex(key,3600,json.dumps({'version':'rec-v1','indices':indices}))
            return indices
        try:
            profile_indices=self.resilience.call('cache',cached,timeout=.4,attempts=1,trace=trace)
            if 'itemcf' in channels:
                row=sparse.csr_matrix((np.ones(len(profile_indices),dtype=np.float32),([0]*len(profile_indices),profile_indices)),shape=(1,len(self.ids)))
                channels['itemcf']=np.asarray((row@self.cf).toarray()).ravel()
        except Exception as exc:degraded.append('cache:'+type(exc).__name__+':local_train_profile')
        candidates=set()
        for name,scores in channels.items():
            if name=='text' and not np.any(scores[idx]>0):
                trace.append({'tool':'recall','channel':name,'count':0,'skipped':'no_positive_text_similarity'});continue
            order=idx[np.lexsort((self.ids[idx],-scores[idx]))[:100]];candidates.update(order.tolist())
            trace.append({'tool':'recall','channel':name,'count':len(order)})
        arr=np.array(sorted(candidates));mids=self.ids[arr];base=self.pop[arr].astype(float);ranker='popular'
        try:
            if 'ranking' in faults:raise RuntimeError('injected')
            from online.ranking.resource_manager import RankingResourceManager
            manager=RankingResourceManager();manager._ensure_resources_loaded()
            if manager.ranking_model is None:raise RuntimeError('model_unavailable')
            user=uid if 0<=uid<len(self.tab['user_user_id']) else 0
            features={k:np.full(len(mids),self.tab['user_'+k][user],dtype='int32') for k in ['user_id','gender','age','occupation','zip_code']}
            features.update({k:self.tab['item_'+k][mids] for k in ['movie_id','genres','startYear']})
            with self.rank_lock:base=np.asarray(manager.ranking_model(features,training=False)).ravel().astype(float)
            ranker='deepfm-rec-v1'
        except Exception as exc:degraded.append('ranking:'+type(exc).__name__+':popular')
        def normalize(x):return x/(max(float(np.max(x)),1e-8))
        score=.75*base+.10*normalize(channels.get('itemcf',self.pop)[arr])+.15*normalize(channels.get('text',self.pop)[arr])
        for pref in preferences:
            if pref['key']=='include_genres':score+=np.array([.12 if pref['value'] in self.movies[int(m)]['genres'] else 0 for m in mids])
        # Greedy genre diversity with explicit fixed penalty, no test-based tuning.
        remaining=list(range(len(mids)));selected=[]
        while remaining and len(selected)<top_k:
            def objective(i):
                g=set(self.movies[int(mids[i])]['genres']);sim=max((len(g&set(self.movies[int(mids[j])]['genres']))/max(1,len(g|set(self.movies[int(mids[j])]['genres']))) for j in selected),default=0)
                return (score[i]-.08*sim,-int(mids[i]))
            winner=max(remaining,key=objective);selected.append(winner);remaining.remove(winner)
        items=[]
        for i in selected:
            item=self.details([int(mids[i])])[0];item.update(score=round(float(score[i]),6),reason='库内类型：'+'、'.join(item['genres'])+('；片长 '+str(item['runtime_minutes'])+' 分钟' if item['runtime_minutes'] else '；片长未知'),ranking_strategy=ranker);items.append(item)
        trace.extend([{'tool':'rank','strategy':ranker,'count':len(mids)},{'tool':'rerank','strategy':'genre-diversity-fixed-0.08','count':len(items)}])
        return {'items':items,'warnings':warnings,'trace':trace,'degradation':degraded,'eligible_count':len(eligible),'elapsed_ms':round((time.perf_counter()-start)*1000,2),'missing_runtime_excluded':missing_runtime,'missing_director_excluded':missing_director}

engine=MovieEngine()


