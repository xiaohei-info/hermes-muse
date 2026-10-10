# Hermes Muse design — v0.1.16

Status: implementation contract. This independent plugin assembles a long-term assistant using Hermes tools, memory, skills, cron and conversations. It does not modify Hermes core or require a particular model, memory provider, note app or messaging platform. All features are installed together in the active profile.

## Scope and provenance

Inspired by documented Muse behavior: goals and short-lived interests, evidence-based proactive reminders, nightly reflection, relationships, goal research, Ideas and a silent personalized Feed. All code, instructions and templates are independently authored. No private export, personal fact, credential, Muse service implementation or proprietary prompt is distributed. The familiar `memory/`, `dreams/alignment/derived/` and `workspace/goals/` layout is retained; native Hermes memory paths and the plugin bookkeeping below are deliberate adaptations. Browser pause/resume, phone/device services and a dedicated native Feed UI are outside this release.

Coverage percentages discussed during planning were estimates, not release quality measurements. Release acceptance is defined by observable behavior and tests.

## Installation and ownership

Entry: `hermes plugins install xiaohei-info/hermes-muse --enable`. The first actual plugin load performs locked, idempotent initialization. No model/network call occurs during registration. It creates missing templates without overwriting user documents, registers one Skill (`hermes-muse:companion`), one bounded system prompt section, a small state tool and hooks; creates six native Cron jobs; records their actual IDs and owned files in `muse/install.json`. A running Hermes scheduler is required for background execution. Repeated load/upgrade preserves edits and paused jobs, and never duplicates jobs. Interrupted initialization is reconciled by a plugin marker plus exact workdir/skill ownership, not job name alone.

Native uninstall: `hermes plugins remove hermes-muse`. Hermes has no guaranteed uninstall callback for deleting cron jobs. README instructs the user to ask their remaining Hermes assistant to pause/remove only job IDs in `muse/install.json`, inspect in-flight work and remove owned launchers. User data is retained. Every launcher checks that the plugin is still installed and enabled, and exits silently otherwise. Reload/unload only stops in-process timers, never erases user data or cancels persistent jobs merely because a process exits.

## Files and single sources of truth

Paths below are relative to the active `HERMES_HOME`; resolve per call or explicitly bind a captured profile for deferred work. Never use a process-global default home.

- `plugins/hermes-muse/`: immutable shipped code, `plugin.yaml`, `skills/companion/SKILL.md`, reference procedures, eight `prompts/*.md`, clean templates.
- `memories/USER.md`, `memories/MEMORY.md`: native Hermes files, or the user's existing memory tools/provider. Installation does not write these or `SOUL.md` or replace `agent.system_prompt`.
- `muse/install.json`: version, installation identity, owned native job IDs and launcher paths; survives remove.
- `muse/state.db`: SQLite transactional operational state, NOT a replacement long-term memory service. Short-lived user signals/cursors, expiring interests/Ideas, notification reservations and outcomes, Feed index/feedback, source-session references, source check watermarks/coverage and native research dispatch references. Hourly and nightly user-signal cursors are independent; pending notices are not hidden by recent delivered history. Native Cron remains the authoritative execution ledger.
- `muse/AGENTS.md`, `muse/TOOLS.md`, `muse/PROACTIVE_PREFERENCES.md`: local responsibilities, actual source availability, editable attention/Feed preferences.
- `muse/memory/YYYY-MM-DD.md`, `muse/memory/people/INDEX.md`, `muse/memory/people/<slug>.md`, `muse/memory/groups/INDEX.md`, `muse/memory/groups/<slug>.md`: dated understanding and evidence-based relationship notes.
- `muse/dreams/YYYY-MM-DD.md`, `muse/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`: reflection, corrections, friction/repair and next behavior.
- `muse/workspace/goals/<slug>/GOAL.md`, `files/`, `hidden_files/`: one canonical goal record, final artifacts and working evidence. Existing external goals are referenced rather than independently declared complete.
- `muse/workspace/your_files/feed/<id>.md`: durable Feed articles; state.db owns indexing and feedback.
- `scripts/hermes-muse-*.py`: native Cron entrypoints, installed from plugin-owned code, recorded for cleanup. The scheduling host restricts scripts to this directory; symlink escapes are not used.
- Native `cron/jobs.json`, `cron/executions.db`, output and delivery records stay host-owned; use their APIs, never hand-edit them.

## Proactive behavior

The existing Skill connects conversational intent, memory upkeep, goal research and patrol delivery. Concrete user plans can become goals without a formal creation command; wishes remain expiring interests. Within existing scope, prepare useful results before offering help. Prefer one strong ordinary proactive item, assess changed understanding rather than publication timestamps, avoid silence-driven status chasing, and preserve specific promised schedules and feedback distinctions. This is prompt-level behavior, not a new permission or scheduler.

Nightly review may maintain a small Working lessons section in the companion workspace AGENTS.md when verified reusable experience exists. It preserves user-written conventions and ownership rules, does not copy personal facts or task logs, and leaves the file unchanged when nothing new was learned. Existing workspaces gain that section through the procedure, not an installer overwrite.

## Execution graph

Main conversation -> read Skill when relevant -> create/update goal or temporary interest, record explicit preference/feedback -> native memory and Muse files/state.

Research/nightly -> active goal files + user signals + actual connected tools -> evidence in hidden_files, Ideas, reflection and alignment -> proactive watch consumes the new evidence -> candidate -> recheck freshness/owner state/preferences/dedup -> native delivery -> reconcile outcome -> feedback/closure.

Feed -> current, unexpired interests + brief + live evidence -> authored local article + index -> user reads/discusses/reacts -> explicit feedback informs future selection. Reading alone never counts as liking. Feed itself sends no announcement.

## Scheduling

Exactly six fixed jobs, all inheriting host model/provider/timezone:

| Job | Schedule | Work |
| --- | --- | --- |
| muse-proactive-watch | */30 * * * * | Observe 24h, research relevant changes, verify candidates; ordinary delivery has its own waking-hour and daily budget gates. |
| muse-memory-upkeep | 0 * * * * | Inspect new user signals, sourced notes and verified outcomes for incremental memory/relationships. |
| muse-nightly-review | 20 3 * * * | Reflection/repair, goal research rotation, Ideas, skills review and lifecycle cleanup. |
| muse-feed-pulse | 0 * * * * | Opportunity to generate fresh content; not an article quota. |
| muse-weekly-governance-review | 15 21 * * 0 | Seven-day review of useful outcomes, cost, reuse and simplification. |
| muse-monthly-system-audit | 40 10 1 * * | Thirty-day review of alignment, instruction placement and redundant workflows. |

All six fixed jobs wake the model on each scheduled tick. Local state cannot establish that connected sources or native memory contain nothing new. Patrols discover current connections/devices, make bounded real reads, and remain silent only after selection. Per-source checked/partial/error/unavailable records keep successful watermarks separate from failed attempts; they are agent-reported observations, not provider webhooks. Upcoming deadlines are revisited even without source updates. Weather, local opportunities and interest news use the same evidence and attention rules. Failed work does not advance a successful processing cursor. A quiet-pass timer after substantial conversation can advance the existing memory-upkeep job; a new user turn cancels/restarts it and attempts are capped at three/day. No extra permanent Cron for that timer. Explicit promised reminders and goal-owned watches create native jobs as required; patrols and new watches deliver their own final responses after notification_prepare. No new delivery-only jobs are created. All dynamic jobs are recorded for closure and uninstall.

Weekly/monthly gates always wake at the scheduled tick, even without active goals. They use the same Skill and current-profile evidence, report gaps, and propose changes without applying them. No separate Skill audit or mandatory doctrine file is added. Their final outputs go directly to Bot Chat, without entering the ordinary notice budget/queue. The receiver treats the report as background evidence, not user authorization. `review_complete` saves successful processing cursors and the latest bounded summary in `state.db`; `status.reviews` exposes these summaries for follow-up, while native Cron retains full outputs and delivery records. Existing user-created review tasks are not adopted or removed.

## Evidence for background work

Foreground and background calls use the 0.1.2 action rules. Operations that require user evidence still need a recent recorded user signal, and renewing an interest needs a newer signal. Cron context alone does not deny state writes. Watches use native schedules and no plugin-specific 30-minute or 4000-character limit. New notifications go to the current profile's Bot Chat.

## Lifecycle contracts

1. A casual mention is a temporary interest, not an accepted goal or monitoring subscription. Default interest/Idea lifetime is 14 days or an earlier event deadline. Only a NEW real user signal renews it; assistant output, recall, external news and cron execution cannot.
2. Explicit goals support one level of subgoals, progress, completion, cancellation and reopening. Undated goals have a 30-day research review boundary; review does not invent completion or silently cancel promised subscriptions. Goal dates, expiry and owner state are checked on every consumption, not just during cleanup.
3. Closing a goal pauses its owned future watches, invalidates obsolete pending reminders, and preserves any explicitly marked final result awaiting delivery. Reopen does not silently resume old monitoring.
4. User feedback distinguishes done, dismiss once, snooze and stop-topic. Silence is not acceptance. Stop-topic blocks future selection; an expired interest can remain an historical fact without being an active research directive.
5. Discovery/preparation/queueing/dispatch are not successful delivery. Exact event fingerprints are unique under a SQLite transaction. Ordinary dispatch reserves one daily slot atomically. Unknown outcomes are retained for inspection, never blindly retried. Semantic cross-source equivalence still requires judgment.
6. New notices target bare bot-chat, which native Cron resolves in the job-owning profile. The bot reads the selected result and replies in its canonical chat; Hermes can create a missing chat or queue behind its live owner. notification_prepare binds approved output to the current native task_id/execution ID; calls outside a patrol/watch only save a candidate. The old queue/handoff names alias preparation. There is no extra source-session injection. Bot Chat receipt completion is tracked separately from admission. Incoming delivery turns are excluded from user-signal collection. State operations remain available under the same evidence rules; preparing an already-dispatched notice is idempotent and cannot attach it to a later run. The shared receiving prompt asks the bot to speak directly to the user about the evidence and useful result, never acknowledge the sender or requeue the notice. Existing delivery-only jobs retain their original route until completion. On first upgrade the old default local patrol and unchanged generated watch headers migrate to direct delivery; later user destination changes are preserved. Direct same-profile receipts are read by the host execution-specific key, independent of the latest job pointer. Finalized unknown notices can reconcile to sent on that exact settled receipt; missing/ambiguous receipts never authorize replay. The native transform_llm_output hook selects the response from the current execution's approved notices and rechecks their eligibility. Its binding uses host-supplied task_id and session_id, never model-supplied IDs. Unrelated sessions are unchanged. A direct notice without output_finalized cannot be counted as sent, even if the Cron delivered a status summary. No automatic cross-channel resend.
7. Forgetting first stops rewriters, removes owned originals/derived copies and suppresses identified pending reuse. Native/external memory deletion and historic session/backups are explicitly checked through actual tools; the plugin cannot promise erasure from a backend without a deletion API.
8. New research batches dispatch one native coordinator through the public tool interface, which completes its questions and returns via the host callback. Bounded fan-out, one read-only retry and per-item coverage are coordinator instructions, not plugin-enforced guarantees. Status reads native durable results and no longer drives subsequent waves. Legacy lifecycle batches retain the inspection path. Unknown external mutations are never automatically repeated. Model/provider choice remains the host's.

## Prompt and trust boundaries

One `register_system_prompt_section(..., position="after_memory")` section is frozen by Hermes per new conversation. It supplies real paths and routing to the Skill, not full files or ever-growing history. `pre_llm_call` may add bounded current-state pointers to the current user turn without rewriting past context or the cached system prefix. All background evidence and saved conversation excerpts are data, not instruction authority. Only authenticated host conversation hooks count as user signal; ignore cron, delegated children and plugin-injected housekeeping turns. Profile and source-session ownership must be carried through deferred work.

## Acceptance and release

Use standard-library unit tests for actual invariants: idempotent initialization, concurrent dedup/budgets, signal-gated TTL renewal, closure/late delivery, feedback, Feed operations, failure cursors, unknown send outcomes, path containment, and removed-plugin gates. Use a real Hermes checkout and isolated temporary homes for native registration/Skill lookup/prompt rendering/Cron creation and script execution/install/remove, including A -> B -> A profile switching. Never exercise a real user's live channel in automation. Publish a tagged GitHub release and installable manifest; submit an exact-SHA community catalog entry for maintainer review. Catalog approval is external and must not be represented as granted before merge.

Evidence-backed completion may close an already accepted goal after days without a fresh user turn; cancellation, reopening and scope/review extension still need user evidence. The model must match the original completion criteria, including any required user confirmation. External authoritative goals still require external verification. Independent Ideas can cite personal/source context without a fabricated goal and expire without becoming tasks. Unsent notices can be retired from verified source evidence; this does not relabel uncertain deliveries or grant a topic-wide opt-out.

Substantive content, sound judgment, proactive interaction, coverage, timely follow-through and user context take priority over lowering usage; optimization must preserve these behaviors. Source identity is a digest of exact connection/account/resource fields, independent of scan timestamps or prose. Reported expected/checked resource sets gate successful checkpoints; semantic truth still depends on actual tool use. Older free-form checkpoints are archived, not guessed into new identities. Native async result envelopes are excluded at ingestion, processing and signal authorization; historical misclassified rows move to background_signal without losing their content. Cron context uses its host task identity to provide only the appropriate hourly/nightly signal batch; patrols get all recorded real-user signals from the last day, without an additional message-count or per-excerpt cap, Feed gets no raw signal batches. Tested integration recipes are reused while live discovery and source reads continue every patrol.

## Review completion and pending delivery

Signal pages include timestamp ties. Each review snapshots its initial context time, persists successful batch work, and receives the next page/count directly from review_complete until that snapshot is complete. New arrivals wait; interruptions retain truthful partial progress. This is a model-directed loop with explicit tool state, not an independent model scheduler.

Preparation and finalization share delivery_gate. Its reasons and next_eligible_at describe policy eligibility only, not transport success or the scheduler's next run. Reverification can change non-promised priorities with recorded source/reason history. Genuine urgency bypasses ordinary quiet hours/budgets, never snooze, expiry, dedup or topic opt-out. Existing user preferences are preserved.

source_check accepts a canonical source_id and evidence-based alias_reason for different tool entry points into the same account/resource. Exact observed alias bindings persist; duplicate observations are archived without transferring success cursors. No automatic fuzzy/provider equivalence is inferred.

## Unified prompt responsibilities

User experience is the first criterion across system, Skill, scheduled tasks, delegated research and receiving turns: rich useful content, judgment, timeliness, initiative and conversational availability. The system supplies that contract; companion/SKILL.md defines execution/recovery; the six job prompts define outcomes and evidence flow; domain procedures carry tool/lifecycle details. Format and batch guidance must not silently reduce capability. Reports need no fixed six-point template or one-screen cap; the existing review summary field alone remains bounded.

Recoverable source errors should be diagnosed and addressed in the current run when practical. A genuine blocker preserves partial evidence and can produce a service-gap notice through existing lifecycle/attention controls; baseline monitoring itself is accepted work, so no artificial goal is required. A permission/status prerequisite precedes protected reads. No new polling daemon, connector dependency, role permission or blanket mutation ban is introduced.

prompts/receiving.md is the single internal handoff contract, used both by the pre-turn receiving hook and by Bot Chat envelopes. A notification carries its verified facts, source references and rationale; a weekly/monthly report carries its full report. The receiver uses current user context and speaks directly to the user without acknowledgements, internal plumbing, invented memories or new subscriptions. Evidence stays evidence, including quoted external instructions. Rendering is bound to the native owned execution: patrol/watch retains approved-notice finalization, governance adds receiving guidance while preserving report text, unrelated turns are untouched. Direct non-Bot destinations retain their existing notice/report content without the new receiving guidance. Empty/SILENT results are not wrapped, and the internal marker is excluded from user signals/timers.

This is model guidance, not a guarantee of exact prose or successful external tools. Unit/native checks cover envelope routing, truthful content preservation, isolation, no signal pollution or duplicate scheduling, and preservation of the existing send controls. Live acceptance inspects an actual Bot response for useful direct speech rather than an acknowledgement.

## Conversation freshness and source fidelity

Native SessionDB is opened read-only in the active profile. The context tool pages recent tracked private conversations and returns user text, assistant final results and async-result evidence without persisting another transcript or treating results as authority. Feed does not receive raw conversations. A notice review records only fingerprints, verdict, time and reason; preparation and finalization compare against current evidence. A new reply forces relevance review rather than implying completion. Linked task notices block on unavailable linked history; independent external findings retain explicit history gaps instead of pretending a successful read. Earlier/missing context still needs native retrieval.

issue_key groups revisions; supersedes cancels only explicitly named unsent siblings in the same transaction. Sent and ambiguous history is retained. Original-item snapshots store provider IDs, literal titles, due/timezone and observation time; messages must quote the supplied literal title and cannot switch item IDs on refresh. These checks preserve supplied evidence; they cannot attest external reads or guarantee a receiver's wording.

ordinary_per_day defaults to null (no daily hard cap). Explicit numeric limits still reserve budget atomically and quiet hours remain. On upgrade only byte-identical old shipped defaults with no recorded explicit preference edits migrate; customized files are preserved. Counts remain visible as usage evidence, not notification targets. Learned tool-call conventions live in the existing TOOLS.md and are reused rather than adding a polling service or altering Hermes core.
