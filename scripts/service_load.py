import concurrent.futures,json,time,uuid,urllib.request,threading,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat'
def req(path,body,token=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=h),timeout=15) as response:return json.load(response)
tokens=[req('/guest',{})['access_token'] for _ in range(5)];queries=['想看悬疑电影，不要恐怖片，两小时以内','想看喜剧电影','想看科幻电影，不要恐怖片']
records=[];guard=threading.Lock()
def worker(client,clients,phase,duration):
 token=tokens[client]
 start=time.monotonic();n=0;period=clients/5
 while time.monotonic()-start<duration:
  target=start+n*period+client*.02
  delay=target-time.monotonic()
  if delay>0:time.sleep(delay)
  if time.monotonic()-start>=duration:break
  t=time.perf_counter();row={'clients':clients,'client':client,'phase':phase,'query_index':n%3,'ok':False}
  try:
   out=req('/message',{'request_id':str(uuid.uuid4()),'message':queries[n%3],'mode':'offline'},token)
   row.update(ok=bool(out['items']),degraded=bool(out['degradation']),mode=out['mode'])
  except Exception as exc:row['error_type']=type(exc).__name__
  row['ms']=round((time.perf_counter()-t)*1000,3)
  with guard:records.append(row)
  n+=1
for clients in [1,5]:
 for phase,duration in [('warmup',30),('measurement',120)]:
  with concurrent.futures.ThreadPoolExecutor(max_workers=clients) as pool:list(pool.map(lambda i:worker(i,clients,phase,duration),range(clients)))
  (root/'reports/SERVICE_LOAD_PARTIAL.json').write_text(json.dumps({'records':records},indent=2))
def percentile(values,q):
 a=sorted(values);x=(len(a)-1)*q;l=int(x);return a[l]+(a[min(l+1,len(a)-1)]-a[l])*(x-l) if a else None
summary=[]
for clients in [1,5]:
 rows=[r for r in records if r['clients']==clients and r['phase']=='measurement'];lat=[r['ms'] for r in rows]
 summary.append({'clients':clients,'attempts':len(rows),'successes':sum(r['ok'] for r in rows),'failures':sum(not r['ok'] for r in rows),'p50_ms':percentile(lat,.5),'p95_ms':percentile(lat,.95),'realized_rps':len(rows)/120})
report={'protocol':'conversation-v2-independent-owners','scope':'offline bounded-rate local HTTP chat path, fresh sessions, distinct guest owner per client; one process/model ranking lock remains; no external LLM','source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'upstream/web_project/backend/app/cineagent').glob('*.py')},'target_total_rps':5,'warmup_seconds_per_setting':30,'measurement_seconds_per_setting':120,'summary':summary,'records':records}
(root/'reports/SERVICE_LOAD.json').write_text(json.dumps(report,indent=2));print(json.dumps(summary))

