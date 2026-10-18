"""Exact bad argument replay + scripted finish, no provider network."""
import json,uuid
from pathlib import Path
from app.cineagent import api
from app.cineagent.evidence import matches
api.engine.load();reportdir=Path('/trial-ledger');baseline=json.loads((reportdir/'AGENT_NATURAL_V2_LIVE.json').read_text());rows=[]
for row in baseline['per_turn']:
    if not row.get('response',{}).get('degradation'):continue
    state=row['response']['constraints'];raw=next(t['arguments'] for c in row['model_calls'] for t in c['tools'] if t['name']=='recommend_movies')
    class Replay:
        calls=0
        def chat(self,*args,**kwargs):
            self.calls+=1
            tool={'name':'recommend_movies','arguments':json.dumps(raw)} if self.calls==1 else {'name':'finish','arguments':'{}'}
            return {'model':'offline-scripted-replay','choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':str(uuid.uuid4()),'type':'function','function':tool}]}}]},'offline-replay-no-network'
    api.DeepSeekTrial=lambda *args,**kwargs:Replay()
    response,effective,mode=api.run_tools(0,state,row['message'],[],'deepseek',{})
    guards=[t for t in response['trace'] if t.get('tool')=='constraint_guard'];assert guards and guards[0]['arguments_original']==raw
    assert set(effective.get('exclude_ids',[]))==set(state.get('exclude_ids',[]))
    assert mode=='deepseek_tools' and not response['degradation'] and response['items']
    assert all(matches(m,state,set(state.get('exclude_ids',[])),api.engine.movies) for m in response['items'])
    rows.append({'scenario':row['scenario_id'],'turn':row['turn'],'passed':True,'raw':raw,'effective':guards[0]['arguments_effective'],'repairs':guards[0]['repairs'],'result_ids':[m['movie_id'] for m in response['items']]})
assert len(rows)==8
checks=[];known=next(iter(api.engine.movies));other=next(i for i in api.engine.movies if i!=known)
for label,bad in [('bool',[True]),('string',[str(known)]),('unknown',[-987654321]),('not_array',known),('oversize',[known]*101)]:
    try:api.project_tool_constraints({'exclude_ids':bad},{'exclude_ids':[known]})
    except ValueError:checks.append({'case':label,'passed':True})
    else:raise AssertionError(label)
args,repairs=api.project_tool_constraints({'exclude_ids':[known,other]},{'exclude_ids':[known]});assert args['exclude_ids']==[known] and repairs[0]['rejected_ids']==[other];checks.append({'case':'preserve_authorized_remove_unrequested','passed':True})
args,repairs=api.project_tool_constraints({'max_runtime':90},{'exclude_ids':[known]});assert api.validated_constraints(args,{'exclude_ids':[known]})['exclude_ids']==[known];checks.append({'case':'omission_never_drops_server_exclusion','passed':True})
assert api.scoped_tools({'exclude_ids':[]})[0]['function']['parameters']['properties']['exclude_ids']['maxItems']==0
assert api.scoped_tools({'exclude_ids':[known]})[0]['function']['parameters']['properties']['exclude_ids']['items']['enum']==[known]
assert 'enum' not in api.TOOLS[0]['function']['parameters']['properties']['exclude_ids']['items'];checks.append({'case':'request_scoped_schema_does_not_mutate_global','passed':True})
result={'scope':'offline exact8 bad raw arguments replay plus explicitly scripted finish, real local engine; not actual API success','replays_passed':len(rows),'replays_total':8,'checks':checks,'per_replay':rows,'external_calls':0}
(reportdir/'EXCLUSION_GUARD_REPLAY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'replays':len(rows),'invariants':len(checks),'passed':True}))
