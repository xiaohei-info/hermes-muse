# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance guide](docs/ACCEPTANCE.md)

Hermes Muse is a personal assistant plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent), inspired by the proactive interactions in [Meta's Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/). It follows up on things you care about after the conversation ends, and gets in touch when something needs your attention.

It uses Hermes memory, Cron, Skills and subagents with the user's existing model and memory backend. Reminders go to the current profile's Bot Chat. Hindsight, Obsidian and other named services are optional. This is an independent project, unaffiliated with Meta/Muse; its code and prompts are independently written.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Installation uses the selected profile. Use `hermes -p default plugins install xiaohei-info/hermes-muse --enable` for default, or replace `default` with a profile name such as `architect`. Each enabled profile gets its own state, six jobs and Bot Chat delivery; omitting `-p` follows the current profile selection.

If you maintain explicit `platform_toolsets` lists, include `muse` in the platforms where you use the plugin. An enabled plugin can otherwise load its prompts while its state tool remains unavailable.

Requires Hermes 0.21.5 and the relevant plugin APIs; see the [tested baseline](docs/ACCEPTANCE.md). First load creates the workspace, registers one Skill, one state tool and four conversation hooks, adds one system prompt section, and creates six recurring Cron jobs. There is no feature selection or separate initialization command. Without a running host, loading happens at the next Hermes start.

The system prompt section takes effect in new conversations. Background execution requires a running scheduler and an available model. Scheduled checks, research and content generation use the existing model and tools at their normal cost.

## Feature comparison

The plugin sets up its jobs and rules on first load, using the existing Hermes model and sources, with notifications handled in the current profile's Bot Chat.

| Muse feature | Native Hermes | With Hermes Muse |
| --- | --- | --- |
| Remember preferences and recent context | Built-in memory and user notes retain facts. Scheduled relationship upkeep and nightly review need their own setup. | Memory upkeep is ready to use: conversations, sourced facts and task outcomes inform relationship notes. A separate nightly review carries useful lessons into later conversations. |
| Notice important changes | Cron, session heartbeats and messaging are built in. You configure what to watch, when to notify, deduplication and frequency limits. | A ready-to-use patrol checks connected mail, calendars, reminders and devices, then weighs changes against your recent context. Weather, travel and interest news can prompt a message when they are useful. |
| Follow goals over time | Persistent tasks and a task board are built in. You organize long-term goals, progress, related watches and stopping conditions. | Follow plans agreed in conversation across days and close them on verified outcomes. Closing a goal stops its watches while keeping any final result awaiting delivery. |
| Prepare work in the background | Asynchronous subagents are built in. You configure which goals to research regularly and how to save and use the results. | Independent multi-step work goes to native asynchronous subagents while the main conversation stays available. Research batches finish and return without repeated status requests. |
| Offer relevant suggestions | Can suggest next steps using conversation and memory. Ongoing research, selection and storage need their own setup. | Prepares suggestions from goals and verified personal context, records evidence and feedback, and leaves new proposals for the user to choose. Accepted work keeps moving. |
| Personalized Feed | Search, writing and scheduled tasks are available. You assemble topic selection, article records, feedback and updates. | A local Feed is ready to use: existing memory, interests and feedback guide quiet article generation without requiring a saved goal. Search, discuss or delete articles through chat. |
| Adjust reminders and stop following up | Can update preferences and stop jobs. You define how feedback affects reminders, goals and watches. | “Done,” “later” and “stop bringing this up” have distinct effects. Completion, cancellation or rescheduling prompts a fresh check of pending reminders; temporary interests expire after 14 days. |
| Handle everyday errands | Can use browser and external tools. Calling, booking and payment services and workflows need to be connected and configured. | The plugin does not supply calling, booking or payment workflows. Existing tools remain available. |

Feed has no dedicated page. New research batches use native Hermes execution and result callbacks; restart recovery depends on the host, and unknown outcomes are never automatically replayed. Memory upkeep, verification and writing depend on the configured model and tools; see the [implementation details](docs/FEATURE-COVERAGE.md).

## Skill and tool

| Name | Purpose |
| --- | --- |
| [hermes-muse:companion](skills/companion/SKILL.md) | Shared procedures for conversations and background jobs: connection and device checks, goals and interests, reminders and feedback, memory and relationships, Feed, delegation, and weekly/monthly reviews. |
| muse_manage | Lets the assistant record and query source checks, goals, interests, reminders, feedback, Feed and research progress, keep source progress by connection, account and resource, distinguish complete, partial and failed checks, and maintain expiry, stopping and delivery state. |

The Skill is registered with the plugin and its files stay in the plugin directory. Conversations load the relevant procedure as needed; all six recurring Cron jobs use the same Skill. Use normal conversation and let the assistant call the tool.

## Prompts

The plugin includes eight prompt files:

| File | Purpose |
| --- | --- |
| [receiving.md](prompts/receiving.md) | Shared Bot Chat handoff: turn internal findings into a direct response to the user, without acknowledging the job or creating another reminder. |
| [system.md](prompts/system.md) | Keep the main conversation available for new input and coordination; delegate independent multi-step work and retain unfinished commitments. |
| [proactive-watch.md](prompts/proactive-watch.md) | Discover available connections/devices, check changes and approaching deadlines, record source coverage, then verify and notify or remain silent. |
| [memory-upkeep.md](prompts/memory-upkeep.md) | Process new conversations, sourced facts and task outcomes; update memory, relationships and processing progress. |
| [nightly-review.md](prompts/nightly-review.md) | Review conversations independently of hourly upkeep; update alignment, research goals and suggestions, check closure, and review working lessons and skills. |
| [feed-pulse.md](prompts/feed-pulse.md) | Use native memory, preferences, current context and real sources to choose topics; quietly write only when there is new value. |
| [weekly-governance-review.md](prompts/weekly-governance-review.md) | Review outcomes and effort, missed sources, unfinished work and repeated reminders; suggest next-week adjustments. |
| [monthly-system-audit.md](prompts/monthly-system-audit.md) | Check whether instructions and recurring work still help, look for duplicate workflows and work that should have stopped, and suggest simplifications. |

Hermes appends `system.md` after the memory section through its plugin API; it takes effect in new conversations. `receiving.md` accompanies Bot Chat results and is also used by the receiving conversation hook. The six task files become the corresponding Cron job prompts and are used when those jobs run. Each plugin load refreshes these job prompts while preserving the user's schedule, model and pause settings.

## Conversation hooks

| Hook | Purpose |
| --- | --- |
| pre_llm_call | Before the reply, records a short user excerpt and its source session, and adds a state-tool pointer to the current turn for goals, interests and feedback. |
| post_llm_call | After replying to a user message of at least 80 characters, waits for five quiet minutes before scheduling memory upkeep. New input cancels the pending timer; at most three early triggers per day. |
| transform_llm_output | For a patrol/watch that used the state tool, replaces the final response with approved notice bodies or `[SILENT]`. Bot Chat notices and weekly/monthly reports include the same receiving guidance. Ordinary conversations and direct channel reports are unchanged. |
| on_session_end | Clears the current turn's busy flag so later reminders do not keep waiting on a conversation that has ended. |

User-signal hooks process private and local conversations, skipping groups, Cron, subagent input and completion callbacks. Older misclassified background messages remain as audit evidence outside the user-signal inbox. The output hook is bound to the current owned patrol/watch or governance execution; it does not modify ordinary replies. Delayed upkeep uses the existing memory Cron job. Unloading the plugin from the running process cancels its temporary timers.

## Six recurring Cron jobs

| Job | Default schedule | Output |
| --- | --- | --- |
| muse-proactive-watch | Every 30 minutes | Source coverage, worthwhile reminders, evidence and delivery state |
| muse-memory-upkeep | Hourly | New facts and people/group notes |
| muse-nightly-review | Daily at 03:20 | Alignment, goal research, Ideas, working lessons and skill review |
| muse-feed-pulse | Hourly | Local Feed articles |
| muse-weekly-governance-review | Sunday at 21:15 | A concrete review of usefulness, execution and proposed adjustments |
| muse-monthly-system-audit | First day of the month at 10:40 | A short audit of priorities, instructions and recurring work |

The plugin does not pin a model or provider on its recurring jobs. Hermes resolves the model at each run: **per-job model → current profile’s `cron.model` → profile’s main model**. Without a Cron default, hourly background work can use the same expensive model as your main conversation. Set a background model before leaving the scheduler running.

For example, merge this into the current profile’s `config.yaml`, using a model and provider available in your installation (`llm` here is a configured provider name):

```yaml
cron:
  model: gpt-6-luna
  model_provider: llm
agent:
  reasoning_overrides:
    gpt-6-luna: high
```

Hermes currently resolves reasoning from a per-job `reasoning_effort`, then the model-specific override, then `agent.reasoning_effort`; `cron.reasoning_effort` is not a supported setting on the tested baseline. The example sets `high` for Luna in this profile, including ordinary conversations that use Luna. Existing per-job model/reasoning choices take priority and survive plugin reloads. Cron defaults are read on the next run. Bot Chat’s receiving turn uses its own conversation model configuration and adds another model call; `cron.model` does not select that receiving model. The plugin does not write these model settings for you.

Schedules use the current Hermes timezone. Watches with an explicit expiry stop when due. Explicitly requested timed reminders and watches can create additional recorded Cron jobs; six is the permanent job count. A patrol delivers approved notices in its own final response, with no extra delivery Cron. Deferred candidates stay for the next patrol. Delivery is checked against that execution’s persistent receipt, independently of later patrols.

All six fixed jobs call the model on schedule to inspect the information relevant to their work. Each patrol discovers available connections and devices and checks mail, calendars, reminders and other sources even without saved goals or interests. Each source reuses a stable record and a tested read recipe. Verified tool aliases reuse the established source record; duplicate observations are archived without advancing its successful checkpoint. Different accounts and collections stay separate. Reducing calls must preserve substantive content, sound judgment, proactive help, relevant context and timely follow-through. A failed read calls for diagnosis and recovery where possible in the same run; consequential gaps in ordinary monitoring can merit a notice even without a saved goal. A missing permission is checked before a protected query, and an unavailable source is never treated as an empty result. Expected and checked resources are recorded separately; a missing calendar, unfinished page or failed read cannot advance the successful checkpoint. Checks consume model calls; tools and subagents can add usage.

Pending reminders expose what blocks them and their earliest policy window, not a promised delivery time. New evidence can change urgency; genuine urgency bypasses ordinary quiet hours, while snoozes and topic opt-outs remain binding. A routine financial email alone does not establish an emergency. A patrol checks the facts and prepares useful help before deciding to interrupt. Examples include weather affecting a trip, a moved meeting, substantive news on an interest, or an event, exhibition or booking window relevant to a known plan. Location, dates and personal relevance need evidence; routine forecasts and repeated headlines do not merit a message. Nothing worthwhile means silence. Ordinary proactive messages focus on one useful item and do not chase a reply because the user stayed quiet. These are model instructions; judgment depends on the model and available sources.

Conversations and background work share goals, interests and feedback. Accepted work can continue across days and close on verified outcomes; criteria that require user confirmation still require it. Completed, cancelled or rescheduled items are rechecked so stale pending reminders can be retired. Renewing an interest requires new user input, never the assistant's own research; snoozing does not extend its original expiry.

Hourly upkeep and nightly review keep separate progress. Both drain the run’s initial backlog in the same run; 25 messages is a page size, not a work limit. New arrivals wait for the next run, and interrupted work retains its completed progress. Feed uses existing memory and current understanding; its hourly check does not require an article every time. Weekly and monthly jobs deliver reports at the depth their findings need; only the stored summary is capped at 2000 characters. They propose changes without applying them and do not run a separate Skill audit. Existing user-created reviews remain in place.

Bot Chat speaks to you about the finding, its real relevance and work already completed. It does not reply “received” to the background task or promise to investigate an already checked result. A question belongs only where your decision is needed; a remembered conversation must have evidence. The shared receiving prompt accompanies the delivered findings and is also used by the conversation hook. This guides the model’s response; it does not guarantee exact wording.

The latest review summaries are available through `muse_manage status`; full outputs stay in native Cron history. The next review can use them to check whether earlier suggestions led to useful changes.

## Files

The root is the active profile's `HERMES_HOME`, usually `~/.hermes`.

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # plugin code and resources
│   ├── skills/companion/
│   │   ├── SKILL.md                # shared procedures
│   │   └── references/             # goals, reminders, memory, Feed, research, governance, communication
│   ├── prompts/                    # the eight prompts listed above
│   └── templates/                  # initial workspace files
├── muse/
│   ├── install.json                # job IDs and owned files
│   ├── install.lock
│   ├── state.db                    # source checks, cursors, interests, notices, Feed, research, reviews
│   ├── AGENTS.md
│   ├── TOOLS.md                    # confirmed connections, devices and limits
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

Nightly review can also maintain a short Working lessons section in `muse/AGENTS.md`, merging duplicate methods and updating stale ones while preserving user-written conventions. Personal facts and task logs stay in memory and goal records. Existing installations add the section only when useful; the whole file is not replaced.

Installation does not rewrite Hermes core, SOUL, native USER/MEMORY files, user project AGENTS files or the configured `agent.system_prompt` value. During use, the assistant saves new facts through existing memory tools.

Conversation hooks keep short user excerpts for upkeep. Unprocessed excerpts remain until maintenance succeeds; processed history is bounded. The plugin collects no telemetry and excludes group chats from personal companion workflows. See [SECURITY.md](SECURITY.md) for data scope.

## Use

**Recommended: use Hermes Muse from the current profile's Bot Chat.** Discuss goals, interests and feedback there. When background work produces something worth bringing up, the bot picks it up:

`Cron prepares a result → delivers to this profile's Bot Chat → the bot reads it → replies to the user in chat`

Receiving the result runs an assistant turn on that profile's model. Hermes can create the Bot Chat on first delivery if it does not exist; its native queue handles a busy chat. Feed writing and routine upkeep stay silent. Selected reminders and scheduled weekly/monthly reports enter this delivery flow.

The official installer displays the plugin's after-install notes, but has no plugin-defined channel/session picker. This version uses Bot Chat by default and does not require an external channel such as Telegram.

Talk about plans, interests and feedback normally. Patrols do not require you to create a goal first. For example:

```text
Create a bicycle-purchase goal, with a budget of $1,000 and a decision by month-end.
Check for a reply to this message until Friday.
I’m visiting Hangzhou this weekend. Let me know if the weather changes enough to affect the trip.
I follow space exploration. Important developments are welcome; I don’t need a daily news digest.
This reminder is done.
Stop reminders about this topic.
List my current goals, interests and pending reminders.
Search my Feed for urban gardening articles.
```

The model identifies goals/interests and calls the state tool to record them. Goals need a clear user plan or commitment, without requiring the words “create a goal.” Temporary interests expire after 14 days by default and do not automatically create permanent monitoring. New user input can renew an interest; the assistant’s own research cannot. Delivery or model failures retain their state for inspection; there is no automatic resend to another channel. Ask what was checked, what failed or what remains open; the assistant can use `muse_manage status` to inspect the records.

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
