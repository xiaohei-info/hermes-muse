# Verification and user acceptance

## Automated checks

- Standard-library unit suite: `python -m unittest discover -s tests -v`.
- Real Hermes integration: `python tests/native_smoke.py` with a Hermes interpreter.
- To test a separate source checkout with that interpreter: `HERMES_SOURCE=/path/to/hermes-agent python tests/native_smoke.py`.
- Published-repository install/remove smoke test: `python tests/install_smoke.py` (network required, isolated home).
- Official validation: `hermes plugins validate . --json`.

Native integration runs under temporary homes and checks actual plugin registration, Skill lookup, bounded system prompt rendering, tool availability, four real Cron jobs, actual script gates, idempotent reload, preserved paused jobs/templates/native identity/memory, A -> B -> A profile switching and harmless launchers after removal. It also checks the Cron user-decision boundary with valid saved user signals, allowed background progress/watch stopping, watch prompt/rate limits, one-off schedules, current-profile Bot Chat routing, receipt completion, rejection of self-triggered user signals and normal interactive completion. These regressions are in tests/native_review_smoke.py and run as part of native_smoke.py. It makes no model calls and sends no real messages.

Public upstream compatibility baseline: `NousResearch/hermes-agent` commit `a28a5d03a9fa60418db5f44f3436fa2aa029c8f2` (2026-10-08). Local Hermes 0.21.5 was also exercised. APIs move; a broad version range is not proof of compatibility with every future revision.

## User acceptance on a separately installed profile

1. Install via the official command. Start a new conversation. Ask what Muse is tracking. Confirm one Skill and four fixed jobs, inherited model/timezone, and no changes to SOUL/USER/MEMORY from installation.
2. Mention a temporary interest. Ask to see its source and expiry. Confirm a Feed/research run does not extend it. A new explicit user mention may renew it. Expired interests do not drive research or sending.
3. Create a formal goal and a subgoal, with completion criteria. Add an explicit bounded watch. Complete/cancel the goal; verify native owned watches are paused. Confirm an already prepared final result still has a tracked delivery obligation.
4. Produce two candidate records for the same original event. Check only one is queued. Exercise waking hours/daily budget, dismiss once, stop-topic and snooze. Verify none uses another route to bypass a denial. Check original-source semantic quality yourself.
5. In this profile's Bot Chat, verify that selected Cron results produce one bot reply and subsequent questions retain context. Try a missing chat and a busy live chat; verify native creation/queueing without another writer. Receipt admission is not processing completion or user-read proof. Confirm receiving a result does not create interests, another notice or a user signal, while the next actual user reply can update state normally. Check failures/unknowns without resending.
6. Generate a Feed article using an available source tool. Search it, discuss it, provide explicit feedback, change the brief, reorder and delete it. Confirm the same deleted article key is not regenerated. No Feed announcement should be sent.
7. Review incremental memory and a nightly reflection: evidence-based people/group notes, concrete repair/next behavior, no invented facts or automatic SOUL rewrite. Force a failed source/model operation and ensure the processing cursor is not advanced.
8. Delegate independent read-only research. Continue chatting, then collect results/advance waves. Verify normalized coverage and bounded retries; cancelled/unknown actions must not be blindly recreated.
9. Request forgetting a scoped topic. Verify watchers and indexed records are removed/suppressed, then inspect native/external memory and derived notes with real tools. Confirm the assistant reports inaccessible histories/backups rather than claiming unverified erasure.
10. Run official remove, then ask Hermes to clean the owned jobs/scripts using install.json. Confirm unrelated jobs/data remain and reinstallation preserves your documents.

These acceptance checks depend on the user's actual model, configured tools and messaging adapter. Unit/integration tests do not establish model judgment quality or real external delivery. Planning coverage percentages are not release pass rates.
