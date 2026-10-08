# Hermes Muse

[English](README.md) · [设计文档](docs/DESIGN.md) · [验收清单](docs/ACCEPTANCE.md)

Hermes Muse 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的个人助理插件，受 [Meta Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) 的主动交互启发：让助手在聊完之后继续跟进你关心的事，有值得留意的变化时主动联系你。

插件复用 Hermes 的记忆、Cron、Skill 和子任务。模型、记忆后端、聊天渠道沿用现有配置，不要求安装 Hindsight、Obsidian 或其他指定服务。本项目与 Meta/Muse 无官方关联，代码和提示词独立编写。

## 安装

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

需要 Hermes 0.21.5 及相关插件接口，已测试版本见[验收清单](docs/ACCEPTANCE.md)。首次加载会自动创建工作区，注册 1 个 Skill、1 个状态工具和 3 个会话钩子，追加 1 段系统提示词，并建立 4 个固定 Cron，无须选择功能或另行初始化。没有运行中的宿主时，下次启动 Hermes 才会加载。

新增系统规则在新会话生效。后台执行需要 Hermes 调度器在线、模型可用；实际研究和内容生成使用现有模型与工具，按相应服务计费。

## 功能对照

插件在首次加载时配好任务和规则，模型、信息源和消息渠道沿用现有 Hermes 配置。

| Muse 功能 | 原生 Hermes | 安装 Hermes Muse 后 |
| --- | --- | --- |
| 记住偏好与近况 | 原生支持长期记忆和用户资料；定期整理人物关系、夜间复盘等流程需要自行配置。 | 开箱即用的记忆维护：定期整理近况和人物关系，每晚复盘。 |
| 主动提醒重要变化 | 原生支持 Cron、会话心跳和推送；关注范围、通知条件、去重与限频规则需要自行配置。 | 开箱即用的主动提醒：结合目标和兴趣检查变化，核实后通知，并控制时段和次数。 |
| 持续跟进目标 | 原生支持持续任务和任务看板；长期目标、进度、关联监控和结束条件需要自行组织。 | 聊天中即可建立和跟进目标，进度与监控关联到目标，目标结束时停止相关检查。 |
| 后台准备资料 | 原生支持异步子任务；定期研究哪些目标、如何保存和使用结果，需要自行配置。 | 目标研究和简报归档已配好，后台准备资料时可以继续聊天。 |
| 主动提出建议 | 原生能根据对话与记忆给出建议；持续研究、筛选和保存建议需要自行安排。 | 定期为活跃目标准备建议，记录候选和反馈，等用户决定是否执行。 |
| 个性化 Feed | 原生支持搜索、写作和定时任务；兴趣选题、文章记录、反馈和更新流程需要自行搭建。 | 开箱即用的本地 Feed：按兴趣生成文章，可在聊天中搜索、反馈和删除。 |
| 调整提醒与停止跟进 | 原生支持修改偏好、停用任务；反馈如何关联提醒、目标和监控，需要自行约定。 | 直接说“已处理”“晚点再说”或“以后别提”即可调整提醒；临时兴趣默认 14 天到期。 |
| 代办生活事务 | 原生可调用浏览器和外部工具；电话、预订、支付需自行接入服务并配置流程。 | 未提供这部分装配，继续使用用户已接入的工具和服务。 |

Feed 暂无独立页面；插件的批量研究仍需助手推进，暂不支持跨重启恢复。记忆整理、事实核实和内容生成由现有模型与工具完成，具体限制见[详细实现对照](docs/FEATURE-COVERAGE.zh-CN.md)。

## Skill 与工具

| 名称 | 作用 |
| --- | --- |
| [hermes-muse:companion](skills/companion/SKILL.md) | 主对话和后台任务共用的操作规程，包括目标与兴趣、主动提醒与反馈、记忆与人物关系、Feed、后台研究。 |
| muse_manage | 供助手记录和查询目标、兴趣、提醒、反馈、Feed 与研究进度，并处理到期、停止和投递状态。 |

Skill 随插件注册，文件保留在插件目录。主对话按需读取其中的规程，四个固定 Cron 都绑定这个 Skill。日常使用直接聊天即可，由助手调用工具。

## 提示词

插件自带 5 份提示词：

| 文件 | 用途 |
| --- | --- |
| [system.md](prompts/system.md) | 主对话的工作约定：何时读取 Skill 和状态，如何记录目标、处理反馈、核实提醒及委派后台工作。 |
| [proactive-watch.md](prompts/proactive-watch.md) | 主动巡查：寻找相关变化，核实来源、重复记录和时效，决定是否提醒。 |
| [memory-upkeep.md](prompts/memory-upkeep.md) | 记忆维护：整理新增用户信息，更新事实、人物关系和处理记录。 |
| [nightly-review.md](prompts/nightly-review.md) | 夜间复盘：更新对齐记录，研究活跃目标，整理建议并复盘技能。 |
| [feed-pulse.md](prompts/feed-pulse.md) | Feed 写作：结合兴趣和反馈生成文章，保存内容与索引。 |

`system.md` 通过 Hermes 插件接口追加到系统提示词的记忆段之后，在新会话生效。其余四份写入对应 Cron 的任务正文，在后台任务运行时使用。每次加载插件会同步这些任务正文，保留用户设置的执行时间、模型和暂停状态。

## 会话钩子

| 钩子 | 作用 |
| --- | --- |
| pre_llm_call | 在回复前记录用户原话片段和来源会话，并在本轮上下文中附上状态工具入口，供助手处理新目标、兴趣和反馈。 |
| post_llm_call | 用户消息达到 80 个字符时，回复后等待 5 分钟安静期，再安排记忆整理；新消息会取消本次计时，每天最多提前触发 3 次。 |
| on_session_end | 清除本轮的忙碌标记，避免后续提醒一直等待已经结束的对话。 |

这些钩子处理私聊和本地对话，跳过群聊、Cron 和子任务输入。延迟整理复用现有的记忆维护 Cron；插件从运行进程卸载时会取消临时计时器。

## 四个固定 Cron

| 任务 | 默认频率 | 输出 |
| --- | --- | --- |
| muse-proactive-watch | 每 30 分钟 | 提醒候选、证据和交付记录 |
| muse-memory-upkeep | 每小时 | 新事实、人物和群组资料 |
| muse-nightly-review | 每天 03:20 | 对齐记录、目标研究、Ideas 和技能复盘 |
| muse-feed-pulse | 每小时 | 本地 Feed 文章 |

频率使用 Hermes 当前时区。有明确截止时间的监控会在到期后停止。具体提醒、监控和通知投递可以产生额外 Cron，均记录到安装清单；四个是固定任务数量。

前置脚本会在没有符合条件的工作时跳过模型调用。Feed 每小时检查一次，不要求每次生成文章。

## 文件

根目录是当前 profile 的 `HERMES_HOME`，通常为 `~/.hermes`。

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # 插件代码与资源
│   ├── skills/companion/
│   │   ├── SKILL.md                # 共用操作规程
│   │   └── references/             # 目标、提醒、记忆、Feed、研究
│   ├── prompts/                    # 上述 5 份提示词
│   └── templates/                  # 工作区初始文件
├── muse/
│   ├── install.json                # 任务 ID 和文件归属
│   ├── install.lock
│   ├── state.db                    # 兴趣、提醒、频次、Feed 索引
│   ├── AGENTS.md
│   ├── TOOLS.md
│   ├── PROACTIVE_PREFERENCES.md
│   ├── memory/
│   │   ├── YYYY-MM-DD.md
│   │   ├── people/INDEX.md, <人物>.md
│   │   └── groups/INDEX.md, <群组>.md
│   ├── dreams/
│   │   ├── YYYY-MM-DD.md
│   │   └── alignment/derived/ALIGNMENT_SYNTHESIS.md
│   └── workspace/
│       ├── goals/<目标>/GOAL.md, files/, hidden_files/
│       └── your_files/feed/<id>.md
├── scripts/hermes-muse-*.py         # 原生 Cron 入口
├── memories/USER.md, MEMORY.md      # 现有原生记忆（如当前后端使用）
└── cron/                           # Hermes 自己管理的任务及执行记录
```

`memory`、`dreams` 和目标目录借鉴 Muse 的组织方式。`install.json`、`state.db`、Feed 落盘和原生记忆路径是 Hermes 适配。首次加载只补齐缺失的工作区模板；目标、笔记和文章在使用时生成。重载不会重复创建固定任务。

安装不改写 Hermes 核心、`SOUL.md`、原生 `USER.md`/`MEMORY.md`、用户项目 `AGENTS.md` 或配置中的 `agent.system_prompt`。运行期间，助手通过现有记忆工具保存新事实。

会话钩子保存短用户原话片段供维护处理，未处理片段保留到维护成功，已处理历史保留有限数量。插件不收集遥测；个人资料流程不进入群聊。数据范围见 [SECURITY.md](SECURITY.md)。

## 使用

直接提出目标、要求监控或反馈即可，例如：

```text
建立购车目标，预算两万元，月底前决定。
帮我检查这封邮件的回复，到周五停止。
这个提醒已经处理了。
这个主题以后不用提醒。
列出当前目标、兴趣和待发送的提醒。
搜索 Feed 中关于城市园艺的文章。
```

目标和兴趣由模型识别后调用状态工具记录。正式目标需要明确请求；临时兴趣默认 14 天到期，不自动创建长期监控。新的用户消息可以续期兴趣，助手自己的研究不能续期。没有可用通知渠道时，候选保留在本地。查看具体状态可以让助手调用 `muse_manage status`。

## 卸载

```sh
hermes plugins remove hermes-muse
```

然后让 Hermes 清理关联任务：

> 读取当前 profile 的 muse/install.json。暂停并删除其中登记的 Cron，检查仍在运行的任务，清理登记的 scripts/hermes-muse-* 入口。保留目标、文章、笔记和记忆，并报告未完成的清理项。

原生 remove 不保证清理插件创建的 Cron，因此需要这一步。插件被删除或停用后，遗留入口会静默；已经开始的任务仍需检查。重装保留数据，普通重载不会重新启用用户暂停的任务。

## 开发与验证

```sh
python -m unittest discover -s tests -v
# 在 Hermes 环境中：
python tests/native_smoke.py
hermes plugins validate . --json
```

测试使用临时 profile，不调用真实模型或消息渠道。[验收清单](docs/ACCEPTANCE.md)列出了需要在实际环境检查的项目。

[官方插件目录申请](https://github.com/NousResearch/hermes-agent/pull/134976)正在等待审核；当前可用上面的仓库地址安装。

MIT 开源协议。
