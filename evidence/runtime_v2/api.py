"""Owned conversations, bounded tool loop, provenance and atomic idempotent writes."""
import hashlib,json,re,threading,time,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from app.database import SessionLocal,Base,engine as db_engine
from app.models import User
from app.core.security import create_access_token,decode_access_token
from .evidence import negotiate,verify_results
from .models import Conversation,Turn,Preference,PreferenceAudit,Feedback,RequestRecord
from .parser import parse,compress,GENRES
from .engine import engine
from .provider import DeepSeekTrial,ProviderError,BudgetExceeded
from .reliability import RateLimited,ProviderUnavailable

router=APIRouter(prefix='/api/chat',tags=['conversation'])
security=HTTPBearer();locks=[threading.Lock() for _ in range(64)]
VERSION={'data':'rec-v1','model':'rec-v1','prompt':'movie-tools-v2','agent':'conversation-v2','content':'content-v1'}

def initialize():
    Base.metadata.create_all(bind=db_engine,tables=[Conversation.__table__,Turn.__table__,Preference.__table__,PreferenceAudit.__table__,Feedback.__table__,RequestRecord.__table__]);engine.load()

def owner(credentials:HTTPAuthorizationCredentials=Depends(security)):
    p=decode_access_token(credentials.credentials)
    if not p:raise HTTPException(401,'登录或访客凭证已失效')
    if p.get('kind')=='cineagent_guest':
        try:value=str(uuid.UUID(p['sub']))
        except Exception:raise HTTPException(401,'访客凭证无效')
        return 'guest:'+value,0
    try:uid=int(p['sub'])
    except Exception:raise HTTPException(401,'凭证无效')
    with SessionLocal() as db:
        u=db.get(User,uid)
        if not u or not u.is_active:raise HTTPException(401,'用户无效')
    return 'user:'+str(uid),uid

class ChatInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:uuid.UUID
    conversation_id:uuid.UUID|None=None
    message:str=Field(min_length=1,max_length=4000)
    mode:Literal['offline','deepseek']='offline'
    use_memory:bool=True
    compress_history:bool=True

class FeedbackInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:uuid.UUID
    conversation_id:uuid.UUID
    movie_id:int
    kind:Literal['seen','dislike']

@router.post('/guest')
def guest():
    return {'access_token':create_access_token({'sub':str(uuid.uuid4()),'kind':'cineagent_guest'},timedelta(days=7)),'expires_in_days':7}

@router.get('/status')
def status():
    p=Path('/run/cineagent-secrets/deepseek.json');ledger=Path('/trial-ledger/DEEPSEEK_TRIAL_LEDGER.json')
    attempts=[]
    try:attempts=json.loads(ledger.read_text())['attempts'] if ledger.exists() else []
    except Exception:pass
    pi=sum(a.get('accounted_input_tokens',0) for a in attempts);po=sum(a.get('accounted_output_tokens',0) for a in attempts)
    return {'versions':VERSION,'provider_configured':p.exists(),'requests_used':len(attempts),'request_limit':30,'conservative_cost_usd':round(pi*.3/1e6+po*1.2/1e6,7),'budget_usd':.10,'content_mode':'title_genre_text_only','ready':engine.ready}

def prefs(db,who):
    now=datetime.now(timezone.utc)
    return [p for p in db.scalars(select(Preference).where(Preference.owner==who,Preference.status=='active')).all() if p.expires_at is None or p.expires_at>now]

def serialized(p):
    return {'id':p.id,'key':p.key,'value':p.value,'scope':p.scope,'source_conversation':p.source_conversation,'source_turn':p.source_turn,'created_at':p.created_at.isoformat(),'expires_at':p.expires_at.isoformat() if p.expires_at else None}

@router.get('/preferences')
def list_prefs(identity=Depends(owner)):
    with SessionLocal() as db:return {'items':[serialized(p) for p in prefs(db,identity[0])]}

@router.delete('/preferences/{preference_id}')
def delete_pref(preference_id:uuid.UUID,identity=Depends(owner)):
    with SessionLocal.begin() as db:
        p=db.get(Preference,str(preference_id))
        if p is None or p.owner!=identity[0]:raise HTTPException(404,'偏好不存在')
        db.add(PreferenceAudit(id=str(uuid.uuid4()),owner=identity[0],preference_id=p.id,action='delete',request_id=str(uuid.uuid4())))
        db.delete(p)
    return {'deleted':True}

@router.post('/preferences/{preference_id}/revoke')
def revoke_pref(preference_id:uuid.UUID,identity=Depends(owner)):
    with SessionLocal.begin() as db:
        p=db.get(Preference,str(preference_id))
        if p is None or p.owner!=identity[0]:raise HTTPException(404,'偏好不存在')
        p.status='revoked';db.add(PreferenceAudit(id=str(uuid.uuid4()),owner=identity[0],preference_id=p.id,action='revoke',request_id=str(uuid.uuid4())))
    return {'revoked':True}

def validated_constraints(args,current):
    allowed={'include_genres','exclude_genres','max_runtime','min_runtime','exclude_ids','similar_to','exclude_director_of'}
    if not isinstance(args,dict) or set(args)-allowed:raise ValueError('invalid_tool_keys')
    updated=json.loads(json.dumps(current))
    for key in ['include_genres','exclude_genres']:
        if key in args:
            val=args[key]
            if not isinstance(val,list) or len(val)>18 or any(x not in set(GENRES.values()) for x in val):raise ValueError('invalid_genre')
            # Preserve deterministic explicit constraints if the model drops one.
            updated[key]=sorted(set(updated.get(key,[]))|set(val))
    for key in ['max_runtime','min_runtime']:
        if key in args and args[key] is not None:
            val=args[key]
            if type(val) is not int or not 1<=val<=600:raise ValueError('invalid_runtime')
            updated[key]=min(val,updated[key]) if key=='max_runtime' and key in updated else max(val,updated[key]) if key=='min_runtime' and key in updated else val
    if args.get('similar_to') is not None:
        if type(args['similar_to']) is not int or args['similar_to'] not in engine.movies:raise ValueError('unknown_seed')
        updated['similar_to']=args['similar_to']
    if args.get('exclude_director_of') is not None:
        val=args['exclude_director_of']
        if type(val) is not int or val not in engine.movies:raise ValueError('unknown_director_seed')
        if val!=current.get('exclude_director_of'):raise ValueError('unsupported_director_exclusion')
        updated['exclude_director_of']=val
    if 'exclude_ids' in args:
        if not isinstance(args['exclude_ids'],list) or len(args['exclude_ids'])>100 or any(type(i) is not int or i not in engine.movies for i in args['exclude_ids']):raise ValueError('invalid_exclusions')
        if set(args['exclude_ids'])-set(current.get('exclude_ids',[])):raise ValueError('unsupported_exclusions')
        updated['exclude_ids']=sorted(set(updated.get('exclude_ids',[]))|set(args['exclude_ids']))
    if set(updated.get('include_genres',[]))&set(updated.get('exclude_genres',[])):raise ValueError('conflicting_genres')
    if updated.get('min_runtime',0)>updated.get('max_runtime',100000):raise ValueError('conflicting_runtime')
    return updated

GENRE_SCHEMA={'type':'array','items':{'type':'string','enum':sorted(set(GENRES.values()))}}
TOOLS=[{'type':'function','function':{'name':'recommend_movies','description':'Recall, filter, score with local recommendation model and diversify real catalogue movies. Supply explicit constraints; unknown attributes require clarification.','parameters':{'type':'object','properties':{'include_genres':GENRE_SCHEMA,'exclude_genres':GENRE_SCHEMA,'max_runtime':{'type':'integer'},'min_runtime':{'type':'integer'},'similar_to':{'type':'integer'},'exclude_director_of':{'type':'integer'},'exclude_ids':{'type':'array','items':{'type':'integer'}}},'additionalProperties':False}}},
{'type':'function','function':{'name':'movie_details','description':'Inspect up to five known movie IDs.','parameters':{'type':'object','properties':{'movie_ids':{'type':'array','items':{'type':'integer'}}},'required':['movie_ids'],'additionalProperties':False}}},
{'type':'function','function':{'name':'finish','description':'Finish after recommend_movies has returned. The server renders the authoritative ranked results.','parameters':{'type':'object','properties':{},'additionalProperties':False}}}]

def run_tools(uid,state,query,preferences,mode,history,faults=()):
    trace=[];degradation=[];result=None;mode_used='offline_rules';current=state
    def recommend():return engine.recommend(uid,current,query,preferences,faults=faults)
    if mode=='deepseek':
        client=DeepSeekTrial('/run/cineagent-secrets/deepseek.json','/trial-ledger/DEEPSEEK_TRIAL_LEDGER.json')
        messages=[{'role':'system','content':'You are a movie tool agent. Call recommend_movies first or inspect movie_details if needed; call finish after receiving recommendations. At most 2 model turns and 6 tool calls. Never invent attributes or movie IDs. Preserve supplied hard constraints. Do not invent exclusions or relax runtime. Include exclude_director_of when supplied in state. Runtime is minutes. Unknown pace/emotion cannot be guaranteed. The server renders ranked items; do not produce recommendation prose. Context: '+json.dumps({'state':state,'preferences':preferences,'history':history},ensure_ascii=False)},{'role':'user','content':query}]
        used=0;previous=set()
        try:
            for step in range(2):
                def invoke():
                    if 'llm' in faults:raise ProviderUnavailable('injected_unavailable')
                    if 'rate_limit' in faults:raise RateLimited('injected_rate_limit')
                    try:return client.chat(messages,TOOLS,max_tokens=512,trial_authorized=True)
                    except ProviderError as exc:
                        if str(exc)=='http_429':raise RateLimited('http_429')
                        raise
                response,rid=engine.resilience.call('llm',invoke,timeout=10,attempts=2,trace=trace)
                message=response['choices'][0]['message'];calls=message.get('tool_calls') or []
                trace.append({'tool':'llm','provider_request_id':rid,'step':step+1,'tool_count':len(calls),'model':response.get('model')})
                if not calls:raise ValueError('missing_tool_call')
                messages.append({'role':'assistant','content':message.get('content'),'tool_calls':calls})
                finished=False
                for call in calls:
                    used+=1
                    if used>6:raise ValueError('tool_limit')
                    name=call['function']['name'];args=json.loads(call['function']['arguments']);signature=json.dumps([name,args],sort_keys=True)
                    if signature in previous:raise ValueError('duplicate_tool_call')
                    previous.add(signature)
                    if name=='recommend_movies':
                        current=validated_constraints(args,current);result=recommend();output={'items':result['items'][:6],'eligible_count':result['eligible_count'],'warnings':result['warnings']}
                    elif name=='movie_details':
                        ids=args.get('movie_ids')
                        if set(args)!={'movie_ids'} or not isinstance(ids,list) or len(ids)>5 or any(type(i) is not int or i not in engine.movies for i in ids):raise ValueError('invalid_details_ids')
                        output={'items':engine.details(ids)}
                    elif name=='finish' and result is not None and args=={}:finished=True;output={'finished':True}
                    else:raise ValueError('invalid_tool_order_or_name')
                    trace.append({'tool':name,'arguments':args,'step':step+1,'ok':True})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(output,ensure_ascii=False)})
                if finished:break
            if result is None:raise ValueError('no_recommendation_tool')
            mode_used='deepseek_tools'
        except Exception as exc:
            degradation.append('llm:'+type(exc).__name__+':offline_recommendation')
            # Preserve already validated constraints, execute the ordinary local engine.
            result=recommend()
    else:result=recommend()
    result['trace']=trace+result['trace'];result['degradation']=degradation+result['degradation'];return result,current,mode_used

@router.post('/message')
def message(body:ChatInput,identity=Depends(owner)):
    who,uid=identity;request_id=str(body.request_id);payload=body.model_dump(mode='json');digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();started=time.perf_counter()
    lock=locks[int(hashlib.sha256(who.encode()).hexdigest(),16)%len(locks)]
    with lock,SessionLocal.begin() as db:
        old=db.scalar(select(RequestRecord).where(RequestRecord.owner==who,RequestRecord.request_id==request_id))
        if old:
            if old.body_sha256!=digest:raise HTTPException(409,'请求 ID 已用于不同内容')
            return old.response
        if not body.message.strip():raise HTTPException(422,'消息不能为空')
        cid=str(body.conversation_id) if body.conversation_id else str(uuid.uuid4());conv=db.get(Conversation,cid)
        if body.conversation_id and (not conv or conv.owner!=who):raise HTTPException(404,'会话不存在')
        if conv is None:conv=Conversation(id=cid,owner=who,state={});db.add(conv)
        oldstate=conv.state or {};turnno=int(oldstate.get('turn_count',0))+1
        if turnno>100:raise HTTPException(422,'会话达到 100 轮，请新建会话')
        parsed=parse(body.message,oldstate,turnno);state=parsed['state'];state.pop('summary',None)
        session_exclusions=list(state.get('exclude_genres',[]))
        active=prefs(db,who) if body.use_memory else []
        feedback_ids=[r.movie_id for r in db.scalars(select(Feedback).where(Feedback.owner==who)).all()]
        state['exclude_ids']=sorted(set(state.get('exclude_ids',[]))|set(feedback_ids))
        memory=[{'key':p.key,'value':p.value,'source_turn':p.source_turn,'source_conversation':p.source_conversation} for p in active]
        for pref in active:
            if pref.key=='exclude_genres' and pref.value not in state.get('include_genres',[]):
                state.setdefault('exclude_genres',[])
                if pref.value not in state['exclude_genres']:state['exclude_genres'].append(pref.value)
        history_rows=db.scalars(select(Turn).where(Turn.conversation_id==cid,Turn.owner==who).order_by(Turn.number)).all()
        original=[{'turn':t.number,'text':t.text} for t in history_rows]
        history={'recent':original[-4:],'summary':compress(state,turnno-1)} if body.compress_history else {'original':original}
        if parsed['needs_clarification']:
            result={'items':[],'trace':[],'degradation':[],'warnings':[],'eligible_count':0,'needs_clarification':True};mode_used='clarification'
        else:result,state,mode_used=run_tools(uid,state,body.message,memory,body.mode,history)
        if parsed['needs_clarification']:parsed['memory_proposals']=[]
        evidence=verify_results(engine,uid,state,result['items'])
        failed_evidence={c['movie_id'] for c in evidence if not c['passed']}
        if failed_evidence:
            result['items']=[m for m in result['items'] if m['movie_id'] not in failed_evidence]
            result['warnings'].append('部分候选未通过库内属性复核，已移除。')
        suggestions=negotiate(engine,uid,state) if not result['items'] and not parsed['needs_clarification'] else []
        for proposal in parsed['memory_proposals']:
            # Only explicit long-term markers create memory. Correction revokes opposite facts.
            if re.search(r'纠正|改成|改为|其实',body.message):
                for p in active:
                    if p.value==proposal['value'] and p.key!=proposal['key']:p.status='revoked';db.add(PreferenceAudit(id=str(uuid.uuid4()),owner=who,preference_id=p.id,action='correct',request_id=request_id))
            if any(p.key==proposal['key'] and p.value==proposal['value'] for p in active):continue
            p=Preference(id=str(uuid.uuid4()),owner=who,key=proposal['key'],value=proposal['value'],source_conversation=cid,source_turn=turnno,scope='long_term');db.add(p)
        if parsed['feedback']:
            f=parsed['feedback'];result['trace'].append({'tool':'record_feedback','arguments':f,'idempotency_key':request_id});db.add(Feedback(id=str(uuid.uuid4()),owner=who,request_id=request_id,movie_id=f['movie_id'],kind=f['kind'],source_conversation=cid,source_turn=turnno))
        effective_constraints={k:v for k,v in state.items() if k not in ('sources','last_results','turn_count')}
        borrowed={p.value for p in active if p.key=='exclude_genres' and p.value not in session_exclusions}
        state['exclude_genres']=[g for g in state.get('exclude_genres',[]) if g not in borrowed]
        state['last_results']=[i['movie_id'] for i in result['items']];state['turn_count']=turnno;conv.state=state
        db.add(Turn(id=str(uuid.uuid4()),conversation_id=cid,owner=who,number=turnno,text=body.message))
        warnings=sorted(set(parsed['warnings']+result['warnings']))
        response={'request_id':request_id,'conversation_id':cid,'turn':turnno,'mode':mode_used,'items':result['items'],'constraints':effective_constraints,'warnings':warnings,'message':'已根据库内信息筛选并排序。' if result['items'] else '需要调整或澄清条件后再推荐。','trace':result['trace'],'degradation':result['degradation'],'eligible_count':result['eligible_count'],'evidence_checks':evidence,'relaxation_suggestions':suggestions,'versions':VERSION,'summary':compress(state,turnno),'history_characters':{'original':len(json.dumps(original,ensure_ascii=False)),'sent':len(json.dumps(history,ensure_ascii=False))},'memory_used':memory,'memory_proposals_saved':len(parsed['memory_proposals']),'elapsed_ms':round((time.perf_counter()-started)*1000,2)}
        db.add(RequestRecord(id=str(uuid.uuid4()),owner=who,request_id=request_id,body_sha256=digest,response=response));return response

@router.post('/feedback')
def feedback(body:FeedbackInput,identity=Depends(owner)):
    who=identity[0];cid=str(body.conversation_id);rid=str(body.request_id)
    with locks[int(hashlib.sha256(who.encode()).hexdigest(),16)%len(locks)],SessionLocal.begin() as db:
        conv=db.get(Conversation,cid)
        if not conv or conv.owner!=who:raise HTTPException(404,'会话不存在')
        if body.movie_id not in (conv.state or {}).get('last_results',[]):raise HTTPException(422,'只能反馈当前推荐中的电影')
        old=db.scalar(select(Feedback).where(Feedback.owner==who,Feedback.request_id==rid,Feedback.movie_id==body.movie_id,Feedback.kind==body.kind))
        if not old:db.add(Feedback(id=str(uuid.uuid4()),owner=who,request_id=rid,movie_id=body.movie_id,kind=body.kind,source_conversation=cid,source_turn=conv.state.get('turn_count')))
    return {'saved':True,'replayed':old is not None}

@router.delete('/conversations/{cid}')
def delete_conversation(cid:uuid.UUID,identity=Depends(owner)):
    with SessionLocal.begin() as db:
        conv=db.get(Conversation,str(cid))
        if not conv or conv.owner!=identity[0]:raise HTTPException(404,'会话不存在')
        db.query(Turn).filter(Turn.conversation_id==str(cid),Turn.owner==identity[0]).delete()
        db.query(RequestRecord).filter(RequestRecord.owner==identity[0],RequestRecord.response['conversation_id'].astext==str(cid)).delete(synchronize_session=False)
        db.delete(conv)
    return {'deleted':True}



