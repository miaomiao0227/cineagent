import json,hashlib,statistics,collections,math
from pathlib import Path
from sqlalchemy import select
from app.database import SessionLocal
from app.cineagent.models import RequestRecord,Preference
P=Path('/trial-ledger');fixture=json.loads((P/'COMPLETE_V4_TASKS.json').read_text());ui=json.loads((P/'COMPLETE_V4_BROWSER.json').read_text());offline=json.loads((P/'COMPLETE_V4_OFFLINE.json').read_text());ledger=json.loads((P/'DEEPSEEK_NATURAL_V2_LEDGER.json').read_text())['attempts'];batch=ledger[156:]
assert len(ledger)<=240 and len(batch)<=84
cost=lambda aa:sum(a['accounted_input_tokens']*.30/1e6+a['accounted_output_tokens']*1.20/1e6 for a in aa)
assert cost(batch)<=.10
rendered=[x for x in ui if x['status']=='rendered'];ids=[r['request_id'] for r in rendered];assert len(ids)==len(set(ids))
with SessionLocal() as db:
 records={r.request_id:r for r in db.scalars(select(RequestRecord).where(RequestRecord.request_id.in_(ids))).all()}
 owners={r.owner for r in records.values()};preferences=[{'owner':p.owner,'key':p.key,'value':p.value,'source_turn':p.source_turn,'source_conversation':p.source_conversation} for p in db.scalars(select(Preference).where(Preference.owner.in_(owners))).all()]
contexts={};rows=[]
for u in ui:
 row=dict(u);row['attempt']=u.get('attempt',1);row['passed']=False
 taskscene=next(s for s in fixture['scenarios'] if s['id']==u['scenario_id']);task=taskscene['turns'][u['turn']-1]
 if u['status']!='rendered':rows.append(row);continue
 rec=records.get(u['request_id'])
 if rec is None:row['status']='missing_persisted_response';rows.append(row);continue
 response=rec.response;key=(u['scenario_id'],row['attempt']);anchor=contexts.get(key)
 if u['turn']==1 and response['items']:contexts[key]=response['items'][0]
 expected=dict(task['expected']);checks=[]
 if task.get('reference_first_turn'):
  if anchor is None:checks.append({'fact':'previous_anchor_available','passed':False})
  else:expected.update(similar_to=anchor['movie_id'],exclude_director_of=anchor['movie_id'],exclude_ids=[anchor['movie_id']])
 state=response['constraints']
 for k,v in expected.items():
  actual=state.get(k);ok=set(v)==set(actual or []) if isinstance(v,list) else v==actual;checks.append({'fact':k,'expected':v,'actual':actual,'passed':ok})
 if task.get('expect_clarification'):checks.append({'fact':'conflict_clarified','passed':response['mode']=='clarification' and not response['items']})
 else:
  checks.append({'fact':'nonempty_for_supported_case','passed':bool(response['items'])})
  for m in response['items']:
   ok=set(expected.get('include_genres',[]))<=set(m['genres']) and not set(expected.get('exclude_genres',[]))&set(m['genres']) and m['movie_id'] not in expected.get('exclude_ids',[])
   if 'max_runtime' in expected:ok=ok and m['runtime_minutes'] is not None and m['runtime_minutes']<=expected['max_runtime']
   if task.get('reference_first_turn') and anchor:ok=ok and bool(m['directors']) and not set(m['directors'])&set(anchor['directors'])
   checks.append({'fact':'catalogue_constraints','movie_id':m['movie_id'],'passed':bool(ok)})
  for k in ['include_genres','exclude_genres','exclude_ids']:checks.append({'fact':'no_extra_'+k,'passed':set(state.get(k,[]))==set(expected.get(k,[]))})
  checks.append({'fact':'no_unrequested_runtime','passed':'max_runtime' in expected or 'max_runtime' not in state})
 if task.get('expect_warning'):checks.append({'fact':'unknown_attribute_disclosed','passed':any(task['expect_warning'] in w for w in response['warnings'])})
 if task.get('memory_expected'):
  v=task['memory_expected'];checks.append({'fact':'memory_direction_source','passed':any(p['owner']==rec.owner and p['key']==v['key'] and p['value']==v['value'] and p['source_turn']==1 and p['source_conversation']==response['conversation_id'] for p in preferences)})
 entries=[a for a in batch if a.get('parent_request_id')==u['request_id']];pi=sum(a['accounted_input_tokens'] for a in entries);po=sum(a['accounted_output_tokens'] for a in entries);usage=response.get('token_usage',{});checks.append({'fact':'usage_matches_ledger','passed':all(a['status']=='ok' for a in entries) and pi==usage.get('input',0) and po==usage.get('output',0)})
 checks.append({'fact':'browser_timer_valid','passed':isinstance(u['browser_ms'],(int,float)) and u['browser_ms']>=response['elapsed_ms']})
 row.update(response=response,expected=expected,checks=checks,passed=all(c['passed'] for c in checks),live_loop=response['mode']=='deepseek_tools' and any(t.get('tool')=='finish' for t in response['trace']),provider_attempts=len(entries),accounted_input_tokens=pi,accounted_output_tokens=po,conservative_cost_usd=cost(entries),server_ms=response['elapsed_ms']);rows.append(row)
def quantile(a,p):
 a=sorted(a);x=(len(a)-1)*p;i=int(x);return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(x-i)
def stats(a):return {'n':len(a),'mean':statistics.mean(a),'p50':quantile(a,.5),'p95':quantile(a,.95),'max':max(a),'min':min(a)} if a else {'n':0}
observed=[r for r in rows if r['status']=='rendered' and 'response' in r];llm=[r for r in observed if r['provider_attempts']];clarify=[r for r in observed if r['response']['mode']=='clarification'];first_success=0;eventual_success=0;missing=[]
for sc in fixture['scenarios']:
 group=[r for r in rows if r['scenario_id']==sc['id']];first=[r for r in group if r['attempt']==1]
 first_success+=len(first)==2 and all(r['passed'] for r in first)
 successful_attempts=[a for a in set(r['attempt'] for r in group) if len([r for r in group if r['attempt']==a])==2 and all(r['passed'] for r in group if r['attempt']==a)];eventual_success+=bool(successful_attempts)
 for t in [1,2]:
  if not any(r['turn']==t and r['attempt']==1 for r in group):missing.append({'scenario':sc['id'],'turn':t,'attempt':1,'reason':'earlier automation wait failed; subsequent turn not submitted'})
paired=[]
for r in observed:
 control=next(x for x in offline['per_turn'] if x['scenario_id']==r['scenario_id'] and x['turn']==r['turn']);paired.append({'scenario':r['scenario_id'],'turn':r['turn'],'live_business_pass':r['passed'],'offline_business_pass':control['passed'],'same_movie_ids':[m['movie_id'] for m in r['response']['items']]==[m['movie_id'] for m in control['response']['items']]})
summary={'frozen_scenarios':20,'frozen_user_turns':40,'ui_attempt_observations':len(rows),'first_attempt_scenarios_success':first_success,'eventual_scenarios_success':eventual_success,'rendered_user_turns':len(observed),'business_passed_rendered':sum(r['passed'] for r in observed),'live_loop_completed':sum(r['live_loop'] for r in observed),'clarification_turns':len(clarify),'ui_observation_failures':sum(r['status']!='rendered' for r in rows),'initial_unsubmitted_turns':len(missing),'degraded_turns':sum(bool(r['response']['degradation']) for r in observed),'provider_attempts':len(batch),'provider_failed_attempts':sum(a['status']!='ok' for a in batch),'cost_all_attempts_usd':cost(batch),'input_tokens':sum(a['accounted_input_tokens'] for a in batch),'output_tokens':sum(a['accounted_output_tokens'] for a in batch),'per_rendered_user_turn_cost_usd':cost(batch)/len(observed),'offline_business_pass':offline['summary']['turns_passed'],'same_movie_lists_vs_offline':sum(x['same_movie_ids'] for x in paired),'failure_facts':dict(collections.Counter(c['fact'] for r in rows for c in r.get('checks',[]) if not c['passed']))}
latency={name:{'browser_ms':stats([r['browser_ms'] for r in group]),'server_ms':stats([r['server_ms'] for r in group]),'input_tokens':stats([r['accounted_input_tokens'] for r in group]),'output_tokens':stats([r['accounted_output_tokens'] for r in group]),'cost_usd':stats([r['conservative_cost_usd'] for r in group])} for name,group in [('all_rendered',observed),('llm_turns',llm),('clarification',clarify)]}
accounted_ids={r['request_id'] for r in observed};unattributed=[a['request_id'] for a in batch if a.get('parent_request_id') not in accounted_ids]
report={'version':'complete-v4','source':'assistant-generated synthetic, actual browser UI + HTTP + official API; not real users or independent human evaluation','task_sha256':hashlib.sha256((P/'COMPLETE_V4_TASKS.json').read_bytes()).hexdigest(),'runtime_source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app/app/cineagent').glob('*.py')},'summary':summary,'latency':latency,'first_attempt_not_submitted':missing,'unattributed_provider_attempt_ids':unattributed,'paired_offline':paired,'per_attempt':rows,'limits':{'batch_attempts':84,'batch_usd':.10,'shared_attempts':240,'shared_usd':.50},'limitations':['first3 browser automation failures retained; UI failures without request IDs do not prove model failures','browser timer covers fetch to Vue nextTick DOM commit, not physical display paint or user think time','sequential synthetic local tests, not load SLA','subjective recommendation quality pending human review']}
assert not unattributed
(P/'COMPLETE_V4_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
review=['# 人工评议：20个双轮场景','', '请逐项填写以下空白。1=很差，5=很好；不确定可写“无法判断”并说明原因。不要根据自动通过结果代填。题目由开发助手生成，需额外判断表达是否自然。A/B为真实API与无LLM规则结果的盲化顺序，完整映射另存，不把相同结果强判胜负。','', '评议人：____  日期：____',''];mapping=[]
for index,sc in enumerate(fixture['scenarios']):
 live=[next(r for r in observed if r['scenario_id']==sc['id'] and r['turn']==t) for t in [1,2]];control=[next(r for r in offline['per_turn'] if r['scenario_id']==sc['id'] and r['turn']==t) for t in [1,2]];arms=[('live',live),('offline',control)] if index%2==0 else [('offline',control),('live',live)];mapping.append({'id':sc['id'],'A':arms[0][0],'B':arms[1][0]})
 review+=['## '+sc['id']+' / '+sc['family'],'']+[f"用户第{i+1}轮：{t['message']}" for i,t in enumerate(sc['turns'])]+['']
 for label,(_,rr) in zip(['A','B'],arms):
  review+=['### 方案'+label,'']
  for number,row in enumerate(rr,1):
   resp=row['response'];review.append(f"第{number}轮："+('；'.join(f"#{m['movie_id']} {m['title']}（{m['reason']}）" for m in resp['items']) or '无结果，需要澄清。')+' 提示：'+'；'.join(resp['warnings']))
 review+=['','表达自然性（是/否/不确定）：____','A相关性1–5：____；B相关性1–5：____','A理由可信度1–5：____；B理由可信度1–5：____','偏好选择（A/B/相同/无法判断）：____','完成任务了吗（A/B分别填写）：____','备注：____','']
Path('/artifacts/HUMAN_REVIEW_V4.md').write_text('\n'.join(review),encoding='utf-8');(P/'HUMAN_REVIEW_V4_MAPPING.json').write_text(json.dumps(mapping,indent=2),encoding='utf-8');print(json.dumps({'summary':summary,'latency':latency,'unattributed':unattributed},ensure_ascii=False))
