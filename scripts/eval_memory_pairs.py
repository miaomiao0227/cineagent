"""Predeclared memory-v1 extension: 30 paired sessions, no task cherry-picking."""
import json,uuid,math,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat'
def request(path,body=None,token=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h),timeout=30) as r:return json.load(r)
def send(token,text,**kw):return request('/message',{'request_id':str(uuid.uuid4()),'message':text,**kw},token)
exclusions=[('恐怖','Horror'),('喜剧','Comedy'),('动作','Action'),('爱情','Romance'),('剧情','Drama'),('科幻','Sci-Fi')];queries=['想看电影','想看惊悚电影','想看冒险电影','想看犯罪电影','想看动画电影']
tasks=[{'id':f'memory-{i}-{j}','remember':f'以后记住我不喜欢{cn}电影','exclude':en,'query':q,'source':'authored factorial 6 excluded genres x 5 fixed requests'} for i,(cn,en) in enumerate(exclusions) for j,q in enumerate(queries)]
# Freeze extension inputs before issuing its first request.
(root/'eval/memory_tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2),encoding='utf-8')
rows=[]
for task in tasks:
 row={'id':task['id'],'task':task,'error':None}
 try:
  tok=request('/guest',{})['access_token'];remember=send(tok,task['remember'])
  on=send(tok,task['query'],use_memory=True);off=send(tok,task['query'],use_memory=False)
  for label,response in [('on',on),('off',off)]:row[label]={'satisfied':bool(response['items']) and all(task['exclude'] not in m['genres'] for m in response['items']),'ids':[m['movie_id'] for m in response['items']],'response':response}
  row['changed']=row['on']['ids']!=row['off']['ids']
 except Exception as exc:row['error']=type(exc).__name__;row['on']={'satisfied':False};row['off']={'satisfied':False}
 rows.append(row)
def interval(k,n):
 z=1.95996398454;p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den;r=z*(p*(1-p)/n+z*z/(4*n*n))**.5/den;return [c-r,c+r]
summary={label:{'satisfied':sum(r[label]['satisfied'] for r in rows),'total':len(rows),'wilson95':interval(sum(r[label]['satisfied'] for r in rows),len(rows))} for label in ['on','off']}
report={'protocol':'memory-v1 extension frozen before this experiment','interpretation':'synthetic preference-constraint engineering check, not recommendation relevance or real-user utility; original Horror/Thriller pair in AGENT_HTTP_EVAL had identical IDs and remains reported','summary':summary,'changed_rankings':sum(r.get('changed',False) for r in rows),'failures':sum(r['error'] is not None for r in rows),'per_task':rows}
(root/'reports/MEMORY_PAIRED_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['summary','changed_rankings','failures']}))
