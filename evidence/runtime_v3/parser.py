"""Deterministic offline parser. This is not an LLM or validated ReAct agent."""
import re
from copy import deepcopy
GENRES={'悬疑':'Mystery','恐怖':'Horror','惊悚':'Thriller','喜剧':'Comedy','动作':'Action','爱情':'Romance','科幻':'Sci-Fi','剧情':'Drama','动画':'Animation','犯罪':'Crime','冒险':'Adventure','战争':'War','纪录':'Documentary','儿童':'Children\'s','奇幻':'Fantasy','西部':'Western','音乐':'Musical','黑色电影':'Film-Noir'}
for _g in tuple(GENRES.values()): GENRES[_g.lower()]=_g
NUM={'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
def number(s):
    if s.isdigit(): return int(s)
    if s in NUM:return NUM[s]
    if '十' in s:
        a,b=s.split('十',1);return NUM.get(a,1)*10+NUM.get(b,0)
    return None

def parse(text, previous=None, turn=1):
    if not isinstance(text,str) or not text.strip():raise ValueError('message must not be empty')
    if len(text)>4000:raise ValueError('message exceeds 4000 characters')
    state=deepcopy(previous or {})
    for key in ('include_genres','exclude_genres','exclude_ids'): state.setdefault(key,[])
    state.setdefault('sources',{})
    updates={};warnings=[];memory=[]
    if re.search(r'重新开始|清空条件|reset constraints',text,re.I):
        state={'include_genres':[],'exclude_genres':[],'exclude_ids':[],'sources':{}}
    if '取消时长限制' in text:
        state.pop('max_runtime',None);state.pop('min_runtime',None)
    if '取消导演限制' in text:state.pop('exclude_director_of',None)
    # Clauses keep negation local; a later positive clause must not inherit it.
    for match in re.finditer(r'[^，,。；;！!？?]+',text):
        clause=match.group(); low=clause.lower()
        negative=bool(re.search(r'不要|不看|别|不推荐|不喜欢|排除|避免|算了|without|exclude|not\s',low))
        found=sorted({v for k,v in GENRES.items() if k in low})
        for genre in found:
            key='exclude_genres' if negative else 'include_genres'
            other='include_genres' if negative else 'exclude_genres'
            # Explicit correction supersedes prior constraints; otherwise report conflict.
            if genre in state[other]:
                if re.search(r'改成|改为|其实|纠正|现在|取消',clause):state[other].remove(genre)
                else:warnings.append('类型条件冲突：'+genre)
            if genre not in state[key]:state[key].append(genre)
            updates[key]=state[key]
            state['sources'][key+':'+genre]={'turn':turn,'start':match.start(),'end':match.end()}
            if re.search(r'记住|以后|长期|一直',clause):memory.append({'key':key,'value':genre,'source_turn':turn,'start':match.start(),'end':match.end()})
    # Consume a composite duration once; corrections use the final complete mention.
    duration = r'([\d一二两三四五六七八九十]+)(?:个)?\s*(小时|钟头|分钟|分)(?:\s*([\d一二两三四五六七八九十]+)\s*(?:分钟|分))?|([\d一二两三四五六七八九十]+)(?:个)?半(?:小时|钟头)|半(?:小时|钟头)'
    for runtime in re.finditer(duration,text):
        if runtime.group(4): value=number(runtime.group(4))*60+30
        elif runtime.group(1):
            value=number(runtime.group(1))*(60 if runtime.group(2) in ('小时','钟头') else 1)
            if runtime.group(3): value+=number(runtime.group(3))
        else:value=30
        prefix=re.split(r'[，,。；;]',text[:runtime.start()])[-1]
        suffix=re.split(r'[，,。；;]',text[runtime.end():])[0]
        lower=bool(re.search(r'至少|不少于|长于',prefix) or ('以上' in suffix))
        key='min_runtime' if lower else 'max_runtime'
        state[key]=value;updates[key]=value;state['sources'][key]={'turn':turn,'start':runtime.start(),'end':runtime.end()}
    if state.get('min_runtime',0)>state.get('max_runtime',100000):warnings.append('片长上下限冲突')
    if re.search(r'节奏快|烧脑|温暖|治愈',text):warnings.append('库内没有经过验证的节奏或情绪标签，不能保证此条件')
    reference=re.search(r'第([\d一二两三四五六七八九十]+)[部个]',text)
    if reference is None and re.search(r'最前面|排在首位|第一位|首部',text):reference=re.search(r'(一)', '一')
    action=None
    if reference and re.search(r'看过|换|类似|导演',text):
        n=number(reference.group(1));last=state.get('last_results',[])
        if n and n<=len(last):
            mid=last[n-1];state['similar_to']=mid;updates['similar_to']=mid
            if re.search(r'看过|换',text):
                if mid not in state['exclude_ids']:state['exclude_ids'].append(mid)
            if '看过' in text:action={'movie_id':mid,'kind':'seen'}
            if re.search(r'不要.*导演|不同.*导演|不.*同.*导演|导演.*别.*重复|导演.*不.*重复',text):state['exclude_director_of']=mid
        else:warnings.append('无法定位上一轮电影，请先获取推荐或指定有效序号')
    return {'mode':'offline_rules','state':state,'updates':updates,'memory_proposals':memory,'feedback':action,'warnings':sorted(set(warnings)),'needs_clarification':any('冲突' in x or '无法定位' in x for x in warnings)}

def compress(state,turn_count):
    """Structured state retains source offsets; originals stay in the turn table."""
    return {'version':'structured-v1','through_turn':turn_count,'constraints':{k:v for k,v in state.items() if k not in ('last_results','sources')},'sources':deepcopy(state.get('sources',{})),'last_results':state.get('last_results',[])}

