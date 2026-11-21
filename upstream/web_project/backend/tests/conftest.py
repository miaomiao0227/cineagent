import os,json,uuid,urllib.request,urllib.error
import pytest
from sqlalchemy import delete,select
from app.database import SessionLocal
from app.models import User,Movie
from app.behavior.models import Behavior,BehaviorVersion
from app.jobs.models import Job
from app.core.security import create_access_token
BASE=os.getenv('BACKEND_TEST_URL','http://127.0.0.1:8000')
def http(path,method='GET',body=None,token=None,headers=None):
    h={'Content-Type':'application/json',**(headers or {})}
    if token:h['Authorization']='Bearer '+token
    q=urllib.request.Request(BASE+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers=h)
    try:
        with urllib.request.urlopen(q,timeout=30) as r:return r.status,json.load(r),{k.lower():v for k,v in r.headers.items()}
    except urllib.error.HTTPError as e:
        try:data=json.load(e)
        except Exception:data={}
        return e.code,data,{k.lower():v for k,v in e.headers.items()}
@pytest.fixture
def actors():
    ids=[]
    with SessionLocal.begin() as db:
        movies=list(db.scalars(select(Movie.movie_id).order_by(Movie.movie_id).limit(3)))
        for admin in [0,1,1]:
            name='backend_pytest_'+uuid.uuid4().hex
            u=User(username=name,email=name+'@example.com',is_active=1,is_superuser=admin);db.add(u);db.flush();ids.append(u.user_id)
    yield {'ids':ids,'tokens':[create_access_token({'sub':str(i)}) for i in ids],'movies':movies}
    with SessionLocal.begin() as db:
        db.execute(delete(Job).where(Job.owner_id.in_(ids)));db.execute(delete(Behavior).where(Behavior.user_id.in_(ids)));db.execute(delete(BehaviorVersion).where(BehaviorVersion.user_id.in_(ids)));db.execute(delete(User).where(User.user_id.in_(ids)))
