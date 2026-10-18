"""Independent package integrity, fresh-base patch, budgets and runtime acceptance."""
import ast,hashlib,json,os,subprocess,tempfile,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'showcase';checks=[]
def check(name,value):
 checks.append({'case':name,'passed':bool(value)})
 if not value:raise AssertionError(name)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
entries=json.loads((OUT/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
check('package_all_file_hashes',all((OUT/x['path']).is_file() and digest(OUT/x['path'])==x['sha256'] for x in entries))
check('required_deliverables',all((OUT/p).is_file() for p in ['START_HERE.md','REPRODUCE.md','RESUME.md','CONTRIBUTIONS.md','ARCHITECTURE.md','DEMO.md','EVAL_SPEC.md','reports/FINAL_RESULTS.md','reports/CHAT_ACCEPTANCE.png','source/upstream.patch']))
load=json.loads((ROOT/'reports/SERVICE_LOAD.json').read_text());check('historical_v3_load_matches_snapshot',bool(load.get('source_sha256')) and all(digest(ROOT/'reports/source_snapshots/conversation-v3'/Path(p).name)==h for p,h in load['source_sha256'].items()))
ledger=json.loads((ROOT/'reports/DEEPSEEK_TRIAL_LEDGER.json').read_text())['attempts'];pi=sum(r['accounted_input_tokens'] for r in ledger);po=sum(r['accounted_output_tokens'] for r in ledger)
check('approved_trial_limits',len(ledger)<=30 and pi<=150000 and po<=30000 and pi*.3/1e6+po*1.2/1e6<=.1)
campaign=json.loads((ROOT/'reports/DEEPSEEK_NATURAL_V2_LEDGER.json').read_text(encoding='utf-8'))['attempts'];cpi=sum(a['accounted_input_tokens'] for a in campaign);cpo=sum(a['accounted_output_tokens'] for a in campaign)
check('approved_new_campaign_limits',len(campaign)<=240 and cpi<=600000 and cpo<=120000 and cpi*.3/1e6+cpo*1.2/1e6<=.5)
natural=json.loads((ROOT/'reports/AGENT_NATURAL_V2_LIVE.json').read_text(encoding='utf-8'))
check('natural_fixture_matches_frozen_input',digest(ROOT/'eval/agent_natural_v2.json')==natural['task_sha256']==digest(ROOT/'reports/AGENT_NATURAL_V2_TASKS.json'))
check('historical_v2_source_matches_snapshot',all(digest(ROOT/'reports/source_snapshots/conversation-v2'/name)==h for name,h in natural['runtime_source_sha256'].items()))
v3=json.loads((ROOT/'reports/AGENT_EXCLUSION_V3_LIVE.json').read_text(encoding='utf-8'))
check('v3_frozen_tasks_match_api_run',digest(ROOT/'eval/agent_exclusion_v3.json')==v3['task_sha256']==digest(ROOT/'reports/AGENT_EXCLUSION_V3_TASKS.json'))
check('historical_v3_api_matches_snapshot',all(digest(ROOT/'reports/source_snapshots/conversation-v3'/name)==h for name,h in v3['runtime_source_sha256'].items()))
v4=json.loads((ROOT/'reports/COMPLETE_V4_RESULTS.json').read_text(encoding='utf-8'))
check('v4_frozen_tasks_match_browser_run',digest(ROOT/'eval/complete_v4.json')==v4['task_sha256']==digest(ROOT/'reports/COMPLETE_V4_TASKS.json'))
check('v4_browser_run_matches_current_backend',all(digest(ROOT/'upstream/web_project/backend/app/cineagent'/name)==h for name,h in v4['runtime_source_sha256'].items()))
check('v4_browser_run_matches_current_frontend',digest(ROOT/'upstream/web_project/frontend/src/views/Chat.vue')==v4['frontend_source_sha256'])
check('v4_sub_budget_and_attribution',v4['summary']['provider_attempts']<=84 and v4['summary']['cost_all_attempts_usd']<=.10 and not v4['unattributed_provider_attempt_ids'])
req=urllib.request.Request('http://127.0.0.1:13000/api/chat/evaluation-guest',data=b'{}',headers={'Content-Type':'application/json'})
try:
 urllib.request.urlopen(req,timeout=10);closed=False
except urllib.error.HTTPError as exc:closed=exc.code==403
check('temporary_paid_evaluation_window_closed',closed)
real_index=ROOT/'upstream/.git/index';before=digest(real_index)
tmp=tempfile.TemporaryDirectory(prefix='.delivery-index-',dir=ROOT/'reports');scratch=Path(tmp.name).resolve()
if scratch.parent!=(ROOT/'reports').resolve():raise RuntimeError('Unexpected temporary directory')
try:
 env=os.environ.copy();env['GIT_INDEX_FILE']=str(scratch/'index');git=['git','-C',str(ROOT/'upstream')]
 subprocess.run(git+['read-tree','5f7bd84d4403b5f92b6bedbd31e3984ef00a4572'],env=env,capture_output=True,check=True)
 subprocess.run(git+['apply','--cached','--check',str(OUT/'source/upstream.patch')],env=env,capture_output=True,check=True)
 check('tracked_patch_applies_to_pinned_clean_index',True)
finally:tmp.cleanup()
check('real_git_index_unchanged',before==digest(real_index))
newfiles=[p for p in (OUT/'source/new_files').rglob('*') if p.is_file()]
check('new_files_match_actual_source',all(digest(p)==digest(ROOT/'upstream'/p.relative_to(OUT/'source/new_files')) for p in newfiles))
for p in newfiles:
 if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
check('exported_python_syntax',True)
with urllib.request.urlopen('http://127.0.0.1:13000/health',timeout=10) as response:health=json.load(response)
check('service_dependencies_healthy',health['status']=='healthy' and all(health[k]=='healthy' for k in ['database','redis','elasticsearch']))
with urllib.request.urlopen('http://127.0.0.1:18000/ready',timeout=10) as response:ready=json.load(response)
check('deployed_models_ready',ready['ready'])
with urllib.request.urlopen('http://127.0.0.1:13000/chat',timeout=10) as response:page=response.read()
check('chat_page_available',b'<div id="app">' in page)
with urllib.request.urlopen('http://127.0.0.1:13000/api/movies?page_size=1',timeout=10) as response:catalogue=json.load(response)
check('catalogue_preserved_after_pinned_restart',catalogue['total']==3883)
req=urllib.request.Request('http://127.0.0.1:13000/api/chat/guest',data=b'{}',headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=10) as response:guest=json.load(response)['access_token']
body={'request_id':str(uuid.uuid4()),'message':'想看悬疑电影，不要恐怖片，两小时以内。','mode':'offline'}
req=urllib.request.Request('http://127.0.0.1:13000/api/chat/message',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+guest})
with urllib.request.urlopen(req,timeout=15) as response:recommendation=json.load(response)
check('offline_chat_after_restart',recommendation['mode']=='offline_rules' and bool(recommendation['items']) and all('Mystery' in m['genres'] and 'Horror' not in m['genres'] and m['runtime_minutes'] is not None and m['runtime_minutes']<=120 for m in recommendation['items']))
report={'passed':all(c['passed'] for c in checks),'checks':checks,'external_api_requests_made_by_this_check':0,'note':'Git patch checked against a temporary clean index; original index unchanged. No training or raw-data download.'}
(ROOT/'reports/FINAL_ACCEPTANCE.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

