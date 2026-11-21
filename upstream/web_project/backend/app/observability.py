import json,logging,re,time,uuid,threading,math
from collections import defaultdict,deque
from fastapi import Depends,APIRouter
from app.core.auth import get_current_admin_user
logger=logging.getLogger('cineagent.requests');lock=threading.Lock();metrics=defaultdict(lambda:{'count':0,'errors':0,'elapsed_ms':deque(maxlen=2000)})
def install(app):
    from starlette.exceptions import HTTPException
    from fastapi.responses import JSONResponse
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        rid=getattr(request.state,'request_id','')
        return JSONResponse(status_code=exc.status_code,content={'detail':exc.detail,'error':{'code':'http_'+str(exc.status_code),'request_id':rid}},headers=exc.headers)

    @app.middleware('http')
    async def request_trace(request,call_next):
        incoming=request.headers.get('X-Request-ID','')
        rid=incoming if re.fullmatch(r'[A-Za-z0-9_-]{1,64}',incoming) else str(uuid.uuid4())
        request.state.request_id=rid;started=time.perf_counter();status=500
        try:
            response=await call_next(request);status=response.status_code;response.headers['X-Request-ID']=rid;return response
        finally:
            elapsed=round((time.perf_counter()-started)*1000,2);route=getattr(request.scope.get('route'),'path','unmatched')
            # Route templates only: never tokens, body, query string or account details.
            logger.info(json.dumps({'request_id':rid,'route':route,'method':request.method,'status':status,'elapsed_ms':elapsed}))
            with lock:
                item=metrics[(request.method,route)];item['count']+=1;item['errors']+=int(status>=500);item['elapsed_ms'].append(elapsed)

router=APIRouter()
@router.get('/api/admin/metrics')
def snapshot(user=Depends(get_current_admin_user)):
    with lock:
        return {'scope':'current_process','routes':[{'method':key[0],'route':key[1],'count':v['count'],'server_errors':v['errors'],'recent_samples':len(v['elapsed_ms']),'p95_ms':sorted(v['elapsed_ms'])[max(0,math.ceil(.95*len(v['elapsed_ms']))-1)] if v['elapsed_ms'] else 0} for key,v in metrics.items()]}
