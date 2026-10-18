"""Bounded dependency calls with finite retries and a single half-open probe."""
import time,threading,concurrent.futures,random
from collections import Counter
class RateLimited(Exception):pass
class ProviderUnavailable(Exception):pass
class CircuitOpen(Exception):pass
class DependencyBusy(Exception):pass
class Resilience:
    def __init__(self,clock=time.monotonic,workers=4):
        self.clock=clock;self.lock=threading.Lock();self.states={};self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=workers,thread_name_prefix='cine-dep');self.slots=threading.BoundedSemaphore(workers*2)
    def state(self,name):
        with self.lock:return dict(self.states.get(name,{'failures':0,'opened':None,'probe':False}))
    def call(self,name,fn,timeout=.5,attempts=2,threshold=3,cooldown=5,trace=None,sleep=time.sleep):
        trace=trace if trace is not None else []
        with self.lock:
            s=self.states.setdefault(name,{'failures':0,'opened':None,'probe':False})
            if s['opened'] is not None:
                if self.clock()-s['opened']<cooldown or s['probe']:raise CircuitOpen(name)
                s['probe']=True
        last=None
        for i in range(attempts):
            started=self.clock();future=None
            try:
                if not self.slots.acquire(blocking=False):raise DependencyBusy(name)
                def job():
                    try:return fn()
                    finally:self.slots.release()
                try:future=self.pool.submit(job)
                except Exception:self.slots.release();raise
                result=future.result(timeout=timeout)
                with self.lock:self.states[name]={'failures':0,'opened':None,'probe':False}
                trace.append({'dependency':name,'attempt':i+1,'ok':True,'ms':round((self.clock()-started)*1000,2)})
                return result
            except Exception as e:
                last=e
                if future is not None and future.cancel():self.slots.release()
                trace.append({'dependency':name,'attempt':i+1,'ok':False,'error_type':type(e).__name__,'ms':round((self.clock()-started)*1000,2)})
                retry=isinstance(e,(TimeoutError,RateLimited,ConnectionError,OSError)) and not isinstance(e,ProviderUnavailable)
                if i+1>=attempts or not retry:break
                sleep(.04*(2**i))
        with self.lock:
            s=self.states[name];s['failures']+=1;s['probe']=False
            if s['failures']>=threshold:s['opened']=self.clock()
        raise last
    def reset(self):
        with self.lock:self.states.clear()
