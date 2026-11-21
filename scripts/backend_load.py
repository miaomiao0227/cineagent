import json,uuid,time,math,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from sqlalchemy import delete
from app.database import SessionLocal
from app.models import User
from app.behavior.models import BehaviorVersion
from app.behavior.recommendations import cache,MODEL_VERSION
from app.core.security import create_access_token
queries=['Mystery','Comedy','Drama','Sci-Fi','Adventure','Crime','Romance','Thriller','Animation','War','Western','Fantasy','Children','Documentary','Musical','Action','Film-Noir','Horror','Suspense','Family']
with SessionLocal.begin() as db:
    u=User(username='backend_load_'+uuid.uuid4().hex,is_active=1);db.add(u);db.flush();uid=u.user_id
jwt=create_access_token({'sub':str(uid)})
from urllib.parse import quote
records=[]
def key(q):return 'ca:recommendations:v1:'+str(uid)+':'+hashlib.sha256(json.dumps([uid,0,MODEL_VERSION,6,q],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def request(q):
    started=time.perf_counter()
    try:
        with urlopen(Request('http://127.0.0.1:8000/api/me/recommendations?limit=6&q='+quote(q),headers={'Authorization':'Bearer '+jwt}),timeout=30) as r:d=json.load(r);status=r.status
        return {'query':q,'status':status,'cache_status':d.get('cache_status'),'items':[x['movie_id'] for x in d['items']],'ms':(time.perf_counter()-started)*1000}
    except Exception as e:return {'query':q,'status':getattr(e,'code',0),'error_class':type(e).__name__,'ms':(time.perf_counter()-started)*1000}
def summarize(name,data,wall):
    times=sorted(x['ms'] for x in data)
    return {'arm':name,'attempts':len(data),'successes':sum(x['status']==200 for x in data),'p50_ms':round(times[math.ceil(.5*len(times))-1],2),'p95_ms':round(times[math.ceil(.95*len(times))-1],2),'throughput_rps':round(len(data)/wall,2),'wall_seconds':round(wall,2)}
try:
    for q in queries:request(q)
    summaries=[]
    for arm in ['cold_c1','warm_c1','warm_c8']:
        data=[];started=time.perf_counter();work=queries*(800 if arm=='warm_c8' else 100)
        if arm=='warm_c8':
            with ThreadPoolExecutor(8) as pool:data=list(pool.map(request,work))
        else:
            for q in work:
                if arm=='cold_c1':cache.delete(key(q))
                data.append(request(q))
        wall=time.perf_counter()-started
        records.extend({'arm':arm,**r} for r in data);summaries.append(summarize(arm,data,wall))
    # Same request order and candidate/model configuration in cold/warm comparison.
    cold=[x for x in records if x['arm']=='cold_c1'];warm=[x for x in records if x['arm']=='warm_c1']
    assert all(a.get('items')==b.get('items') for a,b in zip(cold,warm))
    report={'protocol':'BACKEND_EVAL_SPEC.md v2','source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app/app').rglob('*.py')},'model_version':MODEL_VERSION,'users':1,'queries':20,'warmup_excluded':20,'summary':summaries,'attempts':records}
    Path('/trial-ledger/BACKEND_LOAD_FINAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(summaries))
finally:
    keys=list(cache.scan_iter(match=f'ca:recommendations:v1:{uid}:*'))
    if keys:cache.delete(*keys)
    with SessionLocal.begin() as db:db.execute(delete(User).where(User.user_id==uid))
