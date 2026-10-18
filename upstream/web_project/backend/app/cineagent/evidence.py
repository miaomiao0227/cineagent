"""Evidence checks and opt-in constraint negotiation, without external calls."""
def matches(movie,state,excluded,movies):
    if movie['movie_id'] in excluded:return False
    genres=set(movie['genres'])
    if not set(state.get('include_genres',[]))<=genres or genres&set(state.get('exclude_genres',[])):return False
    if 'max_runtime' in state or 'min_runtime' in state:
        runtime=movie.get('runtime_minutes')
        if runtime is None or not state.get('min_runtime',0)<=runtime<=state.get('max_runtime',100000):return False
    seed=state.get('exclude_director_of')
    if seed:
        directors=set(movies.get(seed,{}).get('directors',[]));actual=set(movie.get('directors',[]))
        if not directors or not actual or directors&actual:return False
    return True

def negotiate(engine,uid,state):
    excluded=set(state.get('exclude_ids',[]))|engine.seen.get(int(uid or 0),set());suggestions=[]
    options=[]
    if 'max_runtime' in state:options.append(('max_runtime',state['max_runtime']+30,f"将最长片长从 {state['max_runtime']} 调整为 {state['max_runtime']+30} 分钟",f"把最长片长改成{state['max_runtime']+30}分钟"))
    if state.get('exclude_director_of'):options.append(('exclude_director_of',None,'取消导演排除限制','取消导演限制'))
    for key,value,label,message in options:
        alternative=dict(state)
        if value is None:alternative.pop(key,None)
        else:alternative[key]=value
        count=sum(matches(m,alternative,excluded,engine.movies) for m in engine.movies.values())
        if count:suggestions.append({'label':label,'message':message,'eligible_count':count,'requires_confirmation':True,'change':{'key':key,'from':state.get(key),'to':value}})
    return suggestions

def verify_results(engine,uid,state,items):
    excluded=set(state.get('exclude_ids',[]))|engine.seen.get(int(uid or 0),set())
    checks=[{'movie_id':item['movie_id'],'passed':item['movie_id'] in engine.movies and matches(engine.movies[item['movie_id']],state,excluded,engine.movies),'evidence_source':'local_catalogue','checked_fields':['movie_id','genres','runtime_minutes','directors','excluded_ids']} for item in items]
    return checks
