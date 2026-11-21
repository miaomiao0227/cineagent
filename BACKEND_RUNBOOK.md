# CineAgent 后端运行与验收

## 本机运行

在本项目根目录执行 `./scripts/project.ps1 up`。启动依次检查基础设施、运行 Alembic、启动 API/Worker/派发器/前端。原训练数据库与部署模型沿用；不删除卷，不修改 psyagent。

- 首页： http://127.0.0.1:13000/
- 我的片单： http://127.0.0.1:13000/library （先注册登录）
- 后台索引任务： http://127.0.0.1:13000/admin/jobs （仅管理员）
- 对话： http://127.0.0.1:13000/chat
- API： http://127.0.0.1:18000/docs

管理员使用显式本机命令创建，不允许网页自行提权。`docker compose --env-file configs/.env -f configs/compose.yaml exec backend python /checks/provision_admin.py --email admin@cineagent.local`。初始密码取自本机 configs/.env 的 DEMO_PASSWORD，不打印、不进入 Git。已有普通账号不会被这个命令提升或改密码。

## 新机器

先按 REPRODUCE.md 完成固定数据和模型准备。`scripts/app.ps1 build` 先构建固定依赖的 cineagent-base:local，再构建 backend.runtime.Dockerfile 的增量层；backend-extra.lock.txt 固定 Celery/Alembic/pytest 及其新增依赖。首次需要网络，日常运行无需重新训练。上线之前必须自行配置凭据、TLS和访问策略；本机版本仅绑定回环地址。

`alembic upgrade head` 只新增/接管独立业务表，原始表不 drop/reset；已存在的业务表采用 checkfirst。禁止无数据保全方案的破坏性降级。实际完成现有库和隔离空 schema 的重复升级验证，尚未在第二台电脑全量重建。

## 在线数据与训练隔离

- 收藏/看过/评分保存在 online_behaviors；评分为1–10分，可清除。
- online_behavior_versions 在同一事务中更新。用户行锁串行化同一用户的写入，重复相同状态不增加版本。
- 原 ratings 表仅保留训练期 MovieLens 数据；全局历史评分统计不随在线评分改变。
- 登录首页及电影详情的个性化推荐使用 /api/me/recommendations；身份由 JWT 决定，不接受客户端 user_id。对话也排除登录用户看过的电影。
- 新增收藏/高评分仅作为有界内容种子和偏好使用，不自动进入训练或评测标签。

## 缓存

推荐缓存键包含用户/行为版本/模型策略版本/limit/query，TTL120秒。用户写入先提交数据库版本，后续请求自然命中新键；旧值只会留到过期。并发回源使用 SET NX EX、随机token和Lua归属校验，最多等待约600ms；仍未生成返回503与Retry-After，不无限阻塞。Redis故障时退回本地计算，降级结果不缓存。

电影详情缓存TTL300秒，缺失结果TTL15秒；描述修改与 movie_cache_versions 更新在同一事务内，新增电影创建初始版本并写入索引任务。缓存命中仍查询数据库版本，明确用一次数据库读取换取一致性，不宣传零SQL。

## 索引任务

管理员提交1–100个真实电影ID与request_id；PostgreSQL事务创建唯一(owner_id,request_key)记录，重复同载荷返回同任务，不同载荷返回409。派发器每2秒扫描，FOR UPDATE SKIP LOCKED 支持多实例。Redis DB2传递JSON任务消息，PostgreSQL保存状态。

Worker单并发，不加载TensorFlow。任务45秒软超时/55秒硬超时，75秒执行租约，最多3次执行，失败按2^attempt秒退避。未派发/派发失败留在数据库；派发成功但进程中断可能重复投递，Worker状态/租约/claim约束和固定文档ID upsert 保证业务幂等。投递语义是至少一次，不宣称消息绝不重复或exactly-once。终态失败由管理员新建任务显式重试。

## 观测

响应X-Request-ID、JSON请求日志、后台 /api/admin/metrics。日志记录路由模板、方法、状态与耗时，不记录Authorization、请求体、查询串或账单。指标是当前进程最多2000条最近样本，无跨进程聚合承诺。/ready表示模型就绪，/health检查数据库/Redis/ES。

## 验收命令

在容器内运行：

```sh
pytest -q -p no:cacheprovider /app/tests --junitxml=/trial-ledger/BACKEND_PYTEST.xml
python /checks/check_behavior_v1.py
python /checks/check_cache_coalescing.py
python /checks/check_backend_ci_isolated.py
python /checks/backend_load.py
```

后三项有合成数据/模拟计算或压力请求，具体边界见BACKEND_EVAL_SPEC.md。实际中断验证只停止本项目worker/Redis，并用finally恢复；不要在面试演示同时运行。真实故障记录与逐请求压测位于 reports/BACKEND_*.json；合成测试账号在finally删除。

GitHub Actions配置位于 .github/workflows/backend.yml，使用独立PG/Redis/ES与合成电影，不下载训练数据和模型、不使用LLM密钥。本地隔离等价流程已运行，云端状态单独记录。

日常DeepSeek配置仍只在本机 local-secrets，独立账本不放入公开包。daily_usage.example.json默认禁用，公共克隆不继承作者的调用额度。
