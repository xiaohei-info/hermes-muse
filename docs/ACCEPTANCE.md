# Verification and user acceptance

## Automated checks

- Standard-library unit suite: `python -m unittest discover -s tests -v`.
- Real Hermes integration: `python tests/native_smoke.py` with a Hermes interpreter.
- To test a separate source checkout with that interpreter: `HERMES_SOURCE=/path/to/hermes-agent python tests/native_smoke.py`.
- Official validation: `hermes plugins validate . --json`.

Native integration runs under temporary homes and checks actual plugin registration, Skill lookup, bounded system prompt rendering, tool availability, four real Cron jobs, actual script gates, idempotent reload, preserved paused jobs/templates/native identity/memory, A -> B -> A profile switching and harmless launchers after removal. It makes no model calls and sends no real messages.

Public upstream compatibility baseline: `NousResearch/hermes-agent` commit `a28a5d03a9fa60418db5f44f3436fa2aa029c8f2` (2026-10-08). Local Hermes 0.21.5 was also exercised. APIs move; a broad version range is not proof of compatibility with every future revision.

## User acceptance on a separately installed profile

1. Install via the official command. Start a new conversation. Ask what Muse is tracking. Confirm one Skill and four fixed jobs, inherited model/timezone, and no changes to SOUL/USER/MEMORY from installation.
2. Mention a temporary interest. Ask to see its source and expiry. Confirm a Feed/research run does not extend it. A new explicit user mention may renew it. Expired interests do not drive research or sending.
3. Create a formal goal and a subgoal, with completion criteria. Add an explicit bounded watch. Complete/cancel the goal; verify native owned watches are paused. Confirm an already prepared final result still has a tracked delivery obligation.
4. Produce two candidate records for the same original event. Check only one is queued. Exercise waking hours/daily budget, dismiss once, stop-topic and snooze. Verify none uses another route to bypass a denial. Check original-source semantic quality yourself.
5. On a configured private channel, verify the actual native notification and follow-up context. On a CLI-only profile, verify pending local review. Treat adapter acceptance separately from phone display/read. Check failures/unknowns; do not cause a replay merely by asking status.
6. Generate a Feed article using an available source tool. Search it, discuss it, provide explicit feedback, change the brief, reorder and delete it. Confirm the same deleted article key is not regenerated. No Feed announcement should be sent.
7. Review incremental memory and a nightly reflection: evidence-based people/group notes, concrete repair/next behavior, no invented facts or automatic SOUL rewrite. Force a failed source/model operation and ensure the processing cursor is not advanced.
8. Delegate independent read-only research. Continue chatting, then collect results/advance waves. Verify normalized coverage and bounded retries; cancelled/unknown actions must not be blindly recreated.
9. Request forgetting a scoped topic. Verify watchers and indexed records are removed/suppressed, then inspect native/external memory and derived notes with real tools. Confirm the assistant reports inaccessible histories/backups rather than claiming unverified erasure.
10. Run official remove, then ask Hermes to clean the owned jobs/scripts using install.json. Confirm unrelated jobs/data remain and reinstallation preserves your documents.

These acceptance checks depend on the user's actual model, configured tools and messaging adapter. Unit/integration tests do not establish model judgment quality or real external delivery. Planning coverage percentages are not release pass rates.
