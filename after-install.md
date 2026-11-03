# Hermes Muse

Recommended: use the current profile's **Bot Chat** for your goals, interests and follow-up.

First plugin load sets up one Skill, the Muse tools (`muse_manage`, `muse_job`), three conversation hooks, five recurring Cron jobs (intake, patrol, nightly review, Feed, weekly digest), a `muse-deliver` job that sends due notices every 10 minutes without a model, and a `muse-health` check that runs every 30 minutes without a model. An existing 0.3.x installation is migrated in place; its jobs keep their ids, schedules and routes. Start a new conversation to load the system prompt section; keep the Hermes scheduler running for background work.

To let events start work on their own, add rules and executors to `muse/RULES.md`; nothing starts until you do. Reminders the patrol selects are sent by `muse-deliver` (urgent ones at once). Health problems show up in the main conversation, on the Dashboard's Muse page and in `muse/health.json`; set `health_deliver` to also send them to a second route.

No external messaging channel is required. See README.md or README.zh-CN.md for the workflow, docs/CUTOVER.md for upgrading and rolling back, and the uninstall instructions.

If this profile has explicit `platform_toolsets` lists, include `muse` in the relevant platform lists so the assistant can call `muse_manage`.
