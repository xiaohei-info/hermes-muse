# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance guide](docs/ACCEPTANCE.md)

Hermes Muse is a personal assistant plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent), inspired by the proactive interactions in [Meta's Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/). It follows up on things you care about after the conversation ends, and gets in touch when something needs your attention.

It uses Hermes memory, Cron, Skills and subagents with the user's existing model and memory backend. Reminders go to the current profile's Bot Chat. Hindsight, Obsidian and other named services are optional. This is an independent project, unaffiliated with Meta/Muse; its code and prompts are independently written.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Requires Hermes 0.21.5 and the relevant plugin APIs; see the [tested baseline](docs/ACCEPTANCE.md). First load creates the workspace, registers one Skill, one state tool and three conversation hooks, adds one system prompt section, and creates four recurring Cron jobs. There is no feature selection or separate initialization command. Without a running host, loading happens at the next Hermes start.

The system prompt section takes effect in new conversations. Background execution requires a running scheduler and an available model. Research and content generation use the existing model and tools at their normal cost.

## Feature comparison

The plugin sets up its jobs and rules on first load, using the existing Hermes model and sources, with notifications handled in the current profile's Bot Chat.

| Muse feature | Native Hermes | With Hermes Muse |
| --- | --- | --- |
| Remember preferences and recent context | Built-in memory and user notes retain facts. Scheduled relationship upkeep and nightly review need their own setup. | Memory upkeep is ready to use: regular updates to recent context and relationship notes, plus nightly review. |
| Notice important changes | Cron, session heartbeats and messaging are built in. You configure what to watch, when to notify, deduplication and frequency limits. | Proactive reminders are ready to use: checks follow goals and interests, with source verification, delivery hours and frequency limits already set up. |
| Follow goals over time | Persistent tasks and a task board are built in. You organize long-term goals, progress, related watches and stopping conditions. | Create and follow goals in conversation. Progress and watches belong to the goal, and related checks stop when it closes. |
| Prepare work in the background | Asynchronous subagents are built in. You configure which goals to research regularly and how to save and use the results. | Scheduled goal research and briefing storage are set up. Research can run while the main conversation continues. |
| Offer relevant suggestions | Can suggest next steps using conversation and memory. Ongoing research, selection and storage need their own setup. | Regularly prepares suggestions for active goals, records candidates and feedback, and waits for the user to decide what to pursue. |
| Personalized Feed | Search, writing and scheduled tasks are available. You assemble topic selection, article records, feedback and updates. | A local Feed is ready to use: articles follow your interests, with search, feedback and deletion through chat. |
| Adjust reminders and stop following up | Can update preferences and stop jobs. You define how feedback affects reminders, goals and watches. | Say “done,” “later” or “stop bringing this up” to adjust reminders. Temporary interests expire after 14 days by default. |
| Handle everyday errands | Can use browser and external tools. Calling, booking and payment services and workflows need to be connected and configured. | The plugin does not supply calling, booking or payment workflows. Existing tools remain available. |

The Feed has no dedicated page. The plugin's batch research still needs the assistant to advance it and cannot resume across restarts. Memory upkeep, factual checks and content generation use the existing model and tools; see [implementation coverage](docs/FEATURE-COVERAGE.md) for specific limits.

## Skill and tool

| Name | Purpose |
| --- | --- |
| [hermes-muse:companion](skills/companion/SKILL.md) | Shared procedures for conversations and background jobs: goals and interests, reminders and feedback, memory and relationships, Feed, and research. |
| muse_manage | Lets the assistant record and query goals, interests, reminders, feedback, Feed and research progress, and handle expiry, stopping and delivery state. |

The Skill is registered with the plugin and its files stay in the plugin directory. Conversations load the relevant procedure as needed; all four recurring Cron jobs use the same Skill. Use normal conversation and let the assistant call the tool.

## Prompts

The plugin includes five prompt files:

| File | Purpose |
| --- | --- |
| [system.md](prompts/system.md) | Conversation rules: when to read the Skill and current state, record goals, handle feedback, verify reminders and delegate background work. |
| [proactive-watch.md](prompts/proactive-watch.md) | Look for relevant changes, check sources, prior reminders and expiry, then decide whether to notify. |
| [memory-upkeep.md](prompts/memory-upkeep.md) | Process new user information, update facts and relationship notes, and record what has been processed. |
| [nightly-review.md](prompts/nightly-review.md) | Update alignment notes, study active goals, prepare suggestions and review skills. |
| [feed-pulse.md](prompts/feed-pulse.md) | Write articles from interests and feedback, and save the content and index. |

Hermes appends `system.md` after the memory section through its plugin API; it takes effect in new conversations. The other four files become the corresponding Cron job prompts and are used when those jobs run. Each plugin load refreshes these job prompts while preserving the user's schedule, model and pause settings.

## Conversation hooks

| Hook | Purpose |
| --- | --- |
| pre_llm_call | Before the reply, records a short user excerpt and its source session, and adds a state-tool pointer to the current turn for goals, interests and feedback. |
| post_llm_call | After replying to a user message of at least 80 characters, waits for five quiet minutes before scheduling memory upkeep. New input cancels the pending timer; at most three early triggers per day. |
| on_session_end | Clears the current turn's busy flag so later reminders do not keep waiting on a conversation that has ended. |

These hooks process private and local conversations, skipping groups, Cron and subagent input. Delayed upkeep uses the existing memory Cron job. Unloading the plugin from the running process cancels its temporary timers.

## Four recurring Cron jobs

| Job | Default schedule | Output |
| --- | --- | --- |
| muse-proactive-watch | Every 30 minutes | Reminder candidates, evidence and delivery records |
| muse-memory-upkeep | Hourly | New facts and people/group notes |
| muse-nightly-review | Daily at 03:20 | Alignment, goal research, Ideas and skill review |
| muse-feed-pulse | Hourly | Local Feed articles |

Schedules use the current Hermes timezone. Watches with an explicit expiry stop when due. Specific reminders, watches and notice deliveries can create additional recorded Cron jobs; four is the permanent job count.

Conversations and background upkeep share goals, interests and feedback records. Background work can continue from recorded user input; renewing an interest still requires a newer user signal, never the assistant's own output. Watches use native Hermes scheduling rules.

Pre-run scripts skip the model when there is no eligible work. An hourly Feed tick does not require an article on every run.

## Files

The root is the active profile's `HERMES_HOME`, usually `~/.hermes`.

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # plugin code and resources
│   ├── skills/companion/
│   │   ├── SKILL.md                # shared procedures
│   │   └── references/             # goals, reminders, memory, Feed, research
│   ├── prompts/                    # the five prompts listed above
│   └── templates/                  # initial workspace files
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

The memory, dreams and goal directories borrow Muse's organization. The ownership record, SQLite state, Feed storage and native memory paths are Hermes adaptations. First load adds missing workspace templates; goals, notes and articles are created during use. Reloading does not duplicate the recurring jobs.

Installation does not rewrite Hermes core, SOUL, native USER/MEMORY files, user project AGENTS files or the configured `agent.system_prompt` value. During use, the assistant saves new facts through existing memory tools.

Conversation hooks keep short user excerpts for upkeep. Unprocessed excerpts remain until maintenance succeeds; processed history is bounded. The plugin collects no telemetry and excludes group chats from personal companion workflows. See [SECURITY.md](SECURITY.md) for data scope.

## Use

**Recommended: use Hermes Muse from the current profile's Bot Chat.** Discuss goals, interests and feedback there. When background work produces something worth bringing up, the bot picks it up:

`Cron prepares a result → delivers to this profile's Bot Chat → the bot reads it → replies to the user in chat`

Receiving the result runs an assistant turn on that profile's model. Hermes can create the Bot Chat on first delivery if it does not exist; its native queue handles a busy chat. Feed writing and routine upkeep stay silent. Only selected reminders enter this delivery flow.

The official installer displays the plugin's after-install notes, but has no plugin-defined channel/session picker. This version uses Bot Chat by default and does not require an external channel such as Telegram.

State a goal, request monitoring or give feedback in normal conversation. For example:

```text
Create a bicycle-purchase goal, with a budget of $1,000 and a decision by month-end.
Check for a reply to this message until Friday.
This reminder is done.
Stop reminders about this topic.
List my current goals, interests and pending reminders.
Search my Feed for urban gardening articles.
```

The model identifies goals/interests and calls the state tool to record them. Formal goals require an explicit request. Temporary interests expire after 14 days by default and do not automatically create permanent monitoring. New user input can renew an interest; the assistant’s own research cannot. Delivery or model failures retain their state for inspection; there is no automatic resend to another channel. Ask the assistant to call `muse_manage status` for current records.

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
