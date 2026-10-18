"""Same initial catalogue/profile/ranker: ordinary vs condition-driven, plus faults."""
import json,math,time,hashlib,concurrent.futures
from pathlib import Path
from app.cineagent.parser import parse,compress
from app.cineagent.engine import engine
from app.cineagent.api import run_tools
from app.cineagent.reliability import Resilience,RateLimited,CircuitOpen,ProviderUnavailable
engine.load();tasks=json.loads(Path('/trial-ledger/AGENT_TASKS_FROZEN.json').read_text(encoding='utf-8'))
rows=[]
for task in tasks['single']:
 if task['kind'] not in ['recommend','unsupported','memory']:continue
 parsed=parse(task['message']);row={'id':task['id'],'task':task,'outputs':{}}
 for method,state,query in [('ordinary',{},''),('condition_driven',parsed['state'],task['message'])]:
  try:
   result=engine.recommend(0,state,query);items=result['items'];ok=bool(items) and all(task['expected_genre'] in m['genres'] and (not task.get('exclude') or task['exclude'] not in m['genres']) and ('max_runtime' not in task or m['runtime_minutes'] is not None and m['runtime_minutes']<=task['max_runtime']) for m in items)
   row['outputs'][method]={'constraint_satisfied':ok,'ids':[m['movie_id'] for m in items],'eligible_count':result['eligible_count'],'degradation':result['degradation']}
  except Exception as exc:row['outputs'][method]={'constraint_satisfied':False,'error':type(exc).__name__}
 rows.append(row)
faults=[];state=parse('想看悬疑电影，不要恐怖片，两小时以内')['state']
for name,injected in [('normal',()),('itemcf_down',('itemcf',)),('text_down',('text',)),('cache_down',('cache',)),('ranking_down',('ranking',)),('llm_unavailable',('llm',)),('rate_limit',('rate_limit',))]:
 engine.resilience.reset();t=time.perf_counter()
 try:
  if name in ['llm_unavailable','rate_limit']:result,_,mode=run_tools(0,state,'想看悬疑电影，不要恐怖片，两小时以内',[],'deepseek',{},faults=injected)
  else:result=engine.recommend(0,state,'Mystery',faults=injected);mode='offline_rules'
  valid=bool(result['items']) and all('Mystery' in m['genres'] and 'Horror' not in m['genres'] and m['runtime_minutes'] is not None and m['runtime_minutes']<=120 for m in result['items'])
  faults.append({'case':name,'passed':valid,'mode':mode,'degradation':result['degradation'],'trace':result['trace'],'ms':round((time.perf_counter()-t)*1000,2)})
 except Exception as exc:faults.append({'case':name,'passed':False,'error':type(exc).__name__})
# Deterministic clock for breaker transitions and real bounded thread timeout.
clock=[0.];r=Resilience(clock=lambda:clock[0]);attempts=[0]
def fail():attempts[0]+=1;raise RateLimited('mock')
for _ in range(3):
 try:r.call('test',fail,attempts=2,sleep=lambda _:None)
 except RateLimited:pass
try:r.call('test',lambda:True);opened=False
except CircuitOpen:opened=True
clock[0]=6;recovered=r.call('test',lambda:True)
faults.append({'case':'breaker_and_recovery','passed':opened and recovered and attempts[0]==6,'attempts':attempts[0],'opened':opened,'recovered':recovered})
t=time.perf_counter()
try:r.call('slow',lambda:time.sleep(.12),timeout=.01,attempts=1);bounded=False
except TimeoutError:bounded=time.perf_counter()-t<.1
faults.append({'case':'bounded_timeout','passed':bounded,'elapsed_ms':round((time.perf_counter()-t)*1000,2)})
summary={method:{'passed':sum(row['outputs'][method]['constraint_satisfied'] for row in rows),'total':len(rows)} for method in ['ordinary','condition_driven']}
report={'protocol':'conversation-v1','initial_catalogue':len(engine.ids),'scope':'offline controlled comparison; same profile/ranker/top6; post-filter candidate changes are the intended intervention','summary':summary,'per_task':rows,'faults':faults,'real_llm_requests':0}
Path('/trial-ledger/AGENT_CONTROLLED_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'summary':summary,'fault_passed':sum(r['passed'] for r in faults),'fault_total':len(faults)}))
