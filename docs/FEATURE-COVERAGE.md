# Feature coverage (0.4.0)

[Back to README](../README.md) · [简体中文](FEATURE-COVERAGE.zh-CN.md)

What code guarantees and what is left to the model. **Code**: deterministic, covered by the acceptance scripts.
**Model**: a job prompt or Skill procedure; the model and the user's tools do the work, so it needs live acceptance.
**Not covered**: Muse has no implementation.

| Feature | Who | Implementation and limits |
|---|---|---|
| Capturing private user messages | Code | Signals from `USER_SOURCES` only, redacted, head/tail excerpts past 8k; watermark in `meta`; parked after 3 packets or 72h |
| Deciding what a message means, which goal it belongs to | Model | intake packet disposition and goal hint |
| Goals: create, update, wait, done, cancel, reopen | Code | GOAL.md is the source of truth; status changes only from the private main session |
| Goal progress and done suggestion | Model | nightly assessment; `done_suggested` never closes a goal |
| Next check, dormancy question, fade cancel | Code | `goals.fade`: activity is a move by the user or an executor; one question per episode, up to 3 attempts, cancel after delivery + `goal_fade_days` |
| Rule matching, assignment ledger | Code | `rules.match`, `kernel/assignments.py`; starting and checking an executor is the model with the user's tools |
| Watches for open goals | Code | one owned job each, 30-day expiry renewed while the goal is open, stopped when it closes |
| Reading external sources (mail, calendar, reminders, web) | Model | with the user's own tools; Muse records each check per `source_id` with interval, limitation and failure state |
| Whether something is worth a notice, and its wording | Model | patrol verdict, text, priority, topic |
| Notice dedupe, quiet hours, budgets, `urgent_per_day`, blocked topics | Code | notice key against 7 days of history; gate computes `next_eligible` |
| Delivery and reconciliation | Code | one owned no-agent `muse-deliver` job prints due notices (every 10 min, urgent wakes it); receipts per run execution; unknown outcomes are never resent |
| Conversation review | Code + Model | code picks ≤10 candidates a day by rules; the model judges `agent_gap` (Finding) or `latent_need` (Idea) |
| Interests and Ideas | Code | 14-day expiry; only user input renews |
| Feed articles | Model | up to 3 interests a day without a recent article; published silently, browsable on the Muse page |
| Dreams, alignment, people and group pages, working lessons | Model | written through `content_write` with revision CAS |
| Native memory write receipts | Code | failed or staged writes shown once in the main session |
| Weekly digest | Model | from the Health summary and 7-day counts only; suggestions, no changes |
| Health and alerts | Code | probes and invariants in `muse/health.json`; main session, Muse page, cron stdout, optional `health_deliver` |
| Calendar views | Code + Model | `calendar_view` window and merge; reading the calendars is the model's |
| Forget | Code | clears the payload, writes a tombstone; Hermes history and native memory are outside Muse |
| Migration from 0.3.x and rollback | Code | `install.install`, `scripts/cutover.py` |
| Writing to external sources, data-source connectors, cross-profile monitoring, telemetry | Not covered | out of scope by design |
| Generic operation audit, model self-assessed run outcome, wake gate | Not covered | removed in v2 |
