# Verification and user acceptance

## Automated checks

- Standard-library unit suite: `python -m unittest discover -s tests -v`.
- Real Hermes integration: `python tests/native_smoke.py` with a Hermes interpreter.
- To test a separate source checkout with that interpreter: `HERMES_SOURCE=/path/to/hermes-agent python tests/native_smoke.py`.
- Published-repository install/remove smoke test: `python tests/install_smoke.py` (network required, isolated home).
- Official validation: `hermes plugins validate . --json`.

Native integration runs under temporary homes and checks actual plugin registration, Skill lookup, bounded system prompt rendering, actual native final-output transformation, tool availability, six real Cron jobs, actual script gates, idempotent reload, preserved paused jobs/templates/native identity/memory, A -> B -> A profile switching and harmless launchers after removal. It also checks restored 0.1.2 background actions with real saved user signals, rejection of fabricated/reused evidence, native schedules and long watch prompts, writable Bot Chat result handling, profile-local routing, exact execution binding, idempotent preparation and migration from the old silent patrol. These regressions are in tests/native_companion_smoke.py and run as part of native_smoke.py. Weekly/monthly checks verify native schedules and routes, empty-profile wake gates, summary persistence and exclusion of delivered reports from user signals. It makes no model calls and sends no real messages.

Public upstream compatibility baseline: `NousResearch/hermes-agent` commit `a28a5d03a9fa60418db5f44f3436fa2aa029c8f2` (2026-10-08). Local Hermes 0.21.5 was also exercised. APIs move; a broad version range is not proof of compatibility with every future revision.

## User acceptance on a separately installed profile

1. Install via the official command. Start a new conversation. Ask what Muse is tracking. Confirm one Skill and six fixed jobs, inherited model/timezone, and no changes to SOUL/USER/MEMORY from installation.
2. Mention a temporary interest. Ask to see its source and expiry. Confirm a Feed/research run does not extend it. A new explicit user mention may renew it. Expired interests do not drive research or sending.
3. Create a formal goal and a subgoal, with completion criteria. Add an explicit bounded watch. Complete/cancel the goal; verify native owned watches are paused. Confirm an already prepared final result still has a tracked delivery obligation.
4. Produce two candidate records for the same original event. Check only one notice is prepared and no delivery-only Cron is created. Exercise waking hours/daily budget, dismiss once, stop-topic and snooze. Verify none uses another route to bypass a denial. Check original-source semantic quality yourself.
5. In this profile's Bot Chat, verify that the selected notice body, not merely a dispatch-status summary, produces one bot reply and subsequent questions retain context. Try a missing chat and a busy live chat; verify native creation/queueing without another writer. Receipt admission is not processing completion or user-read proof. Confirm receiving a result does not manufacture a user signal or prepare the same notice for a later execution; legitimate state updates remain possible with their existing evidence. Check failures/unknowns without resending.
6. Generate a Feed article using an available source tool. Search it, discuss it, provide explicit feedback, change the brief, reorder and delete it. Confirm the same deleted article key is not regenerated. No Feed announcement should be sent.
7. Review incremental memory and a nightly reflection: evidence-based people/group notes, concrete repair/next behavior, no invented facts or automatic SOUL rewrite. Force a failed source/model operation and ensure the processing cursor is not advanced.
8. Delegate independent read-only research. Continue chatting and verify the native result returns without a status request. Check per-question coverage and bounded retries; cancelled/unknown actions must not be blindly recreated.
9. Request forgetting a scoped topic. Verify watchers and indexed records are removed/suppressed, then inspect native/external memory and derived notes with real tools. Confirm the assistant reports inaccessible histories/backups rather than claiming unverified erasure.
10. Run official remove, then ask Hermes to clean the owned jobs/scripts using install.json. Confirm unrelated jobs/data remain and reinstallation preserves your documents.

These acceptance checks depend on the user's actual model, configured tools and messaging adapter. Unit/integration tests do not establish model judgment quality or real external delivery. Planning coverage percentages are not release pass rates.

For weekly/monthly review acceptance, inspect a real scheduled report: it should cite available outcomes, state missing evidence, offer concise recommendations and leave SOUL/configuration/skills/jobs unchanged. Confirm Bot Chat receives it once and the next review can retrieve its summary. Model judgment and report quality require this live acceptance; automated tests do not prove them.

For proactive behavior acceptance, distinguish a committed near-term plan from a speculative wish; confirm an existing in-scope next step is prepared before a generic offer; reject unchanged repeats after silence; distinguish dismiss/snooze/stop-topic; and verify nightly Working lessons updates preserve user instructions and avoid personal facts/task logs. This needs model-level review; keyword or template checks do not establish the behavior.

For connected-source acceptance, begin with no goals/interests/notices. Each fixed job's script must still wake the model. Give the patrol connected mail/calendar/reminder fixtures (and a device/CLI source), verify actual reads and per-source success/partial/error records, then change/cancel a fixture and verify selection or retirement. A failed page must preserve the previous successful watermark. Revisit an upcoming unchanged deadline. Confirm a known-location weather change can be relevant, an unlocated weather guess is not made, a repeated headline stays quiet, and unrelated private details are not surfaced. These semantic checks require real model/tool traces; automated state tests alone do not prove source coverage.

Additional regressions cover hourly/nightly cursor independence, pending notices surviving recent-history limits, snoozed interests returning without extending expiry, evidence-backed cross-day goal completion, independent expiring Ideas, and native research dispatch/status without user-driven waves. Native delegation integration checks the actual public registry dispatch and parent/background binding with a stubbed executor, without model calls. Host callbacks and model judgment still need live acceptance.
