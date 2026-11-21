"""Owner/version-scoped result cache. PostgreSQL is authoritative."""
import hashlib,json,logging,time,uuid
from fastapi import HTTPException
import redis
from redis.retry import Retry
from redis.backoff import NoBackoff
from sqlalchemy import select
from app.config import settings
from .models import BehaviorVersion,Behavior
logger=logging.getLogger(__name__)
cache=redis.Redis.from_url(settings.redis_url,socket_connect_timeout=.15,socket_timeout=.15,retry=Retry(NoBackoff(),0))
MODEL_VERSION='rec-v1:conversation-v4:behavior-v2'
def current_preferences(db,uid):
    from app.models import User
    # Refresh ORM identity loaded by authentication before reading versioned inputs.
    user=db.scalar(select(User).where(User.user_id==uid).execution_options(populate_existing=True))
    return [{'key':'include_genres','value':g} for g in (user.preferred_genres or [])] if user else []

def recommendations(db,uid,limit=6,query='',cache_client=None):
    client=cache if cache_client is None else cache_client
    version=db.scalar(select(BehaviorVersion.version).where(BehaviorVersion.user_id==uid)) or 0
    payload=json.dumps([uid,version,MODEL_VERSION,limit,query],ensure_ascii=False,separators=(',',':'))
    key='ca:recommendations:v1:'+str(uid)+':'+hashlib.sha256(payload.encode()).hexdigest()
    try:
        raw=client.get(key)
        if raw:
            result=json.loads(raw)
            if result.get('behavior_version')!=version or not isinstance(result.get('items'),list):raise ValueError('invalid_cache')
            return {**result,'cache_status':'hit'}
    except (redis.RedisError,ValueError,TypeError):
        logger.warning('recommendation_cache_read_unavailable',extra={'user_id':uid})
    lock_key=key+':lock';lock_token=uuid.uuid4().hex;locked=False
    try:
        locked=bool(client.set(lock_key,lock_token,nx=True,ex=15))
        if not locked:
            deadline=time.monotonic()+.6
            while time.monotonic()<deadline:
                time.sleep(.03)
                raw=client.get(key)
                if raw:
                    value=json.loads(raw)
                    if value.get('behavior_version')==version and isinstance(value.get('items'),list):
                        return {**value,'cache_status':'coalesced'}
            raise HTTPException(503,'推荐正在生成，请稍后重试',headers={'Retry-After':'1'})
    except (redis.RedisError,ValueError,TypeError):
        logger.warning('recommendation_cache_lock_unavailable',extra={'user_id':uid})
    try:
        from app.cineagent.engine import engine
        # Online favorites/positive ratings are a bounded content seed, not training labels.
        seed=db.scalar(select(Behavior.movie_id).where(Behavior.user_id==uid,(Behavior.favorite.is_(True)) | (Behavior.rating>=8)).order_by(Behavior.updated_at.desc(),Behavior.movie_id.desc()).limit(1))
        state={'similar_to':seed} if seed is not None else {}
        preferences=current_preferences(db,uid)
        result=engine.recommend(uid,state,query,preferences=preferences,top_k=limit)
        result={**result,'behavior_version':version,'model_version':MODEL_VERSION}
        status='miss'
        if not result.get('degradation'):
            try:client.setex(key,120,json.dumps(result,ensure_ascii=False))
            except redis.RedisError:status='unavailable'
        return {**result,'cache_status':status}
    finally:
        if locked:
            try:
                client.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",1,lock_key,lock_token)
            except redis.RedisError:
                logger.warning('recommendation_cache_lock_release_failed')
