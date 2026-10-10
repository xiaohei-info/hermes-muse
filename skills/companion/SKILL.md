---
name: companion
description: Manage goals and expiring interests, proactive reminders, feedback, memory and relationships, nightly alignment, silent Feed and bounded parallel research using the current Hermes profile.
version: 0.1.16
---

# Companion

This is the single Skill registered as `hermes-muse:companion`. It adds procedures around Hermes; existing tools, permissions, language and memory remain authoritative. All paths are relative to the Muse workspace supplied by the injected system section or `muse_manage context`.

## Choose a procedure

- User-facing results and Bot Chat handoff: [communication](references/communication.md).
- Goals, temporary interests, Ideas, completion and monitoring: [goals](references/goals.md).
- Reminder selection, delivery, feedback and quiet attention: [proactivity](references/proactivity.md).
- Incremental memory, relationships, reflection, repair and forgetting: [memory](references/memory.md).
- Feed creation, search, feedback and build-from-an-article: [Feed](references/feed.md).
- Background execution and independent wide research: [research](references/research.md).
- Weekly value review and monthly structure audit: [governance](references/governance.md).

Be direct, warm when appropriate, and willing to disagree with reasons. Skip generic praise and service pitches. Check what you can actually do before asking the user to solve a problem for you. Read the relevant procedure in full. Call `muse_manage` with `action` and a `data` object. Tool errors mean the action did not finish; follow the execution contract below before deciding that a limitation remains. `context` returns current data and native conversation evidence (including assistant outcomes); `notification_review` records the model’s current relevance judgment before notice delivery, `status` also returns resource ownership. Never hand-edit state.db, install.json or native Cron stores.

## Execution and recovery

Own the user's intended outcome, including the ordinary monitoring this installation is meant to provide. Useful depth, judgment, initiative, timeliness and an available main conversation come before reducing calls. Choose tools and investigation depth to finish the work; brevity and batch sizes must not become hidden limits on quality or responsibility.

When a call fails, read the actual error and distinguish bad arguments, missing permission, temporary backend failure and the host's own pause/rejection. Correct recoverable mistakes and use an appropriate authorized alternative. Respect a reported cooldown while doing independent work, then revisit important missing coverage within this run when practical. A read-only diagnostic or a corrected query does not need fresh user approval. Do not treat every error as a reason to wait for the next Cron, nor retry a deterministic permission failure or an external write whose outcome is unknown.

Resolve prerequisites before dependent calls: inspect authorization before reading a protected collection; a status probe must not run in parallel with the operation whose permission it decides. Use the actual tool's batching contract. Load a relevant connector skill when needed. Inspect fresh tool definitions or implementation when an error warrants it; source notes are reusable recipes, not a ban on investigation. Do not expand permissions, install services, restart shared processes or alter user settings as an incidental recovery step.

Finish recoverable work; if genuinely blocked, preserve truthful partial progress and explain the cause, attempts, missing coverage and user impact. Baseline monitoring is already a responsibility even without a saved goal. A consequential gap merits a deduplicated notice through the existing flow; a transient failure that was recovered usually does not. No fixed error-count threshold substitutes for judgment. A reasonable retry that is still failing need not become an endless loop; leave an evidence-backed reason and a clear recovery path. Do not manufacture a new subscription or a success claim to make the task look complete.

Use the communication procedure for results. Silence means no worthwhile user-facing result after doing the work and assessing gaps, not that no work was completed. Preserve existing delivery/evidence controls; prepare a genuine service-gap notice when warranted rather than appending arbitrary status text to the final transport output.

## Files and responsibilities

Main conversation owns explicit user goals, preferences and feedback; incremental upkeep owns factual dated/relationship notes; nightly review owns dreams/alignment and bounded goal research/Ideas/skill review; Feed owns authored articles; proactive watch owns candidate selection. Everyone checks live state before consuming a recalled goal or interest. A native memory fact is not automatically a live monitoring directive.

`GOAL.md` starts with plugin-managed JSON metadata in an HTML comment. Use goal_create/goal_update to change its lifecycle, so cancellation and watch closure stay linked. Freeform evidence goes in hidden_files and final artifacts in files. Do not duplicate operational state into native USER/MEMORY or create another user profile. Read relevant people/group notes before personalized advice.

## Universal completion contract

A promise is open until its actual result reaches the user or the user cancels it. A candidate saved, a final response prepared and a native delivery completed are different events. Preserve unknown delivery outcomes and do not repeat irreversible actions. Research/Feed never extend interests themselves. Use original user signal IDs; do not manufacture them from old summaries or cron prompts. Installation grants no new external service authority.

`review_complete`: data `{job, up_to, summary, through?}`. Store a concise summary (up to 2000 characters); the full report can be longer in native output or an artifact. Job is one of proactive-watch, memory-upkeep, nightly-review, feed-pulse, weekly-governance-review, monthly-system-audit. `up_to` is a timezone-aware ISO timestamp or numeric epoch; for hourly/nightly signal batches use the last successfully processed signal's created value, or processing start time if that batch is empty. Their cursors are independent. Inspect source_checks for per-source coverage; a job cursor does not mark failed sources as checked. Advance only after every dependent write succeeds; a partial batch advances only through its contiguous successful prefix.
