import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
v3=read('reports/AGENT_EXCLUSION_V3_LIVE.json');v2=read('reports/AGENT_NATURAL_V2_LIVE.json');replay=read('reports/EXCLUSION_GUARD_REPLAY.json');ledger=read('reports/DEEPSEEK_NATURAL_V2_LEDGER.json')['attempts']
ids={s['id'] for s in read('eval/agent_exclusion_v3.json')['scenarios'] if s.get('evaluation_role')=='known_failure_replay'}
prior=[t for t in v2['per_turn'] if t['scenario_id'] in ids and t['turn']==2];after=[t for t in v3['per_turn'] if t['scenario_id'] in ids and t['turn']==2];new=[t for t in v3['per_turn'] if t['scenario_id'].startswith('NEW')]
assert len(prior)==len(after)==8;assert hashlib.sha256((ROOT/'eval/agent_exclusion_v3.json').read_bytes()).hexdigest()==v3['task_sha256']
newrows=ledger[len(v3['ledger_before']['attempts']):];cost=lambda rows:sum(a['accounted_input_tokens']*.3/1e6+a['accounted_output_tokens']*1.2/1e6 for a in rows)
guards=[t for row in v3['per_turn'] for t in row['response']['trace'] if t.get('tool')=='constraint_guard']
assert all(any(t.get('tool')=='finish' for t in row['response']['trace']) for row in v3['per_turn'])
report=f'''# V3：用户来源约束与工具参数修复

## 实现

模型曾把last_results（展示列表）误当成用户已看/不喜欢。新版调整提示词及请求级工具schema：排除项只能来自服务端state.exclude_ids；空名单限制maxItems=0，非空名单限制items.enum。增加确定性参数投影：合法但缺少用户依据的额外ID被剔除并记录原始参数、有效参数及原因，其他合法约束继续执行；错误类型、不存在的ID、过长列表仍拒绝。严格validated_constraints未放宽，服务端排除项不会因模型省略而丢失。

这是工具治理，不是模型训练、Agentic RL或自进化。本轮没有分别消融提示词/schema/投影，不能单独归因其中一项的收益。

## 离线验证

重放历史8次错误参数，采用明确脚本化finish回应、真实本地推荐引擎：{replay['replays_passed']}/{replay['replays_total']}通过；另8项输入/来源/schema不变量检查通过。这是离线轨迹回放，不冒充API实验。

## 真实API验证

执行前冻结8个历史失败场景与3个新合成探针，共11场景22轮；保留原任务及全部结果，批次中未改源码或oracle。

- 旧8个问题轮次：工具完成{sum(t.get('live_loop',False) for t in prior)}/8，降级{sum(bool(t['response']['degradation']) for t in prior)}/8。
- V3相同8个问题轮次：工具完成{sum(t.get('live_loop',False) for t in after)}/8，降级{sum(bool(t['response']['degradation']) for t in after)}/8。
- 包含前置轮的全批次：11/11场景、22/22轮业务检查通过，22/22轮真实工具循环完成，0次降级，均有finish记录。
- 新3个合成场景：{sum(t['passed'] for t in new)}/{len(new)}轮通过，检查“只是浏览、保留候选、展示不等于已看”的表达。
- 本批次参数修正事件{len(guards)}次：模型此次遵守schema/提示约束。投影分支由离线错误轨迹重放验证，不能声称真实批次触发8次自动修正。

题目与oracle由开发助手编写，8场景属于已知开发回归，新3场景仍非独立人工验收。不能把22/22解释为真实用户总体成功率100%；服务商模型别名权重未由本项目固定。原V2结果46/54、8次降级及当时源码快照保留。

## 费用与部署

本次新增{len(newrows)}次API，按高峰价保守估算${cost(newrows):.7f}。追加实验账本累计{len(ledger)}/240次、${cost(ledger):.7f}/$0.50；原25次试跑账本不变。追加实验累计89个用户轮次，未超先前60至90轮规模。费用不是平台支付账单。

部署后HTTP模板回归60/60单轮、30/30多轮及14/14记忆服务检查通过；协商/证据6项检查通过。重启预热期间曾在获取测试访客前收到502，待ready门禁确认后才开始正式测量；启动请求未计为测量成功请求。

## 简历

RESUME.md只保留项目名称、简介、技术栈及STAR主要工作，突出推荐链路、用户来源约束、偏好记忆、约束协商与可靠性。详细对照和限制保留技术报告及RESUME_EVIDENCE_NOTES.md，不放入简历正文。

证据：AGENT_EXCLUSION_V3_LIVE.json、AGENT_EXCLUSION_V3_TASKS.json、EXCLUSION_GUARD_REPLAY.json。原源码：source_snapshots/conversation-v2；现版本movie-tools-v3/conversation-v3。
'''
(ROOT/'reports/EXCLUSION_V3_RESULTS.md').write_text(report,encoding='utf-8');print(json.dumps({'new_calls':len(newrows),'new_cost':cost(newrows),'campaign_calls':len(ledger),'campaign_cost':cost(ledger),'guard_events':len(guards)}))
