# V4浏览器测量步骤与计时范围

1. 使用既有项目与冻结complete_v4.json，先确认/ready。官方模型调用需要有效授权，原子预算与共享账本不得重置；本轮窗口已关闭，不要直接重跑付费批次。
2. 评测窗口开启时，实际访问/chat?evaluation=v4，每场景刷新生成独立范围访客；等待DeepSeek选项启用后再选模型模式。按题库顺序填写、点击发送，当前场景两轮使用同一会话。
3. 每轮等待.answer[data-render-ms]出现，读取DOM的data-request-id、data-render-ms和可见token/费用行。计时来自Chat.vue发送前performance.now，到响应后Vue nextTick；不是工具执行耗时或截图工具往返时延。
4. 若自动化观察超时，先观察同一请求，不重复提交；仍无结果则记录失败，后续恢复单独attempt编号，不删除首次记录。本轮E02/E04/E18首次观察失败，恢复后完成；第一版等待驱动在两次失败后调整为更长观察窗口，驱动变更与三次失败都留档。
5. 完整43条观测见reports/COMPLETE_V4_BROWSER.json；无渲染数据的三条保留为空，不补时延。collect_complete_v4.py通过请求ID读取ca_requests并关联全部parent_request_id模型账本，检查业务和成本。
6. 人工相关性评分不由脚本生成，使用HUMAN_REVIEW_V4.md空白表。用户编辑D:/recruit/CineAgent人工评议.md期间禁止覆盖。

运行环境：本机Windows/WSL2、Docker、CPU、顺序合成场景；provider8秒HTTP超时、服务有界重试。原始和恢复分母分别报告；36个LLM轮的P95样本较少，不等于生产SLA。网页截图见COMPLETE_V4_UI.png。
