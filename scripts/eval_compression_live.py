"""One predeclared synthetic paired compression smoke, two identical histories."""
import json,uuid,urllib.request,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000/api/chat'
fixture={'version':'compression-live-v1','source':'authored synthetic, not user behavior','first':'想看悬疑电影，不要恐怖片，两小时以内。','filler':'继续保持当前条件。以下只是无新增偏好含义的背景文字：'+'这是用于检验历史长度的中性背景叙述。'*30,'offline_history_turns':12,'query':'继续按当前条件推荐','max_provider_requests_expected':4,'oracle':{'include_genres':['Mystery'],'exclude_genres':['Horror'],'max_runtime':120}}
path=root/'eval/compression_live_task.json'
if path.exists():assert json.loads(path.read_text(encoding='utf-8'))==fixture
else:path.write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
def request(path,body=None,token=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h),timeout=50) as r:return json.load(r)
def send(tok,text,cid=None,mode='offline',compress=True):return request('/message',{'request_id':str(uuid.uuid4()),'conversation_id':cid,'message':text,'mode':mode,'compress_history':compress},tok)
before=request('/status');rows=[]
for compressed in [True,False]:
 tok=request('/guest',{})['access_token'];cid=None
 for n in range(fixture['offline_history_turns']):
  r=send(tok,fixture['first'] if n==0 else fixture['filler'],cid);cid=r['conversation_id']
 response=send(tok,fixture['query'],cid,'deepseek',compressed)
 expected=fixture['oracle'];facts=[response['summary']['constraints'].get(k)==v for k,v in expected.items()]
 source_checks=[]
 for key,term in [('include_genres:Mystery','悬疑'),('exclude_genres:Horror','恐怖'),('max_runtime','两小时')]:
  source=response['summary']['sources'].get(key,{})
  source_checks.append(source.get('turn')==1 and term in fixture['first'][source.get('start',0):source.get('end',0)])
 rows.append({'compressed':compressed,'response':response,'key_facts_retained':sum(facts),'key_facts_denominator':len(facts),'source_locations_correct':sum(source_checks),'source_locations_denominator':len(source_checks),'passed':all(facts+source_checks) and response['mode']=='deepseek_tools' and bool(response['items'])})
same_ids=[m['movie_id'] for m in rows[0]['response']['items']]==[m['movie_id'] for m in rows[1]['response']['items']]
report={'protocol':'compression-live-v1','task_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':'one authored paired task; not statistical evidence of compression quality or token savings','rows':rows,'same_recommendation_ids':same_ids,'passed':all(r['passed'] for r in rows) and same_ids,'before':before,'after':request('/status')}
(root/'reports/COMPRESSION_LIVE_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'same_ids':same_ids,'facts':[[r['key_facts_retained'],r['key_facts_denominator']] for r in rows],'sources':[[r['source_locations_correct'],r['source_locations_denominator']] for r in rows],'history_characters':[r['response']['history_characters'] for r in rows],'after':report['after']}))
