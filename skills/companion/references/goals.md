# Goals and interest lifecycle

Read context before acting. Explicit commitment to an outcome permits a goal; a passing mention permits only a temporary interest. Never assume a suggestion was accepted. An existing external task/goal stays authoritative: record its reference, use its tools to verify changes, and do not invent a competing completion state.

## Actions

- `goal_create`: `{id?, title, description, completion_criteria, signal_id, parent_id?, deadline?, external_ref?}`. IDs use ASCII letters/numbers/hyphens/underscores. One level of subgoals. The record owns a source session, current status and a research review date. Deadlines are ISO timestamps WITH timezone. User explicitly stated constraints belong in description/criteria; preserve financial/health/relationship judgment boundaries.
- `goal_update`: `{id, progress?, status?, signal_id?, research_review_at?, external_status_verified?}`. Progress must point to evidence/artifacts. Status is active/completed/cancelled. Status changes and review extensions need a recent real user signal. Before external_ref completion verify/update the external source. Closing a parent cancels remaining active children and pauses owned watches. Reopen does not resume them automatically.
- `interest_record`: `{id?, title, signal_id, expires?, rationale?}`. Defaults to 14 days from the actual user signal; earlier events shorten it. Reuse the same ID for the same topic. A later mention may renew it; rereading the old mention cannot. Stable enduring preferences belong in native memory/preferences, not an endless chain of temporary renewals.
- `idea_add`: `{goal_id, title, rationale}`. Research can suggest an Idea for a currently eligible goal. It expires after 14 days, is deduplicated and is not a task. Rank fit, feasibility and novelty; acceptance requires user feedback and a new explicit goal/task if execution is requested.
- `watch_create`: `{goal_id, signal_id, schedule, prompt, stop_condition, expires?}`. Only for explicitly agreed monitoring/reminders. Native schedule syntax (cron expression or future timestamp); include evidence source, notification condition and terminal condition. Do not create one watch per temporary interest. When the user gives an end date, set expires to that timezone-aware timestamp; the script gate stops it even if no model can run. Record/verify the returned native ID.
- `watch_stop`: `{job_id}` pauses only owned watches. Use when the condition is resolved, scope is revoked, or the user cancels.
- `feedback`: `{kind:"interest", id, action:"accept"|"done"|"dismiss"|"stop", signal_id}`. Accepting an Idea alone does not execute it.

Undated formal goals request an internal research review after 30 days. Do not mark them completed because they went quiet. Present a review only when useful; pause additional unsolicited research, preserve explicit recurring subscriptions, and never renew based on your own activity. Check expiry on EVERY read/send, not just the nightly pass.

When finishing: update the authoritative outcome, write a short progress/evidence note, stop owned future work, preserve an explicitly marked final result for delivery, and reconcile any already running work. A cancelled watch cannot undo external actions already submitted.
