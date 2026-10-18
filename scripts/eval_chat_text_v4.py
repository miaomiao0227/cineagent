import json,numpy as np
from pathlib import Path
from app.cineagent.engine import engine
P=Path('/trial-ledger');data=json.loads((P/'COMPLETE_V4_RESULTS.json').read_text());engine.load();original=engine.resilience.call;rows=[]
for row in data['per_attempt']:
 if not row.get('response') or row['response']['mode']=='clarification':continue
 state=row['response']['constraints'];query=row['message'];prefs=row['response']['memory_used']
 on=engine.recommend(0,state,query,prefs)
 def without_text(name,fn,*args,**kwargs):
  if name=='recall_text':return np.zeros(len(engine.ids),dtype=np.float32)
  return original(name,fn,*args,**kwargs)
 try:
  engine.resilience.call=without_text;off=engine.recommend(0,state,query,prefs)
 finally:engine.resilience.call=original
 a=[m['movie_id'] for m in on['items']];b=[m['movie_id'] for m in off['items']];rows.append({'scenario':row['scenario_id'],'turn':row['turn'],'on_ids':a,'off_ids':b,'lists_changed':a!=b,'jaccard_at6':len(set(a)&set(b))/len(set(a)|set(b)) if a or b else None,'on_matches_live':[m['movie_id'] for m in row['response']['items']]==a,'on_recall':[t for t in on['trace'] if t.get('tool')=='recall'],'off_recall':[t for t in off['trace'] if t.get('tool')=='recall'],'on_degradation':on['degradation'],'off_degradation':off['degradation']})
report={'scope':'actual ChatEngine text-component ablation on36 saved synthetic nonclarification requests, same guest0/state/query/model; zero text scores before candidate union and fusion; no production changes or externalAPI','n':len(rows),'lists_changed':sum(r['lists_changed'] for r in rows),'on_matches_live':sum(r['on_matches_live'] for r in rows),'mean_jaccard_at6':float(np.mean([r['jaccard_at6'] for r in rows])),'not_a_relevance_gain':'list changes prove intervention only; human quality review pending','per_turn':rows};(P/'CHAT_TEXT_ABLATION_V4.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['n','lists_changed','on_matches_live','mean_jaccard_at6']}))
