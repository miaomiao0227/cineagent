import json,uuid,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,func,delete
from app.database import SessionLocal
from app.models import User,Movie,Rating
from app.behavior.models import Behavior,BehaviorVersion
from app.core.security import create_access_token
checks={};ids=[]
def call(token,path,body=None):
    req=urllib.request.Request('http://127.0.0.1:8000/api/me'+path,data=json.dumps(body).encode() if body is not None else None,method='PUT' if body is not None else 'GET',headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,{}
try:
    with SessionLocal.begin() as db:
        before=db.scalar(select(func.count()).select_from(Rating));movie=db.scalar(select(Movie.movie_id).order_by(Movie.movie_id))
        for _ in range(2):
            u=User(username='behavior_check_'+uuid.uuid4().hex,is_active=1);db.add(u);db.flush();ids.append(u.user_id)
    tokens=[create_access_token({'sub':str(i)}) for i in ids];path=f'/movies/{movie}/behavior'
    code,a=call(tokens[0],path,{'favorite':True});checks['create']=code==200 and a['favorite']
    code,b=call(tokens[0],path,{'favorite':True});checks['idempotent_repeat']=a['behavior_version']==b['behavior_version']
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda _:call(tokens[0],path,{'seen':True}),range(16)))
    checks['concurrent_repeat']=all(c==200 for c,r in results) and len({r['behavior_version'] for c,r in results})==1
    with ThreadPoolExecutor(2) as pool:
        f1=pool.submit(call,tokens[0],path,{'rating':8});f2=pool.submit(call,tokens[0],path,{'favorite':False});f1.result();f2.result()
    code,r=call(tokens[0],'/behaviors');row=r['items'][0];checks['concurrent_fields_preserved']=row['rating']==8 and row['seen'] and not row['favorite'] and r['total']==1
    checks['owner_isolation']=call(tokens[1],'/behaviors')[1]['total']==0
    checks['read_behavior']=call(tokens[0],path)[1]['seen'] is True
    def legacy(method,body=None):
        url='http://127.0.0.1:8000/api/ratings'+('' if method=='POST' else '/movie/'+str(movie))
        req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+tokens[0]})
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
    legacy('POST',{'movie_id':movie,'rating':7})
    checks['legacy_rating_write']=legacy('GET')['rating']==7
    legacy('DELETE');checks['legacy_rating_clear']=legacy('GET')['has_rated'] is False
    # Make online movie the only eligible item: exclusion must make the set empty.
    from app.cineagent.engine import engine
    engine.load()
    result=engine.recommend(ids[0],{'exclude_ids':[i for i in engine.movies if i!=movie]},top_k=6)
    checks['watched_recommendation_exclusion']=result['eligible_count']==0 and not result['items']


    import time
    start=time.perf_counter();code,cold=call(tokens[0],'/recommendations');cold_ms=(time.perf_counter()-start)*1000
    start=time.perf_counter();code,warm=call(tokens[0],'/recommendations');warm_ms=(time.perf_counter()-start)*1000
    checks['cache_miss_then_hit']=cold['cache_status']=='miss' and warm['cache_status']=='hit'
    checks['cache_same_items']=[x['movie_id'] for x in cold['items']]==[x['movie_id'] for x in warm['items']]
    watched=warm['items'][0]['movie_id']
    call(tokens[0],f'/movies/{watched}/behavior',{'seen':True})
    code,updated=call(tokens[0],'/recommendations')
    checks['behavior_version_cache_invalidation']=updated['cache_status']=='miss' and updated['behavior_version']>warm['behavior_version'] and watched not in [x['movie_id'] for x in updated['items']]
    checks['cache_owner_isolation']=call(tokens[1],'/recommendations')[1]['cache_status']=='miss'
    from app.behavior.recommendations import recommendations,cache
    import redis
    class Unavailable:
        def get(self,*args):raise redis.ConnectionError('injected')
        def setex(self,*args):raise redis.ConnectionError('injected')
        def set(self,*args,**kwargs):raise redis.ConnectionError('injected')
    with SessionLocal() as db:fallback=recommendations(db,ids[0],cache_client=Unavailable())
    checks['redis_failure_fallback']=fallback['cache_status']=='unavailable' and bool(fallback['items'])
    for uid in ids:
        keys=list(cache.scan_iter(match='ca:recommendations:v1:'+str(uid)+':*'))
        if keys:cache.delete(*keys)
    print(json.dumps({'single_observation_cold_ms':round(cold_ms,2),'single_observation_warm_ms':round(warm_ms,2),'note':'not a load benchmark'}))
    checks['rating_validation']=call(tokens[0],path,{'rating':11})[0]==422
    checks['null_flag_rejected']=call(tokens[0],path,{'seen':None})[0]==422
    checks['unknown_movie']=call(tokens[0],'/movies/2147483647/behavior',{'seen':True})[0]==404
    checks['owner_spoof_rejected']=call(tokens[0],path,{'user_id':ids[1],'seen':True})[0]==422
    checks['pagination_bound']=call(tokens[0],'/behaviors?page_size=101')[0]==422
    code,r=call(tokens[0],path,{'rating':None});checks['rating_clear']=r.get('rating') is None
    with SessionLocal() as db:checks['offline_ratings_unchanged']=db.scalar(select(func.count()).select_from(Rating))==before
finally:
    with SessionLocal.begin() as db:
        db.execute(delete(Behavior).where(Behavior.user_id.in_(ids)));db.execute(delete(BehaviorVersion).where(BehaviorVersion.user_id.in_(ids)));db.execute(delete(User).where(User.user_id.in_(ids)))
from pathlib import Path
Path('/trial-ledger/BACKEND_BEHAVIOR_V1.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks));assert all(checks.values()),checks
