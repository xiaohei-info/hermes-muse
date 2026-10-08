# Hermes Muse

[English](README.md) · [设计文档](docs/DESIGN.md) · [测试与验收](docs/ACCEPTANCE.md)

给 Hermes 装配长期目标、临时兴趣、主动提醒、记忆维护、夜间对齐、静默 Feed 和后台研究。独立插件，不修改 Hermes 核心，不强制任何模型、Hindsight、Obsidian 或聊天平台。

## 安装

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

使用近期 Hermes，需具备插件 Skill、系统提示词段注入、生命周期 hooks、带脚本门控的 Cron。安装遵循 Hermes 原生来源及安全检查。没有路径选择、功能选择、账号配置或第二个初始化命令。

第一次实际加载插件时自动完成：创建当前 profile 的 muse 工作区和缺失模板；注册 1 个 Skill、1 个状态工具、系统提示词及会话 hooks；配置 4 个固定 Cron；生成原生 scripts 入口；把真实任务 ID 和文件归属写入 muse/install.json。已运行的宿主可以热加载，否则下一次启动 Hermes 时初始化。后台运行仍需 Hermes 调度器在线且模型可用。

安装不改写 SOUL.md、原生 memories/USER.md、memories/MEMORY.md、项目 AGENTS.md，也不替换全局系统提示词。使用中有新事实时，由助手通过已有记忆工具更新。提示词段在新会话生效，已缓存的旧会话不强行重写。

## 四个 Cron

| 任务 | 默认频率 | 作用 |
| --- | --- | --- |
| muse-proactive-watch | 每 30 分钟 | 发现、核实、去重、筛选；通知另过时段和频控检查 |
| muse-memory-upkeep | 每小时 | 有新增用户信息才整理记忆和人物关系 |
| muse-nightly-review | 每天 03:20 | 反思修复、对齐、目标研究、Ideas、技能复盘和退出检查 |
| muse-feed-pulse | 每小时 | 有价值才生成文章，静默保存 |

继承 Hermes 的时区和模型。没有工作时，前置脚本在调用模型前跳过；真正的研究和内容生成仍会产生模型/工具费用。安静时段整理唤醒既有维护任务，不增加第五个常驻 Cron。具体提醒、目标监控和消息交付按需产生附属任务，统一登记和清理。

## 日常使用

直接聊天，例如“这个月我要选一辆自行车，预算……”“最近对城市园艺有点兴趣”“直到周五帮我等这封邮件的回复”“这次不用提醒”“以后别提这个主题”“看看我的 Feed”“忘记这个兴趣及衍生记录”。不需要记工具参数或手动管理文件。

临时兴趣默认 14 天到期；只有新的真实用户信息才能续期。助手自己的研究、新闻和旧记忆不会续期。正式目标有复核和完成/取消流程，目标关闭后停止关联监控，仍待交付的最终结果单独保留。明确订阅不会因为用户沉默就自动取消。

提醒在实际输出前复查目标、时效、反馈和次数。准备完成、入队、发送中、宿主报告已发出、结果未知分别记录。程序保证同一事件标识不被并发重复提交；跨来源语义去重仍需模型判断。无渠道就留到下次私聊，不擅自群发。原主会话唤醒只使用 Hermes 已有的权限，未允许时走原生 Cron 投递；不会自行打开权限。

Feed 可以通过聊天列表、搜索、排序、反馈、解释和删除；本版没有独立原生 Feed 页。研究使用 Hermes 子任务，结构化研究按至多三个一组执行，通过 research_status 回收结果并推进下一组。进程丢失时记录未知，避免重复外部操作。浏览器保留现场、电话、设备服务不包含在本版。

“忘记”会先停止相关工作，清理插件记录及已索引衍生内容，再由助手按实际工具清理原生/外部记忆及其他文件，不把历史聊天、备份或第三方索引谎称为已经全部删除。

## 文件

根目录取当前 profile 的 HERMES_HOME，默认通常为 ~/.hermes。

- plugins/hermes-muse：代码、1 个 Skill、5 份提示词、通用模板。
- muse/install.json：安装归属和所有固定/附属任务 ID，卸载后保留。
- muse/state.db：去重、频次、兴趣有效期、通知状态、Feed 索引等运行状态。
- muse/AGENTS.md、TOOLS.md、PROACTIVE_PREFERENCES.md：工作区约定、已确认信息源、提醒及 Feed 偏好。
- muse/memory：每日整理、人物与群组资料。
- muse/dreams：反思，以及 alignment/derived/ALIGNMENT_SYNTHESIS.md。
- muse/workspace/goals/<目标>：GOAL.md、files、hidden_files。
- muse/workspace/your_files/feed：文章。
- scripts/hermes-muse-*.py：Hermes 要求的脚本入口，实际逻辑仍在插件内。

这些目录沿用已研究的 Muse 组织方式；install.json、state.db、Feed 具体落盘和原生 USER/MEMORY 路径是 Hermes 适配，不宣称是 Muse 原始实现。空白安装不植入任何个人事实或复制原助手身份。

## 卸载

```sh
hermes plugins remove hermes-muse
```

然后告诉现有 Hermes 助手：

> Hermes Muse 已卸载。读取当前 profile 的 muse/install.json，只暂停并删除其中登记的原生 Cron，包括目标监控和交付任务；检查正在执行的任务；清理登记的 scripts/hermes-muse-* 入口。保留我的目标、文章、记忆和其他用户数据，并报告仍在运行或结果未知的事项。

原生 remove 没有保证调用插件 Cron 清理钩子，因此保留这一步。卸载/停用后的遗留入口会静默，不启动新的模型任务；已经在途的工作仍需检查。再次安装保留已有数据并修复缺失任务，普通重载不重新开启用户暂停的任务。

## 发布状态

这是独立编写、受 Muse 类工作流启发的项目，不是 Muse 官方代码或提示词导出包。测试比例不等于真实模型行为质量。请按验收文档检查你的模型、工具、时区和实际渠道表现。GitHub 仓库可以直接安装；官方插件目录收录需要 Hermes 维护者审核。
