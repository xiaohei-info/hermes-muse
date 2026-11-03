# Muse interface (v2)

The field-level interface is generated from code and is not repeated here:
[skills/companion/references/interface.md](../skills/companion/references/interface.md). It is produced by
`python -m hermes_muse.surface` from the action tables `surface.MAIN` (`muse_manage`) and `surface.JOB_ACTIONS`
(`muse_job`) and the six result schemas in `kernel/packets.SCHEMAS`; CI fails when it is out of date.

Two tools, both in the `muse` toolset:

- `muse_manage(action, data)`: 16 actions for the private main session, 13 writes (`goal_create`, `goal_update`,
  `assignment_record`, `assignment_update`,
  `interest_record`, `idea_add`, `preferences`, `feedback`, `forget`, `watch_create`, `watch_stop`, `feed_update`,
  `content_write`) and 3 reads (`read`, `calendar_view`, `installation_prepare`).
- `muse_job(action, data)`: `read`, `observe` and `submit`, only for Muse's own job runs and only against the packet
  in that run's Script Output.

Who may call what is decided by the caller kind from `HostAdapter.caller()`, never by tool arguments; see
[DESIGN.md](DESIGN.md#authorization). Errors are `{ok: false, code, error[, field]}` with `code` one of
`invalid_argument`, `permission_denied`, `not_found`, `revision_conflict`, `host_unavailable`, `outcome_unknown`;
the message names the field and its valid values.

Ids, keys, times, counts and state names are derived by Muse. Callers pass only refs Muse returned, enum values and
free text; content writes pass the `expected_revision` from a previous `read` (`absent` for a new file).

Callers written for 0.3.x: see [CALLER-MIGRATION.md](CALLER-MIGRATION.md).
