import uuid,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from conftest import http
from app.database import SessionLocal
from app.models import Rating

def test_behavior_concurrency_and_isolation(actors):
    token=actors['tokens'][0];movie=actors['movies'][0];path=f'/api/me/movies/{movie}/behavior'
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(Rating))
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda _:http(path,'PUT',{'favorite':True},token),range(16)))
    assert all(c==200 for c,d,h in results)
    assert {d['behavior_version'] for c,d,h in results}=={1}
    assert http('/api/me/behaviors',token=actors['tokens'][1])[1]['total']==0
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Rating))==before
@pytest.mark.parametrize('body',[{}, {'rating':11},{'rating':0},{'seen':None},{'favorite':None},{'owner_id':1},{'rating':'bad'}])
def test_behavior_invalid(actors,body):
    assert http(f"/api/me/movies/{actors['movies'][0]}/behavior",'PUT',body,actors['tokens'][0])[0]==422
@pytest.mark.parametrize('path',['/api/me/behaviors?page=0','/api/me/behaviors?page_size=101','/api/me/recommendations?limit=21','/api/me/recommendations?q='+'a'*201])
def test_bounds(actors,path):assert http(path,token=actors['tokens'][0])[0]==422
@pytest.mark.parametrize('path',['/api/me/behaviors','/api/admin/jobs','/api/admin/metrics'])
def test_requires_auth(path):assert http(path)[0] in (401,403)
def test_admin_permissions(actors):
    assert http('/api/admin/jobs',token=actors['tokens'][0])[0]==403
    assert http('/api/admin/metrics',token=actors['tokens'][0])[0]==403

def test_job_real_roundtrip_and_idempotency(actors):
    token=actors['tokens'][1];body={'request_id':str(uuid.uuid4()),'movie_ids':actors['movies'][:2]}
    c,a,h=http('/api/admin/jobs','POST',body,token);assert c==202
    c,b,h=http('/api/admin/jobs','POST',body,token);assert a['id']==b['id']
    assert http('/api/admin/jobs/'+a['id'],token=actors['tokens'][2])[0]==404
    assert http('/api/admin/jobs','POST',{**body,'movie_ids':actors['movies'][2:]},token)[0]==409
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        c,result,h=http('/api/admin/jobs/'+a['id'],token=token)
        if result['state'] in ('succeeded','failed'):break
        time.sleep(.5)
    assert result['state']=='succeeded',result
    assert result['result']['indexed_count']==2
    from elasticsearch import Elasticsearch
    from app.config import settings
    from app.models import Movie
    with Elasticsearch(settings.elasticsearch_url) as es,SessionLocal() as db:
        for mid in body['movie_ids']:
            doc=es.get(index=settings.movie_index_name,id=str(mid))['_source']
            assert doc['movie_id']==mid and doc['title']==db.get(Movie,mid).title

    from app.jobs.tasks import refresh_index
    refresh_index.run(a['id'])
    assert http('/api/admin/jobs/'+a['id'],token=token)[1]['attempts']==1
@pytest.mark.parametrize('ids',[[],[2147483647],list(range(1,102))])
def test_invalid_job(actors,ids):assert http('/api/admin/jobs','POST',{'request_id':str(uuid.uuid4()),'movie_ids':ids},actors['tokens'][1])[0]==422

def test_request_id(actors):
    c,d,h=http('/api/me/behaviors',token=actors['tokens'][0],headers={'X-Request-ID':'backend-test-123'})
    assert c==200 and h['x-request-id']=='backend-test-123'
    c,d,h=http('/api/admin/metrics',token=actors['tokens'][1]);assert c==200 and d['scope']=='current_process'

def test_catalogue_cache_and_rollback(actors):
    from app.behavior.catalogue import detail,change_description
    from app.behavior.recommendations import cache
    from app.behavior.models import MovieVersion
    from app.models import Movie
    movie=actors['movies'][0]
    with SessionLocal() as db:
        old=db.get(Movie,movie).description
        detail(db,movie)
        # Roll back an admin edit: both description and cache version must roll back.
        change_description(db,movie,'pytest rollback-only description');db.rollback()
    with SessionLocal() as db:assert detail(db,movie).description==old

def test_job_finite_retry_and_lease(actors,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.jobs.models import Job
    from app.jobs import tasks
    job_id=uuid.uuid4()
    with SessionLocal.begin() as db:db.add(Job(id=job_id,owner_id=actors['ids'][1],request_key=uuid.uuid4(),payload={'movie_ids':actors['movies'][:1]},state='dispatched',next_run=datetime.now(timezone.utc)+timedelta(days=1)))
    def unavailable(ids):raise ConnectionError('synthetic dependency outage')
    monkeypatch.setattr(tasks,'index_movies',unavailable)
    for n in range(3):
        tasks.refresh_index.run(str(job_id))
        with SessionLocal.begin() as db:
            j=db.get(Job,job_id);assert j.attempts==n+1
            assert j.state==('failed' if n==2 else 'queued')
            if n<2:j.state='dispatched';j.next_run=datetime.now(timezone.utc)+timedelta(days=1)
    tasks.refresh_index.run(str(job_id))
    with SessionLocal() as db:assert db.get(Job,job_id).attempts==3

def test_movie_update_invalidates_cache(actors):
    from app.models import Movie
    from app.behavior.models import MovieVersion
    from app.behavior.catalogue import detail
    from app.behavior.recommendations import cache
    from sqlalchemy import delete
    mid=1900000000+int(uuid.uuid4().hex[:6],16)
    try:
        with SessionLocal.begin() as db:db.add(Movie(movie_id=mid,title='Synthetic cache test movie',genres=[],description='before'))
        assert http('/api/movies/'+str(mid))[1]['description']=='before'
        c,d,h=http('/api/admin/jobs/movies/'+str(mid)+'/description','PATCH',{'description':'after'},actors['tokens'][1]);assert c==200
        assert http('/api/movies/'+str(mid))[1]['description']=='after'
        assert http('/api/admin/jobs/movies/'+str(mid)+'/description','PATCH',{'description':'forbidden'},actors['tokens'][0])[0]==403
    finally:
        with SessionLocal.begin() as db:db.execute(delete(MovieVersion).where(MovieVersion.movie_id==mid));db.execute(delete(Movie).where(Movie.movie_id==mid))
        keys=list(cache.scan_iter(match=f'ca:movie:v1:{mid}:*'))
        if keys:cache.delete(*keys)

def test_profile_online_ratings_and_preference_version(actors):
    token=actors['tokens'][0];movie=actors['movies'][0]
    c,r,h=http('/api/ratings','POST',{'movie_id':movie,'rating':8},token);assert c==201
    c,p,h=http('/api/users/me',token=token);assert c==200 and p['recent_ratings'][0]['movie_id']==movie and p['recent_ratings'][0]['rating']==8
    from app.behavior.models import BehaviorVersion
    with SessionLocal() as db:before=db.get(BehaviorVersion,actors['ids'][0]).version
    assert http('/api/users/me','PUT',{'preferred_genres':['Drama']},token)[0]==200
    with SessionLocal() as db:assert db.get(BehaviorVersion,actors['ids'][0]).version==before+1
    assert http('/api/users/me','PUT',{'is_superuser':1},token)[0]==422

def test_detail_cache_query_count(actors):
    from app.behavior.catalogue import detail
    from app.behavior.models import MovieVersion
    from app.behavior.recommendations import cache
    from app.database import engine
    from sqlalchemy import event
    mid=actors['movies'][1]
    with SessionLocal() as db:
        v=db.get(MovieVersion,mid);version=v.version if v else 0
    key=f'ca:movie:v1:{mid}:{version}';cache.delete(key);count=[0]
    def record(*args):count[0]+=1
    event.listen(engine,'before_cursor_execute',record)
    try:
        with SessionLocal() as db:detail(db,mid)
        cold=count[0];count[0]=0
        with SessionLocal() as db:detail(db,mid)
        warm=count[0]
    finally:event.remove(engine,'before_cursor_execute',record)
    assert cold==2 and warm==1,(cold,warm)

def test_behavior_rollback_atomicity(actors):
    from app.behavior.service import update
    from app.behavior.models import Behavior,BehaviorVersion
    uid=actors['ids'][0];mid=actors['movies'][0]
    with SessionLocal() as db:
        update(db,uid,mid,{'favorite':True});db.rollback()
    with SessionLocal() as db:
        assert db.get(Behavior,(uid,mid)) is None
        assert db.get(BehaviorVersion,uid) is None

def test_job_concurrent_idempotency(actors):
    token=actors['tokens'][1];body={'request_id':str(uuid.uuid4()),'movie_ids':actors['movies'][:1]}
    with ThreadPoolExecutor(6) as pool:results=list(pool.map(lambda _:http('/api/admin/jobs','POST',body,token),range(12)))
    assert all(c==202 for c,d,h in results)
    assert len({d['id'] for c,d,h in results})==1
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        d=http('/api/admin/jobs/'+results[0][1]['id'],token=token)[1]
        if d['state'] in ('succeeded','failed'):break
        time.sleep(.3)
    assert d['state']=='succeeded' and d['attempts']==1

def test_preference_refresh_after_concurrent_commit(actors):
    from app.models import User
    from app.behavior.recommendations import current_preferences
    uid=actors['ids'][0]
    with SessionLocal() as first:
        cached_user=first.get(User,uid)
        with SessionLocal.begin() as other:other.get(User,uid).preferred_genres=['Mystery']
        assert current_preferences(first,uid)==[{'key':'include_genres','value':'Mystery'}]

@pytest.mark.parametrize('expired',[False,True])
def test_invalid_or_expired_token(actors,expired):
    from app.core.security import create_access_token
    from datetime import timedelta
    token=create_access_token({'sub':str(actors['ids'][0])},timedelta(seconds=-1)) if expired else 'invalid.jwt.value'
    assert http('/api/me/behaviors',token=token)[0]==401

def test_inactive_account(actors):
    from app.models import User
    with SessionLocal.begin() as db:db.get(User,actors['ids'][0]).is_active=0
    assert http('/api/me/behaviors',token=actors['tokens'][0])[0]==403
