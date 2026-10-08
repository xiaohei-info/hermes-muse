# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance guide](docs/ACCEPTANCE.md)

Hermes Muse is a personal assistant plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent), inspired by the proactive interactions in [Meta's Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/). It follows up on things you care about after the conversation ends, and gets in touch when something needs your attention.

It uses Hermes memory, Cron, Skills and subagents with the user's existing model, memory backend and messaging configuration. Hindsight, Obsidian and other named services are optional. This is an independent project, unaffiliated with Meta/Muse; its code and prompts are independently written.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Requires Hermes 0.21.5 and the relevant plugin APIs; see the [tested baseline](docs/ACCEPTANCE.md). First load creates the workspace and registers one Skill and one state tool, and configures the system rules and four recurring Cron jobs from five prompt files. There is no feature selection or separate initialization command. Without a running host, loading happens at the next Hermes start.

The system prompt section takes effect in new conversations. Background execution requires a running scheduler and an available model. Research and content generation use the existing model and tools at their normal cost.

## What it does

In public discussions, Muse users describe getting a nudge about an unanswered message, finding weekend activities suited to their children, and receiving useful follow-ups after mentioning something in conversation. These [user reports](https://www.reddit.com/r/MetaAI/comments/1wxfn5z/muse_isgood/) helped shape the features below.

| Feature | What it means in everyday use | Hermes Muse today |
| --- | --- | --- |
| Remember what you shared | Keep preferences, people and current plans in mind across conversations. | Supported. Uses Hermes memory, with regular upkeep of new facts and relationship notes. |
| Notice important changes | Bring up relevant developments or messages that need your attention. | Supported. Checks connected sources, prepares verified reminders and sends through existing messaging channels. |
| Keep following a goal | Follow a job search, trip or writing project without a fresh explanation every day. | Supported. Tracks goals and progress, checks as agreed, and stops related watches when they expire or the goal closes. |
| Prepare work and report back | Research, compare options and save briefings while you continue chatting. | Partial. Scheduled research and background tasks work; larger studies need the assistant to keep advancing them, and cannot resume automatically after a restart. |
| Suggest something that fits your life | Find suitable family activities or propose a next step for a current goal. | Partial. Uses goals and preferences to prepare suggestions; there is no complete calendar-planning workflow. |
| Pick out things worth reading | Collect articles and updates around your interests, ready when you want them. | Partial. Creates a local Feed with search and feedback, without a dedicated Feed page. |
| Adjust to feedback and stop | Respond differently to “done,” “later” and “stop bringing this up.” | Supported. Records completion, snoozes and topic opt-outs; temporary interests expire, and reminder hours and frequency are limited. |
| Handle everyday errands | Call customer service, make a booking or place an order, handing back when needed. | Not covered. This plugin has no calling, booking or payment workflow. |

Examples range from [helping someone keep a daily writing routine](https://www.reddit.com/r/MetaAI/comments/1whc17p/my_experience_using_muse/) to [waiting on a customer-service phone line](https://www.reddit.com/r/MetaAI/comments/1wqaj5c/muse_is_fucking_amazing/). These are individual reports, not guarantees that every account gets the same result.

Other users report [reminders about things already resolved](https://www.reddit.com/r/MetaAI/comments/1wpdcdd/it_was_great_until_it_wasnt/). That makes feedback and stopping part of the feature set too. This project does not promise perfect recall or zero repetition.

“Supported” means the corresponding workflow is in place. Memory upkeep, factual checks and suggestion quality depend on the configured model and tools; real models and messaging channels still need acceptance testing. See the [implementation coverage](docs/FEATURE-COVERAGE.md) for specific limits.

## Four recurring Cron jobs

| Job | Default schedule | Output |
| --- | --- | --- |
| muse-proactive-watch | Every 30 minutes | Reminder candidates, evidence and delivery records |
| muse-memory-upkeep | Hourly | New facts and people/group notes |
| muse-nightly-review | Daily at 03:20 | Alignment, goal research, Ideas and skill review |
| muse-feed-pulse | Hourly | Local Feed articles |

Schedules use the current Hermes timezone. Watches with an explicit expiry stop when due. Specific reminders, watches and notice deliveries can create additional recorded Cron jobs; four is the permanent job count.

Pre-run scripts skip the model when there is no eligible work. An hourly Feed tick does not require an article on every run.

## Files

The root is the active profile's `HERMES_HOME`, usually `~/.hermes`.

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # code, Skill, prompts and templates
├── muse/
│   ├── install.json                # job IDs and owned files
│   ├── install.lock
│   ├── state.db                    # interests, notices, budgets and Feed index
│   ├── AGENTS.md
│   ├── TOOLS.md
│   ├── PROACTIVE_PREFERENCES.md
│   ├── memory/
│   │   ├── YYYY-MM-DD.md
│   │   ├── people/INDEX.md, <person>.md
│   │   └── groups/INDEX.md, <group>.md
│   ├── dreams/
│   │   ├── YYYY-MM-DD.md
│   │   └── alignment/derived/ALIGNMENT_SYNTHESIS.md
│   └── workspace/
│       ├── goals/<slug>/GOAL.md, files/, hidden_files/
│       └── your_files/feed/<id>.md
├── scripts/hermes-muse-*.py         # native Cron entrypoints
├── memories/USER.md, MEMORY.md      # existing native memory, when used
└── cron/                           # scheduling and execution records owned by Hermes
```

The memory, dreams and goal directories borrow Muse's organization. The ownership record, SQLite state, Feed storage and native memory paths are Hermes adaptations. Notes and goal files are created when needed.

Installation does not rewrite Hermes core, SOUL, native USER/MEMORY files, user project AGENTS files or the global system prompt. During use, the assistant saves new facts through existing memory tools.

Conversation hooks keep short user excerpts for upkeep. Unprocessed excerpts remain until maintenance succeeds; processed history is bounded. The plugin collects no telemetry and excludes group chats from personal companion workflows. See [SECURITY.md](SECURITY.md) for data scope.

## Use

State a goal, request monitoring or give feedback in normal conversation. For example:

```text
Create a bicycle-purchase goal, with a budget of $1,000 and a decision by month-end.
Check for a reply to this message until Friday.
This reminder is done.
Stop reminders about this topic.
List my current goals, interests and pending reminders.
Search my Feed for urban gardening articles.
```

The model identifies goals/interests and calls the state tool to record them. Formal goals require an explicit request. Temporary interests expire after 14 days by default and do not automatically create permanent monitoring. New user input can renew an interest; the assistant’s own research cannot. Without a notification route, candidates stay local. Ask the assistant to call `muse_manage status` for current records.

## Remove

```sh
hermes plugins remove hermes-muse
```

Then ask Hermes to clean the associated tasks:

> Read this profile's muse/install.json. Pause and remove its recorded Cron jobs, check anything still running, and remove the recorded scripts/hermes-muse-* entrypoints. Keep goals, articles, notes and memories, and report any incomplete cleanup.

Native remove does not guarantee cleanup of plugin-created Cron jobs. Leftover entrypoints go silent after deletion or disabling; already running work still needs checking. Reinstallation retains data, and ordinary reload does not resume tasks the user paused.

## Development and verification

```sh
python -m unittest discover -s tests -v
# In a Hermes environment:
python tests/native_smoke.py
hermes plugins validate . --json
```

Tests use temporary profiles without real model calls or messaging channels. The [acceptance guide](docs/ACCEPTANCE.md) lists checks for an actual installation.

The [official catalog application](https://github.com/NousResearch/hermes-agent/pull/134976) is pending review. Install from the repository address above in the meantime.

MIT licensed.
