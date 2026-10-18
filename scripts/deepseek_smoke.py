"""One approved request: synthetic preferences only, no user records or images."""
import importlib.util,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cine_provider',root/'upstream/web_project/backend/app/cineagent/provider.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
client=mod.DeepSeekTrial(root/'configs/local-secrets/deepseek.json',root/'reports/DEEPSEEK_TRIAL_LEDGER.json')
tools=[{'type':'function','function':{'name':'filter_movies','description':'Apply requested genre and duration constraints to local movie candidates.','parameters':{'type':'object','properties':{'include_genres':{'type':'array','items':{'type':'string'}},'exclude_genres':{'type':'array','items':{'type':'string'}},'max_runtime':{'type':'integer'}},'required':['include_genres','exclude_genres','max_runtime'],'additionalProperties':False}}}]
messages=[{'role':'system','content':'You are a movie preference parser. Use filter_movies to represent the explicit constraints. Genre values must be English MovieLens genres. Do not invent films. Return a tool call, not movie recommendations.'},{'role':'user','content':'想看悬疑电影，不要恐怖片，最好两小时以内。'}]
try:
    result,rid=client.chat(messages,tools,max_tokens=256,trial_authorized=True)
    message=result['choices'][0]['message'];calls=message.get('tool_calls') or []
    parsed=[]
    for call in calls:
        name=call['function']['name'];args=json.loads(call['function']['arguments'])
        parsed.append({'name':name,'arguments':args})
    passed=len(parsed)==1 and parsed[0]['name']=='filter_movies' and parsed[0]['arguments'].get('include_genres')==['Mystery'] and parsed[0]['arguments'].get('exclude_genres')==['Horror'] and parsed[0]['arguments'].get('max_runtime')==120
    report={'scope':'single synthetic request; tool selection and argument parsing only, no recommendation executed','request_id':rid,'model_returned':result.get('model'),'usage':result.get('usage'),'parsed_tools':parsed,'passed':passed}
except Exception as exc:
    report={'scope':'single synthetic connectivity request','passed':False,'error_type':type(exc).__name__,'error_code':str(exc) if isinstance(exc,mod.ProviderError) else 'local_validation_error'}
(root/'reports/DEEPSEEK_CONNECTIVITY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
sys.exit(0 if report['passed'] else 1)
