# Compatibility and retention (0.4.0)

## Compatibility

- **Hermes.** Needs the plugin APIs for tools, Skills, system prompt sections, hooks and unload (Hermes 0.21.5 or
  later); tested against `v0.22.5`. Host behavior Muse depends on (cron session identity, delivery semantics and
  target, signal sources, config location, profile home) is checked by 7 probes in `muse/health.json` instead of a
  version range; a missing capability turns off only its feature and shows as a high health item.
- **Upgrade.** 0.3.1 and 0.3.16 databases migrate in place on first load. Job ids, user schedules, routes and pauses
  are kept; job prompts are refreshed from `prompts/jobs/`; `monthly-system-audit` is paused; `muse-health` is added.
  GOAL.md, memory, dreams, people and group pages, Feed articles, TOOLS.md, AGENTS.md and preferences keep their
  formats. Callers of removed actions must be rewritten first ([CALLER-MIGRATION.md](CALLER-MIGRATION.md));
  rollback is in [CUTOVER.md](CUTOVER.md).
- **Platforms.** Linux and macOS. Windows (local NTFS profile) is experimental: content files refuse symlinks and
  junctions by attribute instead of descriptor-relative opens, and locks use `msvcrt`. Rollback to 0.3.x
  (`cutover.py rollback`) is POSIX-only.
- **Isolation.** Everything lives in the current profile; Muse never reads or monitors another profile. Jobs set no
  `workdir`, so Docker and remote terminals work.

## Retention

Muse stores, under `<profile home>/muse/`:

| Data | Content | Kept |
|---|---|---|
| Signals (`state-v2.db`) | redacted excerpt of a private user message (head and tail past 8k), its session/message pointer, disposition and extracted facts | until forgotten; no automatic expiry |
| Notices, Findings | notice text, title, upstream ID, source links and delivery state; review evidence refs | no automatic expiry |
| Goals | GOAL.md (body, progress, assessments) and its mirror | until the user deletes them |
| Assignments | executor name, handle, rule, conclusion, evidence and question; never an event's text | no automatic expiry |
| RULES.md, DECISIONS.md | the user's rules and executor command templates; their decisions in their words | until the user edits them |
| Interests, Ideas, Feed records | title, rationale, source refs | until forgotten (state expiry does not delete) |
| Packets | the items handed to one job run (redacted excerpts) | no automatic expiry |
| Events | state transitions with short reason codes | 30 days |
| `health.json` | health items with entity ids as evidence, recent host fault messages | replaced every run |
| `state.db` (0.3.x) | the old database, read-only after migration | until the user deletes it |
| `backup/cron-prompts-0.3.json`, `muse-backup-<time>/` | 0.3.x job prompts; the cutover preflight copy of `muse/` | until the user deletes them |

Muse copies no full transcript; originals stay in Hermes's own session history under its retention, and `read`
pages them only on demand, redacted. Forget clears the payload and writes a tombstone; it does not delete Hermes
history, native memory, backups or anything outside `muse/`, and the assistant says what remains. There is no
telemetry and no network access of Muse's own; external sources are read only by the model with tools the user
already authorized.

## Validation scope

The acceptance scripts use synthetic data in temporary homes, real Hermes registration and the real HostAdapter,
without model calls or real deliveries. They prove the bookkeeping, not model judgment or live delivery; see
[ACCEPTANCE.md](ACCEPTANCE.md). Catalog admission remains a maintainer decision, and publishing a version does not
update an existing installation.
