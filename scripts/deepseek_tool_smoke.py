"""Two-turn tool execution smoke, bounded by the shared approved trial ledger."""
import importlib.util,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider',root/'upstream/web_project/backend/app/cineagent/provider.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
client=mod.DeepSeekTrial(root/'configs/local-secrets/deepseek.json',root/'reports/DEEPSEEK_TRIAL_LEDGER.json')
properties={'include_genres':{'type':'array','items':{'type':'string'}},'exclude_genres':{'type':'array','items':{'type':'string'}},'max_runtime':{'type':'integer'}}
tool={'type':'function','function':{'name':'filter_movies','description':'Filter the local movie catalogue by explicit genre and runtime constraints.','parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}}
finish={'type':'function','function':{'name':'finish_recommendation','description':'Select up to three real movie IDs from the tool results, or return empty IDs if none qualify.','parameters':{'type':'object','properties':{'movie_ids':{'type':'array','items':{'type':'integer'}}},'required':['movie_ids'],'additionalProperties':False}}}
messages=[{'role':'system','content':'You are a movie tool assistant. First call filter_movies to apply the request to the local catalogue. Genre names are English MovieLens genres. After tool results, call finish_recommendation using only supplied IDs. Do not invent films or attributes.'},{'role':'user','content':'想看悬疑电影，不要恐怖片，最好两小时以内。'}]
report={'scope':'synthetic local catalogue filtering and two model turns; no personalized model ranking or end-to-end Agent evaluation','request_ids':[],'trace':[],'passed':False};started=time.monotonic()
try:
    result,rid=client.chat(messages,[tool],max_tokens=256,trial_authorized=True);report['request_ids'].append(rid)
    message=result['choices'][0]['message'];calls=message.get('tool_calls') or []
    if len(calls)!=1 or calls[0]['function']['name']!='filter_movies':raise ValueError('unexpected_tool')
    call=calls[0];args=json.loads(call['function']['arguments'])
    if set(args)!=set(properties) or args['include_genres']!=['Mystery'] or args['exclude_genres']!=['Horror'] or type(args['max_runtime']) is not int or args['max_runtime']!=120:raise ValueError('invalid_constraints')
    catalogue=json.loads((root/'artifacts/content_v1/local_catalogue.json').read_text(encoding='utf-8'))
    eligible=[];missing=0
    for movie in catalogue:
        genres=set(movie['genres'])
        if not set(args['include_genres'])<=genres or set(args['exclude_genres'])&genres:continue
        if movie['runtime_minutes'] is None:missing+=1;continue
        if 0<movie['runtime_minutes']<=args['max_runtime']:eligible.append(movie)
    # Stable ID order is deliberate: this smoke validates filtering, not ranking quality.
    shown=eligible[:5]
    output={'items':shown,'eligible_count':len(eligible),'missing_runtime_excluded':missing,'order':'movie_id ascending; not personalized ranking'}
    report['trace'].append({'tool':'filter_movies','arguments':args,'catalogue_denominator':len(catalogue),'result':output})
    assistant={'role':'assistant','content':message.get('content'),'tool_calls':calls}
    messages.extend([assistant,{'role':'tool','tool_call_id':call['id'],'content':json.dumps(output,ensure_ascii=False)}])
    result2,rid2=client.chat(messages,[finish],max_tokens=256,trial_authorized=True);report['request_ids'].append(rid2)
    calls2=result2['choices'][0]['message'].get('tool_calls') or []
    if len(calls2)!=1 or calls2[0]['function']['name']!='finish_recommendation':raise ValueError('unexpected_finish_tool')
    final=json.loads(calls2[0]['function']['arguments']);ids=final.get('movie_ids')
    valid={m['movie_id']:m for m in shown}
    if set(final)!={'movie_ids'} or not isinstance(ids,list) or len(ids)>3 or len(set(ids))!=len(ids) or any(type(i) is not int or i not in valid for i in ids) or (shown and not ids):raise ValueError('invalid_final_ids')
    report.update(passed=True,recommendations=[valid[i] for i in ids],usage=[result.get('usage'),result2.get('usage')],model_returned=[result.get('model'),result2.get('model')])
except Exception as exc:
    report['error_type']=type(exc).__name__
    if isinstance(exc,mod.ProviderError):report['error_code']=str(exc)
report['elapsed_ms']=round((time.monotonic()-started)*1000,2)
(root/'reports/DEEPSEEK_TOOL_LOOP.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['passed'] else 1)
