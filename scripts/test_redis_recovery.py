import json,subprocess,os,time,uuid,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];docker=str(Path(os.environ['LOCALAPPDATA'])/'Programs/DockerDesktop/resources/bin/docker.exe');base='http://127.0.0.1:13000';token=''
def request(path,body=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h),timeout=20) as r:return json.load(r)
token=request('/api/chat/guest',{})['access_token'];rows=[]
def check(phase):
 row={'phase':phase,'passed':False};t=time.perf_counter()
 try:
  response=request('/api/chat/message',{'request_id':str(uuid.uuid4()),'message':'想看悬疑电影，不要恐怖片，两小时以内'})
  row.update(passed=bool(response['items']) and all('Mystery' in m['genres'] and 'Horror' not in m['genres'] and m['runtime_minutes'] is not None and m['runtime_minutes']<=120 for m in response['items']),degradation=response['degradation'],request_id=response['request_id'])
 except Exception as exc:row['error_type']=type(exc).__name__
 row['elapsed_ms']=round((time.perf_counter()-t)*1000,2);rows.append(row)
check('normal_before');stopped=False;restore=None
try:
 subprocess.run([docker,'stop','--time','3','cineagent-redis-1'],check=True,capture_output=True,timeout=20);stopped=True
 for _ in range(3):check('redis_stopped')
finally:
 try:subprocess.run([docker,'start','cineagent-redis-1'],check=True,capture_output=True,timeout=20);restore=True
 except Exception as exc:restore=False;rows.append({'phase':'restore_container','passed':False,'error_type':type(exc).__name__})
if restore:
 time.sleep(5.2)
 check('after_cooldown_recovery')
 health=request('/health')
else:health=None
report={'scope':'actual cineagent Redis container stop/start only; no unrelated database/container touched','stopped':stopped,'restored':restore,'rows':rows,'health_after':health,'passed':stopped and restore and all(r['passed'] for r in rows) and any(any('cache:' in d for d in r.get('degradation',[])) for r in rows if r['phase']=='redis_stopped') and not rows[-1].get('degradation')}
(root/'reports/REDIS_RECOVERY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
