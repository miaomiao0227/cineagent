import json,uuid,urllib.request,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat';token=''
def request(path,body=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h),timeout=60) as r:return json.load(r)
token=request('/guest',{})['access_token'];start=request('/status');rows=[];cid=None
for i,text in enumerate(['想看悬疑电影，不要恐怖片，两小时以内。','第一部看过了，换类似的，但不要同一个导演。','以后记住我不喜欢恐怖片。']):
 body={'request_id':str(uuid.uuid4()),'conversation_id':cid,'message':text,'mode':'deepseek'}
 try:
  out=request('/message',body);cid=out['conversation_id'];valid=bool(out['items']) and all('Horror' not in m['genres'] and m['runtime_minutes'] is not None and m['runtime_minutes']<=120 for m in out['items'])
  if i==1 and rows[0].get('response',{}).get('items'):
   old=rows[0]['response']['items'][0];valid=valid and all(m['movie_id']!=old['movie_id'] and m['directors'] and not set(m['directors'])&set(old['directors']) for m in out['items'])
  rows.append({'case':i+1,'source':'authored synthetic live smoke','message':text,'passed':valid and out['mode']=='deepseek_tools','response':out})
 except Exception as exc:rows.append({'case':i+1,'passed':False,'error_type':type(exc).__name__})
report={'scope':'three conversational HTTP requests, not statistical LLM capability evaluation','rows':rows,'passed':sum(x['passed'] for x in rows),'total':len(rows),'before':start,'after':request('/status')}
(root/'reports/DEEPSEEK_HTTP_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['passed','total','before','after']}))
