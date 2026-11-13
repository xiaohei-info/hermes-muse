# Verification and acceptance

## Automated checks

Run in isolated directories: `export TMPDIR=$(mktemp -d) HERMES_HOME=$(mktemp -d)`. `<hermes-agent>` is a Hermes
source checkout and `<py>` its venv python. Without Hermes, the system python runs the scripts marked *SKIP-able*;
their native parts print `SKIP`.

| Check | Command |
|---|---|
| Outbound boundaries, no 0.3.x modules | `python scripts/check_boundaries.py` |
| No removed 0.3.x dependency in Muse's own prompts, skills and templates | `python scripts/check_callers.py prompts templates skills after-install.md` |
| Compile | `python -m compileall -q hermes_muse dashboard scripts tests` |
| Dashboard and Desktop page (after `python ui/build.py`) | `node --test tests/page_markdown.test.mjs tests/page_actions.test.mjs` |
| Generated interface is current | `python -m hermes_muse.surface && git diff --exit-code skills/companion/references/interface.md` |
| Store v2, migration, rollback (SKIP-able; needs tags `v0.3.1`, `v0.3.16`) | `python tests/store_v2_acceptance.py` |
| Kernel (SKIP-able) | `PYTHONPATH=<hermes-agent> <py> tests/kernel_acceptance.py` |
| Model surface S1–S11 (SKIP-able) | `PYTHONPATH=<hermes-agent> <py> tests/surface_acceptance.py` |
| Health | `PYTHONPATH=<hermes-agent> <py> tests/health_acceptance.py` |
| Install, hooks, views, cutover and rollback | `PYTHONPATH=<hermes-agent> <py> tests/wp6_acceptance.py` |
| Host contract (run after every Hermes upgrade) | `HERMES_SOURCE=<hermes-agent> <py> tests/native_host_contract.py` |
| Official plugin validation | `HERMES_HOME=$(mktemp -d) hermes plugins validate . --json` |
| External callers before a cutover | `python scripts/check_callers.py <their prompts and scripts>` |

CI (`.github/workflows/test.yml`) runs the SKIP-able set on Linux and macOS without Hermes, kernel and surface on
Windows, and everything on
Linux against Hermes `v0.22.5` (`NousResearch/hermes-agent@bf0203a794a07aac3ff764972ab9087baa4e4f4e`), the
tested baseline. Probes judge host capabilities, not versions, so a newer Hermes is accepted when the host contract
passes.

## Release acceptance A1–A13

| # | Invariant | Where it is computed |
|---|---|---|
| A1 | Migrating twice gives no diff | `store_v2_acceptance` |
| A2 | Migrated counts match the 0.3.x database, every difference has a reason code | `store_v2_acceptance` |
| A3 | Every timed entity has a deadline | `store_v2_acceptance`, `kernel_acceptance`, Health `deadlines` |
| A4 | All probes ok on the host (a broken delivery target shows as high) | `native_host_contract`, `health_acceptance`, `wp6_acceptance`, `cutover.py verify` |
| A5 | Replayed duplicates leave one sendable notice per notice key | `kernel_acceptance`, `store_v2_acceptance` |
| A6 | In a shadow run on a data copy, v2 would send nothing the old version did not | manual, before release |
| A7 | Signal watermark age < 2h | Health `signal_watermark`, `cutover.py verify` |
| A8 | Packet expiry rate < 10% | Health |
| A9 | Tool error rate per job < 3% | Health |
| A10 | No tool result > 20k; no credential pattern after redaction | `kernel_acceptance`, Health |
| A11 | Rewritten external callers use no removed action | `scripts/check_callers.py`, `wp6_acceptance` |
| A12 | After rollback, 0.3.x resends no notice and reprocesses no signal | `store_v2_acceptance` |
| A13 | Host contract and per-machine table tests pass | `native_host_contract`, `kernel_acceptance` |

Release gate: every check above passes and the A1–A13 outputs are attached; install only from a tag; for 7 days
after release fix only high-level problems. Health keeps computing the post-release invariants (watermark age,
parked signals, 7-day duplicate sends, hanging or unknown notices, run outcomes, overdue next checks, fade
deadlocks, cron session recognition, probes, review candidates) in `muse/health.json`.

## User acceptance on a scratch profile

Use a separate profile with synthetic data; never a profile in daily use.

1. Install, start a new conversation and ask what Muse tracks. `muse_manage read(kind=status)` shows Health and
   counts; `hermes cron list` shows the five jobs and `muse-health`. SOUL and native memory are unchanged.
2. Accept a concrete piece of work in chat; a goal appears (or the next intake proposes it). Mention a passing
   interest; it expires after 14 days unless renewed by you.
3. Give the patrol two reports of the same upstream item; one notice is delivered. Check quiet hours, the daily
   budget, `urgent_per_day`, a blocked topic and "stop" feedback.
4. Let a goal go dormant (`goal_dormant_days`, default 3): one question arrives, even if nightly assessed it every night;
   without activity, code cancels the goal `goal_fade_days` (default 3) after the question was delivered.
5. Break the delivery route: a high health item appears in the main session and on the Muse page, not through a notice.
6. Ask Muse to forget an interest; it is gone from `read`, and a tombstone stops later evidence from rebuilding it.
7. Run `installation_prepare(operation=remove)`, confirm, pause the jobs and remove the plugin; data stays in `muse/`.

Model judgment (what is worth a notice, review conclusions, writing quality) needs real traces; the scripts only
prove the bookkeeping.
