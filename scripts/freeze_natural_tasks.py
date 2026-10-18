import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
tasks=[
 {'id':'N01','group':'single','message':'想看科幻电影，片长最多九十分钟，不要恐怖片。','expected':{'include_genres':['Sci-Fi'],'exclude_genres':['Horror'],'max_runtime':90},'intent_source':'authored explicit genre/runtime control'},
 {'id':'N02','group':'single','message':'想看喜剧，恐怖的就算了，总时长别超过一个半钟头。','expected':{'include_genres':['Comedy'],'exclude_genres':['Horror'],'max_runtime':90},'intent_source':'authored colloquial rejection and one-and-a-half-hour upper bound'},
 {'id':'N03','group':'single','message':'找科幻片，一小时三十分钟以内，不要恐怖。','expected':{'include_genres':['Sci-Fi'],'exclude_genres':['Horror'],'max_runtime':90},'intent_source':'authored composite duration equals90minutes'},
 {'id':'N04','group':'single','message':'以后都别给我推恐怖类型的电影。','expected':{'exclude_genres':['Horror']},'memory_expected':{'key':'exclude_genres','value':'Horror'},'intent_source':'authored explicit long-term negative preference'},
 {'id':'M01','group':'multi1','message':'想看悬疑电影，不要恐怖片，两小时以内。','expected':{'include_genres':['Mystery'],'exclude_genres':['Horror'],'max_runtime':120}},
 {'id':'M02','group':'multi1','message':'排在最前面的那部已经看了，换一部相似的，导演也别重复。','expected':{'include_genres':['Mystery'],'exclude_genres':['Horror'],'max_runtime':120},'reference_first_turn':True,'different_director':True},
 {'id':'M03','group':'multi1','message':'把刚才的两小时改成九十分钟，其他排除条件都留着。','expected':{'include_genres':['Mystery'],'exclude_genres':['Horror'],'max_runtime':90},'reference_first_turn':True,'different_director':True},
 {'id':'N05','group':'single','message':'恐怖片先别推荐，来些喜剧，九十分钟封顶。','expected':{'include_genres':['Comedy'],'exclude_genres':['Horror'],'max_runtime':90}},
 {'id':'N06','group':'single','message':'只想看科幻，不接受恐怖元素，两个小时是上限。','expected':{'include_genres':['Sci-Fi'],'exclude_genres':['Horror'],'max_runtime':120}},
 {'id':'N07','group':'single','message':'想看悬疑，但恐怖也想看，同时完全不能是恐怖片。','expected_clarification':True},
 {'id':'N08','group':'single','message':'来一部节奏很快又治愈的电影，不能瞎猜情绪标签。','expected_unsupported_disclosure':True},
 {'id':'N09','group':'single','message':'这次别推荐爱情片，这只是今晚的要求，不要长期记住。','expected':{'exclude_genres':['Romance']},'memory_must_be_empty':True},
 {'id':'N10','group':'single','message':'至少一个半小时，最多两小时的剧情片。','expected':{'include_genres':['Drama'],'min_runtime':90,'max_runtime':120}},
 {'id':'N11','group':'single','message':'第二部我已经看过了。','expected_clarification':True}
]
fixture={'version':'agent-natural-v1','source':'assistant-generated synthetic tasks and oracle labels; not independently human-reviewed; not real users','predeclared_execution_ids':[x['id'] for x in tasks[:7]],'not_selected_reason':'remaining quota at freeze17 provider attempts; initial batch expects14 plus retry margin; no success-based selection','tasks':tasks,'grading':'deterministic authored intent + catalogue attributes; invalid/missing constraints and memory facts retained as failure; no LLM judge','runtime_change_policy':'do not modify parser/prompt/tools while running this baseline'}
p=root/'eval/agent_natural_v1.json'
if p.exists():assert json.loads(p.read_text(encoding='utf-8'))==fixture
else:p.write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'eval/agent_natural_v1.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest(),encoding='ascii')
(root/'reports/AGENT_NATURAL_TASKS.json').write_bytes(p.read_bytes())
print('Frozen tasks',len(tasks),'selected',len(fixture['predeclared_execution_ids']))

