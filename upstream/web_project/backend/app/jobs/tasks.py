import uuid,logging
from datetime import datetime,timedelta,timezone
from celery import Celery
from sqlalchemy import select,update
from app.config import settings
from app.database import SessionLocal
from app.models import Movie
from .models import Job
logger=logging.getLogger(__name__)
celery_app=Celery('cineagent',broker=settings.redis_url.rsplit('/',1)[0]+'/'+str(settings.job_broker_db))
celery_app.conf.update(task_default_queue=settings.job_queue,task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,broker_connection_retry_on_startup=True,broker_connection_timeout=3,broker_transport_options={'visibility_timeout':30,'socket_connect_timeout':3,'socket_timeout':3},task_soft_time_limit=45,task_time_limit=55,task_ignore_result=True,accept_content=['json'],task_serializer='json')
def now():return datetime.now(timezone.utc)
def index_movies(movie_ids):
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk
    with SessionLocal() as db:
        rows=db.scalars(select(Movie).where(Movie.movie_id.in_(movie_ids))).all()
        if len(rows)!=len(movie_ids):raise ValueError('movie_deleted')
        docs=[{'_index':settings.movie_index_name,'_id':str(m.movie_id),'_source':{k:getattr(m,k) for k in ['movie_id','title','year','genres','description','imdb_id','avg_rating','imdb_rating','rating_count','imdb_votes','runtime_minutes','title_type']}} for m in rows]
    with Elasticsearch(settings.elasticsearch_url,request_timeout=5,max_retries=0) as client:
        succeeded,_=bulk(client,docs,refresh='wait_for',raise_on_error=True,max_retries=0)
    return {'indexed_count':succeeded,'index':settings.movie_index_name}
@celery_app.task(name='cineagent.refresh_index')
def refresh_index(job_id):
    token=str(uuid.uuid4())
    with SessionLocal.begin() as db:
        j=db.scalar(select(Job).where(Job.id==uuid.UUID(job_id)).with_for_update())
        if j is None or j.state in ('succeeded','failed'):return
        if j.state=='running' and j.lease_until and j.lease_until>now():return
        if j.state=='queued' and j.next_run>now():return
        if j.attempts>=3:j.state='failed';j.error_class='AttemptLimit';return
        j.state='running';j.attempts+=1;j.claim=token;j.lease_until=now()+timedelta(seconds=75);j.updated_at=now();ids=j.payload['movie_ids'];attempt=j.attempts
    try:result=index_movies(ids);error=None
    except Exception as exc:result=None;error=type(exc).__name__;logger.warning('index_job_failed',extra={'job_id':job_id,'attempt':attempt,'error_class':error})
    with SessionLocal.begin() as db:
        j=db.scalar(select(Job).where(Job.id==uuid.UUID(job_id)).with_for_update())
        if j is None or j.claim!=token:return
        j.lease_until=None;j.updated_at=now();j.result=result;j.error_class=error
        if error:j.state='failed' if attempt>=3 else 'queued';j.next_run=now()+timedelta(seconds=2**attempt)
        else:j.state='succeeded'
