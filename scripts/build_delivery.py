"""Build small reviewable delivery with explicit inputs, hashes and credential scan."""
import hashlib,json,math,os,random,shutil,subprocess,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'showcase';BASE='5f7bd84d4403b5f92b6bedbd31e3984ef00a4572'
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8')
def wilson(k,n):
 z=1.95996398454;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;e=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [c-e,c+e]
def paired_ci(values):
 rng=random.Random(20261018);n=len(values);sample=sorted(sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(2000));return {'mean':sum(values)/n,'bootstrap_95':[sample[49],sample[1949]],'n':n}
def build_report():
 warm=read('artifacts/rec_v1/test_Popular_ItemCF_YouTubeDNN_YT100_DeepFM_summary.json');cold=read('reports/COLD_RESULTS.json');agent=read('reports/AGENT_HTTP_V2_EVAL.json');memory=read('reports/MEMORY_PAIRED_EVAL.json');controlled=read('reports/AGENT_CONTROLLED_EVAL.json');live=read('reports/DEEPSEEK_HTTP_EVAL.json');compression=read('reports/COMPRESSION_LIVE_EVAL.json');load=read('reports/SERVICE_LOAD.json');redis=read('reports/REDIS_RECOVERY.json');lifecycle=read('reports/MEMORY_LIFECYCLE.json');expiry=read('reports/MEMORY_EXPIRY_CHECK.json');ledger=read('reports/DEEPSEEK_TRIAL_LEDGER.json')
 assert load.get('source_sha256') and all(sha(ROOT/'reports/source_snapshots/conversation-v3'/Path(p).name)==h for p,h in load['source_sha256'].items()),'Historical V3 load does not match archived source'
 assert all(s['passed']==s['total'] for s in agent['summary'].values()) and live['passed']==live['total'] and redis['passed'] and compression['passed'] and lifecycle['passed']==lifecycle['total']
 assert all(row['passed'] for row in controlled['faults']) and all(s['failures']==0 for s in load['summary'])
 assert expiry['expired_ignored'] and expiry['revoked_ignored'] and expiry['active_loaded']
 delta=paired_ci([row['metrics']['text_title_genres']['Recall@20']-row['metrics']['id_order_no_cold_signal']['Recall@20'] for row in cold['per_user']])
 rows=ledger['attempts'];pi=sum(x['accounted_input_tokens'] for x in rows);po=sum(x['accounted_output_tokens'] for x in rows);cost=pi*.30/1e6+po*1.20/1e6
 tool_attempts=sum(x.get('tool_count',0) for r in live['rows'] for x in r['response']['trace'] if x.get('tool')=='llm');accepted=sum(1 for r in live['rows'] for x in r['response']['trace'] if x.get('tool') in ['recommend_movies','movie_details','finish'] and x.get('ok'))
 repeated=0
 for r in live['rows']:
  calls=[json.dumps([x['tool'],x.get('arguments')],sort_keys=True) for x in r['response']['trace'] if x.get('tool') in ['recommend_movies','movie_details','finish']];repeated+=len(calls)-len(set(calls))
 report=['# 最终验收与评测结果（文本版 V4）','', '日期：2026-10-18。人工模板/合成任务，不是真实用户行为；所有逐任务和失败/排除保留。离线推荐、对话回归、真实LLM和服务指标分别报告。','', '## 暖启动推荐：固定全量候选','',f"合格用户 {warm['eligible_users']}/{warm['heldout_users']}，排除 {warm['excluded_users']}；候选分母 {warm['catalogue_denominator']}，每用户排除其训练已评分项。标签为官方评分>=4，未观测采样不是曝光负样本。",'', '| 方法 | Recall@20 [95%用户bootstrap] | NDCG@20 | 覆盖率@20 | 类型多样性@20 | 失败 |','|---|---|---:|---:|---:|---:|']
 for name,x in warm['methods'].items():
  r=x['Recall@20'];report.append(f"| {name} | {r['mean']:.4f} [{r['ci95'][0]:.4f}, {r['ci95'][1]:.4f}] | {x['NDCG@20']['mean']:.4f} | {x['coverage@20']:.4f} | {x['genre_diversity@20']['mean']:.4f} | {x['failures']} |")
 report+=['','神经路线未超过ItemCF，不宣称模型效果提升。这里的YT100→DeepFM不是完整在线多通道/重排；没有真实CTR、线上A/B或人工满意度。更多K值、配对差值及排除原因在原summary/per-user文件。','', '## 独立冷启动文本实验','',f"按固定SHA256规则隔离 {cold['cold_catalogue']} 部，移除 {cold['removed_train_interactions']} 条训练交互；合格用户 {cold['eligible_users']}/{cold['heldout_users']}，排除 {len(cold['excluded_users'])}，失败 {cold['failures']}。每用户同一个368部冷候选池，不能与暖启动表混报。",'', '| 方法 | Recall@20 [95%用户bootstrap] | NDCG@20 | 覆盖率@20 |','|---|---|---:|---:|']
 for name,x in cold['summary'].items():
  r=x['Recall@20'];report.append(f"| {name} | {r['mean']:.4f} [{r['user_bootstrap_95'][0]:.4f}, {r['user_bootstrap_95'][1]:.4f}] | {x['NDCG@20']['mean']:.4f} | {x['coverage_at20']:.4f} |")
 report+=['',f"文本减无信号基线的配对Recall@20差值 {delta['mean']:.4f}，描述性95%用户bootstrap [{delta['bootstrap_95'][0]:.4f}, {delta['bootstrap_95'][1]:.4f}]（2000次，seed20261018）。",'', '冷物品行为全部隔离后，热门/ItemCF在冷候选上均无观测信号，因此固定ID排序是明确的弱基线；它不是强内容模型。暖训练神经checkpoint未用于冷启动。内容只含官方标题/类型，元数据快照不证明历史时点可用性。text+image臂未运行：海报许可与语义ID映射未核验，新对话页不展示它们；不声称多模态能力。','', '## 对话、记忆与压缩','', '| 检查 | 通过/分母 | 解释 |','|---|---:|---|']
 for key,label in [('single','单轮'),('multi','多轮'),('checks','记忆/幂等/压缩服务检查')]:
  s=agent['summary'][key];report.append(f"| {label} | {s['passed']}/{s['total']} | Wilson95% [{s['wilson_95'][0]:.3f}, {s['wilson_95'][1]:.3f}] |")
 report += [f"| 记忆纠正/删除生命周期补充 | {lifecycle['passed']}/{lifecycle['total']} | 合成访客，未改人类用户偏好 |",'| 过期/撤销/有效偏好隔离 | 3/3 | 隔离事务回滚 |',f"| 真实DeepSeek对话HTTP | {live['passed']}/{live['total']} | 小样本功能验收；Wilson95% [{wilson(live['passed'],live['total'])[0]:.3f}, 1.000] |",f'| 真实工具参数结构与预期约束 | {accepted}/{tool_attempts} | 原3轮；重复调用{repeated}次 |','', '60单轮=10模板族×6变体，30多轮=6模板族×5变体；样本相关，区间只是描述，不能代表开放域语言准确率。失败也留在分母，本次任务集未出现失败。','', f"同初始目录、访客画像、排序器和top6的42例，普通无条件满足全部指定约束 {controlled['summary']['ordinary']['passed']}/42，条件驱动 {controlled['summary']['condition_driven']['passed']}/42。无条件系统本来未接收这些需求，因此仅证明条件改变了实际筛选，不表示推荐相关性从0提升至100%。",'',f"30组长期否定偏好成对任务：有记忆 {memory['summary']['on']['satisfied']}/30（Wilson95% {memory['summary']['on']['wilson95']}），无记忆 {memory['summary']['off']['satisfied']}/30（{memory['summary']['off']['wilson95']}）；{memory['changed_rankings']}/30列表改变，失败{memory['failures']}。这是约束满足率，不是用户喜好质量。初始恐怖/惊悚单例结果完全相同，仍保留在AGENT_HTTP_EVAL。",'', '压缩真实模型配对：相同12轮合成历史、同画像/候选/提示词与当前请求；结构化摘要+最近4轮 vs 全历史。两臂关键事实各3/3、原文定位各3/3，最终电影ID一致。只有1组成对任务，不能宣称普遍无损或任务提升。']
 ledger_by_id={a['request_id']:a for a in rows}
 for arm in compression['rows']:
  response=arm['response'];ids=[x['provider_request_id'] for x in response['trace'] if x.get('tool')=='llm'];tokens=sum(ledger_by_id[i]['accounted_input_tokens'] for i in ids)
  report.append(f"- {'压缩' if arm['compressed'] else '完整历史'}：发送历史结构 {response['history_characters']['sent']} 字符，原历史 {response['history_characters']['original']} 字符；该臂两模型轮累计实际输入 {tokens} tokens（包含系统、工具schema及结果，不等于历史字符）。")
 report+=['','短会话摘要可能增加长度，不把字符比例冒充token节省率。原始离线长历史示例的6382→2574字符保留在原报告。','', '## 可靠性与服务：历史V3离线压测','',f"模拟故障 {sum(x['passed'] for x in controlled['faults'])}/{len(controlled['faults'])}：召回通道、缓存、排序、LLM不可用/429、超时、熔断和半开恢复；实际Redis停止期间3/3降级成功，恢复后无降级且健康。有限重试不重复写反馈，消息与反馈重放检查通过。",'', '| 客户端 | 测量请求成功/全部 | P50 ms | P95 ms | 实际总rps |','|---:|---:|---:|---:|---:|']
 for row in load['summary']:report.append(f"| {row['clients']} | {row['successes']}/{row['attempts']} | {row['p50_ms']:.2f} | {row['p95_ms']:.2f} | {row['realized_rps']:.1f} |")
 report+=['','每组30秒预热+120秒测量，固定总5rps、每客户端独立访客token与owner（单进程及模型排序锁仍存在）、fresh会话、三种固定需求、离线chat路径，无LLM；预热不计入分位数。每组成功率Wilson95% [0.9936,1]。原始1500条含预热记录保留；哈希对应归档V3源码，不是当前V4代码的并发性能。V4当前测量见COMPLETE_V4_RESULTS。Ryzen7 6800H/16线程、主机RAM15.2GB、Windows/WSL2、CPU推理、容器TF线程4/2。这不是饱和吞吐量；普通首页多路模型路径、外部模型耗时不能套用这些延迟。分位数是本次测量，不做跨机器保证。','', '## API费用、交付与尚缺输入','',f"截至打包：请求 {len(rows)}/30，实际已记输入 {pi}、输出 {po} tokens；按官方高峰输入缓存未命中0.30美元/百万与输出1.20美元/百万保守估算 ${cost:.6f}，上限$0.10。该数不是支付账单；后续演示继续累计，同一持久账本不重置。模型别名由服务商控制，未虚构固定权重版本。",'', '当前交付为可运行文本版V4。未交付：图像表征与图文对照、人工主观评分、真实用户/线上A-B。人工表在eval/HUMAN_REVIEW.md；其缺失不被补造。上游前端安全依赖告警仍待专项处理，本机演示不等于生产安全验收。独立展示包包含源码增量、说明、任务和结果，不含密钥/原始数据/完整模型/依赖缓存。']
 if (ROOT/'reports/AGENT_NATURAL_EVAL.json').exists():
  natural=read('reports/AGENT_NATURAL_EVAL.json');s=natural['summary']
  report[3:3]=['**历史自然表达基线：'+str(s['task_successes'])+'/'+str(s['tasks'])+'通过，另7题未执行；该基线保存修复前缺陷。修复后新批次与降级分母见PHASE2_RESULTS.md，不能混报为同一测试提升。**','']
  report+=['','## 新增路线诊断与自然表达评测','', '训练期两折滚动基线与已见validation的召回/同候选排序拆解已完成；无test数组读取、无神经重训或部署。真实模型自然表达首批2/7通过，失败逐条保存。任务与期望由开发助手合成，未独立人工复核，来源元数据更正保留原冻结快照。详细结果与缺陷见DIAGNOSIS_RESULTS.md，不把开发诊断当新测试提升。']
 if (ROOT/'reports/EXCLUSION_V3_RESULTS.md').exists():report[3:3]=['**历史V3：用户来源排除治理已部署，11个合成场景22轮真实工具循环完成，详见EXCLUSION_V3_RESULTS.md。旧V2结果作为历史保留。**',''];report+=['','---','',(ROOT/'reports/EXCLUSION_V3_RESULTS.md').read_text(encoding='utf-8')]
 if (ROOT/'reports/PHASE2_RESULTS.md').exists():report[3:3]=['**历史V2修复及扩展验收：见 PHASE2_RESULTS.md；30场景60轮业务检查通过，但仅46/54非澄清轮由真实工具循环完成，8轮降级。**',''];report+=['','---','',(ROOT/'reports/PHASE2_RESULTS.md').read_text(encoding='utf-8')]
 if (ROOT/'reports/COMPLETE_V4_RESULTS.md').exists():report[3:3]=['**当前V4：已完成内容贡献、实际浏览器交互、端到端与逐轮成本测量；首次17/20场景完成，恢复后20/20；36轮含LLM浏览器P95=2.41秒。主观人工评议待填，详见COMPLETE_V4_RESULTS.md。**',''];report+=['','---','',(ROOT/'reports/COMPLETE_V4_RESULTS.md').read_text(encoding='utf-8')]
 write(ROOT/'reports/FINAL_RESULTS.md','\n'.join(report)+'\n')
 write(ROOT/'reports/PAIRED_COLD_DIFFERENCE.json',json.dumps(delta,indent=2))
 return {'warm_eligible_users':warm['eligible_users'],'cold_eligible_users':cold['eligible_users'],'offline_single':agent['summary']['single'],'offline_multi':agent['summary']['multi'],'load':load['summary'],'api_requests':len(rows),'conservative_api_cost_usd':cost,'new_campaign':{'attempts':len(read('reports/DEEPSEEK_NATURAL_V2_LEDGER.json')['attempts']),'conservative_cost_usd':sum(a['accounted_input_tokens']*.3/1e6+a['accounted_output_tokens']*1.2/1e6 for a in read('reports/DEEPSEEK_NATURAL_V2_LEDGER.json')['attempts']),'max_attempts':240,'budget_usd':.5},'natural_v2':read('reports/AGENT_NATURAL_V2_LIVE.json')['summary'],'exclusion_v3':read('reports/AGENT_EXCLUSION_V3_LIVE.json')['summary'],'complete_v4':read('reports/COMPLETE_V4_RESULTS.json')['summary']}

def copy(source,target):
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)

def main():
 summary=build_report()
 if OUT.exists() and not (OUT/'.cineagent-showcase').exists():raise RuntimeError('Refuse to overwrite unknown showcase directory')
 OUT.mkdir(exist_ok=True);write(OUT/'.cineagent-showcase','Generated review package; no dataset/model cache/credentials.\n')
 docs=['README.md','REPRODUCE.md','EVAL_SPEC.md','ARCHITECTURE.md','CONTRIBUTIONS.md','DEMO.md','RESUME.md','IMPROVEMENTS.md']
 for name in docs:copy(ROOT/name,OUT/name)
 for path in (ROOT/'eval').glob('*'):
  if path.is_file():copy(path,OUT/'eval'/path.name)
 for path in (ROOT/'scripts').iterdir():
  if path.is_file() and path.suffix in ['.py','.ps1']:copy(path,OUT/'scripts'/path.name)
 for name in ['compose.yaml','backend.Dockerfile','requirements.in','requirements.lock.txt','eval_protocol.json']:copy(ROOT/'configs'/name,OUT/'configs'/name)
 copy(ROOT/'.dockerignore',OUT/'.dockerignore');copy(ROOT/'.gitignore',OUT/'.gitignore')
 copy(ROOT/'配置DeepSeek密钥.cmd',OUT/'配置DeepSeek密钥.cmd')
 reports=['FINAL_ACCEPTANCE.json','FINAL_RESULTS.md','REC_RESULTS.md','MODEL_MANIFEST.json','REC_RUN_MANIFEST.json','DATA_DOWNLOAD.json','MOVIELENS_REFERENCE.json','METADATA_OFFICIAL_LINKS.json','AGENT_HTTP_EVAL.json','AGENT_CONTROLLED_EVAL.json','MEMORY_PAIRED_EVAL.json','MEMORY_LIFECYCLE.json','MEMORY_EXPIRY_CHECK.json','DEEPSEEK_HTTP_EVAL.json','DEEPSEEK_TRIAL_LEDGER.json','DEEPSEEK_BUDGET_CHECKS.json','COMPRESSION_LIVE_EVAL.json','COLD_RESULTS.json','PAIRED_COLD_DIFFERENCE.json','REDIS_RECOVERY.json','ONLINE_HTTP_ACCEPTANCE.json','SERVICE_LOAD.json','CHAT_ACCEPTANCE.png','BACKEND_IMAGE_ID.txt']
 for name in reports:copy(ROOT/'reports'/name,OUT/'reports'/name)
 for name in ['DIAGNOSIS_RESULTS.md','AGENT_NATURAL_EVAL.json','AGENT_NATURAL_TASKS.json','AGENT_NATURAL_PROVENANCE.json','PHASE2_RESULTS.md','AGENT_REPAIR_OFFLINE.json','AGENT_REPAIR_LIVE.json','AGENT_NATURAL_V2_TASKS.json','AGENT_NATURAL_V2_OFFLINE.json','AGENT_NATURAL_V2_LIVE.json','AGENT_HTTP_V2_EVAL.json','DEEPSEEK_NATURAL_V2_LEDGER.json','API_CAMPAIGN_V2_APPROVAL.json','NEGOTIATION_EVIDENCE_CHECK.json','NEGOTIATION_UI.png','EXCLUSION_V3_RESULTS.md','AGENT_EXCLUSION_V3_TASKS.json','AGENT_EXCLUSION_V3_LIVE.json','EXCLUSION_GUARD_REPLAY.json','RESUME_EVIDENCE_NOTES.md','COMPLETE_V4_RESULTS.md','COMPLETE_V4_RESULTS.json','COMPLETE_V4_TASKS.json','COMPLETE_V4_BROWSER.json','COMPLETE_V4_APPROVAL.json','COMPLETE_V4_BUDGET_CHECK.json','COMPLETE_V4_OFFLINE.json','CHAT_TEXT_ABLATION_V4.json','COMPLETE_V4_UI.png','LATENCY_AUDIT_V4.json','LATENCY_AUDIT_V4.md']:
  if (ROOT/'reports'/name).exists():copy(ROOT/'reports'/name,OUT/'reports'/name)
 for path in (ROOT/'artifacts/content_contribution_v4').glob('*.json'):copy(path,OUT/'results/content_contribution_v4'/path.name)
 for path in (ROOT/'reports/source_snapshots/conversation-v3').glob('*.py'):copy(path,OUT/'evidence/runtime_v3'/path.name)
 for path in (ROOT/'artifacts/ablation_v2').glob('*.json'):copy(path,OUT/'results/ablation_v2'/path.name)
 for path in (ROOT/'reports/archive_v2').glob('*.json'):copy(path,OUT/'reports/archive_v2'/path.name)
 for path in (ROOT/'reports/source_snapshots/conversation-v2').glob('*'):
  if path.is_file():copy(path,OUT/'evidence/runtime_v2'/path.name)
 for path in (ROOT/'reports/archive_v1').glob('*.json'):copy(path,OUT/'reports/archive_v1'/path.name)
 for path in (ROOT/'artifacts/diagnostics_v1').glob('*.json'):copy(path,OUT/'results/diagnostics_v1'/path.name)
 for path in (ROOT/'eval/archive').glob('*.json'):copy(path,OUT/'eval/archive'/path.name)
 # Preserve complete derived offline predictions/metrics, not the raw interaction dataset.
 for name in ['test_Popular_ItemCF_YouTubeDNN_YT100_DeepFM_summary.json','test_Popular_ItemCF_YouTubeDNN_YT100_DeepFM_per_user.jsonl','test_Popular_ItemCF_YouTubeDNN_YT100_DeepFM_excluded.json','PREPARE.json','PROTOCOL_CHECKS.json','TRAINING.json']:copy(ROOT/'artifacts/rec_v1'/name,OUT/'results/rec_v1'/name)
 copy(ROOT/'artifacts/content_v1/COLD_SPLIT.json',OUT/'results/content_v1/COLD_SPLIT.json')
 git=['git','-C',str(ROOT/'upstream')]
 head=subprocess.check_output(git+['rev-parse','HEAD'],stderr=subprocess.PIPE).decode().strip();assert head==BASE
 patch=subprocess.check_output(git+['diff','--binary','--no-ext-diff'],stderr=subprocess.PIPE);patch_path=OUT/'source/upstream.patch';patch_path.parent.mkdir(exist_ok=True);patch_path.write_bytes(patch)
 subprocess.run(git+['apply','--reverse','--check',str(patch_path)],check=True,capture_output=True)
 added=[]
 for path in (ROOT/'upstream/web_project/backend/app/cineagent').glob('*.py'):added.append(path)
 added.append(ROOT/'upstream/web_project/frontend/src/views/Chat.vue')
 for path in added:copy(path,OUT/'source/new_files'/path.relative_to(ROOT/'upstream'))
 write(OUT/'UPSTREAM_NOTICE.md',f'FunRec: https://github.com/datawhalechina/fun-rec\nPinned commit: {BASE}\nRoot README declares CC BY-NC-SA 4.0; no standalone LICENSE was found in the audited checkout. Preserve attribution and clarify scope before public redistribution. Metadata/poster permissions are separate; package contains neither raw data nor posters. New functionality is incremental; see CONTRIBUTIONS.md.\n')
 write(OUT/'START_HERE.md','''# CineAgent 文本版 V4 展示入口

本机页面：http://127.0.0.1:13000/chat；普通首页：http://127.0.0.1:13000。

1. 先读 DEMO.md，演示多轮条件、偏好记忆、反馈与降级。
2. 看 reports/CHAT_ACCEPTANCE.png 和 reports/FINAL_RESULTS.md；原始逐任务与逐用户结果保留，不能只挑成功样本。
3. 看 ARCHITECTURE.md、CONTRIBUTIONS.md、RESUME.md，区分上游复用、最小修复与个人增量。
4. REPRODUCE.md给出从原始数据到服务的命令；源码增量为 source/upstream.patch 与 source/new_files，需配合固定上游commit。

本文件夹没有API key、数据库密码、原始数据、完整模型或依赖缓存，不能直接离线双击替代完整项目。实际运行产物在本机主项目目录；迁移机器须按说明获取数据并训练。图像理解与人工主观评分未完成；这是明确的文本内容交付范围。不要将模板回归或弱冷启动基线写成真实用户/CTR提升。
''')
 source_paths=sorted([p for p in (ROOT/'upstream/web_project/backend/app/cineagent').glob('*.py')]+[ROOT/'upstream/web_project/frontend/src/views/Chat.vue'])
 manifest={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'version':'text-v4','upstream_commit':BASE,'upstream_patch_sha256':sha(patch_path),'runtime_source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in source_paths},'protocol_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in [ROOT/'configs/eval_protocol.json',ROOT/'eval/agent_tasks.json',ROOT/'eval/memory_tasks.json',ROOT/'eval/compression_live_task.json',ROOT/'eval/agent_exclusion_v3.json',ROOT/'eval/complete_v4.json',ROOT/'eval/COMPLETE_V4_SPEC.json',ROOT/'EVAL_SPEC.md']},'data_and_models_reference':{'DATA_DOWNLOAD.json':sha(ROOT/'reports/DATA_DOWNLOAD.json'),'MODEL_MANIFEST.json':sha(ROOT/'reports/MODEL_MANIFEST.json'),'REC_RUN_MANIFEST.json':sha(ROOT/'reports/REC_RUN_MANIFEST.json')},'prompt_version':'movie-tools-v3; source api.py hash above','evaluation_summary':summary,'limitations':['V4 synthetic sequential browser tasks; first3 UI observations failed and recovered; human subjective review pending','text only; no image arm','authored/synthetic dialogues','human review pending','no production security acceptance']}
 write(ROOT/'reports/FINAL_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2));copy(ROOT/'reports/FINAL_MANIFEST.json',OUT/'reports/FINAL_MANIFEST.json')
 # Use secret values in memory solely to detect accidental inclusion. Never print values.
 secrets=[]
 config=ROOT/'configs/local-secrets/deepseek.json'
 if config.exists():secrets.append(read('configs/local-secrets/deepseek.json').get('api_key','').encode())
 for line in (ROOT/'configs/.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   key,value=line.split('=',1)
   if key in ['POSTGRES_PASSWORD','SECRET_KEY','DEMO_PASSWORD'] and value:secrets.append(value.strip().encode())
 forbidden=[];leaks=[];files=[]
 for path in sorted(OUT.rglob('*')):
  if not path.is_file():continue
  rel=path.relative_to(OUT).as_posix()
  if path.name=='.env' or any(part in ['local-secrets','node_modules','__pycache__','.git'] for part in path.relative_to(OUT).parts) or path.suffix in ['.pkl','.zip','.h5','.npy','.npz']:forbidden.append(rel)
  if any(s and s in path.read_bytes() for s in secrets):leaks.append(rel)
  if path.name not in ['PACKAGE_MANIFEST.json','PACKAGE_CHECK.json']:files.append({'path':rel,'bytes':path.stat().st_size,'sha256':sha(path)})
 assert not forbidden and not leaks,'Package content policy failed (credential values withheld)'
 check={'passed':True,'files':len(files),'bytes':sum(f['bytes'] for f in files),'credential_matches':0,'forbidden_paths':forbidden,'raw_data_or_full_models_included':False,'patch_reverse_check_passed':True}
 write(OUT/'PACKAGE_MANIFEST.json',json.dumps(files,ensure_ascii=False,indent=2));write(OUT/'PACKAGE_CHECK.json',json.dumps(check,indent=2));write(ROOT/'reports/DELIVERY_CHECK.json',json.dumps(check,indent=2))
 print(json.dumps({'delivery':str(OUT),'package':check,'evaluation':summary},ensure_ascii=False))
if __name__=='__main__':main()





