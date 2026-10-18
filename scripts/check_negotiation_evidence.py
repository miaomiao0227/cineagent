import json,uuid,hashlib
from pathlib import Path
from app.cineagent import api
from app.cineagent.evidence import verify_results
api.engine.load();who='guest:'+str(uuid.uuid4());rows=[]
valid=[m['runtime_minutes'] for m in api.engine.movies.values() if 'Mystery' in m['genres'] and m['runtime_minutes'] and m['runtime_minutes']>1]
bound=min(valid)-1
first=api.message(api.ChatInput(request_id=uuid.uuid4(),message=f'悬疑电影，最多{bound}分钟。',mode='offline'),identity=(who,0))
assert not first['items'];assert first['constraints']['max_runtime']==bound
options=first['relaxation_suggestions'];assert options and all(o['requires_confirmation'] and o['eligible_count']>0 for o in options)
assert first['constraints']['max_runtime']==bound
second=api.message(api.ChatInput(request_id=uuid.uuid4(),conversation_id=first['conversation_id'],message=options[0]['message'],mode='offline'),identity=(who,0))
assert second['items'] and second['constraints']['max_runtime']==bound+30
assert all(c['passed'] for c in second['evidence_checks'])
mid=next(m['movie_id'] for m in api.engine.movies.values() if m['runtime_minutes'] and m['runtime_minutes']>bound)
check=verify_results(api.engine,0,{'max_runtime':bound},[{'movie_id':mid}]);assert not check[0]['passed']
try:api.validated_constraints({'exclude_ids':[mid]},{'exclude_ids':[]})
except ValueError as e:assert str(e)=='unsupported_exclusions'
else:raise AssertionError('unrequested exclusion accepted')
report={'checks':{'empty_result_does_not_relax':True,'suggestions_have_verified_candidates':True,'confirmation_changes_only_requested_runtime':True,'returned_items_pass_catalogue_checks':True,'injected_bad_candidate_rejected_by_validator':True,'invented_exclusion_rejected':True},'first':first,'confirmed':second,'bad_candidate_check':check,'scope':'deterministic actual service integration, synthetic identity; no external API; evidence checks verify local fields, not external truth or all natural-language claims'}
Path('/trial-ledger/NEGOTIATION_EVIDENCE_CHECK.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['checks']))
