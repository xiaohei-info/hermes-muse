# Cutover and rollback (0.3.x → v2)

One profile at a time; do the less used profile first and watch it for 24 hours before the next.
Every step is `PYTHONPATH=<hermes-agent> <hermes python> scripts/cutover.py <step> --home <profile home>`.

## Cutover

1. **Prerequisites.** External callers' rewritten prompts and scripts are approved and ready
   (see [CALLER-MIGRATION.md](CALLER-MIGRATION.md); `python scripts/check_callers.py <files>` passes).
   Known delivery problems are fixed: the `delivery_target` probe must not report a missing Bot Chat cwd.
2. **`preflight`** copies `muse/` to `<home>/muse-backup-<time>/` (SQLite files through the backup API)
   and prints the host probes and the owned jobs. It changes nothing else.
3. **Install the new version** with Hermes plugin management. The first load runs the install under
   `muse/install.lock`:
   - writes `muse/migrating.json`, so every Muse cron launcher prints `{"wakeAgent": false}` and the
     background tick stays off;
   - migrates `muse/state.db` into `muse/state-v2.db` once; the old file stays, read-only;
   - saves the 0.3.x job prompts to `muse/backup/cron-prompts-0.3.json` (once);
   - refreshes the Muse jobs in place under their 0.3.x names (ids, schedules, routes and pauses are kept),
     pauses `muse-monthly-system-audit` (merged into the weekly digest), creates the `muse-deliver` and
     `muse-health` no_agent jobs and removes settled 0.4.1 one-shot delivery jobs;
   - removes the marker. A failed install keeps the marker and its error; jobs stay silent and the main
     session says so. `apply` repeats the install without a gateway (or on a copy).
4. **Swap the external callers** to their rewritten versions (user-authorized step).
5. **`verify`** runs one Health pass and must pass A4 (all probes ok) and A7 (signal watermark ok).
   Then watch the first patrol, intake and nightly runs and the main-session injection.

## Rollback

Use it when a high Health finding cannot be fixed within 2 hours.

1. **`rollback`** sets the marker (v2 jobs go silent), runs the rollback bridge (v2 sent notices and
   settled signals are written back into `muse/state.db`, so 0.3.x neither resends nor reprocesses them),
   restores the saved 0.3.x job prompts (with their installation markers, so 0.3.x finds its jobs
   instead of creating duplicates), resumes the job the install paused and pauses `muse-health` and `muse-deliver`.
2. Reinstall the 0.3.x version (catalog users: the 0.3.1 SHA; local: the previous checkout).
3. Put back the external callers' previous prompts and scripts.
4. After 0.3.x has loaded, delete `muse/migrating.json`. Goals need nothing: GOAL.md is shared.

To cancel a rollback (or upgrade again later), delete `muse/migrating.json` and load v2: the install resumes the
jobs the rollback paused (`muse-health`, `muse-deliver`) and leaves pauses you set yourself.

Residual risk: 0.3.x does not dedupe against sent history, so an event that arrives after the rollback
can still be notified twice; the bridge only guarantees that what v2 already sent is not sent again.

## Windows acceptance

The bridge uses the same stdlib mutation lock as normal writes (`flock` on POSIX,
`msvcrt.locking` on Windows). This supports an existing custom Windows 0.3.x install;
it does not make the historical upstream 0.3.x tags Windows-compatible. Reinstall the
previous **Windows-compatible** checkout when rolling back such an installation.

Run the acceptance scripts with a scratch `HERMES_HOME` and `TMPDIR`, never the active
profile. `tests/local_session_acceptance.py` checks native gateway `source=local`
with immutable `created_source=cli/tui/gui/acp` for private caller authority and signal
intake. `tests/local_receipt_acceptance.py` covers native reservation rows whose later
placeholder writer stamped `created_source=unknown`: only a matching immutable
`gateway.local_policy.v1:` receipt can prove that exact root session, principal,
route, LOCAL origin and interactive launch policy. A present invalid/machine receipt
fails closed. Bare LOCAL/unknown, finite oneshot, machine/import creation labels,
child, group, hidden and background turns remain excluded. Older schemas without
provenance keep legacy source rules; LOCAL itself is never allowlisted. For live model acceptance,
use the actual interactive gateway CLI (not an unlabeled finite `chat -q` run), and
verify stored metadata plus create/read/update/cancel readbacks. Photon classification
or registered-handler integration alone does not prove a Photon transport/model turn.
With Hermes available, `python tests/native_windows_contract.py` additionally
checks private Photon callers and background/group/import exclusion, a goal lifecycle,
stale content CAS, real NTFS junction refusal, an occupied editor's replace failure and
recovery, shared bridge/user/cron locks held past the Windows ten-second retry window,
all six owned launchers, and Health without high items. The synthetic historical-store
probe supplies only the current platform lock seam on Windows; it still executes the
tags' real Store and pending-signal code. POSIX runs the tags without that seam.

Home resolution is checked on local NTFS with spaces and non-ASCII names. It still
resolves the home once through `host.resolve_home`; this is not a guarantee about
subst/mapped drives, OneDrive or 8.3 aliases. Report those path shapes separately if used.
Windows keeps an unrelated process cwd during host acceptance because it cannot delete
the current directory; POSIX retains the deleted-cwd check. Both restore cwd before cleanup.
