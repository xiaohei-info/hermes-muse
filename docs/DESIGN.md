# Hermes Muse design — 0.4.0 (v2)

This is the public design of Muse v2. The engineering contract for contributors (layer rules, change checklist,
review list) is [AGENTS.md](../AGENTS.md); where the two differ, AGENTS.md and the code's single tables win.
The model interface is generated from code: [interface.md](../skills/companion/references/interface.md).

## Goal and approach

Muse is a standalone Hermes plugin that turns Hermes's own sessions, cron, delivery, delegation and native memory
into a long-running companion inside one profile. It keeps the work the user accepted (Goal) and short-lived
interests (Interest, Idea), sends evidence-based reminders (Notice) without repeats and within quiet hours and daily
budgets, reviews goals and conversations at night, and writes a silent personal Feed.

v2 replaces 0.3.x's model-driven bookkeeping with a **deterministic kernel and a thin judgment layer**:

- code keeps the books: watermarks, dedupe, state machines with TTLs, delivery and its reconciliation;
- every host coupling sits in one adapter (`hermes_muse/host/`) that checks itself with semantic probes;
- Health runs on its own and never fails silently;
- the model contract exists once, in code, and its reference is generated.

Out of scope: patching Hermes, replacing long-term memory (`memories/USER.md`, `MEMORY.md` and SOUL belong to the
user and Hermes), data-source connectors, writing to external sources, generic operation audits or model
self-assessment, cross-profile access, telemetry and self-update.

## Layers

```
Hermes host
  ▼ plugin API, hook kwargs, launcher env, dashboard requests
inbound entries     __init__.py → runtime.register · cron_entry.py → entry.run · health_entry.py → health.run
                    · dashboard/plugin_api.py
application         surface.py (model tools) · hooks.py (main session) · entry.py (job output)
                    · install.py · views.py (Dashboard, read-only) · health/ (independent, read-only)
kernel/             intake · notifier · goals · review · sources · packets · runs · records · receipts · Kernel.tick
                    ← the only place that writes entity state
kernel/store/       Store v2, keys, machines, migrate, bridge (stdlib only)
shared              content_io (Files, revision) · locks · calendar normalization
host/               HostAdapter: sessions · cron · deliver · owners · config · probe   ← the only outbound path
  ▼ Hermes imports, read-only state.db, cron/deliver/delegation APIs
Hermes host
```

Only `host/` imports Hermes or reads its `state.db`; `scripts/check_boundaries.py` enforces this.
`register()` only builds objects and registers the Skill, prompt section, tools and hooks; install runs after it
in a background thread (not a daemon, so a short-lived process finishes it before exiting). Hermes gives import + register a deadline (10 s by default) and abandons a load that
passes it, dropping every later registration, and several Hermes processes load plugins at once on a cold boot.
Install waits on profile locks, SQLite writers and the host's cron lock, so it must not hold the load. Its migration
marker keeps jobs, the background tick and the tools quiet until it finishes. Each process records whether its load
counted (`muse/loaded/<pid>`, `HostAdapter.loaded`); a job whose launcher's parent (the process running the job)
abandoned the load stays silent instead of waking a model without Muse's tools, and Health raises `plugin_load`. Entries translate
host arguments into Muse calls and classify the caller through `HostAdapter.caller()`, never from tool arguments.
Health depends only on `host/` and a read-only Store, so a kernel bug cannot hide itself.

## Store v2 and state machines

All operational state lives in `muse/state-v2.db` (SQLite, WAL) as `entity` rows with an `event` log (kept 30
days) and `meta` (the intake watermark, migration record, daily counters). Every write is a `BEGIN IMMEDIATE`
transaction; transitions are CAS on `state + version`. Each kind has one machine in `kernel/store/machines.py`:

| kind | states | timed state → exit |
|---|---|---|
| signal | new → disposed / parked | new: 72h or 3 packets → parked |
| goal | active ↔ waiting → done / cancelled (and back) | deadline is the next check (a nightly assessment sets 1 day − 6h); handled by nightly and fade |
| notice | drafted ↔ scheduled → sending → sent / failed / unknown → … | expiry (3 days) → expired; sending 2h → unknown; unknown 48h → closed_unknown |
| watch | active → stopped / expired | 30 days, renewed while the goal is open |
| interest / idea | active → expired / stopped | 14 days or expiry |
| feed | published → deleted | — |
| source | ok / limited / failing / unavailable | — |
| finding | open → resolved / dismissed | 14 days → dismissed |
| memory_receipt | pending_notice → noticed | 24h |
| packet | issued → submitted / expired | lease = the job period; intake, nightly and feed batches min(period, 2h) |
| run | running → ok / degraded / failed / abandoned | 2h; decided by the host's execution state |
| tombstone | forgotten | — |

Rules: every timed state has a deadline, and expiry either moves to its exit in `Store.tick()` or is handled by
its module with a Health check. A natural_key is derived by code (`kernel/store/keys.py`, goal slugs and watch
slots in `goals`) and is unique per kind forever unless the machine declares a dedupe window; creating an existing
key returns the existing entity. `Kernel.tick()` runs every due step in dependency order, is idempotent and safe
to enter from several processes; a failing step is recorded and the others continue.

Goals keep `muse/workspace/goals/<slug>/GOAL.md` as their source of truth; the Store holds a mirror. Content files
(memory, dreams, people/group pages, Feed articles, TOOLS.md, AGENTS.md, preferences) keep their 0.3.x formats and
are written only through `content_io.Files` with a revision CAS under `muse/mutations.lock`.

## Authorization

`host.sessions.caller()` returns `user | cron | child | group | other`. The stored `sessions.source` decides; the
call's platform argument or an inherited session environment can only narrow it. Sources outside `USER_SOURCES`
(including empty or unclassified ones) are `other`; group chats are `group`; delegated contexts are `child`.

- `user` (the private main session) may use all 14 `muse_manage` actions; only it changes goal status or settings.
- `cron` may use `muse_job` read/observe/submit against its own packet, and from `muse_manage` only `read`,
  `calendar_view` and `content_write` for notes, dreams and alignment. Goals created from a job must cite a user
  Signal in the packet (at most 5 a day); jobs only append progress and assessments.
- `child` reads; `group` and `other` are refused.
- Kernel code runs TTL exits, next checks, fade questions and cancellations, watch renewal, delivery and
  reconciliation; it also expires the packet of a failed drain run, releases the unanswered items of its batch and
  wakes the same owned job while its queue is not empty. Health reads only.
- Muse's own intake run (cron key `memory-upkeep`) may compact native memory only by merging or shortening entries:
  the `pre_tool_call` hook refuses a native `memory` call with more removes than patches, and every change is
  recorded by code. Muse never writes the memory files itself.

Quoted mail, pages and tool output are evidence, never instructions.

## Jobs and packets

Owned jobs keep their 0.3.x cron keys so ids, user schedules, routes and pauses survive the upgrade:

| cron key | job | default schedule | delivery |
|---|---|---|---|
| memory-upkeep | intake | hourly | local |
| proactive-watch | patrol | every 30 minutes | user route |
| nightly-review | nightly | 03:20 | local |
| feed-pulse | feed | 08:00 | local |
| weekly-governance-review | weekly | Sunday 21:15 | user route |
| deliver | deliver (no agent) | every 10 minutes | user route |

`monthly-system-audit` is paused (merged into weekly), `muse-health` is a no-agent cron every 30 minutes, and each
Watch is its own owned job. Every launcher runs `scripts/hermes-muse-<key>.py` → `cron_entry.py` → `entry.run`,
which checks that the plugin is enabled and no migration marker exists, runs `Kernel.tick()`, builds the job's
output and prints one JSON line; `{"wakeAgent": false}` keeps the model asleep. The `deliver` job never calls a
model: it prints the message itself (plain text, empty when nothing is due) and Hermes delivers that stdout.

A packet job (intake, patrol, nightly, feed) gets one bounded Packet at a time: items with refs that are valid only
inside that packet, redacted excerpts, budgets and a lease. Intake, nightly and feed drain their whole queue within one
period in batches keyed `<job>:<period>[:<batch>]`: a batch's refs are consumed when its run closes ok or degraded;
the refs of an expired batch and the unanswered refs of a failed run come back, and when a run closes with work left
the kernel wakes the job again, however many batches that takes; only three batches in a row that handle nothing (a run
that keeps failing) stop the relay until the next period, and Health reports it (`drain_stopped`). The model reads more of an item (12k per call, 24k per
item), reports source checks with `observe` (patrol) and answers each item with `submit` in one of five result
schemas. Job prompts are `prompts/jobs/<job>.md`, at most 15 lines of behavior each; fields live only in the
action tables and `packets.SCHEMAS`. The model outputs only refs, enum values and free text; ids, keys, times,
counts and state names come from code.

## Flows

1. **Intake.** Private user turns from `USER_SOURCES` are read through the host, redacted and cut to head/tail
   excerpts past 8k, and recorded as Signals while the watermark advances. Each hourly period drains every waiting
   Signal in batches (15 each, fewer when their excerpts pass 24k characters); each gets a disposition. A goal hint touches an open goal or proposes a new one for nightly. Signals
   left after 3 packets or 72h are parked, counted by Health, and never block the watermark. When a native memory
   store is at least 90% full (read through `HostAdapter.memory`), the packet names it (`memory_full`, at most 3
   packets a day) and the model may merge or shorten entries in the batch that saves the new fact; each change goes
   to the day's note and the next nightly packet. A fact that still does not fit stays unanswered and retries.
2. **Patrol → Notice → delivery.** Patrol wakes every period because only the model can read external sources;
   the packet lists sources past their minimum interval and due notices. The model observes sources, then submits a
   verdict, text, priority and topic. The notifier derives the notice key (`src:<upstream id>` or a weak title+day
   key), dedupes against 7 days of history and gates it. One real event often reaches Muse through several sources
   (the mail, the PR comment and a news item about one reply; one CI failure per push), each with its own upstream
   id, and only the model can tell they are one event. So the packet lists the notified events of the last 7 days
   (`context.notified`, refs), and the model answers an item about one of them with `about` that ref: `skip`, or
   `supersede` for a real development (`send` with `about` is refused). Code then records the item's key as an alias
   of the event, and an aliased key never drafts a new notice for 7 days. Code-derived thread identity was rejected:
   Muse owns no connectors and cannot tell a provider id, a comment URL and a news id apart; topic grouping was
   rejected because topics are free text that drifts. The gates are quiet hours and per-priority daily budgets; urgent may pass
   quiet hours only within `urgent_per_day` (default 2) and is gated as time-sensitive past it; blocked topics are
   withdrawn. Sources are `<kind>:<account>`; migrated 0.3.x per-resource check ids (`source-<hex>`) stay as history,
   never due and never counted. A packet lists at most 20 due sources, least recently checked first.
   Only the owned no-agent `muse-deliver` job sends (the tick, other jobs and hooks never do): each run
   re-checks the gates and claims the due notices as `sending` in one transaction, tied to its own host execution,
   and prints them as one message (at most 5, separated by a rule; no signature, and a closing rule only when the
   last line could parse as Hermes' `{"wakeAgent": false}` gate) that Hermes delivers to the job's route. A `deliver` preference becomes that
   route at the next run (that run stays silent). An
   urgent notice that may go now wakes `muse-deliver` at once instead of waiting up to 10 minutes. Reconciliation
   reads that execution's delivery receipt; an outcome that is unknown is never resent. Notices that 0.4.1 left
   `sending` keep being read from their one-shot job by delivery key until they settle; finished one-shot jobs
   that no notice waits for are removed by install and by each deliver run.
3. **Nightly.** Every due goal gets an assessment and progress note (`done_suggested` never closes a goal); the
   next check moves to 1 day − 6h so the goal is due again the next night. Code picks review candidates from the last
   72h by rules, oldest first, all of them the same night (no per-night cap). The model's `agent_gap`
   becomes a Finding with evidence and `latent_need` an Idea. Goal proposals (disposed in the last 7 days) are
   offered until the model creates or declines them, no more per day than cron may still create (5); the rest wait for
   the next period. Batches hold a fixed 10 items. In the last batch, dream and alignment are written when the day changed
   something, listing every native memory change.
4. **Feed.** Each active interest is researched at most once in 20h, longest unchecked first; the model writes
   articles with source refs and they are published silently. One article per packet may carry a notice: its
   source becomes the `src:` notice key (shared with patrol's 7-day history), it passes the same gates (no urgent),
   and code withdraws it when the interest stops or expires.
5. **Weekly.** Health summary and 7-day counts only; one digest to the user route, suggestions only.
6. **Fade.** A goal without activity for `goal_dormant_days` gets one question (`goal:<id>:fade:<episode>:<attempt>`);
   a withdrawn, expired, failed or unknown question is asked again up to 3 times, then `fade_blocked` is reported.
   Code cancels the goal once `fade_at` has passed and the question was delivered at least a day earlier. Waiting
   goals do not fade.
7. **Hooks** (user callers only, except the intake guard of flow 1 in `pre_tool_call`/`post_tool_call`). `pre_llm_call` injects at most three things: a high Health line, a
   one-line summary when it changed, and memory_receipts for failed or staged native memory writes (once each).
   `post_tool_call` records those receipts. `post_llm_call` runs a background tick and, after 5 quiet minutes, may
   wake intake (at most 3 times a day).

## What the main session receives

Hermes has no way for a plugin or a no-agent job to speak as the assistant without a turn: `post_message` refuses
calls outside a session, `inject_message` queues a user turn, and the cron transcript mirror is a user-role row on
platform sessions only. The `bot-chat` route (the default, and the only one for a Desktop-only profile) admits a
job's stdout as an internal Bot Chat turn with Hermes' fixed prefix ("[Cronjob "<name>" output — scheduled job, not
the user. Review it, act on anything that needs action, and summarize for the chat.]"). Platform routes start no
turn but bypass the conversation and carry Hermes' "Cronjob Response" wrapper. So Muse keeps `bot-chat` and fixes
the meaning of that turn on its side: the system prompt section and the communication reference say that whatever a
`muse-*` job delivers (notices, a watch result, the weekly digest, a health alert) is a message the assistant has
already sent the user in its own voice. The main session answers exactly `[SILENT]` (Hermes drops a bare silence
marker on internal turns) and speaks only for a decision or an action it can take now, as itself; it never repeats,
reviews or adds verification notes. Notices are written in the assistant's voice and carry no Muse signature.

## Health

`health_entry.py` runs `health.run()` every 30 minutes and atomically writes `muse/health.json`: the 7 host probes
(`symbols`, `cron_sessions`, `delivery_semantics`, `delivery_target`, `signal_purity`, `config_location`, `home`)
plus invariants over the Store, deliveries, Muse's own tool results (`muse_manage`, `muse_job`; other tools' output
belongs to the host and the user's tools), jobs and the plugin load (`plugin_load`). Each health item has an id, level
(`ok/low/medium/high`), detail, evidence and fix. Alerts never use the Notifier; they reach the user through the
main-session injection, the Dashboard and Desktop page, cron stdout when the alert set changes, and an optional
`health_deliver` route added as a second target of the health job, so Hermes delivers the same stdout to both.
`deliver_stalled` reports notices left unclaimed for three `muse-deliver` periods (its `next_run_at − last_run_at`). Probes judge capability and semantics, not version ranges; a missing capability degrades
only its feature and raises a high item.

## Install, upgrade and rollback

On plugin load, `install.install` holds `muse/install.lock`, writes `muse/migrating.json`, migrates the 0.3.1 or
0.3.16 `muse/state.db` into Store v2 once (the old file becomes read-only), adds missing content files from
`templates/` without overwriting, backs up the 0.3.x job prompts once to `muse/backup/cron-prompts-0.3.json`,
refreshes owned jobs and watches in place (creating `muse-deliver`), removes settled 0.4.1 one-shot delivery
jobs, creates the Health cron, resumes the jobs a cancelled rollback paused and removes the marker. A failed install keeps
the marker and its error: jobs and the background tick stay silent and the main session is told. Cutover and
rollback steps are in [CUTOVER.md](CUTOVER.md); the rollback bridge writes v2's sent notices and settled signals back
into the 0.3.x database so the old version neither resends nor reprocesses them.

## Privacy

Everything handed to the model is redacted first, read at most 12k at a time and 24k per item; long texts are
head/tail excerpts. There is one gate (`host.sessions.clean`) on both ways Muse reaches the model, tool results and
Script Output, and every Muse read (files, entities, lists) pages at 12k with `next_offset`. A labelled credential is
redacted only when its value looks like one (6+ characters with a digit), so prose and code are not mangled. Only private user surfaces are read; groups and unlisted sources are neither read nor
authorizing. Forget clears the payload, writes a tombstone so later evidence cannot rebuild it, and says what remains.
Retention is listed in [CATALOG-COMPATIBILITY.md](CATALOG-COMPATIBILITY.md).

## Verification

Acceptance scripts A1–A13 and the release gate are in [ACCEPTANCE.md](ACCEPTANCE.md). Releases install from a tag;
after a Hermes upgrade the native host contract and probes run again.
