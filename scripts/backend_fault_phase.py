import json,uuid,time,sys
from pathlib import Path
from sqlalchemy import select,delete
from app.database import SessionLocal
from app.models import User,Movie
from app.jobs.models import Job
from app.core.security import create_access_token
from urllib.request import Request,urlopen
statefile=Path('/trial-ledger/BACKEND_FAULT_STATE.local.json');reportfile=Path('/trial-ledger/BACKEND_REAL_FAULTS.json')
def api(path,token,body=None):
    with urlopen(Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token}),timeout=30) as r:return json.load(r)
phase=sys.argv[1]
if phase=='create':
    with SessionLocal.begin() as db:
        u=User(username='backend_fault_'+uuid.uuid4().hex,is_active=1,is_superuser=1);db.add(u);db.flush();uid=u.user_id;mid=db.scalar(select(Movie.movie_id).order_by(Movie.movie_id))
    result=api('/api/admin/jobs',create_access_token({'sub':str(uid)}),{'request_id':str(uuid.uuid4()),'movie_ids':[mid]})
    record={'uid':uid,'job_id':result['id'],'started':time.time(),'scenario':sys.argv[2]}
    if sys.argv[2]=='redis_broker_and_recommendation_outage':
        fallback=api('/api/me/recommendations?limit=3',create_access_token({'sub':str(uid)}))
        assert len(fallback['items'])==3 and fallback['degradation']
        record['recommendation_fallback_items']=len(fallback['items']);record['recommendation_fallback']=True
        print('Real Redis outage: personalized recommendation returned 3 items through fallback')
    statefile.write_text(json.dumps(record));print('Task accepted:',result['state'])
else:
    s=json.loads(statefile.read_text());token=create_access_token({'sub':str(s['uid'])})
    if phase=='running':
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            j=api('/api/admin/jobs/'+s['job_id'],token)
            if j['state']=='running':print('RUNNING observed');break
            time.sleep(.1)
        else:raise RuntimeError('No running task observed')
    elif phase=='verify':
        deadline=time.monotonic()+110
        while time.monotonic()<deadline:
            j=api('/api/admin/jobs/'+s['job_id'],token)
            if j['state'] in ('succeeded','failed'):break
            time.sleep(1)
        assert j['state']=='succeeded',j
        reports=json.loads(reportfile.read_text()) if reportfile.exists() else []
        reports.append({'scenario':s['scenario'],'state':j['state'],'attempts':j['attempts'],'indexed_count':j['result']['indexed_count'],'elapsed_s':round(time.time()-s['started'],2),'recommendation_fallback':s.get('recommendation_fallback'),'fallback_items':s.get('recommendation_fallback_items')})
        reportfile.write_text(json.dumps(reports,indent=2));print(json.dumps(reports[-1]))
        with SessionLocal.begin() as db:db.execute(delete(Job).where(Job.id==uuid.UUID(s['job_id'])));db.execute(delete(User).where(User.user_id==s['uid']))
        statefile.unlink()
