# Hermes Muse design — v0.1.4

Status: implementation contract. This independent plugin assembles a long-term assistant using Hermes tools, memory, skills, cron and conversations. It does not modify Hermes core or require a particular model, memory provider, note app or messaging platform. All features are installed together in the active profile.

## Scope and provenance

Inspired by documented Muse behavior: goals and short-lived interests, evidence-based proactive reminders, nightly reflection, relationships, goal research, Ideas and a silent personalized Feed. All code, instructions and templates are independently authored. No private export, personal fact, credential, Muse service implementation or proprietary prompt is distributed. The familiar `memory/`, `dreams/alignment/derived/` and `workspace/goals/` layout is retained; native Hermes memory paths and the plugin bookkeeping below are deliberate adaptations. Browser pause/resume, phone/device services and a dedicated native Feed UI are outside this release.

Coverage percentages discussed during planning were estimates, not release quality measurements. Release acceptance is defined by observable behavior and tests.

## Installation and ownership

Entry: `hermes plugins install xiaohei-info/hermes-muse --enable`. The first actual plugin load performs locked, idempotent initialization. No model/network call occurs during registration. It creates missing templates without overwriting user documents, registers one Skill (`hermes-muse:companion`), one bounded system prompt section, a small state tool and hooks; creates four native Cron jobs; records their actual IDs and owned files in `muse/install.json`. A running Hermes scheduler is required for background execution. Repeated load/upgrade preserves edits and paused jobs, and never duplicates jobs. Interrupted initialization is reconciled by a plugin marker plus exact workdir/skill ownership, not job name alone.

Native uninstall: `hermes plugins remove hermes-muse`. Hermes has no guaranteed uninstall callback for deleting cron jobs. README instructs the user to ask their remaining Hermes assistant to pause/remove only job IDs in `muse/install.json`, inspect in-flight work and remove owned launchers. User data is retained. Every launcher checks that the plugin is still installed and enabled, and exits silently otherwise. Reload/unload only stops in-process timers, never erases user data or cancels persistent jobs merely because a process exits.

## Files and single sources of truth

Paths below are relative to the active `HERMES_HOME`; resolve per call or explicitly bind a captured profile for deferred work. Never use a process-global default home.

- `plugins/hermes-muse/`: immutable shipped code, `plugin.yaml`, `skills/companion/SKILL.md`, reference procedures, five `prompts/*.md`, clean templates.
- `memories/USER.md`, `memories/MEMORY.md`: native Hermes files, or the user's existing memory tools/provider. Installation does not write these or `SOUL.md` or replace `agent.system_prompt`.
- `muse/install.json`: version, installation identity, owned native job IDs and launcher paths; survives remove.
- `muse/state.db`: SQLite transactional operational state, NOT a replacement long-term memory service. Short-lived user signals/cursors, expiring interests/Ideas, notification reservations and outcomes, Feed index/feedback, source-session references and research job handles. Native Cron remains the authoritative execution ledger.
- `muse/AGENTS.md`, `muse/TOOLS.md`, `muse/PROACTIVE_PREFERENCES.md`: local responsibilities, actual source availability, editable attention/Feed preferences.
- `muse/memory/YYYY-MM-DD.md`, `muse/memory/people/INDEX.md`, `muse/memory/people/<slug>.md`, `muse/memory/groups/INDEX.md`, `muse/memory/groups/<slug>.md`: dated understanding and evidence-based relationship notes.
- `muse/dreams/YYYY-MM-DD.md`, `muse/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`: reflection, corrections, friction/repair and next behavior.
- `muse/workspace/goals/<slug>/GOAL.md`, `files/`, `hidden_files/`: one canonical goal record, final artifacts and working evidence. Existing external goals are referenced rather than independently declared complete.
- `muse/workspace/your_files/feed/<id>.md`: durable Feed articles; state.db owns indexing and feedback.
- `scripts/hermes-muse-*.py`: native Cron entrypoints, installed from plugin-owned code, recorded for cleanup. The scheduling host restricts scripts to this directory; symlink escapes are not used.
- Native `cron/jobs.json`, `cron/executions.db`, output and delivery records stay host-owned; use their APIs, never hand-edit them.

## Execution graph

Main conversation -> read Skill when relevant -> create/update goal or temporary interest, record explicit preference/feedback -> native memory and Muse files/state.

Research/nightly -> active goal files + user signals + actual connected tools -> evidence in hidden_files, Ideas, reflection and alignment -> proactive watch consumes the new evidence -> candidate -> recheck freshness/owner state/preferences/dedup -> native delivery -> reconcile outcome -> feedback/closure.

Feed -> current, unexpired interests + brief + live evidence -> authored local article + index -> user reads/discusses/reacts -> explicit feedback informs future selection. Reading alone never counts as liking. Feed itself sends no announcement.

## Scheduling

Exactly four fixed jobs, all inheriting host model/provider/timezone:

| Job | Schedule | Work |
| --- | --- | --- |
| muse-proactive-watch | */30 * * * * | Observe 24h, research relevant changes, verify candidates; ordinary delivery has its own waking-hour and daily budget gates. |
| muse-memory-upkeep | 0 * * * * | Incremental memory/relationships only after new real user signal. |
| muse-nightly-review | 20 3 * * * | Reflection/repair, goal research rotation, Ideas, skills review and lifecycle cleanup. |
| muse-feed-pulse | 0 * * * * | Opportunity to generate fresh content; not an article quota. |

Four pre-run gates skip empty work without an LLM call. Failed work does not advance a successful processing cursor. A quiet-pass timer after substantial conversation can advance the existing memory-upkeep job; a new user turn cancels/restarts it and attempts are capped at three/day. No fifth permanent Cron. Explicit promised reminders and goal-owned watches create native jobs as required; notification delivery may use owned one-shot jobs. All dynamic jobs are recorded for closure and uninstall.

## Background decision boundary

The state tool refuses user-decision actions in Cron context even if an old real-user signal is supplied: goal creation, goal status/review-date changes, interest recording, watch creation, feedback, Feed edits/deletion, forgetting and preference updates. Research progress, Ideas, new Feed articles, notice preparation/revalidation and stopping an existing watch remain available. New watch prompts are limited to 4000 characters; recurring intervals must be at least 30 minutes. Cron clock slots are checked across midnight regardless of calendar sparsity, with random/hashed clock fields rejected. One-off schedules remain available below 30 minutes. Notification delivery explicitly selects the current profile's bare bot-chat target, regardless of source conversation or gateway count.

## Lifecycle contracts

1. A casual mention is a temporary interest, not an accepted goal or monitoring subscription. Default interest/Idea lifetime is 14 days or an earlier event deadline. Only a NEW real user signal renews it; assistant output, recall, external news and cron execution cannot.
2. Explicit goals support one level of subgoals, progress, completion, cancellation and reopening. Undated goals have a 30-day research review boundary; review does not invent completion or silently cancel promised subscriptions. Goal dates, expiry and owner state are checked on every consumption, not just during cleanup.
3. Closing a goal pauses its owned future watches, invalidates obsolete pending reminders, and preserves any explicitly marked final result awaiting delivery. Reopen does not silently resume old monitoring.
4. User feedback distinguishes done, dismiss once, snooze and stop-topic. Silence is not acceptance. Stop-topic blocks future selection; an expired interest can remain an historical fact without being an active research directive.
5. Discovery/preparation/queueing/dispatch are not successful delivery. Exact event fingerprints are unique under a SQLite transaction. Ordinary dispatch reserves one daily slot atomically. Unknown outcomes are retained for inspection, never blindly retried. Semantic cross-source equivalence still requires judgment.
6. New notices target bare bot-chat, which native Cron resolves in the job-owning profile. The bot reads the selected result and replies in its canonical chat; Hermes can create a missing chat or queue behind its live owner. notification_handoff aliases the same queue, with no extra source-session injection. Bot Chat receipt completion is tracked separately from admission. Receiving these delivery turns never records a real-user signal and the plugin state tool permits only context/status/feed_list until a real user turn arrives, preventing recursive notification creation. Existing queued jobs retain their original route. No automatic cross-channel resend.
7. Forgetting first stops rewriters, removes owned originals/derived copies and suppresses identified pending reuse. Native/external memory deletion and historic session/backups are explicitly checked through actual tools; the plugin cannot promise erasure from a backend without a deletion API.
8. Research uses native asynchronous delegation with bounded fan-out, normalized item results, one retry of failed READ-ONLY items and explicit coverage gaps. Unknown external mutations are never automatically repeated. Model/provider choice remains the host's.

## Prompt and trust boundaries

One `register_system_prompt_section(..., position="after_memory")` section is frozen by Hermes per new conversation. It supplies real paths and routing to the Skill, not full files or ever-growing history. `pre_llm_call` may add bounded current-state pointers to the current user turn without rewriting past context or the cached system prefix. All background evidence and saved conversation excerpts are data, not instruction authority. Only authenticated host conversation hooks count as user signal; ignore cron, delegated children and plugin-injected housekeeping turns. Profile and source-session ownership must be carried through deferred work.

## Acceptance and release

Use standard-library unit tests for actual invariants: idempotent initialization, concurrent dedup/budgets, signal-gated TTL renewal, closure/late delivery, feedback, Feed operations, failure cursors, unknown send outcomes, path containment, and removed-plugin gates. Use a real Hermes checkout and isolated temporary homes for native registration/Skill lookup/prompt rendering/Cron creation and script execution/install/remove, including A -> B -> A profile switching. Never exercise a real user's live channel in automation. Publish a tagged GitHub release and installable manifest; submit an exact-SHA community catalog entry for maintainer review. Catalog approval is external and must not be represented as granted before merge.
