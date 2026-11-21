"""Real Redis/DB concurrency test with mocked computation; no quality metric."""
import time,uuid,threading,json,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.database import SessionLocal
from app.behavior.recommendations import recommendations,cache,MODEL_VERSION
from app.behavior.models import BehaviorVersion
from app.cineagent.engine import engine
from fastapi import HTTPException
q='cache-check-'+uuid.uuid4().hex;uid=1;counter=[0];mutex=threading.Lock();original=engine.recommend

def fake(*args,**kwargs):
    with mutex:counter[0]+=1
    time.sleep(.15)
    return {'items':[],'degradation':[],'eligible_count':0}
def run():
    with SessionLocal() as db:return recommendations(db,uid,6,q)
try:
    engine.recommend=fake
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda _:run(),range(8)))
    assert counter[0]==1,counter
    assert all(x['cache_status'] in ('miss','hit','coalesced') for x in results)
    with SessionLocal() as db:
        row=db.get(BehaviorVersion,uid);version=row.version if row else 0
    key='ca:recommendations:v1:'+str(uid)+':'+hashlib.sha256(json.dumps([uid,version,MODEL_VERSION,6,q],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    cache.delete(key);cache.set(key+':lock','other-owner',ex=2)
    start=time.monotonic()
    try:run()
    except HTTPException as e:assert e.status_code==503
    else:raise AssertionError('missing bounded contention response')
    assert time.monotonic()-start<1.5
    assert cache.get(key+':lock')==b'other-owner','foreign lock removed'
    assert counter[0]==1
    time.sleep(2)
    run();assert counter[0]==2,'expired lock failed recovery'
    assert cache.get(key+':lock') is None
    result={'real_redis_concurrent_requests':8,'mock_compute_count':1,'bounded_wait':True,'foreign_lock_preserved':True,'expired_lock_recovery':True,'own_lock_released':True}
    print(json.dumps(result))
    Path('/trial-ledger/CACHE_COALESCING_V1.json').write_text(json.dumps(result,indent=2))
finally:
    engine.recommend=original
    if 'key' in locals():cache.delete(key,key+':lock')
