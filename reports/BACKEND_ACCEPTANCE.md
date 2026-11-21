# 后端改造最终验收

本轮定位为Python后端与推荐业务；保留单Agent入口，不增加多Agent/Harness/LoRA。普通页面不调用LLM。本轮没有新增付费模型调用。

## 功能与自动化

- 正式服务 pytest：32/32；隔离PG schema、Redis DB3和独立ES索引的CI等价流程同样32/32。
- 业务/缓存回归21项通过；8并发回源使用模拟计算与真实Redis，计算1次；锁归属、有限等待、过期恢复通过。
- 登录、收藏/取消、看过/取消、评分/删除、片单分页筛选和管理员索引任务已通过真实浏览器验证。截图使用合成账号，随后清理。
- 详情缓存冷/热查询分别2/1条SQL；保留数据库版本检查，不声称零SQL。
- 对话“看过”反馈与在线业务表/首页推荐联动验证通过，原排除参数回放8例和8项不变量通过，无外部模型调用。

## 固定负载结果

计时边界：后端容器内urllib发起HTTP至完整JSON解析；不含nginx、浏览器DOM、LLM。1个合成账号、20个固定文本查询、limit=6、同一模型/候选目录。20次预热不计入；闭环客户端、单次本机共享主机运行，不是公网SLA/最大容量。

| 条件 | 成功/请求 | P50 ms | P95 ms | 请求/秒 | 测量时长 s |
|---|---:|---:|---:|---:|---:|
| cold_c1 | 2000/2000 | 31.81 | 34.67 | 30.82 | 64.88 |
| warm_c1 | 2000/2000 | 4.58 | 6.13 | 212.78 | 9.4 |
| warm_c8 | 16000/16000 | 30.97 | 38.91 | 252.36 | 63.4 |

冷/热两臂同序列返回的电影ID一致。并发8的单请求时延高于顺序热缓存，不能拿顺序P95代表并发P95。逐请求结果、失败分母与47个相关app源码哈希在BACKEND_LOAD_FINAL.json；V1短烟测、V2及共享主机/修复前运行单独保留，不混成一次实验。

## 实际中断与恢复

- 暂停ES并观察running后实际杀掉Worker，恢复服务后，同一任务第2次执行成功，约78.28秒；包含75秒租约等待，不宣传瞬时恢复。
- 实际停止Redis，PG继续接收任务；恢复后完成。补充验证停止Redis期间个性化推荐回退并返回3部电影，恢复后索引任务完成。
- 可控依赖失败在第3次执行后进入failed；重放终态任务不增加执行次数。
- 任务投递至少一次，固定文档ID upsert和PG状态/claim保证业务幂等，不承诺消息exactly-once。

## 迁移与资源

- Alembic对现有数据库及隔离空schema各验证；隔离环境重复upgrade head成功，不drop/reset训练数据。
- 复用现有TensorFlow基础镜像，仅添加固定版本的Celery/Alembic/pytest依赖层；Worker单并发、512MiB上限，派发器192MiB上限。
- 观测到Worker约120MiB、派发器约73MiB；是当时快照，不是峰值内存。原PG/Redis/ES继续复用。

## 证据与限制

- BACKEND_PYTEST.xml / BACKEND_CI_LOCAL.xml / BACKEND_BEHAVIOR_V1.json / CACHE_COALESCING_V1.json。
- BACKEND_REAL_FAULTS.json / BACKEND_CHAT_BRIDGE.json / BACKEND_AGENT_GUARD_REPLAY.json。
- BACKEND_REPAIR_NOTES.json保留首次失败与修复原因，未把失败尝试抹除为首轮全通过。
- GitHub云端Actions状态以BACKEND_GITHUB_CI.json为准；本地通过不等于云端已通过。
- 本机回环部署，关机/休眠期间不可访问；未部署公网服务器。新机器说明完整，但未在第二台电脑重新下载/训练。
- 旧推荐/Agent论文式评测仍保留其原数据协议，本轮后端指标不能替代它们；没有新增推荐准确率或真实CTR提升声明。

公开包保留最终完整逐请求结果；此前重复成功压测提供 BACKEND_LOAD_HISTORY_SUMMARIES.json（摘要与原文件哈希），完整原件在作者工作区保留。没有删除失败任务来提高分母。

## GitHub 云端 CI

实际云端流程已通过，包含真实PG/Redis/ES服务、Alembic和pytest执行步骤。[运行记录](https://github.com/miaomiao0227/cineagent/actions/runs/44919456004)。云端使用合成片库，不下载MovieLens/模型，不调用LLM；不替代本机完整推荐链路验收。
