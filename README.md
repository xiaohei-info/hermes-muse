# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance guide](docs/ACCEPTANCE.md)

This project was inspired by [Meta's Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) and its approach to proactive interaction. I wanted to bring that kind of personal agent to [Hermes](https://github.com/NousResearch/hermes-agent): one that follows up on goals between conversations, brings back useful findings, and knows when to stop.

A passing interest should fade if I never return to it. An agreed reminder should still happen. When I say a task is done, the assistant should stop checking on it. And I should be able to ask why it brought something up.

Hermes already has memory, Skills, Cron and background tasks. This plugin connects them into those everyday workflows. It installs one Skill, four recurring jobs, five prompt files and a small state tool. It uses the model, memory and services you already have connected; Hindsight, Obsidian and any particular chat platform are optional.

The code and prompts are independently written. This project is unaffiliated with Meta or Muse and does not reproduce all of Muse's features.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Use Hermes 0.21.5 or a newer version with the plugin APIs listed in the [acceptance guide](docs/ACCEPTANCE.md). Hermes runs its normal source and security checks during installation. The plugin needs no extra Python packages or credentials.

Setup happens when Hermes first loads the plugin, either through a running host's reload or at the next start. It creates the companion workspace in your current profile, registers the Skill and prompt section, and adds the four Cron jobs. You do not need to choose features or paths, or run a second setup command. Existing workspace documents stay intact.

Start a new conversation to pick up the system prompt section. Hermes keeps an existing conversation's cached system prompt unchanged. The scheduler must be running, and its model must be available, for background work to execute.

Installation does not change Hermes core, SOUL, native USER/MEMORY files, project AGENTS files or the global system prompt. During use, the assistant can save new facts through your existing memory tools.

## Using it

Talk to Hermes as usual. For example:

- "I want to choose a bicycle this month. My budget is ..."
- "I've been curious about urban gardening lately."
- "Check for a reply to this message until Friday."
- "Why did you remind me?" or "Not this time."
- "I've bought the bike. You can stop looking."
- "Show me the gardening posts in my Feed."

A casual mention becomes a temporary interest, normally lasting 14 days. Only something you say later can renew it. The assistant's own research or a fresh news story cannot keep that interest alive indefinitely. An explicit goal has progress, completion criteria and a review date; an undated goal reaches a research review after 30 days. That review does not cancel a reminder you asked for.

Completing or cancelling a goal stops its future watches and retires related Ideas. A final result that still needs to reach you remains tracked. "Done", "not this time", "later" and "stop mentioning this topic" have different effects, so the assistant can act on your feedback without treating every dismissal as a permanent preference.

You can ask "What is Hermes Muse tracking?" to see current goals, interests, reminders and task IDs. Normal use does not require learning tool arguments.

## Background work

| Job | Default schedule | What it does |
| --- | --- | --- |
| muse-proactive-watch | Every 30 minutes | Looks for relevant changes, checks the evidence and decides whether a reminder is useful. |
| muse-memory-upkeep | Hourly | Saves new confirmed facts and updates people/group notes after actual user conversation. |
| muse-nightly-review | Daily at 03:20 | Reviews recent interactions, updates alignment, researches selected goals and reviews Ideas and skills. |
| muse-feed-pulse | Hourly | Writes a sourced article when there is something worth adding to the Feed. |

Jobs inherit your Hermes timezone and model. A small script skips an empty run before calling the model. Research and article generation use your usual model and source tools, with their normal costs. The hourly Feed job is an opportunity to write, not a quota.

After a substantial conversation goes quiet, a short timer can bring the existing memory job forward. A new message resets the timer, and it can trigger at most three times a day. This measures activity in Hermes; it does not know whether you are busy elsewhere.

Explicit watches, promised reminders and notice delivery may add temporary native jobs. The plugin records their IDs in `muse/install.json` so goal completion and uninstall cleanup can find them. A passing interest does not create a permanent watch.

## Reminders, Feed and research

Before a prepared reminder is dispatched, the plugin checks its expiry, owning goal or interest, topic preferences, quiet hours and daily budget. Equal event keys share a transaction, so two workers cannot queue the same event independently. Recognizing two differently worded sources as the same event still depends on the assistant's judgment.

Messages use the recorded source conversation or a single configured home destination. If neither is available, the reminder stays pending for local review. The plugin can ask the original conversation to reconsider background evidence when Hermes already allows session injection; otherwise it uses native Cron delivery. It does not grant itself that permission.

The delivery record distinguishes preparation, queueing, dispatch and the transport's reported outcome. An uncertain or partial send is not automatically repeated. A transport reporting success does not prove that your phone displayed the notification or that you read it.

Feed articles stay local until you ask to read them. Through chat, you can list, search, reorder, discuss or delete them, and change the brief for future posts. The assistant records explicit feedback; opening an article is not treated as liking it. There is no separate native Feed tab in this release.

For independent research questions, the plugin uses Hermes subagents in groups of up to three. The assistant collects results and advances the next group with `research_status`, while the main conversation remains available. It reports missing results and retries a failed research item once. A task lost after a host restart stays unknown rather than being silently recreated.

Browser pause/resume, phone calls and device services are outside this release. They still depend on what your own Hermes installation supports.

## Files and memory

Everything belongs to the current Hermes profile:

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # code, Skill, five prompts and templates
├── muse/
│   ├── install.json                # owned jobs and launcher files
│   ├── install.lock                # prevents concurrent setup
│   ├── state.db                    # interests, notice state, budgets and Feed index
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
├── scripts/hermes-muse-*.py         # entrypoints required by native Cron
├── memories/USER.md, MEMORY.md      # existing native memory, when in use
└── cron/                           # Hermes scheduling and execution records
```

The `memory`, `dreams` and goal directories borrow Muse's organization. The ownership record, SQLite state, Feed storage and native memory paths are adaptations for Hermes. Notes and goal files appear when there is something to put in them; a fresh install contains no invented personal history.

Conversation hooks keep short user excerpts for upkeep. Unprocessed excerpts stay until maintenance succeeds; processed history is bounded. Lasting facts go through your existing memory provider. The plugin does not collect telemetry, and it keeps personal companion state out of group conversations. More detail is in [SECURITY.md](SECURITY.md).

If you ask to forget something, the assistant first stops related work, removes owned records and indexed derivatives, then checks other notes and the available memory tools. It must report any history, backups or external indices it cannot verify as deleted.

## Remove

```sh
hermes plugins remove hermes-muse
```

Then ask your remaining Hermes assistant:

> Read this profile's muse/install.json. Hermes Muse is removed. Pause and remove only its recorded Cron jobs, including goal watches and delivery jobs. Check anything still running, and remove the recorded scripts/hermes-muse-* entrypoints. Keep my goals, Feed, notes and memories. Tell me if any work is still running or has an unknown outcome.

Hermes's native remove does not guarantee a callback to clean a plugin's Cron jobs, which is why this second step exists. Leftover launchers go silent after removal or disabling; an already running job still needs checking.

Reinstalling keeps your data and repairs missing owned jobs. Reloading respects tasks you intentionally paused. Delete the retained `muse/` directory only if you also want to erase that data.

## Development

```sh
python -m unittest discover -s tests -v
# In a Hermes environment:
python tests/native_smoke.py
hermes plugins validate . --json
```

Tests use temporary profiles and do not send messages through your accounts. The [acceptance guide](docs/ACCEPTANCE.md) covers checks with your actual model and channels; automated tests cannot establish their behavior on your behalf. See the [design document](docs/DESIGN.md) for the file and task responsibilities.

Install and update through Hermes's official commands. The plugin has no self-updater. GitHub releases are available directly; the [official catalog application](https://github.com/NousResearch/hermes-agent/pull/134976) is pending review.

MIT licensed.
