"""Additional lifecycle checks using synthetic guest identities, no paid API."""
import json,uuid,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat'
def req(path,body=None,token=None,method=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h,method=method),timeout=20) as r:return json.load(r)
def send(tok,text,cid=None):return req('/message',{'request_id':str(uuid.uuid4()),'conversation_id':cid,'message':text,'mode':'offline'},tok)
checks=[]
def check(name,ok,**detail):checks.append({'case':name,'passed':bool(ok),**detail})
tok=req('/guest',{})['access_token'];send(tok,'以后记住我喜欢喜剧电影');corrected=send(tok,'纠正，以后记住我不喜欢喜剧电影');p=req('/preferences',token=tok)['items'];check('explicit_correction_revokes_opposite',len(p)==1 and p[0]['key']=='exclude_genres' and p[0]['value']=='Comedy')
tok2=req('/guest',{})['access_token'];remember=send(tok2,'以后记住我不喜欢恐怖片');a=send(tok2,'想看惊悚电影');pref=req('/preferences',token=tok2)['items'][0];req('/preferences/'+pref['id'],token=tok2,method='DELETE');b=send(tok2,'继续推荐',a['conversation_id']);check('deleted_borrowed_memory_not_stuck_in_session',not b['memory_used'] and 'Horror' not in b['constraints']['exclude_genres'],before=a['constraints'],after=b['constraints'])
# Explicit same-session constraint remains until corrected/reset, independently of memory deletion.
c=send(tok2,'想看喜剧电影，不要恐怖片');d=send(tok2,'继续推荐',c['conversation_id']);check('explicit_session_constraint_retained','Horror' in d['constraints']['exclude_genres'])
report={'scope':'synthetic offline lifecycle extension; zero LLM calls','checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks)}
(root/'reports/MEMORY_LIFECYCLE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));assert all(c['passed'] for c in checks)
