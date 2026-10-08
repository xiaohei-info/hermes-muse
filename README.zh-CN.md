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

## 功能对照

| Muse 功能 | 原生 Hermes | 安装 Hermes Muse 后 |
| --- | --- | --- |
| 记住偏好与近况 | 已有长期记忆和用户资料，可跨会话保存事实与偏好。 | 沿用原有记忆，增加定期整理、人物关系记录和夜间复盘。 |
| 主动提醒重要变化 | 可用 Cron 和会话心跳定期检查、推送消息，检查内容需自行配置。 | 默认检查目标、兴趣和相关信息，核实后决定是否提醒，并限制提醒时段和次数。 |
| 持续跟进目标 | 支持会话内持续任务、任务看板和定时检查。 | 统一记录目标、进度和关联监控；目标结束或监控到期时，停止后续检查。 |
| 后台准备资料 | 已有异步子任务，可边聊天边处理后台工作。 | 增加目标的定时研究和简报归档。插件的批量研究仍需助手推进，暂不支持跨重启恢复。 |
| 主动提出建议 | 能根据对话和记忆给建议；主动选题与跟进需自行安排。 | 定期围绕活跃目标整理资料和建议，等用户决定是否执行。 |
| 个性化 Feed | 能搜索、写文章，也能配置定时简报。 | 按兴趣生成本地 Feed，支持搜索、反馈和删除；没有独立的 Feed 页面。 |
| 调整提醒与停止跟进 | 可修改偏好、暂停或删除定时任务；反馈如何影响后续任务需自行约定。 | 分别处理完成、延后、单次忽略和主题退订；临时兴趣默认 14 天到期。 |
| 代办生活事务 | 取决于已接入的浏览器、服务工具及授权。 | 沿用现有工具，插件未新增电话、预订或支付流程。 |

信息查询、记忆整理和内容生成使用现有模型与工具。具体限制见[详细实现对照](docs/FEATURE-COVERAGE.zh-CN.md)。

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
