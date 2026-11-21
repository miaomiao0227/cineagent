"""Bounded dependency health checks without connection details in responses."""
from fastapi import APIRouter,Depends
from sqlalchemy import text
from app.api.deps import get_db
from app.schemas import HealthCheck
from app.config import settings
router=APIRouter()
@router.get('/health',response_model=HealthCheck,tags=['health'])
def health_check(db=Depends(get_db)):
    status={}
    try:db.execute(text('SELECT 1'));status['database']='healthy'
    except Exception:status['database']='unhealthy'
    from redis import Redis
    from redis.retry import Retry
    from redis.backoff import NoBackoff
    try:
        with Redis.from_url(settings.redis_url,socket_connect_timeout=.3,socket_timeout=.3,retry=Retry(NoBackoff(),0)) as r:r.ping()
        status['redis']='healthy'
    except Exception:status['redis']='unhealthy'
    from elasticsearch import Elasticsearch
    try:
        with Elasticsearch(settings.elasticsearch_url,request_timeout=.5,max_retries=0) as es:status['elasticsearch']='healthy' if es.ping() else 'unhealthy'
    except Exception:status['elasticsearch']='unhealthy'
    return HealthCheck(status='healthy' if all(x=='healthy' for x in status.values()) else 'degraded',version=settings.app_version,**status)
