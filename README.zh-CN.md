# Hermes Muse

[English](README.md) · [设计文档](docs/DESIGN.md) · [验收清单](docs/ACCEPTANCE.md)

Hermes Muse 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的个人助理插件，受 [Meta Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) 的主动交互启发：让助手在聊完之后继续跟进你关心的事，有值得留意的变化时主动联系你。

插件复用 Hermes 的记忆、Cron、Skill 和子任务。模型、记忆后端、聊天渠道沿用现有配置，不要求安装 Hindsight、Obsidian 或其他指定服务。本项目与 Meta/Muse 无官方关联，代码和提示词独立编写。

## 安装

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

需要 Hermes 0.21.5 及相关插件接口，已测试版本见[验收清单](docs/ACCEPTANCE.md)。首次加载会自动创建工作区，注册 1 个 Skill 和 1 个状态工具，并用 5 份提示词配置系统规则及 4 个固定 Cron，无须选择功能或另行初始化。没有运行中的宿主时，下次启动 Hermes 才会加载。

新增系统规则在新会话生效。后台执行需要 Hermes 调度器在线、模型可用；实际研究和内容生成使用现有模型与工具，按相应服务计费。

## 能做什么

Muse 的公开使用分享里，有人提到它会主动提醒被搁置的消息，按孩子的年龄推荐周末活动，也有人只是聊了近况，过后就收到相关的建议。这些[用户分享](https://www.reddit.com/r/MetaAI/comments/1wxfn5z/muse_isgood/)帮助我们确定了下面的功能方向。

| 功能 | 日常使用中的表现 | Hermes Muse 当前覆盖 |
| --- | --- | --- |
| 记得你说过的话 | 记住偏好、身边的人和最近在忙什么，后续交流能接上。 | 支持。沿用 Hermes 记忆，定期整理新信息和人物关系。 |
| 主动留意重要变化 | 发现与当前计划有关的新进展，或需要你关注的消息，主动告诉你。 | 支持。检查已连接的信息源，核实后准备提醒，通过现有消息渠道发送。 |
| 持续跟进一件事 | 关注求职、旅行或写作进度，不用每天重新交代。 | 支持。记录目标和进度，按约定检查，到期或结束后停止相关监控。 |
| 提前准备，有结果再反馈 | 先查资料、做比较、整理简报，期间可以继续聊天。 | 部分支持。已有定时研究和后台子任务；复杂研究仍需助手继续推进，重启后不能自动续跑。 |
| 根据你的情况提出建议 | 推荐适合家人的活动，或围绕当前目标提出下一步。 | 部分支持。会结合目标与偏好整理建议，尚无完整的日程统筹流程。 |
| 帮你挑值得看的内容 | 围绕兴趣整理文章和动态，想看时再看。 | 部分支持。可生成、搜索和反馈本地 Feed，没有独立的信息流页面。 |
| 按反馈调整，知道何时停 | “已处理”“晚点再说”“以后别提”会改变后续跟进。 | 支持。分别处理完成、延后与退订；临时兴趣会过期，并限制提醒时段和频率。 |
| 代办生活琐事 | 打客服电话、预约、下单，需要时交回给你确认。 | 未覆盖。本插件没有电话、预订或支付流程。 |

持续跟进可以小到[陪用户按日推进写作](https://www.reddit.com/r/MetaAI/comments/1whc17p/my_experience_using_muse/)，代办则有[替用户等待客服电话接通](https://www.reddit.com/r/MetaAI/comments/1wqaj5c/muse_is_fucking_amazing/)的分享。这些是个人体验，不代表所有账号都能获得同样的效果。

也有用户抱怨 Muse [反复提醒已经解决的事](https://www.reddit.com/r/MetaAI/comments/1wpdcdd/it_was_great_until_it_wasnt/)。因此，反馈和退出也是这里的一项功能；“永不重复、永不忘记”不在承诺之内。

表中的“支持”指对应流程已接入。记忆整理、事实核实和建议质量依赖当前模型及工具，真实模型与消息渠道仍需验收。[详细实现对照](docs/FEATURE-COVERAGE.zh-CN.md)列出了各项限制。

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
├── plugins/hermes-muse/             # 代码、Skill、提示词和模板
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

`memory`、`dreams` 和目标目录借鉴 Muse 的组织方式。`install.json`、`state.db`、Feed 落盘和原生记忆路径是 Hermes 适配。笔记和目标文件按实际内容创建。

安装不改写 Hermes 核心、`SOUL.md`、原生 `USER.md`/`MEMORY.md`、用户项目 `AGENTS.md` 或全局系统提示词。运行期间，助手通过现有记忆工具保存新事实。

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
