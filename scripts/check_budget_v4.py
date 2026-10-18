import json,tempfile
from pathlib import Path
from app.cineagent.provider import DeepSeekTrial,BudgetExceeded
rows=[]
with tempfile.TemporaryDirectory(prefix='budget-v4-',dir='/artifacts') as temp:
 d=Path(temp).resolve();assert d.parent==Path('/artifacts');cfg=d/'config.json';ledger=d/'DEEPSEEK_NATURAL_V2_LEDGER.json'
 cfg.write_text(json.dumps({'model':'deepseek-flash','base_url':'https://api.deepseek.com','api_key':'test-not-a-key','approved_trial':{'max_requests_including_retries':30,'max_input_tokens':150000,'max_output_tokens':30000,'budget_usd':.10}}))
 cases=[('batch_attempt_limit',156,{'start_attempt':156,'max_new_attempts':0,'max_new_cost_usd':.10},True,'batch_request_limit'),('batch_cost_limit',156,{'start_attempt':156,'max_new_attempts':84,'max_new_cost_usd':0},True,'batch_cost_limit'),('shared240_limit',240,None,True,'request_limit'),('normal30_limit',30,None,False,'request_limit')]
 for name,n,window,campaign,error in cases:
  ledger.write_text(json.dumps({'attempts':[{'accounted_input_tokens':0,'accounted_output_tokens':0} for _ in range(n)]}));before=ledger.read_bytes()
  try:DeepSeekTrial(cfg,ledger,approved_campaign=campaign,budget_window=window).chat([],trial_authorized=True)
  except BudgetExceeded as exc:assert str(exc)==error
  else:raise AssertionError(name)
  assert before==ledger.read_bytes();rows.append({'case':name,'passed':True,'no_reservation_or_network':True})
Path('/trial-ledger/COMPLETE_V4_BUDGET_CHECK.json').write_text(json.dumps({'checks':rows,'external_calls':0},indent=2));print(json.dumps(rows))
