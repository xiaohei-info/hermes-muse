# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance guide](docs/ACCEPTANCE.md)

Hermes Muse is a personal assistant plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent), inspired by [Meta's Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/). It adds goal tracking, proactive reminders, background research, memory upkeep and a local Feed.

It uses Hermes memory, Cron, Skills and subagents with the user's existing model, memory backend and messaging configuration. Hindsight, Obsidian and other named services are optional. This is an independent project, unaffiliated with Meta/Muse; its code and prompts are independently written.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Requires Hermes 0.21.5 and the relevant plugin APIs; see the [tested baseline](docs/ACCEPTANCE.md). First load creates the workspace and registers one Skill and one state tool, and configures the system rules and four recurring Cron jobs from five prompt files. There is no feature selection or separate initialization command. Without a running host, loading happens at the next Hermes start.

The system prompt section takes effect in new conversations. Background execution requires a running scheduler and an available model. Research and content generation use the existing model and tools at their normal cost.

## Muse feature coverage

The tables describe the current code, Skill and Cron setup. Individual connector operations are grouped together.

- Implemented: plugin code or a native API integration exists.
- Configured: a Skill/Cron prompt procedure exists; the model and available tools do the work.
- Partial: some support exists; the remaining limits or prerequisites are listed.
- Not covered: this plugin has no corresponding implementation.

Configured procedures are not programmatic guarantees of model behavior. Actual models and channels still require acceptance testing.

### Goals and proactive reminders

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Goals, one level of subgoals and progress | Implemented | GOAL.md stores state; goals can be completed, cancelled and reopened. |
| Goal-owned watches and closure | Implemented | Records native Cron IDs; closing a goal pauses future watches and retires related Ideas while retaining pending final results. |
| One-off and recurring reminders | Implemented | Uses native Hermes Cron; background execution requires an available scheduler and model. |
| Polling mail, prices and progress | Configured | Watch procedures are provided; the model queries whichever source tools are available. |
| Finding useful opportunities to notify | Configured | proactive-watch reads goals, interests and research; the model judges relevance and new value. |
| Checking original evidence and current state | Configured | Prompts require source checks. Code checks verification time, expiry and owner state, not factual truth. |
| Main-conversation review of background evidence | Partial | Hands off when the source session exists and Hermes permits injection; otherwise uses native Cron delivery. |
| Deduplication across sources | Partial | Equal event keys cannot be queued concurrently; semantic duplicates still require model judgment. |
| Expiry, quiet hours and frequency limits | Implemented | Checks hours, budgets, topic blocks, owner state and expiry before dispatch. |
| Reminder feedback | Implemented | Separate actions for done, dismiss, snooze and stop-topic; the model interprets the user reply. |
| Explaining a reminder | Implemented | Stores sources, related items and rationale; recent records are available through the state tool. |
| Disclosure of background changes | Partial | Prompts require progress notes and disclosure; there is no separate comprehensive change audit. |
| Execution and delivery tracking | Partial | Links native execution and delivery records; no cross-channel exactly-once or phone read guarantee. |

### Memory and ongoing maintenance

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Assistant identity and user preferences | Partial | Preserves Hermes SOUL and user data, adds reminder preferences; no Muse identity editor. |
| Retaining tool experience | Configured | TOOLS.md records confirmed sources; the Skill directs the assistant to reuse existing knowledge and skills. |
| Long-term memory, retrieval and correction | Configured | Uses the current Hermes memory tools; no additional memory backend is supplied. |
| People and group notes | Configured | The hourly upkeep procedure updates notes and indexes from new user information. |
| Nightly reflection, alignment and repair | Configured | Provides procedures for dreams and ALIGNMENT_SYNTHESIS.md; synthesis quality depends on the model. |
| Upkeep after a conversation goes quiet | Implemented | For user messages of at least 80 characters, waits five minutes after the reply; new input resets it, with at most three triggers/day. |
| Skill learning and review | Configured | Nightly instructions use existing skill tools or Curator; no separate optimization engine. |
| Complete forgetting and prevention of reconstruction | Partial | Removes owned records and some indexed derivatives; other notes, history, backups and external memory require further checks. |
| Importing another assistant's memory | Not covered | No import workflow. |

### Feed, research and task execution

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Personalized Feed writing | Configured | A scheduled procedure writes sourced articles from interests, the brief and feedback, without announcing them. |
| Feed search, ordering, feedback and deletion | Implemented | Local articles and a SQLite index, operated through chat; changing the brief can wake the writer job. |
| Dedicated Feed page and cards | Not covered | No additional desktop or mobile Feed UI. |
| Idea selection, acceptance and retirement | Partial | Has storage, 14-day expiry, feedback and goal closure; selection and task conversion use the model, with no card action UI. |
| Goal research, briefings and letters | Configured | The nightly procedure studies selected goals and saves evidence/briefings; no separate goal-research scheduler. |
| Conversation alongside background tasks | Implemented | Uses the native asynchronous subagent API while the main conversation continues. |
| Nested coordinator/worker delegation | Not covered | The plugin research tool launches leaf tasks, without a nested coordinator. |
| Wide parallel research | Partial | Up to three concurrent leaves and 24 questions, one retry for failed items; research_status must advance subsequent waves. |
| Task state, stopping and restart recovery | Partial | Stores handles/results and checks cancellation when polled. Tasks lost across processes become unknown, without automatic resumption. |
| Browser task execution | Partial | Can use the host's browser tools; the plugin adds no browser executor. |
| Browser pause for login/CAPTCHA and resume | Not covered | No persistent browser-task pause/resume mechanism. |
| Reports, documents and interactive applications | Partial | Provides goal output directories and uses Hermes for generation; no Muse Library or app surface. |
| Scheduled updates of dynamic pages | Not covered | No page-action service equivalent to space_action. |

### Channels and external services

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Multiple conversations and reply routing | Partial | Records source sessions/routes, subject to client support. Personal companion workflows exclude group chats. |
| Interactive questions and approval cards | Partial | Uses existing Hermes questions and approvals; no additional Muse components. |
| Mobile notifications and user availability | Partial | Uses configured messaging channels; no Muse app or cross-device foreground/busy-state awareness. |
| Mail, calendar, drive and other connectors | Partial | Reuses connected tools; does not ship Muse's connector services or full service-specific skill collection. |
| Device control and health data | Not covered | No device pairing, phone control or health-data service. |
| Images, audio, video and podcasts | Partial | Host media tools remain available; the plugin adds no media-production workflow. |
| Phone calls, SMS and live voice calls | Not covered | No calling, SMS or live-voice service integration. |
| Shopping, booking and payments | Not covered | No transaction workflow or Muse Wallet integration. |
| Permissions, credentials and independent security review | Partial | Uses Hermes approvals and authorization; no Muse Sentinel or separate secure VM. |
| Avatar editing | Not covered | No avatar tool or UI. |
| Invitations, subscriptions and product operations | Not covered | No Muse commercial-service backend. |

### System tasks whose behavior is unverified

| Muse task | Known information | Treatment here |
| --- | --- | --- |
| heartbeat | Runs every 30 minutes; the original checklist was unavailable | Uses its own proactive-watch procedure, not a verified equivalent |
| deterministic-doctor | Runs hourly; checks and repair behavior are unknown | No corresponding diagnostic job |
| profile-image | Runs every 168 hours; its actions are unknown | No corresponding job |

The 14-day temporary-interest expiry and 30-day research review for undated goals are this project's rules, not verified Muse defaults. A new user signal can renew an interest; assistant research and old memories cannot. A research review does not automatically cancel an explicitly promised reminder.

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

The model identifies goals/interests and calls the state tool to record them. Formal goals require an explicit request; temporary interests do not automatically create permanent monitoring. Without a notification route, candidates stay local. Ask the assistant to call `muse_manage status` for current records.

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
