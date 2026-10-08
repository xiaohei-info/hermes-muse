# Hermes Muse

[简体中文](README.zh-CN.md) · [Design](docs/DESIGN.md) · [Acceptance checks](docs/ACCEPTANCE.md)

An independent, provider-neutral companion assembly for [Hermes Agent](https://github.com/NousResearch/hermes-agent): persistent goals, expiring interests, considered reminders, memory upkeep, nightly reflection, silent Feed and background research.

**One Skill, four recurring jobs, one state tool.** Install the whole assembly or remove it. It reuses your Hermes model, timezone, memory and connected tools. No required Hindsight, Obsidian or chat platform. No core patches, copied identity or SOUL replacement.

This is an independently written project inspired by Muse-like workflows, not an official Muse product or a distribution of Muse's code/prompts.

## Install

```sh
hermes plugins install xiaohei-info/hermes-muse --enable
```

Use a recent Hermes with plugin Skills, `register_system_prompt_section`, lifecycle hooks and native script-gated Cron (tested against 0.21.5 locally and the public upstream baseline recorded in [acceptance](docs/ACCEPTANCE.md)). Installation uses Hermes's normal source/security review. The plugin has no credentials or third-party Python dependencies to configure. Unsupported API versions report an error; they are not patched.

On the first actual plugin load (live host reload, or your next Hermes start), it:

1. Creates missing companion templates and a private state database in the active profile's `muse/` directory. Existing documents are preserved.
2. Registers `hermes-muse:companion`, `muse_manage`, a bounded system prompt section, and conversation hooks.
3. Creates four native Cron jobs and their small native `scripts/` entrypoints; records ownership and actual IDs in `muse/install.json`.
4. Starts using your current Hermes tools/model when work is due. A running Hermes scheduler and a usable model are still necessary. Installation itself makes no model calls.

No install wizard, custom path, feature selection or separate initialization command. Opening a new conversation picks up the system section; Hermes intentionally freezes an existing conversation's cached system prompt.

## Use

Talk normally. Examples:

- “I want to choose a bicycle this month. My budget is …”
- “I'm curious about urban gardening.” — a temporary interest, not a permanent watch.
- “Check for a reply to this message until Friday.” — an explicit, bounded goal-owned watch.
- “Why did you remind me?” / “Done.” / “Not this time.” / “Remind me tomorrow.” / “Stop mentioning this topic.”
- “Show my Feed about gardening.” / “More technical posts like this one.” / “Delete this article.”
- “What is Hermes Muse tracking?” / “Forget this interest and its derived notes.”

`muse_manage status` (asked through the assistant) exposes current records and installed task IDs. There is no new mandatory slash command or external dashboard.

## What runs

| Native Cron | Default schedule | Behavior |
| --- | --- | --- |
| muse-proactive-watch | Every 30 minutes | Read active context/evidence, verify relevance, select notices. Ordinary sends have a separate waking-hours/budget check. |
| muse-memory-upkeep | Hourly | Incremental confirmed facts and people/group notes only after new real user signal. |
| muse-nightly-review | Daily 03:20 | Reflection/repair, alignment, bounded goal research/Ideas, skill review and lifecycle cleanup. |
| muse-feed-pulse | Hourly | Opportunity for an original sourced article; silent, no forced article quota. |

Schedules use the existing Hermes timezone and default model/provider. Script gates skip empty work before an LLM call. Active research/Feed work can still consume model tokens and source-tool fees. After substantial conversation quiets, a capped debounce advances the existing memory job; it does not add a fifth recurring job.

Promised reminders/watches and prepared-message delivery use additional **owned, bounded native jobs** as needed. Their IDs are recorded for goal closure and uninstall. A candidate is not a subscription. No source, account or messaging platform is presumed connected.

## Lifecycle guarantees and limits

- Temporary interests/Ideas normally expire after 14 days. Only a new real user signal renews an interest; recall, Feed, research and cron runs cannot. Undated formal goals reach a 30-day research review boundary without being falsely marked completed.
- Equal event keys are deduplicated transactionally. Dispatch checks current expiry, owner state, blocked topics, waking hours, current Hermes activity and daily budget. Cross-source semantic sameness still requires model judgment.
- Goals have one level of subgoals; completion/cancellation stops owned future watches. An explicitly marked final result may still need delivery. A watch stopping cannot undo an external action already submitted.
- Notices use a recorded source route or one unambiguous configured native home destination. No channel means pending local review; no arbitrary broadcast. Main-session injection is attempted only when Hermes already permits it; the plugin never self-grants that permission. The native Cron route remains available otherwise.
- Prepared, queued, dispatching, host-reported sent and unknown are distinct. Phone display/read receipts are not promised. Unknown/partial sends are not blindly retried; semantic quality and external service delivery require real-world acceptance.
- Feed supports local articles, search, ordering, explicit feedback, explanation and deletion through chat. This release does not add a native Feed tab.
- Research reuses native async delegation. The structured research tool starts bounded waves; `research_status` collects them and advances the next wave. Host process loss yields unknown, not duplicate work. No browser pause/resume implementation is included.
- Forgetting removes owned indexed records/derivatives and stops associated work, then guides the assistant through actual native/external memory and file tools. Session histories, backups and arbitrary external indices are not silently claimed erased.
- Personal companion state is restricted to private/direct/local conversation use. The host's authentication, approval and external service boundaries remain in force.

## Files

```text
$HERMES_HOME/
├── plugins/hermes-muse/             # installed code, Skill, five prompts, templates
├── muse/
│   ├── install.json                # owned jobs and launcher files; survives removal
│   ├── install.lock                # cross-process initialization lock
│   ├── state.db                    # transactional operational state, not a memory provider
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
├── scripts/hermes-muse-*.py         # host-required entrypoints, recorded for cleanup
├── memories/USER.md, MEMORY.md      # existing native memory, not replaced
└── cron/                           # native host scheduling/execution/delivery stores
```

Installation never rewrites SOUL, native USER/MEMORY, user project AGENTS or the global system prompt. During use, the assistant may update confirmed facts through your existing memory tools. The retained Muse-like layout is an organizational convention; `install.json`, state.db, native memory paths and Feed storage are Hermes-specific adaptations. Dynamic goal/relationship/article files appear when there is actual content.

## Remove

```sh
hermes plugins remove hermes-muse
```

Then ask your remaining Hermes assistant:

> Read the current profile's muse/install.json. Hermes Muse is removed. Pause and remove only its recorded native Cron jobs, including goal watches and delivery jobs. Check in-flight tasks. Remove only its recorded scripts/hermes-muse-* entrypoints. Keep my goals, Feed, notes, memories and other user data; report anything still running or uncertain.

Hermes's native remove does not guarantee a plugin-owned Cron cleanup callback. Launchers left behind become silent when the plugin is removed/disabled, so they do not start new model work. A run already in flight needs the explicit check above. Reinstall preserves user data and repairs missing owned jobs; reload preserves intentionally paused tasks. Delete the retained `muse/` data only when you explicitly want to erase it.

## Develop and verify

```sh
python -m unittest discover -s tests -v
# With a Hermes environment (no model or live channel required):
python tests/native_smoke.py
hermes plugins validate . --json
```

All tests use temporary profiles. See [design](docs/DESIGN.md), [acceptance](docs/ACCEPTANCE.md) and [security scope](SECURITY.md). The repository has no self-updater: use Hermes's official update/install commands. GitHub releases are installable immediately; official catalog listing requires a separate maintainer-reviewed exact-SHA submission.

MIT licensed. Contributions should preserve the single-install experience and provider independence.
