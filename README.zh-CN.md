# Hermes Muse

[English](README.md) · [设计文档](docs/DESIGN.md) · [验收清单](docs/ACCEPTANCE.md)

Hermes Muse 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的个人助理插件，受 [Meta Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) 的主动交互启发：让助手在聊完之后继续跟进你关心的事，有值得留意的变化时主动联系你。

插件复用 Hermes 的记忆、Cron、Skill 和子任务。模型和记忆后端沿用现有配置，提醒默认交给当前 profile 的 Bot Chat，不要求安装 Hindsight、Obsidian 或其他指定服务。本项目与 Meta/Muse 无官方关联，代码和提示词独立编写。

## 安装

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

安装到当前选定的 profile。明确安装到 default：`hermes -p default plugins install xiaohei-info/hermes-muse --enable`；安装到其他 profile 时，将 `default` 换成 `architect` 等名称。每个启用插件的 profile 独立保存状态、创建 6 个任务并投递到自己的 Bot Chat；省略 `-p` 会沿用当前 profile 选择。

需要 Hermes 0.21.5 及相关插件接口，已测试版本见[验收清单](docs/ACCEPTANCE.md)。首次加载会自动创建工作区，注册 1 个 Skill、1 个状态工具和 3 个会话钩子，追加 1 段系统提示词，并建立 6 个固定 Cron，无须选择功能或另行初始化。没有运行中的宿主时，下次启动 Hermes 才会加载。

新增系统规则在新会话生效。后台执行需要 Hermes 调度器在线、模型可用；实际研究和内容生成使用现有模型与工具，按相应服务计费。

## 功能对照

插件在首次加载时配好任务和规则，模型和信息源沿用现有 Hermes 配置，通知默认在当前 profile 的 Bot Chat 中处理。

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
| [hermes-muse:companion](skills/companion/SKILL.md) | 主对话和后台任务共用的操作规程，包括目标与兴趣、主动提醒与反馈、记忆与人物关系、Feed、后台研究和周／月复盘。 |
| muse_manage | 供助手记录和查询目标、兴趣、提醒、反馈、Feed 与研究进度，并处理到期、停止和投递状态。 |

Skill 随插件注册，文件保留在插件目录。主对话按需读取其中的规程，六个固定 Cron 都绑定这个 Skill。日常使用直接聊天即可，由助手调用工具。

## 提示词

插件自带 7 份提示词：

| 文件 | 用途 |
| --- | --- |
| [system.md](prompts/system.md) | 主对话的工作约定：何时读取 Skill 和状态，如何记录目标、处理反馈、核实提醒及委派后台工作。 |
| [proactive-watch.md](prompts/proactive-watch.md) | 主动巡查：寻找相关变化，核实来源、重复记录和时效，决定是否提醒。 |
| [memory-upkeep.md](prompts/memory-upkeep.md) | 记忆维护：整理新增用户信息，更新事实、人物关系和处理记录。 |
| [nightly-review.md](prompts/nightly-review.md) | 夜间复盘：更新对齐记录，研究活跃目标，整理建议并复盘技能。 |
| [feed-pulse.md](prompts/feed-pulse.md) | Feed 写作：结合兴趣和反馈生成文章，保存内容与索引。 |
| [weekly-governance-review.md](prompts/weekly-governance-review.md) | 周复盘：哪些产出有用、哪些投入浪费、下周值得调整什么。 |
| [monthly-system-audit.md](prompts/monthly-system-audit.md) | 月度审计：检查规则和定时任务是否仍服务于用户，提出迁移、精简或删除建议。 |

`system.md` 通过 Hermes 插件接口追加到系统提示词的记忆段之后，在新会话生效。其余六份写入对应 Cron 的任务正文，在后台任务运行时使用。每次加载插件会同步这些任务正文，保留用户设置的执行时间、模型和暂停状态。

## 会话钩子

| 钩子 | 作用 |
| --- | --- |
| pre_llm_call | 在回复前记录用户原话片段和来源会话，并在本轮上下文中附上状态工具入口，供助手处理新目标、兴趣和反馈。 |
| post_llm_call | 用户消息达到 80 个字符时，回复后等待 5 分钟安静期，再安排记忆整理；新消息会取消本次计时，每天最多提前触发 3 次。 |
| on_session_end | 清除本轮的忙碌标记，避免后续提醒一直等待已经结束的对话。 |

这些钩子处理私聊和本地对话，跳过群聊、Cron 和子任务输入。延迟整理复用现有的记忆维护 Cron；插件从运行进程卸载时会取消临时计时器。

## 六个固定 Cron

| 任务 | 默认频率 | 输出 |
| --- | --- | --- |
| muse-proactive-watch | 每 30 分钟 | 提醒候选、证据和交付记录 |
| muse-memory-upkeep | 每小时 | 新事实、人物和群组资料 |
| muse-nightly-review | 每天 03:20 | 对齐记录、目标研究、Ideas 和技能复盘 |
| muse-feed-pulse | 每小时 | 本地 Feed 文章 |
| muse-weekly-governance-review | 周日 21:15 | 产出、成本和调整建议的简短复盘 |
| muse-monthly-system-audit | 每月 1 日 10:40 | 用户需求、提示词和运行流程的简短审计 |

插件不会为固定任务指定模型或 provider。Hermes 每次执行时按这个顺序选择：**任务单独指定的模型 → 当前 profile 的 `cron.model` → profile 主模型**。不设 Cron 默认模型，每小时的后台工作也可能使用主对话的高成本模型，建议先配好再让调度器持续运行。

例如，将下面的配置合并到当前 profile 的 `config.yaml`。模型和 provider 要换成自己实际可用的名称；这里的 `llm` 是已配置的 provider 名称：

```yaml
cron:
  model: gpt-6-luna
  model_provider: llm
agent:
  reasoning_overrides:
    gpt-6-luna: high
```

推理级别依次取任务的 `reasoning_effort`、该模型的 override、全局 `agent.reasoning_effort`；已测试的 Hermes 版本不支持 `cron.reasoning_effort`。上例会将该 profile 中 Luna 的推理设为 `high`，也适用于使用 Luna 的普通会话。任务已有的单独模型和推理设置优先，插件重载时会保留。Cron 默认配置在下次运行时读取。Bot Chat 接收结果后使用自己的会话模型再处理一轮，仍会产生模型调用；`cron.model` 不控制这一轮的模型。插件安装不会替用户写入上述模型配置。

频率使用 Hermes 当前时区。有明确截止时间的监控会在到期后停止。具体提醒、监控和通知投递可以产生额外 Cron，均记录到安装清单；六个是固定任务数量。

主对话和后台整理共用目标、兴趣和反馈记录。后台可以根据已记录的真实用户表达继续处理；兴趣续期仍需要新的用户表达，助手自己的输出不会续期兴趣。监控使用 Hermes 原生调度规则。

前四个任务在没有符合条件的工作时跳过模型调用。Feed 每小时检查一次，不要求每次生成文章。周复盘和月度审计按时执行，有资料不足的地方会说明，报告投递到 Bot Chat。两者只提建议，不自动修改配置，也不额外执行 Skill 巡检。用户已有的同类任务会保留。

最近一次周／月报告摘要可通过 `muse_manage status` 查询，完整输出保留在原生 Cron 历史中，下一轮可据此检查之前的建议有没有带来改善。

## 文件

根目录是当前 profile 的 `HERMES_HOME`，通常为 `~/.hermes`。

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # 插件代码与资源
│   ├── skills/companion/
│   │   ├── SKILL.md                # 共用操作规程
│   │   └── references/             # 目标、提醒、记忆、Feed、研究、周／月复盘
│   ├── prompts/                    # 上述 7 份提示词
│   └── templates/                  # 工作区初始文件
├── muse/
│   ├── install.json                # 任务 ID 和文件归属
│   ├── install.lock
│   ├── state.db                    # 兴趣、提醒、频次、Feed 索引、复盘摘要
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

**推荐配合当前 profile 的 Bot Chat 使用。** 在这里聊目标、兴趣和反馈，后台有值得通知的结果时，Bot 会接着向你说明：

`Cron 准备结果 → 投递到当前 profile 的 Bot Chat → Bot 阅读结果 → 在聊天中回复用户`

Bot Chat 的接收会触发一轮助手处理，使用该 profile 的模型。没有 Bot Chat 会话时，Hermes 可在首次投递时自动创建；已有会话繁忙时由原生机制排队。Feed 和日常整理仍保持静默，筛选出的提醒和定期周／月报告进入这条流程。

官方安装命令会显示插件的安装后说明，目前不提供插件自定义的渠道／会话选择菜单。本版默认使用 Bot Chat，不要求先接 Telegram 等外部渠道。

直接提出目标、要求监控或反馈即可，例如：

```text
建立购车目标，预算两万元，月底前决定。
帮我检查这封邮件的回复，到周五停止。
这个提醒已经处理了。
这个主题以后不用提醒。
列出当前目标、兴趣和待发送的提醒。
搜索 Feed 中关于城市园艺的文章。
```

目标和兴趣由模型识别后调用状态工具记录。正式目标需要明确请求；临时兴趣默认 14 天到期，不自动创建长期监控。新的用户消息可以续期兴趣，助手自己的研究不能续期。投递或模型处理失败时保留状态供检查，不自动换渠道重发。查看具体状态可以让助手调用 `muse_manage status`。

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
