> **公开仓库版：** 已包含运行源码；下方本机测量是来源说明。历史build_delivery/check_delivery用于作者维护的增量展示包，依赖原上游Git工作区；新克隆机器的运行按本文件数据/训练/服务流程，不需调用这两个维护脚本。

# 复现与运行说明

## 现有本机产物直接运行

PowerShell 7，Docker Desktop Linux engine/WSL2 已运行。本机所有项目路径如下；只在本项目目录操作，不运行全库reset/flush。

```powershell
Set-Location cineagent
.\scripts\project.ps1 status
.\scripts\project.ps1 up
```

等待模型预热就绪后打开 http://127.0.0.1:13000/chat 。普通首页在根路径，API /docs 在18000端口。默认离线模式不收费；DeepSeek模式仅在选择后使用本机已配置的官方接口和持久预算。改密钥用根目录“配置DeepSeek密钥.cmd”，不要直接把密钥写入命令行。停止应用用 project.ps1 stop，不删卷。

## 从原始文件重建（新机器或新的空目录）

以下是完整命令协议，不代表已在第二台空机器再次执行过。当前机器已实际完成原始数据到服务链路，最近补齐的下载/核验驱动用已有文件验证了复用和结果一致性；全量下载与训练没有为文档重复执行。先检查目标目录不存在或确认内容，不能覆盖其他工作。

要求：Windows/PowerShell7、Docker Desktop Linux/WSL2、Git、可执行stdlib脚本的Python（宿主3.13已验证）。容器Python3.11/TensorFlow2.15与精确依赖锁定；Node/nginx和PG/Redis/ES镜像摘要固定在源码/Compose。CPU可运行，不要求GPU。建议可用RAM至少约6GB、D盘可用10GB以上；Docker实际另占C盘VHD空间，当前未迁移。当前空闲容器合计约1.8GB，训练容器限3GB；不要并行训练与负载测试。

1. 克隆本仓库。仓库已包含固定FunRec版本所需的运行源码和本项目修改，无须再克隆嵌套upstream仓库或重复应用补丁。

```powershell
git clone https://github.com/runmiao0227-star/cineagent.git
Set-Location cineagent
```

source/upstream.patch仅供审查增量，当前源码已经应用，不要重复apply。首次依赖、数据、训练按后续步骤完成；本机历史结果不等于第二台空机器已复现。

2. 创建本机配置、构建锁定依赖镜像：

```powershell
python .\scripts\init_local.py
.\scripts\app.ps1 build
```

init_local仅在 .env 不存在时生成随机凭据，不打印值；已存在则保留。build记录实际backend image ID供隔离训练使用。基础镜像/依赖首次下载需要网络；不要运行无关npm audit fix或全系统升级。

3. 获取并校验唯一数据和两个官方参考包：

```powershell
python .\scripts\prepare_references.py references
python .\scripts\prepare_data.py
.\scripts\inspect_data_isolated.ps1
.\scripts\prepare_catalog.ps1
python .\scripts\prepare_references.py audit
```

大包约1.93GB，只下载一次；支持断点、SHA256、ZIP路径/CRC校验。已有解压文件仅CRC/长度一致时复用，不覆盖不一致文件。data/ml-1m-reference.zip 是正式交互来源；latest-small只读 movies.csv/links.csv 核验身份，不读其评分。若官网latest下载内容已更新导致哈希不符，停止并报告，不能静默替换已冻结参考。外部pickle仅在无网络、无凭据、只读、非root、限资源的独立容器内转JSON，服务只消费该JSON。

4. 固定数据协议、预处理、检查、基线与训练：

```powershell
.\scripts\rec_pipeline.ps1 prepare
.\scripts\rec_pipeline.ps1 check
.\scripts\rec_pipeline.ps1 baselines
.\scripts\rec_pipeline.ps1 train
```

顺序不能跳过；EVAL_SPEC.md/configs/eval_protocol.json在训练前固定。check发现泄漏或不一致应停止。正式产物 artifacts/rec_v1，隔离smoke产物不部署。固定种子不能保证跨硬件/框架完全逐位一致，需比较协议、输入哈希、指标区间与物品ID映射；不得为逼近已见测试分数调参。

5. 只初始化本项目数据库并修复元数据，再启动服务：

```powershell
.\scripts\infra.ps1 up
.\scripts\rec_pipeline.ps1 bootstrap
.\scripts\rec_pipeline.ps1 repair-metadata
.\scripts\project.ps1 up
.\scripts\rec_pipeline.ps1 verify
```

bootstrap只接受空的cineagent_db；已有成功标记时跳过重复PG导入，保留训练期画像和模型指针。若非空却无成功标记，先诊断而不是drop/reset。只导入800164条训练评分，未把验证/测试反馈泄漏到在线画像。元数据修复使用同ID+标题年份确认，未确认属性留空；ES不执行全库删除重建。启动后的标题类型索引在 artifacts/content_v1，外部元数据不在每次请求关键路径。

## 评测入口

```powershell
.\scripts\project.ps1 offline-eval  # 完整模板/记忆/压缩、受控故障、冷启动
.\scripts\project.ps1 faults        # 会短暂停止并finally恢复本项目Redis
.\scripts\project.ps1 load          # 约5分钟；期间不要运行训练或其他压测
.\scripts\project.ps1 live-smoke    # 真实API，消耗共享试跑额度，不是离线命令
.\scripts\project.ps1 showcase      # 构建无密钥展示包并检查
```

离线推荐与对话评测独立，完整/采样候选不能混报。对话任务文件哈希不匹配必须停止，空输入报错、失败保留。真实DeepSeek验收当前只是小样本，不将模板90项通过率归因于LLM。服务负载为1/5客户端各30s预热+120s测量、总5rps，P50/P95不是最大容量。工具参数/版本/请求ID/错误/降级/耗时保存在请求记录或逐任务报告；预算账本不保存凭据和原始提示词。

## 数据与模型校验路径

reports/DATA_DOWNLOAD.json与MOVIELENS_REFERENCE.json、configs/eval_protocol.json、artifacts/rec_v1/PREPARE.json/PROTOCOL_CHECKS.json、reports/MODEL_MANIFEST.json/REC_RUN_MANIFEST.json及最终FINAL_MANIFEST.json。公开展示不打包 .env、local-secrets、完整数据、Docker卷、node_modules或模型缓存。

项目所有额外文件位于D盘；Docker Desktop镜像/卷仍在原C盘虚拟磁盘，不能据此声称全部依赖都在D盘。版本别名deepseek-flash由服务商控制；调用记录无法证明固定权重快照。图像编码和图文对照未做，文本版是明确交付范围。


迁移继续同一API试跑时，保留展示包 reports/DEEPSEEK_TRIAL_LEDGER.json 到新项目reports，不要重置原30次额度；该账本不含密钥或原始提示词。密钥仍需用户在新机器本机配置。若只是复现离线结果，不需要配置任何API key。

## 本轮新增诊断的复现

```powershell
.\scripts\project.ps1 diagnose       # 约一分钟CPU诊断；不读取原test数组、不训练神经模型
.\scripts\project.ps1 agent-natural  # 首批7题真实服务函数评测；整批需至少14次剩余请求
```

现有预算已用25/30，仅余5次，agent-natural会在额度不足时拒绝整批重跑，不会重置账本或超额调用。新增14道题和期望为开发助手合成、未独立人工复核；初始来源标签更正有原冻结快照与语义哈希，题目/期望/选题未变。自然任务首批2/7通过，未执行7题和所有失败均独立记录；服务函数集成不代表本轮覆盖HTTP/鉴权。报告为reports/DIAGNOSIS_RESULTS.md。

## 本轮增量验证
`powershell -File scripts/project.ps1 ablation`执行492验证用户消融；`repair-offline`复核原七题。`scripts/eval_agent_http_v2.py`使用明确记录的冲突记忆政策判据。付费natural-v2与原7题修复重放已完成，结果和预算账本保留，不应直接覆盖或重置再跑。新增实验预算仅由显式评测脚本启用，交互页面保留旧30次上限。

## V3排除来源治理
离线：容器执行`python /checks/check_exclusion_guard.py`重放8个错误参数并验证8项输入/来源不变量；`scripts/summarize_exclusion_v3.py`从原始结果生成报告。真实V3批次已完成，脚本拒绝覆盖结果；若新增版本继续共享原追加账本，不重置额度。

## V4测量
容器脚本eval_content_contribution_v4.py、check_content_budget_v4.py、eval_chat_text_v4.py为离线；eval_complete_v4_offline.py保存同题无LLM对照。实际浏览器UI的43条观测在COMPLETE_V4_BROWSER.json，collect_complete_v4.py关联数据库和账本。付费批次已结束，evaluation_v4.json窗口关闭，重放不得自行开启/重置预算。人工表D:/recruit/CineAgent人工评议.md由用户填写，勿覆盖。
