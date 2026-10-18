"""Frozen synthetic natural tasks, real service integration. No HTTP/auth claim."""
import json,uuid,hashlib,time,sys,collections
from pathlib import Path
from app.cineagent import api
from app.cineagent.provider import DeepSeekTrial
LIVE='--live' in sys.argv
REPORT=Path('/trial-ledger');raw=(REPORT/'AGENT_EXCLUSION_V3_TASKS.json').read_bytes();fixture=json.loads(raw)
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app/app/cineagent').glob('*.py')}
api.engine.load();calls=[];original=DeepSeekTrial.chat
ledger=REPORT/'DEEPSEEK_NATURAL_V2_LEDGER.json'
def campaign(config,unused):return DeepSeekTrial(config,ledger,approved_campaign=True)
def traced(self,*args,**kwargs):
 if not LIVE:raise AssertionError('provider forbidden during offline regression')
 result,rid=original(self,*args,**kwargs);tools=[]
 for t in result['choices'][0]['message'].get('tool_calls') or []:
  f=t['function'];item={'name':f['name'],'arguments_raw':f['arguments']}
  try:item['arguments']=json.loads(f['arguments'])
  except Exception:item['parse_error']=True
  tools.append(item)
 calls.append({'request_id':rid,'model':result.get('model'),'usage':result.get('usage'),'tools':tools});return result,rid
DeepSeekTrial.chat=traced;api.DeepSeekTrial=campaign
suffix='LIVE' if LIVE else 'OFFLINE';path=REPORT/f'AGENT_EXCLUSION_V3_{suffix}.json'
assert not path.exists(), 'Do not overwrite completed evaluation; archive and use a new version'
rows=[];started=time.time();before=json.loads(ledger.read_text()) if ledger.exists() else {'attempts':[]}
for scene in fixture['scenarios']:
 who='guest:'+str(uuid.uuid4());cid=None;anchor=None;scenario_rows=[]
 for number,task in enumerate(scene['turns'],1):
  row={'scenario_id':scene['id'],'family':scene['family'],'turn':number,'message':task['message'],'passed':False};calls.clear();tick=time.perf_counter()
  try:
   expected=dict(task['expected'])
   if task.get('reference_first_turn'):
    if anchor is None:raise ValueError('missing_previous_anchor')
    expected.update(similar_to=anchor['movie_id'],exclude_director_of=anchor['movie_id'],exclude_ids=[anchor['movie_id']])
   response=api.message(api.ChatInput(request_id=uuid.uuid4(),conversation_id=cid,message=task['message'],mode='deepseek' if LIVE else 'offline'),identity=(who,0));cid=response['conversation_id']
   if number==1 and response['items']:anchor=response['items'][0]
   state=response['constraints'];checks=[]
   for key,value in expected.items():
    actual=state.get(key);checks.append({'fact':key,'passed':set(value)<=set(actual or []) if isinstance(value,list) else value==actual,'expected':value,'actual':actual})
   if task.get('expect_clarification'):
    checks.append({'fact':'conflict_requires_clarification','passed':response['mode']=='clarification' and not response['items']})
   else:
    checks.append({'fact':'nonempty_catalogue_results','passed':bool(response['items'])})
    for movie in response['items']:
     ok=set(expected.get('include_genres',[]))<=set(movie['genres']) and not set(expected.get('exclude_genres',[]))&set(movie['genres']) and movie['movie_id'] not in expected.get('exclude_ids',[])
     if 'max_runtime' in expected:ok=ok and movie['runtime_minutes'] is not None and movie['runtime_minutes']<=expected['max_runtime']
     if task.get('different_director'):ok=ok and bool(movie['directors']) and not set(movie['directors'])&set(anchor['directors'])
     checks.append({'fact':'catalogue_constraint','movie_id':movie['movie_id'],'passed':bool(ok)})
   if task.get('expect_warning'):checks.append({'fact':'unknown_attribute_disclosed','passed':any(task['expect_warning'] in x for x in response['warnings'])})
   if task.get('memory_expected'):
    desired=task['memory_expected'];mem=api.list_prefs(identity=(who,0))['items'];checks.append({'fact':'memory_direction_provenance','passed':any(p['key']==desired['key'] and p['value']==desired['value'] and p['source_turn']==1 and p['source_conversation']==cid for p in mem) and not any(p['value']==desired['value'] and p['key']!=desired['key'] for p in mem)})
   checks.append({'fact':'no_invented_excluded_ids','passed':set(state.get('exclude_ids',[]))<=set(expected.get('exclude_ids',[]))})
   checks.append({'fact':'evidence_checks_pass','passed':len(response.get('evidence_checks',[]))==len(response['items']) and all(c['passed'] for c in response.get('evidence_checks',[]))})
   row.update(expected=expected,checks=checks,response=response,passed=all(c['passed'] for c in checks),live_loop=response['mode']=='deepseek_tools',status='executed')
  except Exception as exc:row.update(status='error',error_type=type(exc).__name__)
  row.update(model_calls=list(calls),elapsed_ms=round((time.perf_counter()-tick)*1000,2));rows.append(row);scenario_rows.append(row)
  (REPORT/f'AGENT_EXCLUSION_V3_{suffix}_PARTIAL.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'scenario':scene['id'],'family':scene['family'],'passed':sum(r['passed'] for r in scenario_rows),'turns':len(scenario_rows),'provider_calls':sum(len(r['model_calls']) for r in scenario_rows)}),flush=True)
assert source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app/app/cineagent').glob('*.py')},'source changed during batch'
groups={s['id']:[r for r in rows if r['scenario_id']==s['id']] for s in fixture['scenarios']};families={f:{'turns':sum(r['family']==f for r in rows),'passed':sum(r['passed'] for r in rows if r['family']==f)} for f in sorted({r['family'] for r in rows})}
report={'version':'exclusion-guard-v3','mode':suffix,'scope':'V3 scoped exclusion validation, 8 known failures + 3 new synthetic probes; actual service function, no HTTP/auth or independent real-user claim','task_sha256':hashlib.sha256(raw).hexdigest(),'runtime_source_sha256':source,'summary':{'scenarios':len(groups),'scenarios_all_turns_passed':sum(len(g)==2 and all(r['passed'] for r in g) for g in groups.values()),'turns':len(rows),'turns_passed':sum(r['passed'] for r in rows),'live_tool_loop_turns':sum(r.get('live_loop',False) for r in rows),'clarification_turns':sum(r.get('response',{}).get('mode')=='clarification' for r in rows),'observed_successful_provider_calls':sum(len(r['model_calls']) for r in rows),'families':families,'failure_counts':dict(collections.Counter(c['fact'] for r in rows for c in r.get('checks',[]) if not c['passed']))},'ledger_before':before,'ledger_after':json.loads(ledger.read_text()) if ledger.exists() else {'attempts':[]},'seconds':time.time()-started,'per_turn':rows,'not_run':[],'uncertainty':'8 known failures and 3 new assistant-authored probes; dependent synthetic scenarios, no real-user claim'}
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['summary']),flush=True)
