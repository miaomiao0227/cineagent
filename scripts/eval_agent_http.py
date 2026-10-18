"""HTTP regression suite; all authored tasks retained, no external calls by default."""
import json,uuid,time,math,hashlib,urllib.request,urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat'
raw=(root/'eval/agent_tasks.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==(root/'eval/agent_tasks.sha256').read_text().strip();tasks=json.loads(raw)

def request(path,body=None,token=None,method=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 req=urllib.request.Request(base+path,data=json.dumps(body).encode('utf-8') if body is not None else None,headers=headers,method=method)
 with urllib.request.urlopen(req,timeout=75) as r:return json.load(r)
def guest():return request('/guest',{})['access_token']
def send(token,text,cid=None,**kw):return request('/message',{'request_id':str(uuid.uuid4()),'conversation_id':cid,'message':text,**kw},token)
def satisfies(items,t):
 return all(t['expected_genre'] in m['genres'] and (not t.get('exclude') or t['exclude'] not in m['genres']) and ('max_runtime' not in t or m['runtime_minutes'] is not None and m['runtime_minutes']<=t['max_runtime']) for m in items)
def wilson(k,n):
 if not n:return None
 z=1.95996398454;p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den;r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return [c-r,c+r]
rows=[];token=guest()
for task in tasks['single']:
 row={'id':task['id'],'family':task['family'],'passed':False}
 try:
  response=send(token,task['message'],use_memory=False)
  kind=task['kind'];items=response['items'];ok=satisfies(items,task)
  if kind=='clarify':passed=response['mode']=='clarification' and not items
  elif kind=='unsupported':passed=bool(items) and ok and any('没有经过验证' in w for w in response['warnings'])
  elif kind=='memory':passed=bool(items) and ok and response['memory_proposals_saved']==1
  else:passed=bool(items) and ok
  row.update(passed=passed,response=response,constraint_satisfied=ok)
 except Exception as exc:row['error_type']=type(exc).__name__
 rows.append(row)
multi=[]
for task in tasks['multi']:
 row={'id':task['id'],'family':task['family'],'passed':False}
 try:
  tok=guest();a=send(tok,task['messages'][0],use_memory=False);b=send(tok,task['messages'][1],a['conversation_id'],use_memory=False)
  family=task['family'];first=a['items'][0] if a['items'] else None
  if family==0:passed=bool(first and b['items']) and first['movie_id'] not in [m['movie_id'] for m in b['items']] and b['constraints'].get('similar_to')==first['movie_id']
  elif family==1:
   passed=bool(first) and ((not first['directors'] and not b['items'] and any('导演' in w for w in b['warnings'])) or bool(b['items']) and all(m['directors'] and not set(m['directors'])&set(first['directors']) for m in b['items']))
  elif family==2:passed=b['mode']=='clarification' and b['memory_proposals_saved']==1
  elif family==3:passed=bool(b['items']) and all('Horror' in m['genres'] for m in b['items']) and 'Horror' not in b['constraints']['exclude_genres']
  elif family==4:passed=bool(b['items']) and b['constraints']['include_genres']==[task['genre']] and 'max_runtime' not in b['constraints']
  else:passed=b['mode']=='clarification' and not b['items']
  row.update(passed=passed,responses=[a,b])
 except Exception as exc:row['error_type']=type(exc).__name__
 multi.append(row)
checks=[]
def check(name,condition,**details):checks.append({'case':name,'passed':bool(condition),**details})
tok=guest();remember=send(tok,'以后记住我不喜欢恐怖片');prefs=request('/preferences',token=tok)['items'];check('explicit_memory_provenance',len(prefs)==1 and prefs[0]['scope']=='long_term' and prefs[0]['source_conversation']==remember['conversation_id'] and prefs[0]['source_turn']==1)
on=send(tok,'想看惊悚电影',use_memory=True);off=send(tok,'想看惊悚电影',use_memory=False)
check('memory_on_excludes_horror',bool(on['items']) and all('Horror' not in m['genres'] for m in on['items']),on_ids=[m['movie_id'] for m in on['items']],off_ids=[m['movie_id'] for m in off['items']],off_horror_count=sum('Horror' in m['genres'] for m in off['items']))
check('memory_off_does_not_load_preferences',not off['memory_used'])
other=guest()
try:request('/preferences/'+prefs[0]['id'],token=other,method='DELETE');blocked=False
except urllib.error.HTTPError as exc:blocked=exc.code==404
check('cross_owner_memory_delete_blocked',blocked)
request('/preferences/'+prefs[0]['id']+'/revoke',{},tok);revoked=send(tok,'想看惊悚电影');check('revoked_not_used',not revoked['memory_used'])
request('/preferences/'+prefs[0]['id'],token=tok,method='DELETE');check('deleted_not_listed',not request('/preferences',token=tok)['items'])
short=send(tok,'想看喜剧电影');check('session_not_permanent',not request('/preferences',token=tok)['items'])
try:send(other,'继续推荐',short['conversation_id']);blocked=False
except urllib.error.HTTPError as exc:blocked=exc.code==404
check('cross_owner_conversation_blocked',blocked)
body={'request_id':str(uuid.uuid4()),'conversation_id':short['conversation_id'],'message':'第一部看过了，换类似的'}
a=request('/message',body,tok);b=request('/message',body,tok);check('message_idempotency',a==b)
try:request('/message',dict(body,message='不同的请求'),tok);blocked=False
except urllib.error.HTTPError as exc:blocked=exc.code==409
check('idempotency_body_mismatch',blocked)
fbody={'request_id':str(uuid.uuid4()),'conversation_id':a['conversation_id'],'movie_id':a['items'][0]['movie_id'],'kind':'seen'}
f1=request('/feedback',fbody,tok);f2=request('/feedback',fbody,tok);check('feedback_idempotency',not f1['replayed'] and f2['replayed'])
# Long history uses an explicit filler paragraph; no external LLM sees it.
longtok=guest();cid=None;longresponse=None
for n in range(12):
 msg=('想看悬疑电影，不要恐怖片，两小时以内。' if n==0 else '请继续保持当前筛选条件。')+'以下是无偏好含义的背景说明：'+'用于验证长历史摘要的占位叙述。'*32
 longresponse=send(longtok,msg,cid);cid=longresponse['conversation_id']
compressed=send(longtok,'继续推荐',cid,compress_history=True);full=send(longtok,'继续推荐',cid,compress_history=False)
check('compression_preserves_constraints',compressed['constraints']==full['constraints'] and [m['movie_id'] for m in compressed['items']]==[m['movie_id'] for m in full['items']],compressed_characters=compressed['history_characters'],full_characters=full['history_characters'])
check('compression_keeps_source_offsets',bool(compressed['summary']['sources']) and compressed['summary']['constraints']['exclude_genres']==['Horror'])
check('long_history_characters_reduced',compressed['history_characters']['sent']<compressed['history_characters']['original'])
report={'protocol':'conversation-v1','task_sha256':hashlib.sha256(raw).hexdigest(),'source':'authored template-generated, not real users','llm_calls':0,'single':rows,'multi':multi,'memory_and_service_checks':checks,'summary':{}}
for name,data in [('single',rows),('multi',multi),('checks',checks)]:
 k=sum(r['passed'] for r in data);report['summary'][name]={'passed':k,'total':len(data),'wilson_95':wilson(k,len(data))}
(root/'reports/AGENT_HTTP_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['summary']))
