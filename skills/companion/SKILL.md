---
name: companion
description: Manage goals and expiring interests, proactive reminders, feedback, memory and relationships, nightly alignment, silent Feed and bounded parallel research using the current Hermes profile.
version: 0.1.5
---

# Companion

This is the single Skill registered as `hermes-muse:companion`. It adds procedures around Hermes; existing tools, permissions, language and memory remain authoritative. All paths are relative to the Muse workspace supplied by the injected system section or `muse_manage context`.

## Choose a procedure

- Goals, temporary interests, Ideas, completion and monitoring: [goals](references/goals.md).
- Reminder selection, delivery, feedback and quiet attention: [proactivity](references/proactivity.md).
- Incremental memory, relationships, reflection, repair and forgetting: [memory](references/memory.md).
- Feed creation, search, feedback and build-from-an-article: [Feed](references/feed.md).
- Background execution and independent wide research: [research](references/research.md).

Read the relevant procedure in full. Call `muse_manage` with `action` and a `data` object. Tool errors mean the action did not finish; repair inputs or report the limitation. `context` returns current data, `status` also returns resource ownership. Never hand-edit state.db, install.json or native Cron stores.

## Files and responsibilities

Main conversation owns explicit user goals, preferences and feedback; incremental upkeep owns factual dated/relationship notes; nightly review owns dreams/alignment and bounded goal research/Ideas/skill review; Feed owns authored articles; proactive watch owns candidate selection. Everyone checks live state before consuming a recalled goal or interest. A native memory fact is not automatically a live monitoring directive.

`GOAL.md` starts with plugin-managed JSON metadata in an HTML comment. Use goal_create/goal_update to change its lifecycle, so cancellation and watch closure stay linked. Freeform evidence goes in hidden_files and final artifacts in files. Do not duplicate operational state into native USER/MEMORY or create another user profile. Read relevant people/group notes before personalized advice.

## Universal completion contract

A promise is open until its actual result reaches the user or the user cancels it. Evidence prepared, job queued, main-session wake accepted and message generated are different events. Preserve unknown delivery outcomes and do not repeat irreversible actions. Research/Feed never extend interests themselves. Use original user signal IDs; do not manufacture them from old summaries or cron prompts. Installation grants no new external service authority.

`review_complete`: data `{job, up_to, summary}`. Job is one of proactive-watch, memory-upkeep, nightly-review, feed-pulse. `up_to` is a timezone-aware ISO timestamp or numeric epoch; for memory use the last successfully processed signal's created value. Advance only after every dependent write succeeds; a partial batch advances only through its contiguous successful prefix.
