"""Real official-model evaluation of frozen natural-language tasks.
Invokes the actual service function with isolated synthetic guest owners; HTTP/auth
were separately tested. Wraps only this subprocess's provider to retain tool args.
"""
import hashlib,json,time,uuid,math
from pathlib import Path
from app.cineagent import api
from app.cineagent.parser import parse
from app.cineagent.provider import DeepSeekTrial
from app.database import SessionLocal
from app.cineagent.models import Conversation
specpath=Path('/trial-ledger/AGENT_NATURAL_TASKS.json');fixture=json.loads(specpath.read_text());api.engine.load();source_dir=Path('/app/app/cineagent');source_hash={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.glob('*.py')}
observed={'calls':[]};original=DeepSeekTrial.chat

def traced(self,*args,**kwargs):
 result,rid=original(self,*args,**kwargs);message=result['choices'][0]['message'];tools=[]
 for call in message.get('tool_calls') or []:
  fn=call['function'];entry={'name':fn['name'],'arguments_raw':fn['arguments']}
  try:entry['arguments']=json.loads(fn['arguments'])
  except Exception:entry['arguments_parse_error']=True
  tools.append(entry)
 observed['calls'].append({'budget_request_id':rid,'model':result.get('model'),'usage':result.get('usage'),'tools':tools})
 return result,rid
def forbidden(*args,**kwargs):raise AssertionError('external API forbidden in offline regression')
DeepSeekTrial.chat=forbidden
before=api.status()
if False:raise RuntimeError('Insufficient remaining approved attempts for full batch; preserve existing ledger and request a new authorized evaluation budget.')
rows=[];contexts={};selected=set(fixture['predeclared_execution_ids'])
for task in fixture['tasks']:
 if task['id'] not in selected:continue
 context=contexts.setdefault(task['group'],{'who':'guest:'+str(uuid.uuid4()),'cid':None,'anchor':None,'previous_failed':False}) if task['group']!='single' else {'who':'guest:'+str(uuid.uuid4()),'cid':None,'anchor':None,'previous_failed':False}
 observed['calls']=[];start=time.perf_counter();row={'id':task['id'],'message':task['message'],'source':'authored natural-language task','task_success':False,'live_tool_loop_success':False,'prior_turn_failed':context['previous_failed']}
 if False:
  row.update(status='not_run_budget_exhausted',exclusion_reason='approved request cap');rows.append(row);continue
 try:
  old={}
  if context['cid']:
   with SessionLocal() as db:old=db.get(Conversation,context['cid']).state or {}
  preparsed=parse(task['message'],old,int(old.get('turn_count',0))+1)
  row['preparsed_state']=preparsed['state'];row['preparsed_memory']=preparsed['memory_proposals'];expected=dict(task.get('expected',{}));anchor=context['anchor']
  if task.get('reference_first_turn') and anchor:
   expected.update(similar_to=anchor['movie_id'],exclude_director_of=anchor['movie_id']);expected['exclude_ids']=[anchor['movie_id']]
  body=api.ChatInput(request_id=uuid.uuid4(),conversation_id=context['cid'],message=task['message'],mode='offline')
  response=api.message(body,identity=(context['who'],0));context['cid']=response['conversation_id']
  if context['anchor'] is None and response['items']:context['anchor']=response['items'][0]
  state=response['constraints'];checks=[]
  for key,value in expected.items():
   actual=state.get(key)
   ok=set(value)<=set(actual or []) if isinstance(value,list) else actual==value
   checks.append({'fact':key,'expected':value,'actual':actual,'passed':ok})
  for movie in response['items']:
   valid=set(expected.get('include_genres',[]))<=set(movie['genres']) and not set(expected.get('exclude_genres',[]))&set(movie['genres']) and movie['movie_id'] not in expected.get('exclude_ids',[])
   if 'max_runtime' in expected:valid=valid and movie['runtime_minutes'] is not None and movie['runtime_minutes']<=expected['max_runtime']
   if task.get('different_director') and anchor:valid=valid and bool(movie['directors']) and not set(movie['directors'])&set(anchor['directors'])
   checks.append({'fact':'returned_movie_constraints','movie_id':movie['movie_id'],'passed':bool(valid)})
  checks.append({'fact':'nonempty_for_these_catalogue_supported_tasks','passed':bool(response['items'])})
  memories=api.list_prefs(identity=(context['who'],0))['items']
  if task.get('memory_expected'):
   desired=task['memory_expected'];checks.append({'fact':'long_term_memory_direction_and_source','passed':any(p['key']==desired['key'] and p['value']==desired['value'] and p['source_conversation']==response['conversation_id'] and p['source_turn']==response['turn'] for p in memories) and not any(p['value']==desired['value'] and p['key']!=desired['key'] for p in memories)})
  passed=all(c['passed'] for c in checks);row.update(status='executed',expected=expected,checks=checks,response=response,active_memories=memories,task_success=passed,live_tool_loop_success=passed and response['mode']=='deepseek_tools' and bool(observed['calls']))
  row['failure_facts']=[c['fact'] for c in checks if not c['passed']]
  # Attribute guard/parse conflicts using raw model arguments, not the final fallback list.
  comparisons=[]
  for call in observed['calls']:
   for tool in call['tools']:
    args=tool.get('arguments',{})
    if tool['name']=='recommend_movies':
     for key,value in expected.items():
      if key not in args:continue
      actual=args[key];ok=set(value)<=set(actual or []) if isinstance(value,list) else actual==value
      comparisons.append({'field':key,'expected':value,'model_argument':actual,'passed':ok})
  row['model_argument_oracle_comparisons']=comparisons
  context['previous_failed']=context['previous_failed'] or not passed
 except Exception as exc:row.update(status='execution_error',error_type=type(exc).__name__);context['previous_failed']=True
 row['model_calls']=list(observed['calls']);row['elapsed_ms']=round((time.perf_counter()-start)*1000,2);rows.append(row)
 # Checkpoint every outcome so provider failures cannot erase the denominator.
 Path('/trial-ledger/AGENT_REPAIR_OFFLINE_PARTIAL.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
assert source_hash=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.glob('*.py')}
executed=[r for r in rows if r['status']!='not_run_budget_exhausted'];comparisons=[c for r in rows for c in r.get('model_argument_oracle_comparisons',[])];calls=[c for r in rows for c in r.get('model_calls',[])];repeats=0
for row in rows:
 sigs=[json.dumps([t['name'],t.get('arguments')],sort_keys=True) for c in row.get('model_calls',[]) for t in c['tools']];repeats+=len(sigs)-len(set(sigs))
def wilson(k,n):
 if not n:return None
 z=1.95996398454;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;e=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [c-e,c+e]
k=sum(r['task_success'] for r in executed)
report={'version':'agent-repair-offline-v2','scope':'offline repaired rules + actual service function; development regression on known failures; NOT real API results','task_sha256':hashlib.sha256(specpath.read_bytes()).hexdigest(),'runtime_source_sha256':source_hash,'all_frozen_tasks':len(fixture['tasks']),'preselected_tasks':len(selected),'executed_denominator':len(executed),'not_run_tasks':[{'id':t['id'],'reason':'not selected for bounded initial batch'} for t in fixture['tasks'] if t['id'] not in selected]+[{'id':r['id'],'reason':r.get('exclusion_reason')} for r in rows if r['status']=='not_run_budget_exhausted'],'summary':{'task_successes':k,'tasks':len(executed),'wilson95_descriptive':wilson(k,len(executed)),'live_tool_loop_successes':sum(r['live_tool_loop_success'] for r in executed),'observed_model_calls':len(calls),'model_argument_fields_correct':sum(c['passed'] for c in comparisons),'model_argument_fields_scored':len(comparisons),'argument_omissions_not_in_that_field_denominator':True,'repeated_tool_calls':repeats,'failure_fact_counts':dict(__import__('collections').Counter(f for r in rows for f in r.get('failure_facts',[])))},'before':before,'after':api.status(),'per_task':rows,'interpretation':'Do not combine with old90 rule-template pass rate; count all failed natural tasks. Multi-turn cascade is labelled. Repaired development regression; baseline remains unchanged in AGENT_NATURAL_EVAL.json.'}
Path('/trial-ledger/AGENT_REPAIR_OFFLINE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'summary':report['summary'],'after':report['after'],'outcomes':[{'id':r['id'],'pass':r['task_success'],'failures':r.get('failure_facts'),'mode':r.get('response',{}).get('mode')} for r in rows]},ensure_ascii=False))

