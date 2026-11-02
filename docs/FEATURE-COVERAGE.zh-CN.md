# 功能覆盖（0.4.0）

[返回 README](../README.zh-CN.md) · [English](FEATURE-COVERAGE.md)

哪些由代码保证、哪些交给模型。**代码**：确定性实现，由验收脚本覆盖。**模型**：job prompt 或 Skill 流程，由模型和用户已有的工具完成，需要实际验收。**不覆盖**：Muse 没有对应实现。

| 功能 | 由谁 | 实现与限制 |
|---|---|---|
| 捕获私聊用户消息 | 代码 | 只收 `USER_SOURCES`，先脱敏，超过 8k 只取头尾摘录；水位在 `meta`；3 次 packet 或 72h 未处置转 parked |
| 判断消息含义、归属哪个目标 | 模型 | intake packet 的 disposition 和 goal hint |
| Goal 的创建、更新、等待、完成、取消、重开 | 代码 | GOAL.md 是事实源；状态只能在私聊主会话修改 |
| 目标进展与完成建议 | 模型 | nightly assessment；`done_suggested` 不关闭目标 |
| next_check、休眠询问、淡出取消 | 代码 | `goals.fade`：活动指用户或执行者的进展；每个休眠期一次询问，最多 3 次；送达后满 `goal_fade_days` 取消 |
| 规则匹配、分派账本 | 代码 | `rules.match`、`kernel/assignments.py`；启动和查询执行者由模型用用户的工具完成 |
| 开放目标的 Watch | 代码 | 每个 watch 一个 owned job；30 天到期，目标开放时续期，目标关闭时停止 |
| 读外部来源（邮件、日历、提醒、网页） | 模型 | 用用户自己的工具；Muse 按 `source_id` 记录每次检查的间隔、limitation 和失败状态 |
| 是否值得通知、措辞 | 模型 | patrol 的 verdict、text、priority、topic |
| Notice 去重、静默时段、预算、`urgent_per_day`、blocked_topics | 代码 | notice key 对 7 天历史去重；gate 计算 `next_eligible` |
| 投递与对账 | 代码 | 一个固定的 no_agent `muse-deliver` job 打印到期通知（每 10 分钟，urgent 立即唤醒）；按 run 的 execution 读回执；结果未知不重发 |
| 对话复盘 | 代码 + 模型 | 代码按规则每天挑 ≤10 个候选；模型判断 `agent_gap`（Finding）或 `latent_need`（Idea） |
| Interest 与 Idea | 代码 | 14 天到期；只有用户输入能续期 |
| Feed 文章 | 模型 | 每天最多 3 个近期无文章的 interest；静默发布，可在 Muse 页面浏览 |
| dream、alignment、人物/群组页、工作经验 | 模型 | 经 `content_write` 按 revision CAS 写入 |
| 原生记忆写入回执 | 代码 | failed/staged 的写入在主会话提示一次 |
| 周报 | 模型 | 只用 Health 摘要和 7 天计数；只提建议，不改任何东西 |
| 健康检查与告警 | 代码 | probe 与 invariant 写入 `muse/health.json`；主会话、Muse 页面、cron stdout、可选 `health_deliver` |
| 日历视图 | 代码 + 模型 | `calendar_view` 计算窗口与合并；读日历由模型完成 |
| 遗忘 | 代码 | 清空 payload 并写 tombstone；Hermes 会话历史和原生 memory 不在 Muse 范围内 |
| 从 0.3.x 迁移与回滚 | 代码 | `install.install`、`scripts/cutover.py` |
| 写外部来源、数据源连接器、跨 profile 监控、遥测 | 不覆盖 | 设计上不做 |
| 通用操作审计、模型自评 run 结果、唤醒门 | 不覆盖 | v2 已删除 |
